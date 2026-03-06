# Clinical Voice AI Agent

Real-time multilingual voice AI platform for clinical appointment booking. Supports English, Hindi, and Tamil with sub-450ms response latency.

## Architecture

**4-Tier, 12-Microservice Platform**

```
                                 ARCHITECTURE OVERVIEW

    +------------------------------------------------------------------+
    |                        TIER 1: EDGE                               |
    |  +------------------------+    +-----------------------------+    |
    |  |   Audio Gateway :8080  |    |    API Gateway :3000        |    |
    |  |   (Python/FastAPI/WS)  |    |    (Node.js/Express)        |    |
    |  +----------+-------------+    +-----------------------------+    |
    +-------------|----------------------------------------------------+
                  |
    +-------------|----------------------------------------------------+
    |             |          TIER 2: AI PIPELINE                        |
    |  +----------v-------------+  +--------------+  +---------------+ |
    |  |  STT Service :50051    |  | LLM Agent    |  | TTS Service   | |
    |  |  (faster-whisper/gRPC) |->| :8090        |->| :50052        | |
    |  |  + VAD + Lang Detect   |  | (litellm)    |  | (XTTS v2)    | |
    |  +------------------------+  +------+-------+  +---------------+ |
    +----------------------------------|-------------------------------+
                                       |
    +----------------------------------|-------------------------------+
    |                                  v    TIER 3: APP LOGIC          |
    |  +-------------------+  +--------+--------+  +----------------+ |
    |  | Session Manager   |  | Tool Orchestr.  |  | Campaign       | |
    |  | :6380 (Redis)     |  | :8091 (gRPC)    |  | Engine :3030   | |
    |  +-------------------+  +--------+--------+  | (BullMQ)       | |
    |                           |            |      +----------------+ |
    |                    +------+------+  +--+----------------+        |
    |                    | Appointment |  | Patient Memory    |        |
    |                    | Sched :3010 |  | :3020 (Mongoose)  |        |
    |                    | (Mongoose)  |  +-------------------+        |
    |                    +-------------+                               |
    +------------------------------------------------------------------+
                                       |
    +------------------------------------------------------------------+
    |                     TIER 4: INFRASTRUCTURE                        |
    |  +----------+  +----------+  +------------+  +----------------+  |
    |  | MongoDB  |  | Redis    |  | Prometheus |  | Grafana/Jaeger |  |
    |  | 7.0      |  | 7.2      |  | + Alerts   |  | + Loki         |  |
    |  +----------+  +----------+  +------------+  +----------------+  |
    +------------------------------------------------------------------+
```

## Voice Flow

```
User speaks -> Browser captures audio
  -> WebSocket (binary PCM frames)
    -> Audio Gateway
      -> gRPC stream -> STT Service (Whisper large-v3)
        -> Language Detection (FastText + Whisper)
          -> LLM Agent (GPT-4o / Claude fallback)
            -> Tool Orchestrator -> Appointment Scheduler / Patient Memory
          -> TTS Service (XTTS v2)
        -> gRPC stream -> Audio Gateway
      -> WebSocket (binary PCM frames)
    -> Browser plays audio
User hears response (<450ms from end of speech)
```

## Services

| Service | Port | Stack | Purpose |
|---------|------|-------|---------|
| audio-gateway | 8080 | Python/FastAPI | WebSocket audio streaming, pipeline orchestration |
| stt-service | 50051 | Python/gRPC | Speech-to-text (faster-whisper), VAD, language detection |
| llm-agent | 8090 | Python/FastAPI+gRPC | Conversational AI with tool calling |
| tool-orchestrator | 8091 | Python/FastAPI+gRPC | Routes LLM tool calls to backend services |
| tts-service | 50052 | Python/gRPC | Text-to-speech (XTTS v2), multilingual |
| session-manager | 6380 | Python/FastAPI | Redis-backed conversation state |
| api-gateway | 3000 | Node.js/Express | Auth, rate limiting, request routing |
| appointment-scheduler | 3010 | Node.js/Express | Booking CRUD, availability, conflict resolution |
| patient-memory | 3020 | Node.js/Express | Patient records, PHI encryption, consent |
| campaign-engine | 3030 | Node.js/Express | Outbound reminder campaigns (BullMQ) |

## Code Pattern

All services follow the **Model / Service / Controller / Validator / Route** pattern:

```
Request -> Route (path binding) -> Controller (HTTP handling)
  -> Validator (input + business rules) -> Service (business logic)
    -> Client/DB (external calls) -> Response
```

### Python Services (FastAPI)
```
services/{name}/app/
  models/       # Pydantic schemas (requests.py, responses.py, domain.py)
  services/     # Business logic (framework-agnostic)
  controllers/  # FastAPI router handlers (thin, delegates to services)
  validators/   # Business rule validation
  routes/       # Route registration (v1.py)
  middleware/   # Error handling, request ID
  clients/      # Redis, gRPC, HTTP clients
```

