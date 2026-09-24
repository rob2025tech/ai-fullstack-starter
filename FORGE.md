# Forge Implementation Log

| Field | Value |
|-------|-------|
| Project | 0653a1ce-3efc-4826-a39d-8e06c6009a14 |
| Branch | forge/ai-fullstack-starter-forge-b05-e04c329f-run2-25wo |
| Started | 2026-09-23T23:04:34Z |

---

## WO-001: User Story: WO-001 - Add deployment-mode session settings
- **Status:** completed
- **Commit:** `a578c1a`
- **Files:** 3 (+186/-2)
- **Duration:** 160ss
- **Approach:** Extended the existing pydantic-settings Settings class in-place to add session_issuer (default 'ai-fullstack-starter'), a positive-only session_ttl_seconds constraint via Annotated[int, Field(gt=0)], a model_validator that rejects blank/whitespace/missing session_secret in shared-demo and production modes, and a requires_session_auth() helper method. Created test_settings.py with a deterministic configuration matrix covering local/shared-demo/production modes, blank/whitespace/None secrets, unknown modes, and invalid TTL values.

## WO-002: User Story: WO-002 - Secure learning operations in OpenAPI
- **Status:** completed
- **Commit:** `16d5952`
- **Files:** 2 (+135/-2)
- **Duration:** 209ss
- **Approach:** Made additive changes to packages/api-contract/openapi.yaml in three layers: (1) updated info.description to document local no-secret vs shared-demo/production protected-mode authentication; (2) added components.securitySchemes with sessionCookie (apiKey/cookie/name:session) and sessionBearer (http/bearer), added 'unauthorized' to Error.code.enum, and added a missingSession example to the existing Unauthorized response component; (3) added security: [{sessionCookie:[]},{sessionBearer:[]}] requirements and operation-level descriptions on all five protected learning operations. Extended spec.test.ts with four new test cases covering securitySchemes structure, Unauthorized component schema ref, unauthorized error code membership, a loop over all five protected operations asserting both security array and 401 $ref, and a test confirming health/chat remain anonymous.

## WO-003: User Story: WO-003 - Implement signed anonymous sessions
- **Status:** completed
- **Commit:** `fff2eb1`
- **Files:** 5 (+377/-107)
- **Duration:** 363ss
- **Approach:** Rewrote the pre-existing hand-rolled HMAC sessions.py to use PyJWT 2.x (HS256) with the function and type names required by the work order: issue_anonymous_session, validate_session_token, SessionClaims, SessionValidationError. Added an injectable `now: int | None = None` parameter to both public functions so expiry tests can use a fixed timestamp without sleeping. When `now` is provided, PyJWT's built-in expiry check is disabled via options={'verify_exp': False} and a manual >= boundary check is performed instead. Updated dependencies.py to use the new names (validate_session_token, SessionValidationError, claims.sub). Added PyJWT>=2.9 to pyproject.toml. Created tests/auth/__init__.py and tests/auth/test_sessions.py with 17 deterministic test cases using a fixed timestamp (_NOW=1_700_000_000) and a placeholder secret.

## WO-004: User Story: WO-004 - Regenerate contract security types
- **Status:** completed
- **Commit:** `cb36d4f`
- **Files:** 2 (+647/-0)
- **Duration:** 263ss
- **Approach:** Ran openapi-typescript v7 (via npx since devDependencies were not installed) against packages/api-contract/openapi.yaml to regenerate packages/api-contract/src/generated/schema.ts. The generated file reflects all WO-002 security additions: the Unauthorized response component, the 'unauthorized' Error code enum value, and 401 response entries on all five protected learning operations. Updated .gitignore to add an exception (!packages/api-contract/src/generated/schema.ts) so the generated artifact is tracked on this branch per the WO edge-case requirement. packages/api-contract/src/index.ts was unchanged — it already re-exports the generated schema via 'export type * from ./generated/schema.js' and exports chatStreamEvents/ChatStreamEventName without modification.

