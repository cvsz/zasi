# AI Futures Project Superintelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the safe, local-first AI Futures Project Superintelligence vertical slice in ZASI so an authenticated operator can define and publish an agent, sandbox-test it, run a supervised task, observe a tenant-scoped read-only knowledge result, approve or reject an exact simulated ticket update, and inspect the complete event, audit, and evidence history.

**Architecture:** Extend the existing `backend.app` authoritative FastAPI control plane. Agent definitions, immutable versions, executions, and simulator approvals become durable tenant-scoped records in the existing SQLite/PostgreSQL repositories. The agent runtime delegates every tool action through the existing `ToolRegistry`, `PolicyEngine`, `ActionBroker`, `ActionWorker`, evidence, audit, and event/outbox path. The reference profile remains one local Python process with SQLite and an in-process event consumer; Ollama is an optional localhost-only adapter and the deterministic simulator is the default. The historical 176-subsystem catalog remains inventory/documentation and is not promoted to runtime capability evidence.

**Tech Stack:** Python 3.9+, FastAPI, Pydantic v2, SQLite, PostgreSQL/psycopg adapter, existing ZASI policy/broker/event store, optional standard-library `urllib` Ollama client, React 18, React Router v6, TypeScript, existing SSE event feed, Python `unittest`, and the repository Makefile.

## Global Constraints

- Preserve `backend.app` as the only authoritative application owner. Do not create a parallel unauthenticated `ai_futures_superintelligence` server or bypass the current session/tenant context.
- Preserve the user’s unrelated `docs/javis` additions/deletions. Do not broad-stage, delete, restore, or format those files.
- Keep all real-world side effects disabled: no credentials, browser automation, arbitrary code execution, robotics, financial actions, live SaaS writes, or external connector calls.
- `knowledge.search` is read-only and tenant-scoped. `ticket.update` is a deterministic local simulator whose result must explicitly state `simulated=true` and `external_write=false`.
- Every agent mutation is authenticated, tenant-scoped, bounded, idempotent, auditable, and fail-closed. Unknown tools, stale versions, malformed plans, missing scopes, missing evidence, mismatched approval bindings, and ambiguous outcomes must not execute.
- An approval is valid only for the exact tenant, execution, agent version digest, tool/version, action payload digest, and approval expiry. Replays must return the original durable result without invoking a handler twice.
- Extend both the SQLite schema/migrations and the PostgreSQL schema/migrations. Existing databases at schema version 11 must migrate forward without data loss; newer schemas must still be rejected.
- Do not claim ASI exists or that research-only components are implemented. RSI, architecture search, kernel generation, self-deployment, formal proof, physical actuation, and external egress remain explicit disabled/research-only states.
- Do not send user data to hosted models. Ollama requests are allowed only when explicitly configured to loopback (`localhost`, `127.0.0.1`, or `::1`) and are bounded by a short timeout; otherwise use the deterministic planner.
- Keep the implementation dependency-light. The Python verification gate must not require Node, npm, Docker, PostgreSQL, Redis, Ollama, or network access.
- Use existing ZASI identifier, timestamp, digest, scope, and error helpers where possible. Do not expose exception text, prompts, secrets, or hidden chain-of-thought in API responses or evidence.

---

## Existing Integration Points

The implementation must adapt these current components instead of replacing them:

- `backend/app.py:create_app(settings=None, store=None)` owns the FastAPI app, registry, policy, broker, lifespan, auth dependency, snapshot, audit, and SSE routes.
- `src/control_plane/storage.py:ControlPlaneStore` owns SQLite initialization, schema versioning, tenant checks, idempotency, plans, runs, actions, evidence, audit, and events. `PostgresControlPlaneStore` inherits the repository contract and has a parallel schema/migration list in `src/control_plane/postgres_storage.py`.
- `src/control_plane/execution.py:ToolRegistry`, `ToolDefinition`, `ActionBroker`, `ActionWorker` own capability manifests, policy-mediated submission, durable action claims, bounded execution, and evidence.
- `src/control_plane/policy.py:PolicyEngine` owns exact risk-tier and scope evaluation. Reuse it for each planned step.
- Existing `/api/v2/sessions`, `/api/v2/approvals`, `/api/v2/audit`, `/api/v2/evidence`, `/api/v2/snapshot`, and `/api/v2/events` routes remain compatible. Agent-specific endpoints add the missing workflow without weakening generic route guards.
- `web/static/cockpit.tsx` already has typed API helpers, authentication, responsive cards, route shell, and reconnecting SSE with snapshot resynchronization. Extend those primitives rather than introducing another frontend entry point.

