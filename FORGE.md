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

## WO-007: User Story: WO-007 - Implement agent models and router
- **Status:** completed
- **Commit:** `f68b111`
- **Files:** 4 (+813/-0)
- **Duration:** 229ss
- **Approach:** Created agent_models.py with 8 Pydantic models (3 request + 5 response) aligned to the OpenAPI schemas, using Literal types for enums. Created agent.py router with APIRouter prefix /api/v1/agent covering all 8 contract paths. Routes read agent_repository from app.state (per learning.py pattern), map NotFoundError/InvalidApprovalTransitionError to InvalidRequestError, and emit SSE frames via StreamingResponse. Added list_tasks(session_id) to AgentRepository to avoid accessing private _db from router code. Router is not wired into create_app per the WO constraint.

## WO-006: User Story: WO-006 - Implement deterministic tool registry
- **Status:** completed
- **Commit:** `917ac98`
- **Files:** 4 (+610/-0)
- **Duration:** 244ss
- **Approach:** Created a pure domain module (no FastAPI/LLMProvider imports) with four public types: ToolRisk (str enum: read_only/mutating/unsafe), frozen ToolDefinition dataclass (name, description, input_schema, output_schema, callable, risk), ToolResult dataclass (tool_name, risk, output, metadata), and ToolInvocationError (reason, tool_name, details). ToolRegistry holds an insertion-ordered dict. register() rejects empty/whitespace names and duplicates before mutating state. invoke() does: exact-name lookup → Pydantic input validation → callable call with exception wrapping → Pydantic output validation → ToolResult. errors.py not modified (registry errors are self-contained).

## WO-010: User Story: WO-010 - Wire agent services into FastAPI
- **Status:** completed
- **Commit:** `06868ad`
- **Files:** 4 (+165/-11)
- **Duration:** 271ss
- **Approach:** Made the smallest composition-root change: added AgentRepository import and agent router import to main.py, instantiated AgentRepository() (defaults to :memory: for per-call isolation) on app.state.agent_repository, and added app.include_router(agent.router) after the existing three routers. Added an optional agent_repository_override parameter to create_app() for test injection without changing the default call. Updated all 8 agent route response declarations to include 401 to match the canonical spec. Added AgentSseEvent to DOC_ONLY_SCHEMAS since the SSE stream endpoint returns StreamingResponse with no typed model and FastAPI does not auto-emit that schema.

## WO-008: User Story: WO-008 - Add workspace inspection tools
- **Status:** completed
- **Commit:** `610b534`
- **Files:** 2 (+571/-0)
- **Duration:** 546ss
- **Approach:** Implemented WorkspacePolicy as a dataclass that resolves the workspace root once via pathlib.Path.resolve and exposes resolve_safe() which (1) normalizes paths via os.path.normpath to catch traversal before following symlinks, then (2) calls Path.resolve() to follow symlinks and re-checks the result stays within root. RepositoryTreeTool and FileReadTool are factory functions (PascalCase per AC) that return ToolDefinition instances with closures capturing the policy. Both are ToolRisk.read_only. The file.read tool rejects directories, oversized files, and non-UTF-8 content with structured error details.

## WO-009: User Story: WO-009 - Add governed mutation and command tools
- **Status:** completed
- **Commit:** `ce4a9b4`
- **Files:** 4 (+1008/-0)
- **Duration:** 485ss
- **Approach:** mutation.py: FileWriteInput/FileWriteOutput Pydantic models + FileWriteTool factory that reuses WorkspacePolicy.resolve_safe for path validation, enforces overwrite=False protection (returns reason=overwrite_refused without writing), create_parents flag for mkdir -p, and returns action='created'|'overwritten'. commands.py: ALWAYS_BLOCKED frozenset (rm, sudo, curl, pip, bash, ssh, etc.), GIT_READ_ONLY_SUBCOMMANDS frozenset, CommandRiskClassifier dataclass that strips path prefix and classifies argv[0] against constants (git subcommand routing, _BASE_READ_ONLY fallback, mutating default), CommandPolicy dataclass (max_output_bytes, timeout_seconds), injectable CommandRunner callable type, _default_runner using asyncio.create_subprocess_exec with shell=False, CommandInput/CommandOutput Pydantic models, and CommandTool factory that enforces: blocked→reject, mutating/unsafe+unapproved→command_requires_approval, read_only→execute. Output truncation applied per stream with truncated_stdout/truncated_stderr flags. No shell=True anywhere. No public endpoint added.

## WO-011: User Story: WO-011 - Implement exact-once approval service
- **Status:** completed
- **Commit:** `f40d84a`
- **Files:** 4 (+830/-0)
- **Duration:** 555ss
- **Approach:** Created ApprovalService in backends/fastapi/app/agent/approvals.py with canonical SHA-256 action fingerprinting, injectable clock for deterministic tests, and four methods: request_approval (creates pending record + audit event), decide (idempotent approve/reject + event), expire_due_approvals (demand-driven sweep), and consume_approval (atomic binding-verified exact-once transition). Extended AgentRepository with public get_approval wrapper and expire_pending_before that sweeps both pending AND approved records past their TTL. Wired ApprovalService onto app.state in main.py. All 32 tests pass.