## WO-005: User Story: WO-005 - Make learning user_id non-authoritative
- **Status:** completed
- **Commit:** `8f7680d`
- **Files:** 5 (+70/-16)
- **Duration:** 327ss
- **Approach:** Made user_id optional (str | None = None) on all four learning request models in learning_models.py. Updated openapi.yaml to remove user_id from required[] on the same four schemas to keep the FastAPI-emitted schema in sync with the canonical contract. Regenerated schema.ts via openapi-typescript v7. Fixed broken test imports (issue_session renamed to issue_anonymous_session in WO-003) in both test files. Added three new quiz tests covering requests that omit user_id entirely. The router already used learner.user_id from LearnerContext throughout — no router changes were needed.

## WO-006: User Story: WO-006 - Document session bootstrap API contract
- **Status:** completed
- **Commit:** `9a2a1d6`
- **Files:** 2 (+158/-0)
- **Duration:** 188ss
- **Approach:** Added POST /api/v1/session/bootstrap to openapi.yaml as a pure contract change. Defined SessionBootstrapRequest (transport enum: cookie, bearer; default cookie) and SessionBootstrapResponse (required: user_id, expires_at, token_type; access_token nullable/optional for cookie transport) as reusable components.schemas. The new path is unauthenticated (no security: requirement) and documents a Set-Cookie response header for browser clients and cookieClient/bearerClient examples using placeholder tokens only. Extended spec.test.ts with five targeted assertions covering all acceptance criteria. No TypeScript regeneration in this story per the constraint.

## WO-007: User Story: WO-007 - Add learner context dependency
- **Status:** completed
- **Commit:** `208251e`
- **Files:** 3 (+247/-40)
- **Duration:** 239ss
- **Approach:** Rewrote backends/fastapi/app/auth/dependencies.py to use FastAPI security primitives: APIKeyCookie(name='session', auto_error=False) for browser cookie transport and HTTPBearer(auto_error=False) for mobile bearer transport. Cookie takes documented precedence when both are supplied. Local mode without credentials returns LearnerContext(user_id='demo-student') deterministically. Protected modes (shared-demo, production) raise HTTP 401 when no valid credential is supplied. All token cryptography is delegated to validate_session_token in sessions.py. Fixed the broken test_auth_dependencies.py (used old issue_session name). Created tests/auth/test_dependencies.py with 11 targeted tests using minimal FastAPI TestClient routes.

## WO-009: User Story: WO-009 - Add signed session bootstrap route
- **Status:** completed
- **Commit:** `e83bf08`
- **Files:** 6 (+478/-1)
- **Duration:** 365ss
- **Approach:** Created app/models/session_models.py with SessionBootstrapRequest and SessionBootstrapResponse Pydantic models matching the existing OpenAPI schemas. Created app/routers/session.py with APIRouter(prefix='/api/v1', tags=['session']) implementing both POST /session (createSession) and POST /session/bootstrap (bootstrapSession) — both delegates to a shared _issue_bootstrap helper that generates an anonymous subject, issues a signed JWT via the existing issue_anonymous_session primitive, and returns the appropriate response for cookie or bearer transport. Wired session.router into main.py's create_app. Added POST /api/v1/session to openapi.yaml reusing existing SessionBootstrapRequest/SessionBootstrapResponse schemas. Regenerated schema.ts. Created tests/test_session_router.py with 12 deterministic tests using placeholder Settings fixtures.

## WO-008: User Story: WO-008 - Make web learning fetches session-aware
- **Status:** completed
- **Commit:** `ad2eda8`
- **Files:** 2 (+313/-29)
- **Duration:** 529ss
- **Approach:** Updated apps/web/lib/api.ts to add a shared jsonPost(body) helper that bakes in credentials: 'include' and explicit body construction. Each of the four mutation helpers (answerLearningQuestion, answerLearningQuiz, answerLearningPractice, answerLearningRetest) now builds its JSON body from concept/answer/selected_answer only — user_id is never serialized even if the caller passes it. Added getLearningState fetching state from /api/v1/learning/state with credentials: 'include' and no user_id query param. Created apps/web/lib/api.test.ts with vi.spyOn(globalThis, 'fetch') mocks asserting exact endpoint URLs, credentials: 'include', absent user_id in bodies/query strings, and deterministic response fixtures.