## File Map

Create:

- `src/control_plane/agent_contracts.py` — strict API request/response models and bounded enums for agents, versions, executions, approvals, and model status.
- `src/control_plane/agent_models.py` — immutable domain values for version specs, budgets, typed plan steps, model selection, and event context.
- `src/control_plane/agent_tools.py` — registration and context-aware handlers for the local knowledge search and simulated ticket update tools.
- `src/control_plane/model_gateway.py` — simulator-first model selection/proposal gateway and loopback-only Ollama adapter.
- `src/control_plane/agent_planner.py` — deterministic typed planner and fail-closed verifier.
- `src/control_plane/agent_runtime.py` — orchestration service for lifecycle, planning, read-only execution, approval creation/resolution, simulator completion, and dashboard projections.
- `tests/test_agent_platform.py` — unit, repository, policy, replay, simulator, API, tenant-isolation, and idempotency coverage for the new vertical slice.

Modify:

- `src/control_plane/storage.py` — schema version 12, SQLite migrations/tables, event-envelope columns, agent repository methods, filtered audit/event projections, and transactionally idempotent state transitions.
- `src/control_plane/postgres_storage.py` — matching agent tables and `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` migrations, preserving the existing repository method behavior.
- `src/control_plane/execution.py` — bounded execution context support for tenant-aware agent handlers and a deliberately restricted simulator-worker path; retain one-argument compatibility for existing handlers/tests.
- `src/control_plane/config.py` — optional `ZASI_OLLAMA_BASE_URL` and `ZASI_OLLAMA_MODEL` settings with secure defaults and loopback validation.
- `backend/app.py` — register agent tools/runtime, seed only an idempotent local demo definition if useful, add authenticated agent/version/sandbox/execution/approval/model routes, enrich snapshot and audit filters, and preserve generic API behavior.
- `web/static/cockpit.tsx` — typed agent registry, execution timeline, approval queue, audit filters, model status, navigation, and event-driven refreshes.
- `web/static/style.css` — responsive styles for registry, timeline, approval, and audit surfaces using the existing visual language.
- `tests/test_control_plane_api.py`, `tests/test_control_plane_core.py`, `tests/test_control_plane_broker.py`, and `tests/test_action_worker.py` — update capability counts/fixtures and verify compatibility with the expanded registry/context-aware worker.
- `tests/test_components.js` — assert the new routes, labels, safety disclosures, API paths, and no direct transport access from the UI.
- `Makefile` — add `test-agent-platform` and a Python-only `check` target; retain existing full-stack targets.
- `README.md`, `docs/API_REFERENCE.md`, and `docs/ARCHITECTURE.md` — document the product name, safe workflow, API, event envelope, model policy, simulator disclosure, research-only boundaries, and verification command.
- `src/control_plane/research.py` and/or `src/control_plane/topology.py` only if needed to expose typed, disabled research extension status already described by the design; no active self-modification path may be added.

Do not modify or stage unrelated media under `docs/javis/`.

---

## Task 1 — Define the agent domain and durable repository contract

### 1.1 Add strict contracts and immutable values

- [ ] Create `src/control_plane/agent_contracts.py` with `ConfigDict(extra="forbid")` models and bounded fields:

  ```python
  class AgentCreateRequest(BaseModel):
      name: str = Field(min_length=1, max_length=128)
      description: str = Field(default="", max_length=4096)
      version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
      system_prompt: str = Field(default="", max_length=16_384)
      allowed_tools: list[str] = Field(default_factory=lambda: ["knowledge.search", "ticket.update"], max_length=16)
      model_policy: dict[str, Any] = Field(default_factory=dict)
      budget: BudgetRequest = Field(default_factory=BudgetRequest)

  class AgentVersionCreateRequest(BaseModel):
      version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
      system_prompt: str = Field(default="", max_length=16_384)
      allowed_tools: list[str] = Field(min_length=1, max_length=16)
      model_policy: dict[str, Any] = Field(default_factory=dict)
      budget: BudgetRequest = Field(default_factory=BudgetRequest)

  class AgentSandboxRequest(BaseModel):
      task: str = Field(min_length=1, max_length=4096)
      ticket_id: str = Field(default="DEMO-1", min_length=1, max_length=128)
      ticket_fields: dict[str, Any] = Field(default_factory=dict)

  class AgentExecutionRequest(AgentSandboxRequest):
      pass

  class AgentApprovalDecisionRequest(BaseModel):
      reason: str = Field(min_length=1, max_length=2000)
  ```

  Use an explicit `BudgetRequest` with `max_steps`, `max_tool_calls`, and `max_runtime_seconds`; reject booleans, zero, oversized values, and unknown keys.