### Node.js Services (Express/TypeScript)
```
services/{name}/src/
  models/       # Mongoose schemas + Zod validation (requests.ts, responses.ts, domain.ts)
  services/     # Business logic (framework-agnostic)
  controllers/  # Express handlers (thin, delegates to services)
  validators/   # Zod schemas + business rules
  routes/       # Route registration (v1.ts)
  middleware/   # Auth, error handling, audit logging
  clients/      # Redis, HTTP, MongoDB clients
```

## Tech Stack

### AI Components
- **STT:** faster-whisper (CTranslate2, Whisper large-v3) + Silero VAD
- **Language Detection:** FastText lid.176 (in-process with STT)
- **LLM:** GPT-4o (primary) / Claude 3.5 Sonnet (fallback) via litellm
- **TTS:** Coqui XTTS v2 (multilingual, on-premise)

### Backend
- **Python 3.12** with FastAPI, gRPC, uvicorn/uvloop
- **Node.js 20 LTS** with TypeScript, Express.js
- **MongoDB 7.0** with Mongoose ODM
- **Redis 7.2** for sessions, event bus (Streams), caching
- **BullMQ** for campaign job queues

### Infrastructure
- **Docker Compose** for orchestration
- **NGINX** for reverse proxy + WebSocket sticky sessions
- **Prometheus + Grafana** for metrics and dashboards
- **Jaeger** for distributed tracing
- **Loki** for log aggregation

## Latency Budget

Target: **<450ms** from speech end to first audio response byte.

```
Stage                          Budget    Technique
------------------------------ --------  ----------------------------------
VAD endpoint detection          20ms     Silero VAD in-process
Network: Gateway -> STT          5ms     Docker network, persistent gRPC
STT finalization                80ms     faster-whisper float16, greedy decode
Context assembly                15ms     Redis <1ms, pre-built on partials
LLM time-to-first-token       150ms     GPT-4o streaming, prompt caching
Tool execution                  80ms     Indexed MongoDB, circuit breakers
LLM continued generation        50ms     Stream at sentence boundary
TTS first audio chunk           30ms     XTTS v2 GPU, sentence chunking
Network: TTS -> Client          20ms     gRPC stream + WebSocket
------------------------------ --------
TOTAL (with tool call)         450ms
TOTAL (without tool call)      370ms
```

Key optimizations:
- **Pipeline parallelism** - TTS starts on first sentence while LLM generates rest
- **Speculative context assembly** - built during STT, not after
- **Streaming everywhere** - no stage waits for full output before starting next
- **Connection pooling** - persistent gRPC channels, no handshake overhead

## Data Model

### MongoDB Collections

| Collection | Purpose | Key Fields |
|------------|---------|------------|
| patients | Patient records (PHI encrypted) | phone, name (encrypted), language_pref, consent |
| doctors | Doctor profiles + embedded schedules | name, department, schedules[], overrides[] |
| appointmentSlots | Pre-generated time slots | doctorId, startTime, endTime, status, __v |
| appointments | Booked appointments | patientId, doctorId, slotId, status, bookedVia |
| campaigns | Outbound call campaigns | name, type, status, targetDate, analytics |
| campaignCalls | Individual campaign calls | campaignId, patientId, status, outcome, attempts |
| conversationSummaries | AI-generated session summaries | patientId, sessionId, summary, entities |
| auditLogs | HIPAA audit trail | userId, action, resourceType, phiAccessed |
| users | Admin/staff accounts | email, passwordHash, role |

### Redis Keys

| Pattern | Type | TTL | Purpose |
|---------|------|-----|---------|
| session:{id} | Hash | 1h | Session state (status, language, patientId) |
| session:{id}:turns | List | 1h | Conversation history |
| session:{id}:context | String | 60s | Pre-assembled LLM context |
| session:{id}:tools | Hash | 5m | Active tool call tracking |
| ratelimit:{key}:{min} | Counter | 2m | API rate limiting |

## Communication Protocols

| From | To | Protocol | Purpose |
|------|----|----------|---------|
| Client | Audio Gateway | WebSocket (binary PCM) | Real-time audio streaming |
| Audio Gateway | STT | gRPC bidirectional stream | Audio -> transcript |
| STT | LLM Agent | gRPC server-streaming | Transcript -> reasoning |
| LLM Agent | Tool Orchestrator | gRPC unary | Function call dispatch |
| Tool Orchestrator | App Services | REST (internal) | CRUD operations |
| LLM Agent | TTS | gRPC server-streaming | Text -> audio |
| All Services | Redis Streams | Pub/Sub | Async events, audit |
| API Gateway | All Services | REST | Admin/portal operations |

## Fault Tolerance

| Component Failed | Degraded Behavior |
|-----------------|-------------------|
| STT Service | Switch to text-input mode |
| LLM Primary (GPT-4o) | Fallback to Claude 3.5 Sonnet, then canned responses |
| TTS Service | Text-only response |
| Redis | In-memory LRU cache (per instance) |
| MongoDB | Read from replica; writes queued |
| Tool Orchestrator | LLM communicates unavailability to patient |

