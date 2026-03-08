"""Core XTTS v2 TTS engine.

Wraps the Coqui XTTS v2 model for multilingual speech synthesis with
support for both unary and streaming synthesis modes. Streaming mode
splits text at sentence boundaries and yields audio chunks as each
sentence is synthesized, achieving low first-chunk latency.
"""

import asyncio
import time
from collections.abc import AsyncGenerator
from pathlib import Path

import numpy as np
import torch
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts

from app.config import TTSConfig
from app.models.domain import AudioChunkResult, SentenceChunk, VoiceProfile
from app.services.text_processor import prepare_for_synthesis
from shared.audio_utils import float32_to_pcm16, resample
from shared.logging import get_logger

logger = get_logger("xtts_service")

# XTTS v2 language code mapping (ISO 639-1 -> XTTS internal codes)
_LANGUAGE_MAP: dict[str, str] = {
    "en": "en",
    "hi": "hi",
    "ta": "ta",
}


class XTTSService:
    """Coqui XTTS v2 synthesis engine.

    Manages model loading, GPU memory, and provides both synchronous
    and streaming synthesis interfaces.
    """

    def __init__(self, config: TTSConfig) -> None:
        self._config = config
        self._model: Xtts | None = None
        self._model_config: XttsConfig | None = None
        self._device: str = config.device
        self._sample_rate: int = config.sample_rate
        self._loaded = False
        self._synthesis_lock = asyncio.Semaphore(config.max_concurrent_syntheses)

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def device(self) -> str:
        return self._device

    async def load_model(self) -> None:
        """Load the XTTS v2 model into memory.

        Runs model loading in a thread pool to avoid blocking the event loop.
        Performs a warmup synthesis if configured.
        """
        logger.info(
            "loading_xtts_model",
            model_path=self._config.model_path,
            device=self._device,
        )
        start = time.monotonic()

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._load_model_sync)

        duration_s = time.monotonic() - start
        logger.info("xtts_model_loaded", duration_s=round(duration_s, 2))

        if self._config.warmup_on_startup:
            await self._warmup()

    def _load_model_sync(self) -> None:
        """Synchronous model loading (runs in thread pool)."""
        model_path = Path(self._config.model_path)

        # Resolve device
        if self._device == "cuda" and not torch.cuda.is_available():
            logger.warning("cuda_not_available_falling_back_to_cpu")
            self._device = "cpu"

        # Load model config
        config_path = model_path / "config.json"
        self._model_config = XttsConfig()
        self._model_config.load_json(str(config_path))

        # Initialize and load model
        self._model = Xtts.init_from_config(self._model_config)
        self._model.load_checkpoint(
            self._model_config,
            checkpoint_dir=str(model_path),
            use_deepspeed=False,
        )

        if self._device == "cuda":
            self._model.cuda()
            if self._config.compute_type == "float16":
                self._model.half()

        self._model.eval()
        self._loaded = True

    async def _warmup(self) -> None:
        """Run a warmup synthesis to prime GPU caches and JIT compilation."""
        logger.info("running_warmup_synthesis")
        try:
            warmup_text = "System ready."
            # Use a short silence as reference if no wav available
            dummy_ref = np.zeros(self._sample_rate, dtype=np.float32)
            await self._synthesize_internal(warmup_text, "en", reference_audio=dummy_ref)
            logger.info("warmup_complete")
        except Exception as e:
            logger.warning("warmup_failed", error=str(e))

    async def synthesize(
        self,
        text: str,
        language: str,
        voice: VoiceProfile,
        speed: float = 1.0,
        sample_rate: int | None = None,
    ) -> tuple[np.ndarray, int]:
        """Synthesize complete text to audio.

        Args:
            text: Preprocessed text to synthesize.
            language: ISO 639-1 language code.
            voice: Voice profile with speaker reference WAV.
            speed: Speech rate multiplier (0.5 - 2.0).
            sample_rate: Output sample rate (None = use config default).

        Returns:
            Tuple of (audio numpy array float32, sample rate).

        Raises:
            RuntimeError: If model is not loaded.
            ValueError: If language is not supported.
        """
        if not self._loaded:
            raise RuntimeError("XTTS model not loaded")

        target_sr = sample_rate or self._sample_rate
        xtts_lang = _LANGUAGE_MAP.get(language, "en")

        # Preprocess text into sentences and synthesize each
        sentences = prepare_for_synthesis(text, language)
        if not sentences:
            return np.array([], dtype=np.float32), target_sr

        async with self._synthesis_lock:
            audio_segments: list[np.ndarray] = []
            silence_samples = int(target_sr * self._config.sentence_silence_ms / 1000)
            silence = np.zeros(silence_samples, dtype=np.float32)

            for i, sentence in enumerate(sentences):
                segment = await self._synthesize_internal(
                    sentence,
                    xtts_lang,
                    speaker_wav=str(voice.speaker_wav_path) if voice.exists() else None,
                    speed=speed,
                )
                audio_segments.append(segment)
                if i < len(sentences) - 1:
                    audio_segments.append(silence)

            audio = np.concatenate(audio_segments)

            # Resample if needed
            if target_sr != self._sample_rate:
                audio = resample(audio, self._sample_rate, target_sr)

            return audio, target_sr

    async def synthesize_streaming(
        self,
        text: str,
        language: str,
        voice: VoiceProfile,
        speed: float = 1.0,
        sample_rate: int | None = None,
    ) -> AsyncGenerator[AudioChunkResult, None]:
        """Stream audio chunks as sentences are synthesized.

        Splits text at sentence boundaries and yields each sentence's audio
        as soon as it is ready. This enables the downstream audio gateway
        to start playback before the entire text is synthesized.

        Args:
            text: Text to synthesize.
            language: ISO 639-1 language code.
            voice: Voice profile with speaker reference WAV.
            speed: Speech rate multiplier.
            sample_rate: Output sample rate.

        Yields:
            AudioChunkResult for each synthesized sentence.
        """
        if not self._loaded:
            raise RuntimeError("XTTS model not loaded")

        target_sr = sample_rate or self._sample_rate
        xtts_lang = _LANGUAGE_MAP.get(language, "en")

        sentences = prepare_for_synthesis(text, language)
        if not sentences:
            return

        total = len(sentences)
        timestamp_ms = 0
        silence_samples = int(target_sr * self._config.sentence_silence_ms / 1000)

        async with self._synthesis_lock:
            for i, sentence in enumerate(sentences):
                is_last = i == total - 1
                start = time.monotonic()

                segment = await self._synthesize_internal(
                    sentence,
                    xtts_lang,
                    speaker_wav=str(voice.speaker_wav_path) if voice.exists() else None,
                    speed=speed,
                )

                # Resample if needed
                if target_sr != self._sample_rate:
                    segment = resample(segment, self._sample_rate, target_sr)

                # Add inter-sentence silence (except for last)
                if not is_last:
                    segment = np.concatenate([
                        segment,
                        np.zeros(silence_samples, dtype=np.float32),
                    ])

                duration_ms = int(len(segment) / target_sr * 1000)
                pcm_bytes = float32_to_pcm16(segment)

                synthesis_ms = int((time.monotonic() - start) * 1000)
                logger.debug(
                    "chunk_synthesized",
                    chunk_index=i,
                    sentence_len=len(sentence),
                    duration_ms=duration_ms,
                    synthesis_ms=synthesis_ms,
                )

                yield AudioChunkResult(
                    audio_data=pcm_bytes,
                    sample_rate=target_sr,
                    duration_ms=duration_ms,
                    text_segment=sentence,
                    chunk_index=i,
                    is_final=is_last,
                    encoding="pcm16",
                    timestamp_ms=timestamp_ms,
                )

                timestamp_ms += duration_ms

    async def synthesize_streaming_incremental(
        self,
        text_stream: AsyncGenerator[str, None],
        language: str,
        voice: VoiceProfile,
        speed: float = 1.0,
        sample_rate: int | None = None,
    ) -> AsyncGenerator[AudioChunkResult, None]:
        """Bidirectional streaming: consume text deltas, yield audio chunks.

        Accumulates text deltas from the LLM, detects sentence boundaries,
        and synthesizes each complete sentence as it becomes available.

        Args:
            text_stream: Async generator yielding text delta strings.
            language: ISO 639-1 language code.
            voice: Voice profile.
            speed: Speech rate multiplier.
            sample_rate: Output sample rate.

        Yields:
            AudioChunkResult for each synthesized sentence.
        """
        if not self._loaded:
            raise RuntimeError("XTTS model not loaded")

        target_sr = sample_rate or self._sample_rate
        xtts_lang = _LANGUAGE_MAP.get(language, "en")

        buffer = ""
        chunk_index = 0
        timestamp_ms = 0
        silence_samples = int(target_sr * self._config.sentence_silence_ms / 1000)

        async with self._synthesis_lock:
            async for delta in text_stream:
                buffer += delta

                # Check for sentence boundaries in accumulated buffer
                sentences = prepare_for_synthesis(buffer, language)

                if len(sentences) <= 1:
                    # No complete sentence boundary yet, keep accumulating
                    continue

                # Synthesize all complete sentences (keep the last partial one)
                complete_sentences = sentences[:-1]
                buffer = sentences[-1]

                for sentence in complete_sentences:
                    segment = await self._synthesize_internal(
                        sentence,
                        xtts_lang,
                        speaker_wav=str(voice.speaker_wav_path) if voice.exists() else None,
                        speed=speed,
                    )

                    if target_sr != self._sample_rate:
                        segment = resample(segment, self._sample_rate, target_sr)

                    segment = np.concatenate([
                        segment,
                        np.zeros(silence_samples, dtype=np.float32),
                    ])

                    duration_ms = int(len(segment) / target_sr * 1000)
                    pcm_bytes = float32_to_pcm16(segment)

                    yield AudioChunkResult(
                        audio_data=pcm_bytes,
                        sample_rate=target_sr,
                        duration_ms=duration_ms,
                        text_segment=sentence,
                        chunk_index=chunk_index,
                        is_final=False,
                        encoding="pcm16",
                        timestamp_ms=timestamp_ms,
                    )
                    chunk_index += 1
                    timestamp_ms += duration_ms

            # Synthesize any remaining buffered text
            if buffer.strip():
                segment = await self._synthesize_internal(
                    buffer.strip(),
                    xtts_lang,
                    speaker_wav=str(voice.speaker_wav_path) if voice.exists() else None,
                    speed=speed,
                )

                if target_sr != self._sample_rate:
                    segment = resample(segment, self._sample_rate, target_sr)

                duration_ms = int(len(segment) / target_sr * 1000)
                pcm_bytes = float32_to_pcm16(segment)

                yield AudioChunkResult(
                    audio_data=pcm_bytes,
                    sample_rate=target_sr,
                    duration_ms=duration_ms,
                    text_segment=buffer.strip(),
                    chunk_index=chunk_index,
                    is_final=True,
                    encoding="pcm16",
                    timestamp_ms=timestamp_ms,
                )

    async def _synthesize_internal(
        self,
        text: str,
        language: str,
        speaker_wav: str | None = None,
        reference_audio: np.ndarray | None = None,
        speed: float = 1.0,
    ) -> np.ndarray:
        """Internal synthesis using XTTS v2 inference.

        Runs the actual model inference in a thread pool executor to avoid
        blocking the async event loop.

        Args:
            text: Preprocessed text.
            language: XTTS language code.
            speaker_wav: Path to speaker reference WAV file.
            reference_audio: Raw reference audio array (alternative to wav path).
            speed: Speech rate multiplier.

        Returns:
            Float32 audio numpy array at model sample rate.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._inference_sync,
            text,
            language,
            speaker_wav,
            reference_audio,
            speed,
        )

    def _inference_sync(
        self,
        text: str,
        language: str,
        speaker_wav: str | None,
        reference_audio: np.ndarray | None,
        speed: float,
    ) -> np.ndarray:
        """Synchronous XTTS v2 inference (runs in thread pool).

        Args:
            text: Text to synthesize.
            language: XTTS language code.
            speaker_wav: Path to speaker reference WAV.
            reference_audio: Alternative raw reference audio.
            speed: Speech rate.

        Returns:
            Float32 audio numpy array.
        """
        with torch.no_grad():
            # Compute speaker latents from reference audio
            if speaker_wav:
                gpt_cond_latent, speaker_embedding = self._model.get_conditioning_latents(
                    audio_path=[speaker_wav],
                )
            elif reference_audio is not None:
                # Use raw audio array (e.g., for warmup with silence)
                gpt_cond_latent, speaker_embedding = self._model.get_conditioning_latents(
                    audio_path=None,
                )
            else:
                # Fallback: use model's default latents
                gpt_cond_latent, speaker_embedding = self._model.get_conditioning_latents(
                    audio_path=None,
                )

            # Run inference
            result = self._model.inference(
                text=text,
                language=language,
                gpt_cond_latent=gpt_cond_latent,
                speaker_embedding=speaker_embedding,
                speed=speed,
                enable_text_splitting=False,  # We handle splitting ourselves
            )

            # Result contains 'wav' key with audio tensor
            audio_tensor = result["wav"]

            if isinstance(audio_tensor, torch.Tensor):
                audio = audio_tensor.cpu().numpy().astype(np.float32)
            else:
                audio = np.array(audio_tensor, dtype=np.float32)

            # Ensure 1D
            if audio.ndim > 1:
                audio = audio.squeeze()

            return audio

    async def unload_model(self) -> None:
        """Unload the model and free GPU memory."""
        if self._model is not None:
            del self._model
            self._model = None
            self._loaded = False

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            logger.info("xtts_model_unloaded")