- [ ] Define immutable dataclasses in `src/control_plane/agent_models.py`:
  `BudgetPolicy`, `AgentVersionSpec`, `PlanStep`, `TypedAgentPlan`, `ModelSelection`, and `AgentEventContext`. Include `to_jsonable()` methods that canonicalize ordering before digesting.
- [ ] Make the typed plan require `step_id`, `tool_id`, `tool_version`, `risk_tier`, `input`, `preconditions`, and `expected_effects`. Represent `approval_required` as derived from policy, not as an operator-controlled free-form flag.

### 1.2 Add schema version 12 and migrations

- [ ] Change `CURRENT_SCHEMA_VERSION` from `11` to `12`.
- [ ] Add SQLite tables in `ControlPlaneStore.initialize()`:

  - `agents(id, tenant_id, principal_id, name, description, status, created_at, updated_at)` with tenant and principal foreign keys.
  - `agent_versions(id, agent_id, tenant_id, version, status, system_prompt, allowed_tools_json, model_policy_json, budget_json, digest, created_at, published_at)` with `UNIQUE(agent_id, version)`.
  - `agent_executions(id, tenant_id, principal_id, agent_id, agent_version_id, idempotency_key, task, status, plan_json, model_json, knowledge_run_id, ticket_run_id, result_json, error_json, created_at, started_at, finished_at)` with `UNIQUE(tenant_id, idempotency_key)`.
  - `agent_approvals(id, tenant_id, execution_id, agent_version_id, run_id, tool_id, tool_version, action_digest, decision, reason, approver_id, created_at, resolved_at, expires_at)` with a uniqueness constraint over `(tenant_id, execution_id, action_digest)`.

  Status transitions must be enforced in repository methods: agent `active/disabled`; version `draft/published/retired`; execution `created/planning/running/awaiting_approval/completed/rejected/failed`; approval `pending/approved/rejected/revoked`.
- [ ] Add migration checks for existing SQLite files using `PRAGMA table_info`; add the following event envelope columns when absent: `execution_id`, `agent_version`, `correlation_id`, `causation_id`, `sensitivity`, and `idempotency_key`. Existing rows receive safe defaults (`NULL` where not applicable, `sensitivity='tenant'`, and a stable correlation fallback when read).
- [ ] Add equivalent `CREATE TABLE` statements and `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` entries to the PostgreSQL schema/migration collection. The PostgreSQL adapter must continue to translate the repository’s parameter style and must reject a database newer than version 12.
- [ ] Keep all new foreign keys tenant-scoped in repository checks even where the database cannot express a composite foreign key.

### 1.3 Add repository methods with replay-safe transactions