Circuit breakers (pybreaker/opossum) on all inter-service calls with exponential backoff + jitter.

## Security (HIPAA Compliant)

- **PHI Encryption:** AES-256-GCM field-level encryption in MongoDB (name, email, address)
- **Transport:** TLS 1.3 external, mTLS within Docker network
- **Auth:** JWT + API keys, role-based access (admin/staff/doctor/voice_agent)
- **Audit:** All PHI access logged to auditLogs collection
- **Voice Data:** No recording by default; opt-in with consent
- **Retention:** 30-day recordings, 1-year transcripts, then anonymized

## Project Structure

```
ai-voice-agent/
|-- README.md
|-- docker-compose.yml
|-- docker-compose.dev.yml
|-- .env.example
|-- .gitignore
|-- Makefile
|
|-- shared/
|   |-- proto/                    # gRPC protocol definitions
|   |   |-- stt.proto
|   |   |-- tts.proto
|   |   |-- llm_agent.proto
|   |   |-- tool_orchestrator.proto
|   |   +-- health.proto
|   |-- python/                   # Shared Python libraries
|   |   |-- shared/
|   |   |   |-- config.py
|   |   |   |-- logging.py
|   |   |   |-- tracing.py
|   |   |   |-- metrics.py
|   |   |   |-- circuit_breaker.py
|   |   |   |-- redis_client.py
|   |   |   |-- mongo_client.py
|   |   |   |-- grpc_utils.py
|   |   |   |-- audio_utils.py
|   |   |   |-- events.py
|   |   |   +-- exceptions.py
|   |   +-- pyproject.toml
|   +-- typescript/               # Shared TypeScript libraries
|       |-- src/
|       |   |-- config.ts
|       |   |-- logger.ts
|       |   |-- tracing.ts
|       |   |-- metrics.ts
|       |   |-- circuit-breaker.ts
|       |   |-- redis-client.ts
|       |   |-- mongo-client.ts
|       |   |-- events.ts
|       |   |-- auth-middleware.ts
|       |   |-- error-handler.ts
|       |   |-- health-check.ts
|       |   +-- types/
|       +-- package.json
|
|-- services/
|   |-- audio-gateway/            # Python/FastAPI - WebSocket audio
|   |-- stt-service/              # Python/gRPC - Speech-to-text
|   |-- llm-agent/                # Python/FastAPI+gRPC - AI reasoning
|   |-- tool-orchestrator/        # Python/FastAPI+gRPC - Tool routing
|   |-- tts-service/              # Python/gRPC - Text-to-speech
|   |-- session-manager/          # Python/FastAPI - Session state
|   |-- api-gateway/              # Node.js/Express - Auth + routing
|   |-- appointment-scheduler/    # Node.js/Express - Booking engine
|   |-- patient-memory/           # Node.js/Express - Patient records
|   +-- campaign-engine/          # Node.js/Express - Outbound campaigns
|       (each service follows Model/Service/Controller/Validator/Route pattern)
|
|-- infrastructure/
|   |-- mongo/                    # Init scripts, indexes, seed data
|   |-- redis/                    # Redis configuration
|   |-- nginx/                    # Reverse proxy, SSL
|   |-- prometheus/               # Scrape configs, alert rules
|   |-- grafana/                  # Dashboards, datasources
|   +-- scripts/                  # Backup, key rotation, load test
|
|-- tests/
|   |-- integration/              # End-to-end flow tests
|   |-- load/                     # k6 load tests
|   +-- fixtures/                 # Audio samples, mock data
|
|-- docs/
|   |-- architecture.md
|   |-- api-reference.md
|   |-- deployment-guide.md
|   |-- runbooks/
|   +-- adr/
|
|-- tools/                        # Dev scripts
|   |-- dev-setup.sh
|   |-- generate-proto.sh
|   +-- migrate-db.sh
|
+-- .github/workflows/           # CI/CD pipelines
```

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env with your API keys (OPENAI_API_KEY, ANTHROPIC_API_KEY)

# 2. Start all services
docker compose up -d

# 3. Verify health
curl http://localhost:3000/health

# 4. Connect via WebSocket
wscat -c ws://localhost:8080/ws/voice?api_key=YOUR_KEY
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| OPENAI_API_KEY | Yes | GPT-4o API key |
| ANTHROPIC_API_KEY | Yes | Claude fallback API key |
| MONGODB_URI | Yes | MongoDB connection string |
| REDIS_PASSWORD | Yes | Redis authentication |
| JWT_SECRET | Yes | JWT signing secret |
| PHI_ENCRYPTION_KEY | Yes | AES-256 key for patient data |
| GRAFANA_PASSWORD | No | Grafana admin password |

## Supported Languages

| Language | Code | STT | TTS | LLM |
|----------|------|-----|-----|-----|
| English | en | Whisper large-v3 | XTTS v2 | GPT-4o |
| Hindi | hi | Whisper large-v3 | XTTS v2 | GPT-4o |
| Tamil | ta | Whisper large-v3 | XTTS v2 | GPT-4o |

## License

Proprietary - All rights reserved.
