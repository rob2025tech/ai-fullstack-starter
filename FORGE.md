# Forge Implementation Log

| Field | Value |
|-------|-------|
| Project | d0045549-59c6-4b2d-8ddf-4e44469c2006 |
| Branch | forge/ai-fullstack-starter-918a9eb7-run2-16wo |
| Started | 2026-09-25T22:48:46Z |

---

## WO-001: User Story: WO-001 - Define additive agent API contract
- **Status:** completed
- **Commit:** `476eef9`
- **Files:** 2 (+1095/-0)
- **Duration:** 584ss
- **Approach:** Additive-only OpenAPI 3.1 contract extension. Added agent tag, bearerAuth security scheme, 8 new /api/v1/agent path operations (createAgentSession, getAgentSession, submitAgentTask, listAgentEvents, streamAgentEvents, listAgentApprovals, decideAgentApproval, getAgentState), and 9 component schemas (CreateAgentSessionRequest, SubmitAgentTaskRequest, ApprovalDecisionRequest, AgentSessionResponse, AgentTaskResponse, AgentEventResponse, ApprovalRequestResponse, AgentStateResponse, AgentSseEvent). Reused existing Unauthorized response reference for all 401 responses. Ran openapi-typescript generation to produce TypeScript types. Extended spec.test.ts with assertions covering paths, schemas, status codes, SSE content type, constrained enums, and representative JSON fixture examples for all six required event_type values.

## WO-002: User Story: WO-002 - Create durable agent repositories
- **Status:** completed
- **Commit:** `f6ac7b8`
- **Files:** 4 (+1524/-0)
- **Duration:** 496ss
- **Approach:** Created a new backends/fastapi/app/agent/ package with a SQLite-backed AgentRepository using Python's standard-library sqlite3. The repository initializes four tables (agent_sessions, agent_tasks, agent_events, approval_requests) with appropriate indexes on creation. Events use a UNIQUE(task_id, sequence) constraint with BEGIN IMMEDIATE transactions to guarantee monotonic per-task ordering. consume_approval_once is serialized with BEGIN IMMEDIATE to prevent double-consumption. All metadata/payload columns store JSON text with typed deserialization errors. Timestamps are UTC ISO 8601 strings stored/returned as timezone-aware datetime objects. No ORM, Redis, or external database service introduced. 35 tests cover entity fields, durability (close+reopen), session isolation, fixture helpers, approval exact-once guarantee, and edge cases.

## WO-003: User Story: WO-003 - Add provider call policy wrapper
- **Status:** completed
- **Commit:** `edff63a`
- **Files:** 7 (+658/-17)
- **Duration:** 449ss
- **Approach:** Introduced ProviderPolicy as a thin reliability wrapper around LLMProvider.generate. ProviderPolicyConfig (dataclass with __post_init__ validation) holds timeout_seconds, max_retries, and max_payload_bytes. ProviderPolicy.generate enforces: (1) UTF-8 byte size check before any I/O, (2) asyncio.wait_for timeout, (3) ProviderUnavailableError retry up to max_retries, (4) no retry for ProviderError or InvalidRequestError, (5) bare-exception normalisation to ProviderError. ChatService and TeachingService constructors changed to accept ProviderPolicy; streaming path kept unchanged via policy.provider accessor. create_app gained an llm_provider_override parameter for test injection. Settings gained three new fields with safe defaults.

## WO-004: User Story: WO-004 - Fail closed production backend settings
- **Status:** completed
- **Commit:** `905f4fa`
- **Files:** 6 (+373/-7)
- **Duration:** 419ss
- **Approach:** Added a Pydantic v2 model_validator(mode='after') to Settings that fires only when deployment_mode='production'. The validator accumulates all violations (missing SESSION_SECRET, empty/wildcard CORS_ORIGINS, missing OPENAI_API_KEY for openai provider) and raises a single ValueError listing all offending setting names before create_app wires any middleware or routes. Local mode is completely unaffected — no secrets are required. Whitespace-only values are treated as absent. The existing session module's own check is preserved as defense-in-depth for shared-demo mode.

## WO-005: User Story: WO-005 - Validate FastAPI lockfile workflow
- **Status:** completed
- **Commit:** `7b45efc`
- **Files:** 2 (+255/-0)
- **Duration:** 220ss
- **Approach:** Inspected pyproject.toml and requirements-lock.txt first and confirmed all declared runtime and dev dependencies were already exactly pinned. Created test_requirements_lock.py using stdlib tomllib (with tomli fallback for Python 3.10 CI environments). The test normalizes package names with PEP 503 rules (lowercase, collapse [-_.] to hyphen) then asserts: all runtime deps pinned ==, all dev deps pinned == or in _DEV_EXCLUSIONS set, the 9 AC-required packages are pinned, no range pins for declared packages, no editable installs, and pinned versions satisfy declared lower bounds. Updated README with a titled 'Deterministic dependency lock workflow' section covering all four required command groups.