- [ ] Implement tenant-checked methods on `ControlPlaneStore` so `PostgresControlPlaneStore` inherits the same public contract:

  ```python
  def create_agent(self, *, agent_id: str, tenant_id: str, principal_id: str, name: str, description: str) -> dict[str, Any]: ...
  def get_agent(self, agent_id: str, tenant_id: str) -> dict[str, Any]: ...
  def list_agents(self, tenant_id: str, limit: int = 100) -> list[dict[str, Any]]: ...
  def create_agent_version(self, *, version_id: str, agent_id: str, tenant_id: str, version: str, system_prompt: str, allowed_tools: list[str], model_policy: dict[str, Any], budget: dict[str, Any], digest: str) -> dict[str, Any]: ...
  def publish_agent_version(self, *, agent_id: str, version_id: str, tenant_id: str, principal_id: str) -> dict[str, Any]: ...
  def get_agent_version(self, version_id: str, tenant_id: str) -> dict[str, Any]: ...
  def list_agent_versions(self, agent_id: str, tenant_id: str) -> list[dict[str, Any]]: ...
  def create_agent_execution(self, *, execution_id: str, tenant_id: str, principal_id: str, agent_id: str, agent_version_id: str, idempotency_key: str, task: str, plan: dict[str, Any], model: dict[str, Any]) -> dict[str, Any]: ...
  def update_agent_execution(self, *, execution_id: str, tenant_id: str, status: str, knowledge_run_id: str | None = None, ticket_run_id: str | None = None, result: dict[str, Any] | None = None, error: dict[str, Any] | None = None) -> dict[str, Any]: ...
  def get_agent_execution(self, execution_id: str, tenant_id: str) -> dict[str, Any]: ...
  def list_agent_executions(self, tenant_id: str, agent_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]: ...
  def create_agent_approval(self, *, approval_id: str, tenant_id: str, execution_id: str, agent_version_id: str, run_id: str, tool_id: str, tool_version: str, action_digest: str, expires_at: datetime) -> dict[str, Any]: ...
  def resolve_agent_approval(self, *, approval_id: str, tenant_id: str, approver_id: str, decision: str, reason: str) -> dict[str, Any]: ...
  def list_agent_approvals(self, tenant_id: str, decision: str | None = "pending", limit: int = 100) -> list[dict[str, Any]]: ...
  ```

  Match the repository’s current `NotFoundError`, `ScopeViolation`, `ConflictError`, validation, and idempotency conventions. A duplicate create or resolve request returns the original record only when its canonical request/action digest matches; conflicting reuse returns `ConflictError`.
- [ ] Extend `_append_audited_event_locked` and `append_audited_event` with optional execution context while retaining named-call compatibility for existing methods:

  ```python
  def append_audited_event(..., payload: dict[str, Any], *, execution_id: str | None = None, agent_version: str | None = None, correlation_id: str | None = None, causation_id: str | None = None, sensitivity: str = "tenant", idempotency_key: str | None = None, schema_version: int = 1) -> dict[str, Any]: ...
  ```

  Persist the fields in `events`, return them from `list_events`, and include them in audit/event JSON. For non-agent legacy events, leave execution/version/causation/idempotency unset and use the generated event ID as the correlation fallback.
- [ ] Add `list_audit(..., execution_id=None, event_type=None, sensitivity=None, since=None)` filtering without permitting a caller to escape `tenant_id`; validate timestamps and bounded filter values.
- [ ] Add a small `agent_summary(tenant_id)` projection for snapshot metrics: total agents, published versions, active executions, pending approvals, completed executions, and latest execution timestamp.

### 1.4 Test the repository layer before service work

- [ ] In `tests/test_agent_platform.py`, test dataclass canonicalization/digests, strict contract rejection, schema version 12, reopen persistence, tenant isolation, agent/version lifecycle conflicts, execution/approval replay, exact action-digest binding, and event envelope fields.
- [ ] Run `python3 -m unittest tests.test_agent_platform -v` and the existing control-plane core/store tests before moving to Task 2.

---

## Task 2 — Add the bounded cognitive core and safe tools

### 2.1 Register the two first-release tools

- [ ] Create `src/control_plane/agent_tools.py` with a registration function:

  ```python
  def register_agent_tools(registry: ToolRegistry, store: ControlPlaneStore) -> None: ...
  ```

- [ ] Register `knowledge.search` as version `1.0.0`, risk `R0`, required scope `workspace:read`, no network egress, no side effects, and `evidence_status="verified_local"`. It searches only active, non-stale memory in the authenticated tenant and returns bounded snippets plus source/provenance IDs; it must never return another tenant’s memory.
- [ ] Register `ticket.update` as version `1.0.0`, risk `R2`, required scope `workspace:write`, `approval_policy="operator"`, `network_egress="none"`, `side_effects=("simulated_local",)`, and `evidence_status="simulated"`. Its handler returns a deterministic before/after representation and explicit `simulated=true`, `external_write=false`, and disclosure fields; it never calls a connector or writes to a live ticket system.
- [ ] Add a `ToolExecutionContext` in `src/control_plane/execution.py` and an opt-in context-aware handler flag to `ToolDefinition`. `ActionWorker` injects the authenticated tenant/principal/run/action context only for context-aware handlers, overwriting reserved internal fields rather than trusting user payload values. Existing one-argument handlers and tests remain valid.
- [ ] Add a restricted `run_simulated_once(...)` path or worker wrapper that can execute only a registered tool with `risk_tier="R2"`, `network_egress="none"`, and `side_effects=("simulated_local",)`, and only after the agent runtime has validated an exact pending approval. It must reject all external/physical/R3+ tools and must preserve unknown-outcome handling.