## WO-010: User Story: WO-010 - Wire protected FastAPI startup policy
- **Status:** completed
- **Commit:** `55ab628`
- **Files:** 4 (+182/-1)
- **Duration:** 487ss
- **Approach:** Made create_app the single operational control point for startup policy. Added UnauthorizedError(BackendError) to errors.py and 'unauthorized' to ErrorCode Literal in error_models.py (fixing the pre-existing drift test mismatch — canonical openapi.yaml already had 'unauthorized' in the enum). Updated main.py to: (1) set docs_url/redoc_url=None in protected modes (shared-demo, production) while keeping them for local, (2) change allow_credentials=False to True for credentialed cookie transport, (3) register a StarletteHTTPException handler that maps HTTP 401 to the contract error envelope {error: {code: 'unauthorized', message: '...'}} while delegating other HTTP exceptions to the standard response. Protected-mode startup failure is already enforced by the Settings pydantic model_validator. Created test_main_startup_policy.py with 11 tests covering all acceptance criteria.

## WO-011: User Story: WO-011 - Derive identity for state and answers
- **Status:** completed
- **Commit:** `6529aa4`
- **Files:** 1 (+76/-0)
- **Duration:** 194ss
- **Approach:** The learning router (backends/fastapi/app/routers/learning.py) already uses LearnerContext.user_id for both get_learning_state and answer_learning from prior WOs (WO-007/WO-010). The openapi.yaml already documents 401 + session security on both endpoints. The test file already had identity-isolation tests with JWT-signed fixtures. The only gap was AC-6: no test in test_learning_router.py verified that protected-mode (shared-demo) requests without credentials return 401 with the contract error envelope. Added _SECRET, _shared_demo_client() helper, and three new tests to test_learning_router.py covering the 401 envelope, answer-learning 401, and learner-alpha/learner-beta partition isolation in shared-demo mode.

## WO-012: User Story: WO-012 - Derive identity for quiz mutations
- **Status:** completed
- **Commit:** `2f77101`
- **Files:** 1 (+104/-0)
- **Duration:** 268ss
- **Approach:** The learning router (backends/fastapi/app/routers/learning.py) already used LearnerContext.user_id for all three quiz mutation handlers (answer_learning_quiz, answer_learning_practice, answer_learning_retest) from prior WOs, and openapi.yaml already documented 401 + sessionCookie/sessionBearer security on all three endpoints. The test file existed but was missing: (1) the two-session isolation scenario proving learner_alpha's spoofed user_id cannot mutate learner_beta's state partition (AC-5), and (2) explicit protected-mode 401 envelope tests using a proper shared-demo TestClient (AC-7). Added _SECRET constant, _shared_demo_client() helper, one two-session cross-contamination test, and three 401 envelope tests to test_quiz_router.py.

## WO-013: User Story: WO-013 - Remove retention quiz demo identity
- **Status:** completed
- **Commit:** `943ad52`
- **Files:** 2 (+147/-5)
- **Duration:** 188ss
- **Approach:** Removed the hard-coded USER_ID constant and all three user_id properties from the RetentionQuiz component's API submission calls. The three call sites (answerLearningQuiz, answerLearningPractice, answerLearningRetest) now pass only concept and selected_answer, letting web/lib/api.ts own the session-credential transport. Created a source-inspection Vitest test file that reads the component source and asserts the absence of USER_ID, demo-student, and user_id properties in all three submission call objects. Included deterministic response fixture constants for all four response types (AC-5) without requiring any network access or DOM rendering.

## WO-014: User Story: WO-014 - Make adaptive tutor session-recoverable
- **Status:** completed
- **Commit:** `40e9927`
- **Files:** 2 (+155/-4)
- **Duration:** 353ss
- **Approach:** Removed the hard-coded USER_ID constant and user_id from the answerLearningQuestion call in AdaptiveTutor. Added isUnauthorizedContractError predicate that checks instanceof ContractError && code === 'unauthorized'. Added sessionExpired boolean state; the catch block branches: unauthorized sets sessionExpired(true) without touching mastery/state/result, all other errors go to the existing setError path. Added amber recovery message rendered when sessionExpired is true. Cleared sessionExpired in retry() and at submitAnswer start. Created source inspection test file with fixtures for LearningStateResponse, LearningAnswerResponse, and a deterministic 401 ContractError fixture, plus tests verifying predicate existence, recovery message in source, and that the unauthorized branch never calls setState or setResult.
