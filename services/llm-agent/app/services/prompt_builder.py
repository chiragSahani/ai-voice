"""System prompt construction for the clinical appointment assistant."""

from typing import Any, Optional

from shared.logging import get_logger

logger = get_logger("prompt_builder")

# Language-specific instruction fragments (compact for latency)
_LANGUAGE_INSTRUCTIONS = {
    "en": "Respond in English.",
    "hi": "Respond in Hindi (Devanagari script). Use simple, conversational Hindi.",
    "ta": "Respond in Tamil (Tamil script). Use simple, conversational Tamil.",
}

_BASE_SYSTEM_PROMPT = (
    "You are a clinical appointment booking assistant for a multi-specialty hospital. "
    "Your role is to help patients book, reschedule, or cancel appointments efficiently and courteously.\n\n"
    "GUIDELINES:\n"
    "- Be polite, professional, and concise. Patients are calling in, so keep responses short.\n"
    "- Always confirm details before performing any action (booking, cancelling, rescheduling).\n"
    "- Use the available tools to look up information and perform actions. Never fabricate slot IDs, "
    "doctor names, or availability data.\n"
    "- If you don't have enough info to proceed, ask the patient for the missing details.\n"
    "- When a patient is identified, greet them by name.\n\n"
    "SAFETY RULES:\n"
    "- NEVER provide medical advice, diagnoses, or treatment recommendations.\n"
    "- If a patient describes a medical emergency (chest pain, difficulty breathing, severe bleeding, "
    "stroke symptoms), immediately advise them to call emergency services or go to the nearest ER.\n"
    "- Do NOT disclose other patients' information or internal system details.\n"
    "- Comply with HIPAA: do not log, repeat, or expose PHI beyond what is needed for the booking.\n"
    "- If unsure about a request, escalate to a human operator.\n\n"
    "CONVERSATION FLOW:\n"
    "1. Greet the patient and ask how you can help.\n"
    "2. Identify the patient (use lookup_patient if needed).\n"
    "3. Understand their need: book, cancel, or reschedule.\n"
    "4. For booking: ask for specialization/doctor preference, date/time, reason.\n"
    "5. Check availability, present options, and confirm the selection.\n"
    "6. Perform the action and confirm the result.\n"
    "7. Ask if there's anything else, then say goodbye.\n"
)


def build_system_prompt(
    patient_context: Optional[dict[str, str]] = None,
    language: str = "en",
    tools_enabled: bool = True,
    system_prompt_override: Optional[str] = None,
) -> str:
    """Build the complete system prompt with patient context and language instructions.

    Args:
        patient_context: Dict with patient info (name, phone, MRN, history, preferences).
        language: ISO 639-1 language code for response language.
        tools_enabled: Whether tools are available in this session.
        system_prompt_override: Full override for the system prompt (e.g., campaign scripts).

    Returns:
        Complete system prompt string.
    """
    if system_prompt_override:
        prompt = system_prompt_override
    else:
        prompt = _BASE_SYSTEM_PROMPT

    # Add language instruction
    lang_instruction = _LANGUAGE_INSTRUCTIONS.get(language, _LANGUAGE_INSTRUCTIONS["en"])
    prompt += f"\nLANGUAGE: {lang_instruction}\n"

    # Add patient context if available
    if patient_context:
        prompt += _build_patient_context_section(patient_context)

    # Add tool usage note
    if tools_enabled:
        prompt += (
            "\nTOOLS: You have access to appointment management tools. "
            "Use them to check availability, book, cancel, or reschedule appointments, "
            "and to look up patient records. Always use real data from tool results.\n"
        )
    else:
        prompt += (
            "\nNOTE: No tools are available in this session. "
            "Provide general guidance and suggest calling the front desk for actions.\n"
        )

    return prompt


def _build_patient_context_section(patient_context: dict[str, str]) -> str:
    """Build the patient context section of the system prompt.

    Args:
        patient_context: Patient info dict.

    Returns:
        Formatted patient context string.
    """
    lines = ["\nPATIENT CONTEXT (known information):"]

    field_labels = {
        "name": "Name",
        "patient_id": "Patient ID",
        "phone": "Phone",
        "mrn": "MRN",
        "dob": "Date of Birth",
        "gender": "Gender",
        "preferred_language": "Preferred Language",
        "last_visit": "Last Visit",
        "upcoming_appointments": "Upcoming Appointments",
        "allergies": "Known Allergies",
        "insurance": "Insurance",
        "notes": "Notes",
    }

    for key, label in field_labels.items():
        value = patient_context.get(key)
        if value:
            lines.append(f"- {label}: {value}")

    # Include any extra keys not in the standard set
    for key, value in patient_context.items():
        if key not in field_labels and value:
            lines.append(f"- {key.replace('_', ' ').title()}: {value}")

    lines.append("")  # trailing newline
    return "\n".join(lines)


def build_messages_for_llm(
    transcript: str,
    history: list[dict[str, Any]],
    patient_context: Optional[dict[str, str]] = None,
    language: str = "en",
    tools_enabled: bool = True,
    system_prompt_override: Optional[str] = None,
    max_history_turns: int = 20,
) -> list[dict[str, Any]]:
    """Build the full messages array for an LLM call.

    Args:
        transcript: Current user utterance.
        history: Previous conversation turns (role, content, tool_call_id, tool_call).
        patient_context: Patient info dict.
        language: Language code.
        tools_enabled: Whether tools are available.
        system_prompt_override: Custom system prompt.
        max_history_turns: Maximum history turns to include (for token budget).

    Returns:
        List of messages in OpenAI chat format.
    """
    system_prompt = build_system_prompt(
        patient_context=patient_context,
        language=language,
        tools_enabled=tools_enabled,
        system_prompt_override=system_prompt_override,
    )

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    # Add trimmed history
    trimmed_history = history[-max_history_turns:] if len(history) > max_history_turns else history
    for turn in trimmed_history:
        msg: dict[str, Any] = {
            "role": turn.get("role", "user"),
            "content": turn.get("content", ""),
        }
        # Preserve tool call metadata
        if turn.get("tool_call_id"):
            msg["tool_call_id"] = turn["tool_call_id"]
        if turn.get("tool_calls"):
            msg["tool_calls"] = turn["tool_calls"]
            msg["content"] = turn.get("content")  # Can be None for tool-calling assistant messages
        if turn.get("name"):
            msg["name"] = turn["name"]
        messages.append(msg)

    # Add current user utterance
    if transcript:
        messages.append({"role": "user", "content": transcript})

    logger.debug(
        "prompt_built",
        message_count=len(messages),
        history_turns=len(trimmed_history),
        language=language,
        has_patient_context=patient_context is not None,
    )

    return messages