### 2.2 Implement simulator-first model selection

- [ ] Create `src/control_plane/model_gateway.py`:

  ```python
  class ModelGateway:
      def __init__(self, *, base_url: str = "", model: str = "", timeout_seconds: float = 3.0): ...
      def status(self) -> dict[str, Any]: ...
      def select(self, policy: dict[str, Any]) -> ModelSelection: ...
      def propose(self, *, task: str, context: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]: ...
  ```

- [ ] Default to `mode="deterministic_simulator"` with an explicit disclosure. If a base URL is configured, parse it and permit only HTTP loopback hosts; reject credentials, non-HTTP schemes, path traversal, non-loopback hosts, and oversized/invalid timeouts. Call Ollama only through standard-library `urllib`, with no hosted fallback.
- [ ] Treat Ollama output as an untrusted proposal. Do not execute model-selected tool IDs, code, URLs, or permissions without the planner whitelist and policy verifier. Record model name/mode/status and proposal digest, never hidden reasoning.
- [ ] Add `ZASI_OLLAMA_BASE_URL` and `ZASI_OLLAMA_MODEL` to `Settings.from_mapping()` with empty/disabled defaults. `model_status` must distinguish simulator, Ollama ready, Ollama unavailable, and disabled without claiming model capability beyond the observed adapter state.

### 2.3 Implement deterministic planning and verification

- [ ] Create `src/control_plane/agent_planner.py`:

  ```python
  class AgentPlanner:
      def __init__(self, registry: ToolRegistry, policy: PolicyEngine, gateway: ModelGateway): ...
      def plan(self, *, version: AgentVersionSpec, task: str, ticket_id: str, ticket_fields: dict[str, Any], scopes: FrozenSet[str]) -> TypedAgentPlan: ...
      def verify(self, *, plan: TypedAgentPlan, version: AgentVersionSpec, scopes: FrozenSet[str]) -> tuple[bool, tuple[str, ...]]: ...
  ```

- [ ] The deterministic safe demo plan has exactly two ordered steps: `knowledge.search` (`R0`, read-only) followed by `ticket.update` (`R2`, simulated local write). The ticket payload is bounded and canonicalized before its action digest is computed.
- [ ] Enforce agent-version allowed tools, registry version equality, exact declared risk, required scopes, budget limits, dependency order, preconditions, expected effects, and the prohibition on unregistered/disabled/unknown tools. Any violation returns structured reasons and no action is submitted.
- [ ] Expose sandbox planning as a dry run: it returns the typed plan, policy decisions, selected model, action digest, and disclosures without creating an execution, approval, action, or simulated write.

### 2.4 Test tools and model boundaries

- [ ] Test tenant-aware knowledge search, stale-memory exclusion, bounded results, deterministic ticket simulation, no external calls, unknown-tool rejection, underdeclared/overdeclared risk rejection, malformed model proposal rejection, loopback URL validation, simulator fallback, and restricted R2 worker behavior.
- [ ] Run the focused agent tests plus `tests.test_control_plane_broker` and `tests.test_action_worker` before wiring HTTP routes.

---

## Task 3 — Integrate the supervised agent runtime and API

### 3.1 Add the orchestration service

- [ ] Create `src/control_plane/agent_runtime.py` with an `AgentService` constructed by `create_app` and stored as `app.state.agent_service`:

  ```python
  class AgentService:
      def __init__(self, *, store: ControlPlaneStore, registry: ToolRegistry, policy: PolicyEngine, broker: ActionBroker, gateway: ModelGateway): ...
      def create_agent(self, *, tenant_id: str, principal_id: str, request: AgentCreateRequest) -> dict[str, Any]: ...
      def create_version(self, *, tenant_id: str, principal_id: str, agent_id: str, request: AgentVersionCreateRequest) -> dict[str, Any]: ...
      def publish_version(self, *, tenant_id: str, principal_id: str, agent_id: str, version_id: str) -> dict[str, Any]: ...
      def sandbox(self, *, tenant_id: str, principal_id: str, agent_id: str, request: AgentSandboxRequest, scopes: FrozenSet[str]) -> dict[str, Any]: ...
      def start_execution(self, *, tenant_id: str, principal_id: str, agent_id: str, request: AgentExecutionRequest, scopes: FrozenSet[str], idempotency_key: str) -> dict[str, Any]: ...
      def resolve_approval(self, *, tenant_id: str, principal_id: str, approval_id: str, decision: str, reason: str, scopes: FrozenSet[str]) -> dict[str, Any]: ...
      def get_execution(self, *, tenant_id: str, execution_id: str) -> dict[str, Any]: ...
      def model_status(self) -> dict[str, Any]: ...
  ```

- [ ] `create_agent` creates the definition and initial draft version transactionally (or rolls back both); a safe local demo definition may be created idempotently during lifespan, but it must not claim a hosted model or live tool. Publishing requires every allowed tool to be currently registered, enabled, and version-matched.
- [ ] `start_execution` performs this durable sequence:

  1. Validate idempotency and load the published version within the current tenant.
  2. Emit `agent.execution.requested` with execution/version/correlation/idempotency context.
  3. Select the local simulator or explicitly enabled loopback Ollama adapter and emit `model.selected`.
  4. Build and verify the typed plan; persist the plan/model projection and emit `agent.plan.proposed` and `policy.evaluated` events.
  5. Submit the `knowledge.search` step through the existing broker with a stable execution-specific idempotency key; record its run/evidence and emit `tool.requested`/`tool.completed` events.
  6. If the read-only step fails, is unknown, exceeds budget, or lacks evidence, mark the execution failed and do not create an approval.
  7. Submit `ticket.update` through the broker as a waiting-approval R2 action, compute the exact action digest from tenant/execution/version/tool/payload, create a pending `agent_approvals` record, mark the execution `awaiting_approval`, and emit `approval.requested`.
  8. Return the execution, read-only result/evidence, pending approval, full plan, and disclosures.

- [ ] `resolve_approval` must atomically validate tenant, pending state, expiry, published version, action run, tool/version, exact action digest, scope digest, and approver scope. Repeated identical approve/reject requests return the original resolution; conflicting decisions return 409. Approval emits `approval.approved` or `approval.rejected` before any simulator action.
- [ ] On approval, invoke only the restricted simulator-worker path, then persist simulated evidence/result and emit `tool.completed`, `execution.completed`, and audit records. On rejection, mark the execution rejected, emit `execution.rejected`, and prove no handler invocation occurred. A simulator failure is not silently retried as an external action.
- [ ] All agent events use the expanded event envelope: event ID, tenant ID, execution ID, agent version, actor, correlation ID, causation ID, sensitivity, idempotency key, and schema version. Use stable causation chaining from the preceding event ID.

### 3.2 Add authenticated HTTP routes

- [ ] Instantiate the gateway, register the agent tools before constructing `PolicyEngine`, construct `AgentService`, and preserve the existing `registry.system.status` registration and startup capability upsert.
- [ ] Add these routes to `backend/app.py`:

  ```text
  POST /api/v2/agents
  GET  /api/v2/agents
  GET  /api/v2/agents/{agent_id}
  POST /api/v2/agents/{agent_id}/versions
  POST /api/v2/agents/{agent_id}/versions/{version_id}/publish
  POST /api/v2/agents/{agent_id}/sandbox
  POST /api/v2/agents/{agent_id}/executions
  GET  /api/v2/agents/{agent_id}/executions
  GET  /api/v2/agent-executions/{execution_id}
  GET  /api/v2/agent-approvals
  POST /api/v2/agent-approvals/{approval_id}/approve
  POST /api/v2/agent-approvals/{approval_id}/reject
  GET  /api/v2/models/status
  ```

- [ ] Require existing scopes consistently: `workspace:read` for reads/sandbox visibility, `workspace:write` plus `plan:create` for definition/version/execution mutations, and `approval:write` for resolution. Use `_context_from_request`, `require_scope`, `_idempotency_key`, and existing error envelopes; never accept a tenant ID from the body or query as authority.
- [ ] Return 404 for cross-tenant resources without disclosing existence, 409 for digest/state/idempotency conflicts, 403 for policy/scope denial, and 503 only for explicitly unavailable optional adapters. Keep the approval body reason mandatory and bounded.
- [ ] Extend `/api/v2/snapshot` with `agents`, `active_executions`, `pending_agent_approvals`, and `model_status` while preserving existing fields. Extend `/api/v2/audit` filters for execution, event type, sensitivity, and time.
- [ ] Ensure generic `/api/v2/tools/call` and MCP still reject R2 direct calls; the agent route is the only path that can resolve the exact simulated R2 approval.

### 3.3 Test the end-to-end API flow

- [ ] Use `httpx.ASGITransport`/the existing test app factory to cover: create agent, create/publish version, sandbox, run, read-only result, pending approval, exact approve, simulated completion/evidence, reject path, execution timeline, model status, snapshot metrics, SSE replay, audit filters, duplicate run, duplicate approval, stale/mutated digest, missing scope, unknown tool, disabled capability, and cross-tenant access.
- [ ] Assert the handler invocation count is one on approval replay and zero on rejection; assert no connector/network call is possible; assert tenant B cannot see tenant A’s agent, execution, approval, memory, audit, or events.

---

## Task 4 — Build the operator console

### 4.1 Add typed data and routes

- [ ] Extend `web/static/cockpit.tsx` types with `Agent`, `AgentVersion`, `TypedPlan`, `AgentExecution`, `AgentApproval`, `ModelStatus`, and the expanded event envelope. Keep API calls behind the existing authenticated `api` helper.
- [ ] Add route/navigation entries:

  ```text
  /agents       Agent registry and create/publish controls
  /executions   Execution list and selected execution timeline
  /approvals    Pending approval queue with approve/reject forms
  /audit        Tenant-scoped audit stream with execution/type/sensitivity/time filters
  /models       Local simulator/Ollama status and disclosure
  ```

- [ ] Agent registry must show status, published version, model policy, budgets, allowed tools, risk/disclosure, and an explicit disabled/unavailable state. The create flow must create a draft; publish is a separate visible action.
- [ ] Execution view must show request, model mode, typed plan, policy decisions, read-only evidence, pending approval binding (tenant/execution/version/tool/action digest), final simulator evidence, and event causation/order.
- [ ] Approval view must show exact digest and risk, require a reason for both decisions, disable duplicate submission while pending, and show operator identity plus resolved timestamp. Rejection must clearly state that no write handler ran.
- [ ] Audit view must use the REST query projection and tenant session, not read SSE transport directly. Keep the existing `useEventFeed` reconnect/resync behavior and refresh agent projections when relevant event types arrive.
- [ ] Overview must add active executions, pending approvals, event volume, policy outcomes, and model status without removing existing readiness/capability disclosures. Do not label a feed `LIVE` unless the current authenticated SSE state is actually connected.

### 4.2 Style and structural verification

- [ ] Add responsive styles in `web/static/style.css` for compact tables/cards, timeline rows, approval controls, filter controls, and mobile layout; preserve the current theme and keyboard/accessibility patterns.
- [ ] Update `tests/test_components.js` to assert all new routes/components, exact API paths, simulator/no-egress disclosures, approval/rejection labels, and the absence of direct transport access from browser code.
- [ ] Run `npm run typecheck` and `node tests/test_components.js`; do not treat either as backend or deployment proof.

---

## Task 5 — Document operations and research-only boundaries

- [ ] Update `README.md` with the canonical name “AI Futures Project Superintelligence”, the local-first boundary, Python-only quickstart, the exact demo workflow, example curl requests, approval/rejection behavior, deterministic fallback, optional loopback Ollama configuration, and the fact that simulated evidence is not a real-world write.
- [ ] Update `docs/API_REFERENCE.md` with request/response shapes, scope requirements, idempotency behavior, exact approval binding, event envelope fields, audit filters, SSE snapshot/replay rules, and failure codes for the new endpoints.
- [ ] Update `docs/ARCHITECTURE.md` with the two trust zones, local adapter mapping, agent lifecycle, durable event path, model policy, evidence states, and explicit disabled/research-only RSI/neural-symbolic/distributed-topology boundaries.
- [ ] If the existing research/topology modules do not already expose sufficient status, add only typed status projections for:
  `recursive_self_improvement`, `neural_symbolic_verification`, `architecture_search`, `kernel_generation`, `self_deployment`, and `distributed_memory_topology`. Each must report `research_only` or `disabled`, include a disclosure and evidence state, and have no executable mutation hook.
- [ ] Add Makefile targets without changing existing install/build behavior:

  ```make
  test-agent-platform:
  	$(PYTHON) -m unittest tests.test_agent_platform

  check: test-agent-platform test-control-plane
  ```

  Add `check` and `test-agent-platform` to `.PHONY` and help text. `make check` must use Python-only tests and must not invoke npm, Docker, network access, or a live service port.
- [ ] Add a clean-checkout verification note distinguishing local tests, frontend typecheck, optional PostgreSQL/Redis/Ollama adapter checks, hosted CI, and deployed runtime evidence. Do not claim the current staging service proves the new feature until it is rebuilt and exercised.

---

## Task 6 — Independent verification and release handoff

- [ ] Run the focused suite first:

  ```bash
  python3 -m unittest tests.test_agent_platform -v
  python3 -m unittest tests.test_control_plane_core tests.test_control_plane_broker tests.test_action_worker tests.test_control_plane_api -v
  ```

- [ ] Run the Python-only acceptance gate from a clean checkout or isolated temporary copy:

  ```bash
  make check
  ```

  If a host-owned service collides with a legacy hard-coded test port, isolate/skip that unrelated legacy test with evidence rather than reporting the whole implementation green.
- [ ] Run frontend checks:

  ```bash
  node tests/test_components.js
  npm run typecheck
  ```

- [ ] Exercise the API workflow against an in-process app with a temporary SQLite database and verify the persisted records after closing/reopening the store. Validate event replay after a consumer restart and duplicate approval/run requests.
- [ ] Run migration checks against an existing schema-11 SQLite fixture and, when a PostgreSQL test service is available, the matching PostgreSQL repository tests. Keep the PostgreSQL check clearly separate from the Python-only gate if no database is available.
- [ ] Review the final diff with `git status --short`, `git diff --check`, and targeted `git diff` inspection. Confirm only the intended agent implementation, documentation, and tests are included; leave `docs/javis` user changes untouched.
- [ ] Use the verification-before-completion skill before claiming completion. Report exact commands/results and separate local evidence from unrun hosted CI, deployment, signing, or release evidence.

## Acceptance Matrix

| Design requirement | Implementation evidence |
| --- | --- |
| Define and version an agent | Agent tables, strict contracts, create/version/publish routes, registry UI |
| Sandbox test | Deterministic typed planner/verifier and dry-run route with no durable execution/action |
| Read-only knowledge result | Tenant-aware `knowledge.search`, R0 policy, local provenance evidence |
| Approval-gated write | R2 `ticket.update` simulator, exact digest binding, pending/approve/reject routes |
| Durable/replay-safe events | Schema-12 event envelope, SQLite/PostgreSQL persistence, outbox/SSE replay tests |
| Tenant isolation | Repository checks and API tests for agents, memory, executions, approvals, audit, and events |
| Evidence and audit | Existing evidence/audit projections enriched with agent execution context |
| Local model policy | Simulator default, loopback-only Ollama adapter, no hosted fallback |
| Operator control | Agent, execution, approval, audit, and model console surfaces |
| Research blueprint | Typed disabled/research-only statuses; no self-modification or deployment path |
| Free-tier verification | Python-only `make check` plus documented optional frontend/database checks |

## Plan Self-Review

- [ ] The plan adapts the existing governed control plane rather than introducing a parallel runtime.
- [ ] Each design acceptance criterion has a concrete file, route, repository method, test, or UI evidence path.
- [ ] SQLite and PostgreSQL migration behavior is specified.
- [ ] Approval exactness, idempotency, tenant isolation, replay, fail-closed behavior, and no-egress simulation are explicit.
- [ ] Research-only capabilities are surfaced without being activated.
- [ ] The plan preserves unrelated user work and does not authorize commit, push, deployment, or release publication.
