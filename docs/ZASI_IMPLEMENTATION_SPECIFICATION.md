# ZASI Implementation Specification

Status: implemented reference slice; conditional read-only/assistive
Revision: 2026-09-02
Authority: companion specification to ZASI_FULL_ARCHITECTURE.md
Scope: implementation, security hardening, verification, and release gates
Change posture: normative contract with source, test, and release evidence tracked in this revision

Current release boundary: the repository implements local SQLite and
authenticated PostgreSQL/Redis reference paths, plus a bounded durable
Goal/Task scheduler, task-run history, project-scoped memory router, and
source-backed local briefing aggregator. It is not a production-ready managed
deployment or an enabled external productivity connector service, hardware
controller, formal-proof service, or ASI/AGI runtime. Any capability outside
the verified reference slice remains disabled, simulated, research_only, or
unavailable.

## 1. Purpose and authority

This document converts the target architecture into a finite, testable implementation contract. It is the normative source for what must be built, what must remain disabled, and what evidence is required before a capability may be described as available.

The companion architecture document is the product and system vision. This document is the engineering contract. When the two documents disagree on implementation behavior, this specification wins for runtime behavior, security boundaries, API semantics, persistence, testing, and release decisions. Product claims that are not backed by the evidence rules in this document are non-authoritative.

The implementation is a bounded, governed Chief-of-Staff control plane with a J.A.R.V.I.S. cockpit. It is not an autonomous general intelligence claim, a physical autonomy claim, a cryptographic proof system claim, or a promise that a catalog entry is implemented merely because its name exists.

Normative terms:

- MUST and MUST NOT are release-blocking requirements.
- SHOULD and SHOULD NOT are defaults that require a documented exception.
- MAY is optional behavior with no implied capability.
- A claim is valid only when the implementation, test, and runtime evidence requirements in this document are satisfied.

## 2. Implementation decision

The first governed reference slice is:

1. Authenticated operator session.
2. Tenant and device scope resolution.
3. Observe and Assist modes.
4. Typed intent creation from text or voice input.
5. Read-only context retrieval.
6. Deterministic policy evaluation.
7. Read-only plan generation with explainable steps.
8. Evidence-backed result rendering.
9. Durable event stream with cursor, replay, and resync.
10. Explicit transition to Do This only after an approval policy permits the requested risk tier.
11. A bounded durable Goal/Task DAG with tenant scope, dependency gating, worker leases, idempotency, atomic completion events, schedule polling, retry/dead-letter state, and task-run history.
12. Project-aware memory retrieval with provenance/freshness disclosure and a source-backed briefing aggregator; unavailable external connectors remain explicit.

The first slice MUST NOT contain autonomous external writes, credential mutation, arbitrary code execution, runtime hot swap, live physical actuation, or a claim that all catalogued subsystems are active.

The 176-subsystem catalog is a registry and capability inventory. It is not an execution grant. Every entry MUST expose separate fields for implementation state, runtime state, evidence state, and risk policy:

~~~json
{
  "subsystem_id": "example.subsystem",
  "display_name": "Example Subsystem",
  "implementation_state": "implemented|partial|stub|disabled|research_only",
  "runtime_state": "offline|ready|degraded|failed|simulated",
  "evidence_state": "unverified|locally_verified|staging_verified|production_verified",
  "allowed_risk_tiers": ["R0", "R1"],
  "last_verified_at": "2026-09-01T00:00:00Z",
  "evidence_refs": ["ev_01..."],
  "operator_disclosure": "Read-only simulation; no external side effect."
}
~~~

No UI badge, startup log, telemetry field, benchmark, or generated report may collapse these fields into a single “online”, “verified”, or “operational” claim.

## 3. Scope and non-goals

### 3.1 In scope

- A single authoritative API and application lifecycle.
- Local-first operation with a portable production path.
- Identity, tenant isolation, device registration, session management, and capability binding.
- Intent, plan, approval, action, evidence, audit, and event persistence.
- Safe read-only observation and assistive planning.
- Explicit risk-tier enforcement for all mutations.
- Durable event delivery with reconnect and authoritative resync.
- Browser and Electron cockpit hardening.
- Safe connector and MCP brokering.
- Simulation, research, and hardware adapters with truthful disclosure.
- CI, container, installer, migration, backup, and release evidence.
- Compatibility behavior for existing routes during migration.

### 3.2 Out of scope for this specification

- Training a new foundation model.
- A claim of artificial general intelligence or superintelligence.
- Unbounded recursive self-improvement.
- Production deployment of physical actuators.
- Production cryptographic proof generation unless an independently reviewed implementation is supplied.
- Replacement of domain-specific compliance, safety, medical, financial, or industrial controls.
- Automatic migration of arbitrary user data without backup and explicit migration evidence.

## 4. Source-grounded baseline

### 4.1 Entry points and ownership

There must be one authoritative runtime entry point after Phase P0. The following baseline was observed and must be treated as migration risk:

| Existing surface | Current behavior | Required disposition |
|---|---|---|
| backend/server.py | Raw ThreadingTCPServer API, WebSocket handling, background ticks, telemetry, webhooks, chat, MCP, mutation, RSI routes | Migrate behind the authoritative application; retain only an explicit compatibility adapter |
| src/api_server.py | Separate legacy HTTP server, generated dashboard HTML, hardcoded token default, binds all interfaces | Quarantine; no production startup path |
| main.py | Starts the legacy server on the same nominal port | Replace with one lifecycle command and readiness handshake |
| Electron main process | Spawns Python and loads localhost after a fixed delay | Use process supervision, readiness polling, origin restrictions, and clean shutdown |
| web/static/app.tsx + web/static/cockpit.tsx + web/static/app.jsx | React 19 and React Router v7 cockpit with a strict TypeScript root entrypoint and fully checked TypeScript cockpit source; historical JSX path is a compatibility re-export | Keep the Vite bundle authoritative and retain the compatibility export while adding typed source coverage |
| web/static/app.js | Legacy dashboard with direct HTML insertion and GET mutation calls | Quarantine and delete only after compatibility tests and operator sign-off |
| CLI and research modules | Directly expose simulation, self-evolution, sandbox, and hardware-shaped APIs | Convert to adapters with explicit disabled or simulation profiles |

### 4.2 Historical baseline evidence

The following checks were run against the repository baseline before this specification was written:

- node tests/test_components.js passed, with structural React and Router assertions.
- python3 -m unittest tests.test_all_subsystems -q passed with 165 tests.
- An isolated copy of tests.test_api first failed because the JARVIS test timed out while the server was not HTTP-ready; a second run passed 7 of 7 tests. The server also emitted BrokenPipeError and ResourceWarning output.
- The API test readiness helper waits for a TCP connection, not a successful authenticated HTTP readiness response.
- Documentation, startup logs, and installer output use inconsistent subsystem totals, including 176 and 172.

These results establish a baseline only. They do not prove authorization, tenant isolation, formal verification, sandbox isolation, real hardware control, cryptographic soundness, or production readiness.

### 4.3 Current implementation evidence boundary

The current tree now contains the first governed vertical slice described in
Section 2. `backend.app` is the sole authoritative ASGI owner; it initializes
the durable `ControlPlaneStore`, registers code-owned tool manifests, and
serves the bundled cockpit. The repository schema is version 9. SQLite and
the authenticated PostgreSQL adapter are implemented; Redis supplies shared
rate-limit coordination and readiness. Staging and production settings still
require explicit service URLs, an external secret provider, and a managed
backup policy.

Implemented local controls include fail-closed bootstrap authentication,
hashed session credentials, tenant-scoped repositories, device challenge
storage with pairing idempotency, typed intents/plans, deterministic risk policy, exact-digest
approvals, brokered trusted handlers, immutable evidence, audit/event/outbox
transactions, tenant-cursored SSE replay/resync, durable rate limits, bounded
artifact quarantine, dual-stack egress validation helpers, CSP-safe bundled
frontend delivery, supervised Electron startup, and a bounded durable Goal/Task
DAG with dependency gating, worker leases, idempotent task creation, and atomic
completion events. The one enabled runtime
tool is the local system-status observation; its evidence is `verified` by a
named local readiness procedure and is not a claim about the historical
catalog.

This section is an implementation status statement, not a release certificate.
The exact commands and observed results for the current checkout are recorded
in Section 26. Hosted CI, staging, deployment, signing, and independent
verification remain separate evidence classes.

### 4.4 Baseline claims that are not implementation evidence

The following classes of existing output MUST be treated as non-authoritative until replaced:

- Fixed startup messages stating that all subsystems are calibrated or online.
- Telemetry values that are generated from constants or simulation objects.
- Verifier responses that assert treaty compliance, global accounting, or transparency without checking an executable policy model.
- “STARK”, “SNARK”, or “cryptographically sound” labels backed only by hash commitments or fixed proof bytes.
- CAD geometry, mass, stress, and verification fields accepted from caller input or calculated by nominal formulas without a parser and solver evidence chain.
- Git self-evolution records that return a hash-like value without a real signed commit or artifact.
- Voice biometrics results based on caller-supplied verification flags or confidence values.
- Tests that assert fixed values or object shape without testing authorization, side effects, failure behavior, or persistence.

## 5. Critical review and disposition

The findings below are source-grounded design risks. Severity is based on the consequence of the current behavior if the service is reachable by an untrusted or partially trusted client.

| ID | Severity | Finding and evidence | Impact | Required disposition |
|---|---|---|---|---|
| F-001 | Critical | API authentication is disabled when the environment key is empty; WebSocket upgrade handling runs before the API auth check; CORS defaults to wildcard | Unauthenticated access and cross-origin control-plane exposure | Fail closed at configuration load; authenticate WebSocket handshake; explicit origin allowlist |
| F-002 | Critical | GET routes can tick daemon state, execute a subsystem, and mutate or trigger RSI behavior | CSRF, replay, crawler, and cache-triggered side effects | Mutations require POST or command submission; remove privileged GET routes or return 410 |
| F-003 | Critical | Dynamic compilation uses exec with a deny-list; sandbox fallback runs bash on the host while reporting restricted isolation | Arbitrary code execution and false isolation claim | Disable in production; separate research runner; fail closed when isolation is unavailable |
| F-004 | Critical | Legacy server has a hardcoded token default, binds all interfaces, and interpolates runtime values into HTML | Secret exposure, remote reachability, and injection risk | Remove hardcoded secrets; bind loopback by default; eliminate legacy server path |
| F-005 | High | Legacy UI uses innerHTML with logs and catalog fields and inline onclick handlers | DOM XSS and unsafe command invocation | Use text nodes, escaped templates, event delegation, CSP, and typed route handlers |
| F-006 | High | Some CDN scripts have integrity attributes, while router, Babel, and other runtime scripts do not | Supply-chain tampering and non-reproducible UI | Bundle dependencies, lock versions, or require SRI with a verified build manifest |
| F-007 | Critical | Telemetry, formal, CAD, and subsystem responses contain fixed or caller-controlled capability claims | Operators and downstream automation can trust false evidence | Add evidence provenance, freshness, capability state, and explicit simulation labels |
| F-008 | High | Webhook validation checks only resolved IPv4 addresses and requests have no durable queue or redirect policy | SSRF, DNS rebinding, private-network access, and lost deliveries | Central egress broker with dual-stack resolution, redirect denial, bounded payloads, and durable retry |
| F-009 | High | WebSocket clients, rate limits, audit records, and event history are process-local | Restart loss, inconsistent replicas, weak forensics, and reconnect gaps | Persist sessions, audit, cursors, and event/outbox state |
| F-010 | Critical | RSI evaluation approves broad speedup claims and hot swap changes runtime version directly; self-evolution records may be hash-only | Unreviewed code or runtime replacement | Disable; require signed artifact, independent evaluation, approval, staged rollout, and rollback |
| F-011 | High | Voice biometrics trusts caller-provided verification and confidence instead of validating an enrollment and challenge | Voice spoofing can reach command routing | Treat voice as an input signal; require server-side authentication and step-up approval |
| F-012 | High | MCP tools are dispatched directly from the HTTP handler without a central session, capability, approval, or audit broker | Tool calls can bypass governance | Route discovery and calls through the same policy broker as every connector |
| F-013 | High | CI workflows grant write permissions broadly in selected jobs and release/publish behavior is not uniformly least-privilege | Workflow compromise can publish or modify repository state | Default to contents read; grant exact job-scoped permissions only with protected environments |
| F-014 | Medium | Installer overwrites configuration, removes build artifacts, and force-installs packages; container runs as root | Data loss, supply-chain drift, and excessive runtime privilege | Backup before migration; no destructive cleanup by default; pinned lockfile; non-root image |
| F-015 | High | OpenAPI and narrative docs describe capabilities beyond the actual routes and evidence model | Contract drift and unsafe client assumptions | Generate API schema from authoritative contracts and test docs against runtime |
| F-016 | High | API readiness is inferred from a TCP connection, producing a nondeterministic first-run failure | False green or flaky release gate | Require authenticated HTTP readiness with dependency status and bounded startup timeout |

### 5.1 Critical review conclusion

The current repository can serve as a prototype cockpit and a deterministic simulation harness. It is not yet a safe production control plane. The first release must be a governed read-only/assistive slice with simulated and research capabilities visibly separated from verified runtime capabilities.

The following are release blockers, not backlog preferences:

1. Fail-closed authentication and tenant scope.
2. Removal or isolation of privileged GET behavior.
3. No host-shell fallback for sandboxed execution.
4. No direct runtime hot swap or unreviewed self-modification.
5. No unverified capability labels in operator-facing evidence.
6. Durable audit and event replay.
7. Real readiness and security regression tests.

## 6. Hardening gates

### H0: source and runtime ownership

Exit evidence:

- One documented application entry point.
- One port ownership record.
- A readiness endpoint that identifies build, schema, process, and dependency state.
- Legacy server and compatibility routes are not imported by the production process.
- Electron, Docker, CLI, and test commands all select the same authoritative server.

Failure behavior:

- Startup stops if two server owners are detected.
- Startup stops if the configured port is already owned by an unexpected process.

### H1: identity, authentication, authorization

Requirements:

- Configuration MUST fail closed when production authentication material is absent.
- API keys, bearer tokens, and session cookies MUST be accepted only through a dedicated identity middleware.
- Tokens MUST be stored hashed or managed by an external identity provider; raw tokens MUST NOT be logged.
- Every request MUST resolve principal, tenant, device, session, and capability set before dispatch.
- WebSocket handshake, SSE connection, MCP call, file download, and connector call MUST use the same authorization path.
- Authorization MUST be checked server-side at the resource and action boundary, not inferred from UI mode or model output.
- Tenant identifiers supplied in path or body MUST be compared against authenticated scope and never override it.
- Failed authentication and authorization MUST use an indistinguishable error shape where useful and MUST be audited without secrets.

Exit evidence:

- Negative tests for missing, expired, wrong-tenant, downgraded-scope, replayed, and revoked credentials.
- WebSocket and SSE tests proving that unauthenticated clients receive no data.
- A tenant-crossing test proving both read and write isolation.

### H2: request, state, and side-effect safety

Requirements:

- GET, HEAD, and OPTIONS MUST be side-effect free.
- State-changing operations MUST use POST, PUT, PATCH, or DELETE and require an idempotency key where retry can duplicate work.
- All request bodies MUST have bounded size, schema validation, content-type validation, and deadline enforcement.
- JSON parsing errors MUST return a typed 400 response; silently treating malformed input as an empty object is prohibited.
- Every mutation MUST create an audit record and a durable event in the same transaction as the state transition.
- External calls MUST be represented as an action with status, timeout, retry policy, and result evidence.
- A client disconnect MUST not silently convert a running action into an unknown untracked action.

Exit evidence:

- Method safety tests for every route.
- Idempotency replay tests.
- Transaction rollback tests showing no partial state, event, or audit record.

### H3: execution and sandbox safety

Requirements:

- Production application code MUST NOT execute model-generated Python, JavaScript, shell, or SQL text.
- No deny-list, restricted builtins dictionary, or subprocess flag may be described as a security boundary.
- Research compilation MUST run in a separately deployed worker with an OS-level sandbox, read-only input, no default network, resource quotas, and a kill deadline.
- If the required sandbox is unavailable, the job MUST be rejected as unavailable. It MUST NOT fall back to host bash.
- Tool implementations MUST be registered by stable identifier and typed input/output schema; arbitrary callables MUST NOT be accepted from requests.
- Filesystem paths MUST resolve beneath an approved immutable workspace using a realpath check and mount policy.
- Connector egress MUST go through an allowlisted broker.

Exit evidence:

- Adversarial tests for shell metacharacters, import escape, path traversal, symlink escape, fork/resource exhaustion, and network access.
- A negative test showing the service rejects compilation when the sandbox capability is absent.
- A process-level review proving no production route reaches exec, eval, or host shell.

### H4: evidence and truthfulness

Requirements:

- Every capability result MUST include source, adapter, timestamp, freshness, input reference, output reference, verification status, and disclosure.
- “Verified” MUST refer to a named verification procedure and evidence artifact, not a model confidence score.
- The valid status set is verified, rejected, unknown, unavailable, simulated, and research_only.
- Fixed demo data MUST be marked simulated or fixture.
- Evidence MUST be immutable after creation; corrections append a superseding record.
- Operator UI MUST display unavailable and simulated states prominently.
- Claims about cryptography, formal proof, physical hardware, energy, or external competitors MUST be suppressed unless the corresponding evidence adapter is enabled and independently verified.

Exit evidence:

- Golden tests for evidence serialization and disclosure.
- UI tests that render simulated, stale, unknown, and failed results distinctly.
- A claim-to-evidence audit for every operator-facing status field.

### H5: persistence, audit, and recovery

Requirements:

- SQLite is the supported local profile database; PostgreSQL is the supported multi-process production profile.
- In-memory audit logs, rate-limit counters, sessions, cursors, and approvals MUST NOT be the authoritative store.
- State mutation, audit record, event, and outbox record MUST commit atomically.
- Event identifiers MUST be globally unique within a tenant and idempotent under retry.
- Recovery MUST replay pending outbox records without duplicating externally visible actions.
- Backups MUST be encrypted where required, versioned, tested, and restorable.

Exit evidence:

- Kill and restart tests during each state transition phase.
- Backup restore test on a clean database.
- Event replay and duplicate-delivery tests.
- Retention and deletion tests that preserve legally required audit records.

### H6: browser, Electron, and supply chain

Requirements:

- Browser dependencies MUST be bundled and lockfile-pinned.
- External scripts are prohibited in production; any temporary external script MUST have SRI, a version pin, an allowlisted origin, and a documented expiry.
- CSP MUST be enforced as a response header, with no unsafe-eval and no broad unsafe-inline in production.
- Browser rendering MUST avoid innerHTML for untrusted data.
- Electron MUST keep context isolation and node integration disabled, restrict navigation to the approved origin, validate the child process readiness endpoint, and shut down cleanly.
- Container images MUST run as non-root, use a read-only root filesystem where feasible, drop unnecessary capabilities, and define resource limits.

Exit evidence:

- Dependency lock and vulnerability scan.
- CSP and DOM XSS regression tests.
- Electron navigation and IPC boundary tests.
- Container inspection showing non-root execution and no secret baked into image layers.

### H7: network and webhook egress

Requirements:

- Egress requests MUST use an explicit destination policy.
- URL validation MUST resolve and check both IPv4 and IPv6 addresses, reject loopback, link-local, multicast, documentation, private, and cloud metadata ranges, and re-check the connected peer.
- DNS rebinding MUST be mitigated by resolving and connecting under one policy-controlled operation.
- Redirects MUST be rejected by default; each allowed redirect MUST be revalidated.
- Requests MUST have method, content-type, payload, response-size, connection, and total-time limits.
- Authorization headers, cookies, tokens, and sensitive payload fields MUST be redacted before logging.
- Webhook delivery MUST use a durable queue, bounded retries, idempotency key, and dead-letter state.

Exit evidence:

- IPv4 and IPv6 SSRF tests.
- Redirect and DNS rebinding tests.
- Retry, timeout, duplicate, and dead-letter tests.

### H8: release and operational truth

Requirements:

- A release may be called production-ready only after all mandatory gates pass.
- Local test success, a generated brief, a Docker build, or a green static check is not deployment evidence.
- Release evidence MUST identify commit SHA, artifact digest, schema version, test commands, environment profile, signer, deployment target, and observed readiness response.
- Any unknown or skipped mandatory gate yields NO-GO or CONDITIONAL, never GO.

## 7. Target stack and dependency policy

The target stack is deliberately conservative and portable:

| Layer | Required implementation |
|---|---|
| HTTP/API | One ASGI application with typed request and response contracts |
| Schema | Pydantic models or equivalent runtime validation generated into OpenAPI |
| Persistence | SQLAlchemy or equivalent repository layer with migrations; SQLite local, PostgreSQL production |
| Events | Durable event store plus outbox; SSE first, WebSocket only where bidirectional behavior is required |
| Queue | Durable worker queue for external actions and long-running jobs |
| UI | React 19 / React Router 7 bundle built by Vite from a strict TypeScript entrypoint; no production CDN runtime |
| Desktop | Electron shell with a supervised child process and readiness handshake |
| Adapters | Explicit interfaces for model, MCP, web, CAD, vision, voice, hardware, and research workers |
| Observability | Structured logs, metrics, traces, correlation IDs, and redaction middleware |
| Packaging | Reproducible lockfile, SBOM, signed artifacts, non-root container |

Exact versions MUST be pinned in the repository lockfiles and upgraded through dependency review. The specification does not treat an unpinned version range as a security control.

### 7.1 Configuration contract

Configuration MUST be loaded once into a typed immutable settings object. Production startup MUST reject:

- empty authentication secret;
- wildcard CORS;
- public bind address without an explicit deployment profile;
- missing database encryption or backup policy where required;
- enabled connector with no egress policy;
- enabled hardware or research worker without its required isolation capability;
- default development credentials;
- debug exception output;
- unbounded body, queue, request, or worker timeouts.

Configuration diagnostics MUST identify the failed setting name and remediation class without printing its value.

## 8. Repository layout

The target layout is:

~~~text
backend/
  app.py                  authoritative ASGI application
  compatibility.py        explicitly versioned legacy route adapter
  readiness.py             dependency-aware readiness probes
src/
  control_plane/
    contracts/             request, response, event, and error models
    identity/              principals, tenants, sessions, capabilities
    orchestration/         intent, plan, run, sequence state machines
    governance/            policy, approvals, risk, invariants
    execution/             typed action broker and worker interfaces
    events/                append, cursor, replay, resync, outbox
    storage/               repositories, transactions, migrations
    evidence/              provenance, freshness, disclosure
    briefing/              source-backed morning brief generation
    connectors/            MCP, web, webhook, model, device adapters
    multimodal/            voice, vision, CAD, device link
    config/                profile validation and secret references
  legacy/                  quarantined prototype adapters
web/
  src/
    app/
    components/
    features/
    transport/
    security/
    state/
    test/
electron/
  main.ts
migrations/
tests/
  contract/
  security/
  persistence/
  recovery/
  integration/
  reference/
  performance/
deploy/
  profiles/
  docker/
  systemd/
  manifests/
~~~

No module in src/legacy may be imported by the authoritative application unless it is wrapped by a typed adapter and listed in the capability registry.

## 9. Canonical domain contracts

All identifiers are opaque strings generated by the server. Clients MUST NOT select tenant, principal, risk, approval, or evidence identifiers for authorization purposes.

### 9.1 Common envelope

~~~json
{
  "request_id": "req_01H...",
  "trace_id": "trc_01H...",
  "tenant_id": "ten_01H...",
  "principal_id": "usr_01H...",
  "device_id": "dev_01H...",
  "created_at": "2026-09-01T00:00:00Z",
  "schema_version": 1
}
~~~

Requirements:

- Timestamps MUST be UTC and server-issued for authoritative records.
- IDs MUST be non-guessable and bounded in length.
- schema_version MUST be checked and migrated explicitly.
- Correlation IDs MUST propagate into logs, actions, events, evidence, and connector requests.
- The API/event envelope `schema_version` is independent from the repository
  migration schema. The current API/event envelope is version 1; the current
  local SQLite/PostgreSQL repository schema is version 9.

### 9.2 Intent

~~~json
{
  "intent_id": "int_01H...",
  "source": {
    "kind": "text|voice|vision|api|sequence",
    "content_ref": "art_01H...",
    "transcript": "summarized operator request",
    "input_disclosure": "Voice authentication is not established by this field."
  },
  "goal": {
    "verb": "observe|explain|draft|execute|connect|verify",
    "object": "system.status",
    "parameters": {}
  },
  "requested_mode": "observe|assist|do_this|advanced|engineering|humanoid|mobile_link",
  "requested_risk_tier": "R0",
  "scope": {
    "tenant_id": "server-resolved",
    "workspace_id": "wsp_01H..."
  }
}
~~~

The intent is untrusted input. It is never an authorization decision and never directly invokes a tool.

### 9.3 Plan

~~~json
{
  "plan_id": "pln_01H...",
  "intent_id": "int_01H...",
  "status": "draft|awaiting_approval|approved|rejected|expired|executing|completed|failed",
  "steps": [
    {
      "step_id": "stp_01H...",
      "kind": "read|compute|approval|external_write|device_action",
      "tool_id": "registry.tool.example",
      "input_ref": "art_01H...",
      "risk_tier": "R0",
      "side_effect": "none|local|external|physical",
      "preconditions": ["policy.condition.id"],
      "rollback": "not_applicable|compensating_action_ref|manual"
    }
  ],
  "explanation_ref": "art_01H...",
  "expires_at": "2026-09-01T00:10:00Z"
}
~~~

Plans are immutable after approval. A changed input, tool version, scope, or step set requires a new plan and a new approval.

### 9.4 Action and run

~~~json
{
  "run_id": "run_01H...",
  "plan_id": "pln_01H...",
  "status": "created|queued|running|waiting_approval|succeeded|failed|cancel_requested|cancelled|unknown",
  "idempotency_key": "client-or-server-generated-unique-key",
  "started_at": "2026-09-01T00:00:00Z",
  "finished_at": null,
  "result_evidence_refs": [],
  "error_code": null
}
~~~

unknown is a first-class state. It MUST be used when the process loses certainty about an external side effect; the system MUST reconcile before retrying.

### 9.5 Approval

~~~json
{
  "approval_id": "apr_01H...",
  "plan_id": "pln_01H...",
  "approver_principal_id": "usr_01H...",
  "required_capability": "capability.example.write",
  "risk_tier": "R2",
  "decision": "pending|approved|rejected|expired|revoked",
  "reason": "operator supplied reason",
  "approved_at": null,
  "expires_at": "2026-09-01T00:10:00Z"
}
~~~

Approval MUST bind to the exact plan digest, tenant, principal scope, tool version, and expiration. It MUST NOT be reusable for another plan.

### 9.6 Evidence

~~~json
{
  "evidence_id": "ev_01H...",
  "kind": "observation|calculation|test|approval|external_response|simulation|research_output",
  "status": "verified|rejected|unknown|unavailable|simulated|research_only",
  "source": {
    "adapter_id": "adapter.system.telemetry",
    "adapter_version": "1.0.0",
    "origin": "local|staging|production|fixture",
    "input_digest": "sha256:..."
  },
  "observed_at": "2026-09-01T00:00:00Z",
  "fresh_until": "2026-09-01T00:01:00Z",
  "artifact_ref": "art_01H...",
  "method_ref": "procedure.system.telemetry.v1",
  "disclosure": "Exact limitation and simulation status.",
  "supersedes": null
}
~~~

### 9.7 Event envelope

~~~json
{
  "event_id": "evt_01H...",
  "tenant_id": "ten_01H...",
  "sequence": 1042,
  "type": "run.updated",
  "occurred_at": "2026-09-01T00:00:00Z",
  "actor": {
    "kind": "principal|system|worker",
    "id": "usr_01H..."
  },
  "aggregate": {
    "kind": "run",
    "id": "run_01H..."
  },
  "payload": {},
  "visibility": "tenant|workspace|principal",
  "schema_version": 1
}
~~~

Events MUST be append-only, scope-filtered, ordered by a tenant cursor, and safe to deliver more than once. Consumers MUST deduplicate by event_id.

## 10. State machines

### 10.1 Session

~~~text
new -> authenticated -> active -> degraded -> revoked
                         |             |
                         +-> expired <-+
~~~

Transitions:

- new to authenticated requires valid credential and device policy.
- authenticated to active requires readiness and tenant scope.
- active to degraded occurs on transport or dependency degradation; read-only behavior may continue.
- active to revoked occurs on explicit revocation or policy violation.
- degraded to active requires authoritative resync, not merely a successful reconnect.

### 10.2 Run

~~~text
created -> queued -> running -> succeeded
              |        |          ^
              |        +-> failed |
              |        +-> unknown+
              +-> waiting_approval
waiting_approval -> queued | failed
running -> cancel_requested -> cancelled | unknown
~~~

Illegal transitions MUST return a typed conflict error and create an audit event.

### 10.3 Sequence

~~~text
draft -> validated -> awaiting_approval -> approved -> executing
   ^          |             |                 |          |
   +----------+             +-> rejected     +-> expired +-> completed
                                                           +-> failed
~~~

The sequence executor MUST snapshot the validated step list and tool versions. Editing a sequence after approval creates a new revision and invalidates the previous approval.

## 11. Governance and capability model

### 11.1 Risk tiers

| Tier | Meaning | Default policy |
|---|---|---|
| R0 | Read-only observation and explanation | May run with authenticated session and tenant scope |
| R1 | Drafts, local calculations, and simulation | May run with explicit simulation disclosure |
| R2 | Local state or artifact writes | Requires capability and audit; approval by default |
| R3 | External service write or message | Explicit approval, idempotency, egress policy, and durable action |
| R4 | Deployment, credential, code, or runtime change | Disabled by default; two-person approval and signed artifact required |
| R5 | Physical actuation or high-impact action | Disabled in the reference platform; separate certified system required |

A model, voice confidence, UI mode, or tool description MUST NOT raise a request's risk tier or grant a capability.

### 11.2 Capability manifest

Each tool and subsystem MUST register:

~~~json
{
  "capability_id": "capability.example.read",
  "tool_id": "registry.tool.example",
  "version": "1.0.0",
  "risk_tier": "R0",
  "input_schema_ref": "schema.example.input.v1",
  "output_schema_ref": "schema.example.output.v1",
  "required_scopes": ["workspace:read"],
  "side_effects": [],
  "network_egress": "none",
  "data_classes": ["telemetry"],
  "timeout_ms": 2000,
  "retry_policy": "none",
  "approval_policy": "never|operator|two_person|disabled",
  "evidence_method_ref": "procedure.example.v1",
  "availability": "enabled|simulation|research_only|disabled"
}
~~~

Registry registration MUST be code-reviewed and schema-tested. Requests select a registry identifier, never a Python import path or callable name.

### 11.3 Policy evaluation

Policy evaluation returns a decision object:

~~~json
{
  "decision": "allow|allow_with_approval|deny|unknown",
  "risk_tier": "R0",
  "reasons": ["scope.valid", "tool.enabled", "fresh_evidence.required"],
  "required_approvals": 0,
  "policy_version": "policy.v1",
  "evaluated_at": "2026-09-01T00:00:00Z"
}
~~~

Unknown policy results MUST fail closed for side effects. A proof or invariant adapter may support the decision but cannot replace authorization, approval, or audit.

### 11.4 Formal and cryptographic boundaries

The reference implementation may expose a typed invariant checker and a research proof adapter. It MUST distinguish:

- formal_model_checked: a named model was checked by a named solver;
- proof_artifact_present: an artifact exists and has a digest;
- proof_verified: the artifact was verified by an independent verifier;
- cryptographic_assurance: only permitted after algorithm, implementation, parameter, and review evidence exists.

A hash commitment, fixed byte string, caller-provided flag, or local arithmetic check MUST NOT be labelled as a STARK, SNARK, kernel proof, or cryptographically sound proof.

## 12. Canonical API v2

The API version is a contract, not a URL decoration. Every endpoint MUST publish request and response schemas, auth scope, risk tier, idempotency behavior, audit event, and error behavior.

### 12.1 Common errors

~~~json
{
  "error": {
    "code": "AUTH_REQUIRED",
    "message": "Authentication is required.",
    "request_id": "req_01H...",
    "retryable": false,
    "details": {}
  }
}
~~~

Error messages MUST NOT expose stack traces, secrets, SQL, filesystem paths, or connector credentials.

### 12.2 Identity and sessions

| Method | Route | Risk | Behavior |
|---|---|---|---|
| POST | /api/v2/sessions | R0 | Authenticate principal and create scoped session |
| GET | /api/v2/sessions/current | R0 | Return current principal, tenant, device, and capability summary |
| POST | /api/v2/sessions/revoke | R2 | Revoke current or explicitly authorized session |
| POST | /api/v2/devices | R2 | Register a device through an enrollment challenge |
| POST | /api/v2/devices/{device_id}/revoke | R2 | Revoke a device |

Session responses MUST not return reusable secrets. Refresh tokens, if used, MUST rotate and support revocation.

### 12.3 Intents, plans, and runs

| Method | Route | Risk | Behavior |
|---|---|---|---|
| POST | /api/v2/intents | R0 | Validate and store an untrusted intent |
| POST | /api/v2/intents/{intent_id}/plan | R0 | Generate a read-only or approval-bound plan |
| GET | /api/v2/plans/{plan_id} | R0 | Retrieve a scope-checked immutable plan |
| POST | /api/v2/plans/{plan_id}/approve | R2-R4 | Approve exact plan digest when policy permits |
| POST | /api/v2/plans/{plan_id}/run | R1-R4 | Queue execution after policy and approval checks |
| POST | /api/v2/runs/{run_id}/cancel | R2 | Request cancellation |
| POST | /api/v2/runs/{run_id}/reconcile | R2-R4 | Resolve an unknown action or explicitly authorize a retry |
| GET | /api/v2/runs/{run_id} | R0 | Retrieve run state and evidence refs |

/api/v2/intents/{intent_id}/plan MUST never execute a side effect. /api/v2/plans/{plan_id}/run MUST require an idempotency key for any tier above R0.

The bounded durable Goal/Task orchestration slice is separate from tool-run
execution. It records operator-owned work, but it does not grant a task an
external side effect or bypass the policy broker:

| Method | Route | Scope | Behavior |
|---|---|---|---|
| POST | /api/v2/goals | workspace:write | Create an active tenant-scoped goal |
| GET | /api/v2/goals | workspace:read | List goals for the authenticated tenant |
| GET | /api/v2/goals/{goal_id} | workspace:read | Retrieve one tenant-scoped goal |
| POST | /api/v2/goals/{goal_id}/tasks | workspace:write | Create an idempotent queued task with same-goal dependencies |
| GET | /api/v2/goals/{goal_id}/tasks | workspace:read | List tasks without lease credentials |
| POST | /api/v2/goals/{goal_id}/schedules | workspace:write | Create a once or interval schedule with a missed-run policy |
| GET | /api/v2/goals/{goal_id}/schedules | workspace:read | List schedules for the authenticated goal |
| GET | /api/v2/schedules/{schedule_id} | workspace:read | Retrieve schedule state without lease credentials |
| POST | /api/v2/schedules/{schedule_id}/claim | workspace:write | Poll and atomically materialize one due task run |
| POST | /api/v2/schedules/{schedule_id}/cancel | workspace:write | Cancel future occurrences and any active schedule run |
| POST | /api/v2/tasks/{task_id}/claim | workspace:write | Atomically claim a due task with a bounded worker lease |
| POST | /api/v2/tasks/{task_id}/complete | workspace:write | Complete only with the current worker and unexpired lease |
| POST | /api/v2/task-runs/{run_id}/claim | workspace:write | Reclaim a retryable or expired task run |
| POST | /api/v2/task-runs/{run_id}/complete | workspace:write | Complete, retry, or dead-letter a leased task run |
| GET | /api/v2/task-runs/{run_id} | workspace:read | Retrieve one durable task-run record without its lease token |
| GET | /api/v2/tasks/{task_id}/runs | workspace:read | Retrieve bounded task execution history without lease tokens |

Task creation, lease transitions, task completion, and automatic goal completion
MUST be transactional with their audit/event/outbox records. Dependency lookup
MUST reject cross-tenant or cross-goal references. Lease credentials MUST NOT
appear in ordinary task reads or event payloads. The current reference slice
provides a bounded poller, retry/reclaim path, dead-letter transition, schedule
cancellation, and durable task-run history. It does not execute task
instructions or grant external side effects; a governed worker must consume a
claimed run through the action broker.

Action execution uses the same durable repository contract. `ActionBroker.submit`
creates a queued run and action with the immutable request payload digest,
timeout, retry policy, and idempotency key. `ActionWorker` claims the action
with a bounded lease and worker token, invokes only the code-owned registry
handler, and commits evidence plus completion events atomically. The reference
application may drain R0/R1 observations inline after the durable enqueue to
preserve its synchronous compatibility response; the inline path still claims
the lease through `ActionWorker` and never calls a handler from an HTTP route.
Risk-bearing R2-R5 actions remain queued for a separately governed worker and
are not drained by the application process.

Lease expiry, timeout, and a result whose side effect cannot be known are
terminal `unknown` outcomes. They are never retried automatically. An
authenticated principal with `run:reconcile` must record an auditable reason
and choose `retry`, `succeeded`, `failed`, or `cancelled`; only `retry` returns
the action to the queue. A running cancellation becomes `cancel_requested` and
is reported as `unknown` if the handler returns without a cooperative
cancellation proof. The installed `zasi-action-worker` command polls the local
queue with R0/R1 as its default allowed risk set; enabling higher-risk worker
profiles remains a separate Gate E decision.

The durable outbox delivery worker is exposed as `zasi-outbox-worker` and
`scripts/run_outbox_worker.py`. It claims only committed outbox rows through
the repository lease, dispatches a configured handler, retries failures through
the stored attempt policy, and exits on `SIGINT` or `SIGTERM`. `event_stream`
rows may be acknowledged without an external handler because the reference
events table is already the authoritative stream source. Every other
destination fails closed when no handler is configured. This worker does not
execute task instructions, invoke arbitrary tools, or enable external writes.
Use `zasi-outbox-worker --once` for a bounded operational probe and an
explicitly supervised long-running invocation for deployment validation.

### 12.4 Approvals, audit, and evidence

| Method | Route | Risk | Behavior |
|---|---|---|---|
| GET | /api/v2/approvals | R0 | List approvals visible to the principal |
| POST | /api/v2/approvals/{approval_id}/revoke | R2 | Revoke a still-pending approval |
| GET | /api/v2/audit | R0 | Query redacted immutable audit records |
| GET | /api/v2/evidence/{evidence_id} | R0 | Retrieve evidence metadata and authorized artifact |
| POST | /api/v2/evidence/{evidence_id}/supersede | R2 | Append a correction with reason and replacement evidence |

Audit responses have the form `{tenant_id, records, next_cursor}`. `next_cursor`
is either null or the stable `created_at|audit_id` cursor for the last returned
record. Audit pagination MUST be cursor-based and stable under concurrent writes;
the legacy timestamp-only cursor is accepted only for migration compatibility.

### 12.5 Briefing and memory

| Method | Route | Risk | Behavior |
|---|---|---|---|
| POST | /api/v2/briefings | R0 | Generate a source-backed brief from selected scope |
| GET | /api/v2/briefings/{briefing_id} | R0 | Retrieve brief, source refs, freshness, and disclosures |
| GET | /api/v2/memory/search | R0 | Search authorized durable memory |
| POST | /api/v2/memory | R2 | Store an explicitly scoped memory item |
| DELETE | /api/v2/memory/{memory_id} | R2 | Delete or tombstone a memory item under retention policy |

Briefing generation MUST return missing, stale, simulated, and unavailable sources rather than filling gaps with authoritative-sounding numbers.

The reference briefing aggregator reads tenant-scoped goals, dependency
blocked tasks, durable task-run outcomes, pending approval plans, and connector
health. Local control-plane observations carry `verified_local` evidence
metadata; GitHub, email, calendar, files, and web remain `unavailable` until a
separately authorized adapter is registered. A brief is `partial` when any
requested external source is unavailable. Every returned claim and operational
item MUST carry at least one source reference with observed/freshness metadata.

Memory retrieval MUST select an explicit project namespace or the unscoped
workspace namespace; it MUST NOT mix project rows into an unscoped search.
`fresh_until` expiry transitions an active item to `stale` in a durable,
audited transaction. Stale rows are excluded by default and are returned only
when the caller explicitly requests `include_stale=true`.

### 12.6 Sequences

| Method | Route | Risk | Behavior |
|---|---|---|---|
| POST | /api/v2/sequences | R1 | Create a draft sequence |
| POST | /api/v2/sequences/{id}/validate | R1 | Validate graph, schemas, scopes, and risk |
| POST | /api/v2/sequences/{id}/approve | R2-R4 | Approve exact revision |
| POST | /api/v2/sequences/{id}/run | R1-R4 | Queue a revision-bound run |
| GET | /api/v2/sequences/{id}/events | R0 | Stream scoped sequence events |

The sequence builder is an orchestration UI. It is not a direct tool execution surface.

### 12.7 Tools and connectors

| Method | Route | Risk | Behavior |
|---|---|---|---|
| GET | /api/v2/capabilities | R0 | List capabilities filtered by principal and profile |
| GET | /api/v2/connectors | R0 | List connector status without secrets |
| POST | /api/v2/connectors/{id}/authorize | R2 | Start an explicit connector authorization flow |
| POST | /api/v2/tools/preview | R0 | Validate a typed tool call and return policy decision |
| POST | /api/v2/tools/call | R1-R4 | Submit a brokered action; never invoke arbitrary code |
| POST | /api/v2/webhooks | R3 | Register an allowlisted destination through approval |

MCP discovery is read-only. MCP tool execution uses the same tool broker, capability manifest, policy decision, approval, idempotency, audit, and evidence path.

### 12.8 CAD, vision, devices, and artifacts

| Method | Route | Risk | Behavior |
|---|---|---|---|
| POST | /api/v2/artifacts | R1 | Upload bounded, typed artifact to quarantine |
| POST | /api/v2/cad/analyze | R1 | Parse and analyze an authorized artifact with provenance |
| GET | /api/v2/cad/{analysis_id} | R0 | Retrieve analysis and disclosure |
| POST | /api/v2/vision/analyze | R1 | Analyze an image or frame with source digest |
| POST | /api/v2/mobile/pair | R2 | Start one-time mobile device pairing |
| POST | /api/v2/mobile/{device_id}/approve | R2 | Approve a pairing challenge |
| GET | /api/v2/devices/{device_id}/telemetry | R0 | Retrieve authorized device telemetry |

Physical actuation endpoints are absent from the reference profile. An adapter may exist only in a separately certified deployment profile and MUST default to disabled.

### 12.9 Streaming, cursors, and resync

Primary stream:

~~~text
GET /api/v2/events?after=cursor
Accept: text/event-stream
Authorization: session credential
X-ZASI-Event-Cursor: cursor
~~~

Requirements:

- The server MUST return a typed event envelope and periodic keepalive.
- The cursor MUST be tenant-scoped and validated against the session.
- `after` is optional when `Last-Event-ID` or `X-ZASI-Event-Cursor` supplies the
  resume cursor. If no cursor is supplied, replay starts at the beginning of
  the retained tenant history.
- If more than one cursor source is supplied, all values MUST be identical.
- If the requested cursor is outside retention, the server MUST emit resync.required and a snapshot reference.
- The client MUST fetch the authoritative snapshot, replace local state, then reconnect from the returned cursor.
- A reconnect that merely opens a socket without resync is not a successful recovery.
- WebSocket is optional and MUST follow the same auth, cursor, scope, and resync contract.

Compatibility routes:

| Existing route | Required v2 behavior |
|---|---|
| /api/status | Read-only compatibility response with truthful capability registry and deprecation header |
| /api/telemetry | Read-only response with evidence metadata and simulation disclosure |
| /api/tick | Return 410 after migration; no mutation through GET |
| /api/execute/{key} | Return 410 or route to a read-only preview; no direct execution |
| /api/mutate | Return 410; use typed plans and approvals |
| /api/rsi/upgrade | Return 410 in reference profile; research profile requires signed artifact workflow |
| /api/webhooks | Return 410 or proxy to v2 broker with approval and egress validation |
| /api/mcp | Proxy to brokered v2 tool calls; direct dispatch is prohibited |

## 13. Persistence and event model

### 13.1 Required tables

| Table | Required fields |
|---|---|
| tenants | id, status, policy_version, created_at |
| principals | id, tenant_id, status, identity_ref, created_at |
| devices | id, tenant_id, status, enrollment_hash, last_seen_at |
| device_pairing_challenges | id, tenant_id, device_id, challenge_hash, idempotency_key, status, expires_at, used_at |
| sessions | id, tenant_id, principal_id, device_id, token_hash, expires_at, revoked_at |
| capabilities | id, tool_id, version, risk_tier, manifest_json, status |
| intents | id, tenant_id, principal_id, input_ref, goal_json, status, created_at |
| plans | id, tenant_id, intent_id, digest, steps_json, status, expires_at |
| approvals | id, tenant_id, plan_id, digest, approver_id, decision, expires_at |
| runs | id, tenant_id, principal_id, plan_id, idempotency_key, request_digest, status, cancel_requested, unknown_reason, timestamps |
| actions | id, tenant_id, run_id, step_id, tool_id, status, attempt_count, payload, timeout, retry policy, worker lease, cancellation, unknown reason |
| evidence | id, tenant_id, kind, status, provenance_json, artifact_ref, supersedes |
| artifacts | id, tenant_id, digest, media_type, storage_ref, quarantine_status |
| audit_records | id, tenant_id, actor_json, action, target, outcome, redacted_metadata |
| events | id, tenant_id, sequence, type, aggregate_json, payload_json |
| outbox | id, tenant_id, event_id, destination, status, next_attempt_at, attempt_count, max_attempts, claim_token, lease_until, dead_lettered_at |
| rate_limits | tenant_id, subject, bucket, count, reset_at |
| sequence_runs | id, tenant_id, sequence_id, revision, idempotency_key, status, result_json, timestamps |
| connector_grants | id, tenant_id, connector_id, scopes, secret_ref, status |
| schedules | id, tenant_id, principal_id, task_id, kind, status, next_run_at, interval_seconds, misfire_policy, idempotency_key, history counters |
| task_runs | id, tenant_id, goal_id, task_id, schedule_id, occurrence_key, idempotency_key, status, attempts, worker lease, result/error, timestamps |
| memory_items | id, tenant_id, principal_id, content, scope, memory_type, project_id, source_ref, provenance, trust, freshness, status |
| briefings | id, tenant_id, principal_id, source-backed content, generated_at |

Every tenant-owned table MUST carry tenant_id or be reachable only through a tenant-owned parent with an enforced repository constraint.

### 13.2 Transaction rule

A state-changing request MUST perform the following in one database transaction:

1. Verify principal, tenant, capability, plan digest, and idempotency key.
2. Apply the domain state transition.
3. Insert the audit record.
4. Append the domain event.
5. Insert outbox delivery records.
6. Commit.

External delivery happens after commit. If delivery fails, the durable action remains visible and retryable. A worker MUST never silently create a second action because the client disconnected.

### 13.3 Retention and privacy

Retention is profile-specific and must be configured, not implicit:

- Audit records are append-only and retained according to legal and operational policy.
- Raw audio, images, and uploaded CAD files are minimized, encrypted, access-logged, and expire independently from derived evidence.
- Secrets are stored by reference to a secret manager or encrypted local store; they are never placed in event payloads.
- Deletion creates an auditable tombstone where immutable audit retention prevents physical deletion.

## 14. Execution and connector broker

### 14.1 Broker algorithm

Every action follows this sequence:

1. Resolve authenticated principal, tenant, device, and session.
2. Resolve stable tool identifier from the registry.
3. Validate typed input and artifact references.
4. Load capability manifest and current availability.
5. Recompute risk tier from the manifest and action input.
6. Evaluate policy and required approval.
7. Verify exact plan digest and idempotency key.
8. Create action, audit, event, and outbox records transactionally.
9. Dispatch to a worker through a bounded queue.
10. Enforce timeout, cancellation, retry, and result-size policy.
11. Store redacted result evidence.
12. Emit completion event and update run state.

No model output, UI event, browser callback, or connector payload can skip a step.

### 14.2 Model adapter

The model adapter may propose intent normalization, explanations, plan drafts, and summaries. It MUST NOT:

- issue authorization decisions;
- choose an approver;
- mint capability tokens;
- select an arbitrary tool by import path;
- write directly to the database;
- execute shell or code;
- claim a result that is not present in evidence.

Provider failures, timeouts, and unavailability are typed states. Deterministic fallback text MUST be disclosed as fallback text.

### 14.3 MCP adapter

MCP operations are divided into:

- discovery: list server, resource, prompt, and tool metadata;
- preview: validate schemas and policy without side effects;
- call: queue an approved typed action through the broker;
- evidence: store the response, provenance, and redaction result.

The adapter MUST reject server-provided instructions that attempt to alter system policy, identity, approval, or tool registry.

### 14.4 Webhook and HTTP egress

The egress broker MUST:

- accept only an explicit destination policy or approved connector grant;
- resolve IPv4 and IPv6 and reject disallowed ranges;
- connect to the policy-checked peer;
- reject redirects unless each hop is revalidated;
- set bounded connect, read, total, and response-size limits;
- use a fixed allowed method and content type;
- attach an idempotency key where the destination supports it;
- redact authorization and sensitive values from logs;
- write durable retry and dead-letter state.

gethostbyname-only validation and an unbounded direct urlopen path do not satisfy this contract.

### 14.5 Research compiler and self-evolution

The production control plane MUST not expose self-compilation or hot swap. Research work is a separate job type:

~~~text
candidate submitted
  -> static validation
  -> signed source/artifact recorded
  -> isolated evaluation
  -> independent regression and security evaluation
  -> human approval
  -> staged canary
  -> health gate
  -> explicit promotion or rollback
~~~

Required artifact evidence:

- source and dependency digest;
- signer identity and signature verification;
- reproducible build information;
- test and benchmark outputs;
- policy and security evaluation;
- rollback artifact;
- promotion approvals;
- observed canary health.

An apparent speedup is not sufficient approval evidence. If isolation, signature, evaluation, approval, or rollback is missing, the result is rejected or research_only.

## 15. Reference cockpit implementation

### 15.1 Shell

The cockpit MUST use one responsive shell with:

- top bar: connection, tenant, device, mode, and profile;
- left navigation: Observe, Assist, Do This, Advanced, Engineering, Humanoid, Mobile Link;
- center workspace: current route and evidence-backed content;
- right rail: command stream, plan preview, approvals, and event health;
- mobile layout: stacked panels with touch-safe targets and no hidden approval controls.

Routes are views over the same session and event state. Routing MUST NOT grant capabilities.

### 15.2 Modes

| Mode | Allowed default | Required visible state |
|---|---|---|
| Observe | R0 | Read-only, source and freshness |
| Assist | R0-R1 | Draft versus executed distinction |
| Do This | R2-R3 | Plan digest, approval, idempotency, action status |
| Advanced | R0-R4 | Disabled or research badges; no implicit power |
| Engineering | R0-R2 | Artifact provenance, parser status, solver evidence |
| Humanoid | R0-R1 | Simulator or advisory disclosure; actuator unavailable |
| Mobile Link | R0-R2 | Device identity, challenge, expiration, revoke control |

### 15.3 Orb and command stream

The central orb is an event-driven status visualization. It MUST derive state from session and event data rather than a timer or static “LIVE” label.

The command stream item MUST contain:

~~~json
{
  "stream_item_id": "str_01H...",
  "created_at": "2026-09-01T00:00:00Z",
  "kind": "input|plan|approval|action|evidence|system",
  "status": "pending|running|succeeded|failed|unknown|simulated",
  "summary": "Short operator-facing summary",
  "run_id": "run_01H...",
  "evidence_refs": ["ev_01H..."],
  "disclosure": "What this item does not establish."
}
~~~

The UI MUST show a reconnecting/degraded state and a resync prompt when event history is unavailable.

### 15.4 Browser security

- Use text rendering or safe component properties for all server data.
- Do not concatenate untrusted values into HTML or inline event attributes.
- Set CSP, frame, referrer, and MIME-sniffing protections on the authoritative server.
- Bundle React, Router, Babel replacement, and visualization dependencies.
- Disable source maps in production unless access-controlled and intentionally published.
- Redact sensitive values from client telemetry and error reports.

### 15.5 Electron security

- Keep contextIsolation enabled and nodeIntegration disabled.
- Expose a minimal typed preload API only.
- Allow navigation only to the expected local origin and approved application routes.
- Wait for readiness with bounded HTTP probes rather than a fixed sleep.
- Verify the child process identity and configured port.
- Propagate termination and remove child processes on shutdown.
- Do not print environment variables or tokens in stdout/stderr.

## 16. Multimodal and device contracts

### 16.1 Voice

Voice processing has separate states:

~~~text
captured -> transcribed -> normalized -> authenticated_signal -> authorized_intent
                                      \-> rejected
~~~

Transcription confidence is not authorization. A biometric adapter, if enabled, MUST validate enrolled material server-side, use anti-replay/liveness controls appropriate to the threat model, and return an evidence reference. Voice alone MUST NOT authorize R3-R5 actions.

The UI MUST disclose when browser speech recognition, local transcription, or deterministic text fallback is used.

### 16.2 Morning brief

Every brief section MUST carry source refs, observed time, freshness, and status. Missing data is rendered as missing or unavailable. The generator MUST not fill the brief with fixed subsystem counts, energy values, invariant counts, or RSI claims as if they were live measurements.

### 16.3 CAD

CAD processing pipeline:

1. Authenticate upload and enforce size/type limits.
2. Store artifact in quarantine with digest.
3. Parse only supported formats with a versioned parser.
4. Reject malformed, oversized, or unsupported geometry.
5. Compute derived values with a named method and units.
6. If stress or safety analysis is requested, invoke an approved solver adapter.
7. Store evidence and disclosure.
8. Permit download or downstream action only when policy allows.

Caller-provided mass, stress, verification, or “approved” fields are inputs to review, not evidence.

### 16.4 Vision and visual analysis

Every analysis result MUST identify source artifact digest, model/adapter version, preprocessing, timestamp, confidence as a non-authoritative signal, and limitations. Visual similarity or competitor analysis is advisory unless independently sourced and verified.

### 16.5 Humanoid and hardware

The reference profile exposes visualization, telemetry fixtures, and simulation. It does not expose physical actuation. Any future hardware adapter MUST define emergency stop, command allowlist, rate limits, hardware identity, signed firmware compatibility, operator presence, and a separate certification gate.

### 16.6 Mobile link

Pairing uses:

1. server-generated one-time challenge;
2. short expiration;
3. device confirmation;
4. scoped capability grant;
5. durable audit event;
6. immediate revoke path.

QR contents MUST not contain a reusable API secret. A displayed pairing code is not a credential after expiry.

## 17. Threat model

### 17.1 Assets

- tenant data and memory;
- session and connector credentials;
- approval records and audit integrity;
- uploaded audio, images, CAD, and generated artifacts;
- tool registry and policy configuration;
- event cursors and run state;
- source, build, and release artifacts;
- physical or external side effects.

### 17.2 Trust boundaries

1. Browser or Electron client to API.
2. API to identity and policy layer.
3. API to persistence and event store.
4. API to worker queue.
5. Worker to external connectors and webhooks.
6. Upload quarantine to parser and solver.
7. Control plane to research compiler.
8. Control plane to optional hardware gateway.

Every crossing MUST authenticate, authorize, validate, rate-limit, correlate, and record the operation according to its risk tier.

### 17.3 Prioritized abuse paths

| Abuse path | Required control |
|---|---|
| Empty API key exposes routes | Fail-closed settings and auth middleware |
| WebSocket bypasses auth | Authenticate upgrade before protocol response |
| GET request triggers tick or action | Method safety and 410 compatibility response |
| Model prompt selects shell or import | Typed registry only and no dynamic execution |
| Sandbox unavailable falls back to host shell | Reject job; no fallback |
| Webhook reaches metadata service | Dual-stack egress validation and redirect denial |
| Wrong tenant requests an object by ID | Repository scope constraints and negative tests |
| Voice caller asserts trusted flag | Server-side auth signal and step-up approval |
| DOM payload injects script or handler | Safe rendering and CSP |
| Event cursor skips history | Cursor validation, replay, and resync.required |
| Worker retry duplicates external write | Idempotency key, reconciliation, and unknown state |
| Compromised workflow publishes artifact | Least-privilege permissions, protected environment, signed release |
| Research candidate hot swaps runtime | Isolated signed-artifact promotion workflow |

## 18. Environment profiles

### 18.1 Local profile

Defaults:

- bind loopback only;
- SQLite database;
- simulation adapters enabled only with visible labels;
- external egress disabled unless explicitly configured;
- research compiler disabled;
- hardware disabled;
- developer authentication required for API and stream tests;
- local artifact directory outside the web root.

Local profile may use a test credential supplied through the environment, but no credential may be committed or baked into an image.

### 18.2 Staging profile

Requirements:

- PostgreSQL or an equivalent multi-process database;
- external identity or managed secret store;
- real event replay and worker queue;
- egress allowlist with test endpoints;
- signed build and SBOM;
- synthetic tenant isolation tests;
- canary deployment and rollback test;
- no production credentials or customer data.

### 18.3 Production profile

Requirements:

- explicit non-default bind and ingress policy;
- managed secrets and rotation process;
- encrypted storage and tested backups;
- least-privilege service identity;
- non-root container;
- immutable build artifact;
- protected deployment environment;
- alerting for auth failures, policy denials, unknown actions, queue age, event lag, and resync rate;
- hardware and self-evolution disabled unless a separately approved profile exists.

## 19. CI, supply chain, and release

### 19.1 Workflow permissions

The default workflow permission is:

~~~yaml
permissions:
  contents: read
~~~

Any write permission MUST be job-scoped, justified in the workflow, protected by environment or tag policy, and absent from ordinary test jobs. Release and package publication MUST use short-lived credentials and trusted signing material. Pull requests from untrusted forks MUST not receive write-capable secrets.

### 19.2 Required checks

- formatting, type checking, schema generation, and unit tests;
- contract tests against the running authoritative server;
- tenant and authorization negative tests;
- WebSocket/SSE auth and resync tests;
- SSRF and DOM XSS regression tests;
- sandbox fail-closed tests;
- migration, backup, restore, and crash recovery tests;
- dependency audit, secret scan, CodeQL or equivalent static analysis;
- frontend bundle and CSP/SRI verification;
- container vulnerability scan and non-root inspection;
- SBOM generation;
- artifact digest and signature verification;
- installer dry-run and backup/rollback test.

### 19.3 Release evidence bundle

A release candidate MUST publish:

~~~text
commit SHA
artifact digests
schema and migration version
dependency lock digest
SBOM reference
signature verification
test command and result
security scan result
container identity and runtime user
deployment profile
readiness response
rollback reference
known limitations and skipped gates
~~~

An evidence bundle that says “all systems online” without per-capability evidence is invalid.

The tag release workflow MUST fail closed unless the protected `release`
environment provides `ZASI_RELEASE_GPG_PRIVATE_KEY` and the matching
`ZASI_RELEASE_GPG_FINGERPRINT`. `scripts/sign_release_artifacts.py` MUST
create and verify detached signatures for every wheel, sdist, the CycloneDX
SBOM, and `SHA256SUMS`, and the release MUST publish the signatures and public
key beside those assets. The private key and optional passphrase MUST enter
only through the protected environment; they MUST NOT appear in repository
files, command arguments, logs, or release assets.

### 19.4 Installer and container requirements

Installer behavior:

- MUST detect existing config and make a timestamped backup before migration.
- MUST not overwrite user config by default.
- MUST not remove dist, build, virtual environments, databases, keys, or backups without an explicit destructive flag.
- MUST install from the lockfile or a verified artifact.
- MUST validate the resulting service and report the exact profile.

Container behavior:

- MUST run as a non-root UID.
- MUST use a minimal image and pinned dependencies.
- MUST not include development credentials, private keys, local databases, or untracked artifacts.
- MUST use a healthcheck that calls authenticated application readiness where applicable.
- MUST define a writable data mount explicitly rather than making the whole root filesystem writable.

## 20. Verification plan

### 20.1 Contract tests

For every API operation:

- valid request and response schema;
- missing and malformed fields;
- wrong method;
- unauthorized and wrong-tenant access;
- expired and revoked session;
- policy deny and unknown;
- duplicate idempotency key;
- timeout and cancellation;
- event and audit emission;
- documentation schema parity.

### 20.2 Security tests

Required cases:

- empty or missing production auth configuration;
- WebSocket and SSE without credentials;
- wildcard origin rejection;
- CSRF-style cross-origin mutation attempt;
- path traversal and symlink escape;
- shell metacharacter and import escape;
- sandbox capability unavailable;
- SSRF loopback, link-local, private IPv4, private IPv6, metadata, redirect, and DNS-rebinding cases;
- DOM payload in logs, subsystem names, errors, and artifact metadata;
- secret redaction in logs, events, exceptions, and client telemetry;
- cross-tenant object enumeration;
- replayed approval and expired plan;
- workflow permission regression.

### 20.3 Persistence and recovery tests

- crash before transaction commit;
- crash after commit before outbox delivery;
- duplicate worker delivery;
- unknown external result and reconciliation;
- action lease ownership, timeout, cancellation, bounded retry, and unknown-before-retry;
- cursor replay after reconnect;
- cursor outside retention and resync;
- backup restore into a clean environment;
- schema migration forward and documented rollback strategy.

### 20.4 Reference cockpit tests

- first load only after readiness;
- authenticated mode and tenant display;
- Observe and Assist cannot invoke side effects;
- Do This shows plan and approval before action;
- simulated and unavailable badges are visible;
- event disconnect shows degraded state;
- resync replaces local state;
- keyboard and touch navigation;
- no untrusted value reaches HTML insertion;
- Electron cannot navigate outside the approved origin.

### 20.5 Performance and reliability budgets

Initial budgets:

| Operation | Target |
|---|---|
| readiness response | p95 under 500 ms when dependencies are healthy |
| authenticated read | p95 under 750 ms for local data |
| plan creation | p95 under 3 s excluding external model time |
| event delivery | first event under 1 s after commit |
| event replay | 10,000 scoped events without loss or duplication |
| worker retry | bounded by policy with visible queue age |
| UI reconnect | resync or explicit failure within 5 s |

These are test targets, not evidence of capability. Performance tests MUST record environment, dataset size, and profile.

## 21. Finite implementation plan

### P0: baseline and ownership

Outputs:

- authoritative entrypoint;
- profile settings object;
- readiness endpoint;
- route ownership map;
- legacy startup path quarantined;
- baseline test inventory.

Validation:

- one process starts;
- readiness returns structured dependency state;
- existing compatibility tests identify intentional changes;
- no duplicate port owner.

Rollback:

- retain the legacy entrypoint behind an explicit development-only command until compatibility tests pass.

Stop conditions:

- more than one production startup path remains;
- readiness cannot distinguish process alive from dependency ready.

### P1: identity and persistence foundation

Outputs:

- tenant, principal, device, session, capability, audit, and event repositories;
- migrations;
- auth middleware;
- scope-enforced repository methods;
- secret redaction.

Validation:

- negative auth and tenant tests;
- database restart and migration tests;
- audit immutability tests.

Rollback:

- migration backup and restore; no destructive schema rewrite.

Stop conditions:

- any route can access tenant data without repository scope;
- credentials appear in logs or events.

### P2: intent, plan, policy, and evidence

Outputs:

- typed intent and plan contracts;
- risk tiers;
- policy engine;
- approval records;
- evidence provenance;
- truthful capability registry.

Validation:

- policy matrix tests for R0-R5;
- exact plan digest approval tests;
- simulated versus verified disclosure tests.

Rollback:

- disable all plans above R1 and retain read-only observation.

Stop conditions:

- model or voice output can authorize an action;
- fixed values are rendered as live evidence.

### P3: event store, outbox, and stream

Outputs:

- append-only event store;
- cursor and retention policy;
- outbox worker;
- SSE stream;
- authoritative snapshot and resync.

Validation:

- reconnect, replay, duplicate, gap, retention, and resync tests;
- event-to-audit correlation.

Rollback:

- disable live action views and serve polling snapshots with a visible degraded label.

Stop conditions:

- a reconnect can silently miss an event;
- event history exists only in process memory.

### P4: typed action broker

Outputs:

- tool registry;
- action and run state machines;
- idempotency;
- worker queue;
- timeout, cancellation, retry, and unknown-result handling.

The current reference implementation supplies `ActionBroker.submit`,
`ActionWorker`, `zasi-action-worker`, action leases, immutable payload storage,
bounded result serialization, explicit reconciliation, and a protected R0/R1
inline drain. Higher-risk action deployment remains deliberately disabled from
the application process until an independently governed worker and Gate E
evidence exist.

Validation:

- no direct route-to-callable path;
- duplicate delivery and cancellation tests;
- risk and approval enforcement.

Rollback:

- allow R0 and simulation-only R1; disable external connectors.

Stop conditions:

- an action can execute without an audit and event;
- a GET route can trigger an action.

### P5: connector and MCP boundary

Outputs:

- MCP discovery/preview/call adapter;
- egress broker;
- webhook queue;
- secret references;
- connector grants.

Validation:

- SSRF, redirect, DNS rebinding, timeout, retry, and redaction tests;
- MCP tools cannot bypass policy.

Rollback:

- disable all external egress and retain discovery metadata only.

Stop conditions:

- connector code can open a socket outside the broker;
- a connector response can inject instructions into policy or identity.

### P6: cockpit and desktop

Outputs:

- authoritative bundled React cockpit;
- event-driven shell;
- mode and disclosure rendering;
- safe rendering;
- hardened Electron lifecycle.

Validation:

- browser, mobile viewport, reconnect, CSP, DOM XSS, and Electron navigation tests.

Rollback:

- serve a read-only static status page while preserving API and audit.

Stop conditions:

- UI mode changes permissions;
- static “LIVE” state is possible without an active authenticated stream.

### P7: multimodal adapters

Outputs:

- voice input with explicit auth signal;
- source-backed briefing;
- quarantined CAD parser;
- vision provenance;
- simulation-only humanoid and mobile pairing.

Validation:

- malformed artifact and source digest tests;
- stale/missing evidence tests;
- mobile challenge expiration and revoke tests.

Rollback:

- disable upload, voice command execution, and device pairing; keep text Observe/Assist.

Stop conditions:

- caller-provided verification is accepted as identity;
- CAD or voice output is treated as an approval.

### P8: release hardening

Outputs:

- CI least privilege;
- reproducible artifacts, SBOM, signatures;
- non-root container;
- installer backup/migration behavior;
- staging canary and rollback evidence.

Validation:

- complete release evidence bundle;
- independent verification pass;
- all mandatory gates green.

Rollback:

- revert to the last signed artifact and compatible schema version; preserve audit and evidence.

Stop conditions:

- any mandatory security gate is skipped;
- deployment behavior cannot be observed and rolled back.

## 22. Definition of done

### Architecture and ownership

- [ ] One authoritative application entrypoint.
- [ ] One documented port and readiness owner.
- [ ] Legacy server paths quarantined or explicitly compatibility-only.
- [ ] API schema generated from the same contracts used at runtime.

### Security and governance

- [ ] Production auth fails closed.
- [ ] All streams and upgrade paths authenticate.
- [ ] Tenant and device scope is enforced server-side.
- [ ] GET is side-effect free.
- [ ] Risk tiers and approvals gate every mutation.
- [ ] Dynamic execution is disabled in the control plane.
- [ ] Sandbox absence fails closed.
- [ ] Egress is brokered and SSRF-tested.
- [ ] Secrets are redacted and externally managed.

### Truthfulness and evidence

- [ ] Capability inventory separates implementation, runtime, evidence, and risk.
- [ ] Simulated and research outputs are visibly disclosed.
- [ ] No fixed telemetry or formal claim is labelled live or verified.
- [ ] Evidence is immutable, source-backed, timestamped, and freshness-aware.
- [ ] Voice, CAD, visual, and hardware claims have provenance and limits.

### Persistence and realtime

- [ ] State, audit, event, and outbox writes are atomic.
- [ ] Sessions, cursors, rate limits, and approvals survive process restart.
- [ ] Replay, duplicate delivery, retention gap, and authoritative resync are tested.
- [ ] Unknown external side effects are reconciled before retry.

### UI and desktop

- [ ] Frontend dependencies are bundled and locked.
- [ ] CSP and safe rendering are enforced.
- [ ] Realtime UI shows actual authenticated connection state.
- [ ] Operator mode does not grant permissions.
- [ ] Electron process and navigation lifecycle are supervised.

### Delivery

- [ ] CI defaults to contents read and uses narrowly scoped exceptions.
- [ ] Release artifact is signed, hashed, and accompanied by an SBOM.
- [ ] Container runs non-root with bounded resources.
- [ ] Installer backs up configuration and avoids destructive cleanup by default.
- [ ] Staging canary and rollback are evidenced.
- [ ] Independent verification confirms the evidence bundle.

## 23. Release decision

The current baseline is NO-GO for production control-plane claims.

The earliest acceptable release is a Conditional Read-Only/Assistive release after P0 through P3 and the mandatory H0 through H6 gates pass. It must visibly declare:

- external writes disabled;
- research compiler and self-evolution disabled;
- hardware and physical actuation disabled;
- formal and cryptographic proof claims unavailable unless independently verified;
- simulation and fixture data wherever used;
- known limitations and the exact evidence timestamp.

Full Do This capability requires P4 and the relevant connector, approval, egress, audit, recovery, and staging gates. R4 and R5 remain disabled until their separate certification and operational controls exist.

## 24. Resolved implementation constraints

| Constraint | Decision |
|---|---|
| Two existing HTTP servers | Select one authoritative ASGI server; legacy server is not a production owner |
| Raw WebSocket and SSE | SSE is the primary durable stream; WebSocket is optional and governed identically |
| SQLite versus PostgreSQL | SQLite local profile; PostgreSQL multi-process production profile |
| Fixed subsystem count | Use registry-derived counts and per-capability evidence; never hardcode “all online” |
| Model autonomy | Models propose typed intents/plans only; policy and broker decide |
| Voice authorization | Voice is an input and optional authentication signal; it is not sufficient for high-risk actions |
| Formal proof | Typed invariant evidence is allowed; cryptographic/formal labels require real independent evidence |
| Self-evolution | Disabled in reference profile; signed artifact and staged promotion required for research profile |
| Hardware | Simulation and telemetry only in reference profile; no actuator endpoint |
| Compatibility | Preserve safe read-only routes temporarily; explicitly retire side-effecting legacy routes |
| Installer behavior | Backup and migrate non-destructively; no implicit deletion |
| Release truth | A claim requires implementation, test, and runtime evidence at the declared profile |

## 25. Final implementation rule

Build the smallest trustworthy path first:

~~~text
authenticated session
  -> scoped observation
  -> typed intent
  -> deterministic policy
  -> immutable read-only plan
  -> source-backed evidence
  -> durable event
  -> explicit approval
  -> brokered action
~~~

Every capability that cannot complete this path remains disabled, simulated, research_only, or unavailable. The cockpit may still be ambitious and visually complete, but its language, badges, telemetry, and automation must always reflect the evidence actually available.

## 26. Current implementation evidence and issue reconciliation

### 26.1 Evidence boundary

Evidence capture date: **2026-09-02 UTC**. The results below distinguish local
working-tree evidence, the signed implementation commits, hosted PR checks, and
unverified deployment gates. The core PostgreSQL/Redis, CI, cockpit, and
encrypted-backup hardening is recorded through signed code commit `49bba1c`,
with the scheduler fixture, bounded outbox worker, protected release signing,
and durable action-worker follow-up in signed commits `25ad5f3`, `1c1dd62`,
`7ba35f9`, `eaf4c15`, `17e3771`, and `3e61e9a`. PR
[#29](https://github.com/cvsz/zasi/pull/29) passed hosted
checks for exact pushed verification head `e19d4de7e0d7d0e47745e0cf0982ab5b4806798a`,
which includes the bounded outbox worker, release-signing gate, and evidence
updates. Hosted verification for the two new action-worker commits will be
recorded after they are pushed. There is no
staging deployment, production checkout, or production release authorization.
The existing `.coverage` deletion is preserved and is not part of the
implementation claim.

| Command or inspection | Observed result | Evidence class |
|---|---|---|
| `python3 -m unittest discover -s tests -q` | 284 tests passed, 2 optional live-service checks skipped | Local functional regression |
| `PYTHONWARNINGS=error::ResourceWarning python3 -m unittest discover -s tests -q` | 284 tests passed, 2 optional live-service checks skipped; no unclosed SQLite warning | Local resource-lifecycle regression |
| Focused control-plane/security suite (`tests.test_control_plane_core`, `tests.test_control_plane_broker`, `tests.test_control_plane_api`, `tests.test_security_hardening`, `tests.test_egress_security`) | Passed, including memory-hard API-key verification and TLS 1.2 floor tests | Local governed/security regression |
| Focused outbox worker suite (`tests.test_outbox_worker tests.test_control_plane_core`) | 20 tests passed; bounded polling, interruptible shutdown, retry/dead-letter preservation, configuration fail-closed behavior, and worker identifier validation covered | Local outbox worker regression |
| `PYTHONPATH=. python3 -m unittest tests.test_release_signing -v` | 4 tests passed; artifact selection/checksum determinism and protected release workflow requirements covered | Local release-signing regression |
| `python3 -m unittest tests.test_api -q` | 8 legacy compatibility tests passed, including retired webhook and truthful legacy OpenAPI assertions | Local migration-surface regression |
| `python3 -m compileall -q backend src scripts tests main.py` | Passed | Local syntax check |
| `python3 -m unittest tests.test_encrypted_backup -q` | 10 passed, including AES-256-GCM tamper and wrong-key rejection, atomic mode-600 files, missing-source rejection, no-clobber restore, and SQLite restore integrity | Local encrypted backup/restore regression |
| `node tests/test_components.js` | Passed; verifies React 19/Router 7 pins, typed entrypoint ownership, local scripts, and governed route declarations | Local bundle/source safety assertions |
| `npm run typecheck` | Passed with TypeScript 7 strict settings for the production entrypoint | Local frontend type safety |
| `node --check electron/main.js` | Passed | Local Electron syntax check |
| `npm run build` | Vite production bundle passed; emitted a chunk-size advisory | Local frontend build |
| `python3 -m build` | Source distribution and wheel build passed | Local package build |
| `zasi-outbox-worker --once` against a temporary SQLite profile | Bounded one-iteration run passed; output contained only sanitized status/count fields and no secret material | Local worker CLI smoke |
| `python3 scripts/run_action_worker.py --once` against a temporary SQLite profile | Direct source-checkout CLI smoke passed; one bounded R0/R1 poll completed with sanitized status/count output and no secret material | Local durable action-worker CLI smoke |
| `scripts/sign_release_artifacts.py` in an isolated temporary output directory with the configured local GPG key | Wheel, sdist, SBOM, and SHA256SUMS were signed and verified; public key export and checksum verification passed; temporary signatures were outside the repository | Local artifact-signing smoke |
| `ZASI_DATABASE_BACKEND=postgresql` with `PostgresControlPlaneStore` against the shared cluster | Schema 10 initialization, integrity check, authenticated session, project-memory/briefing/schedule repository paths, readiness, and custom-format backup catalog smoke passed | Local PostgreSQL integration |
| Shared PostgreSQL/Redis ASGI smoke with a uniquely scoped tenant probe | Unauthenticated goals access returned `401`; authenticated session bootstrap returned `201` and remained scoped to `local`; `/health/ready` returned HTTP `200` with PostgreSQL schema 10 and Redis `ready`; a foreign-tenant goal returned `404` and was absent from the local goal list; exact probe rows were removed and cleanup was verified | Local authenticated API, dependency, and tenant-isolation evidence |
| `PostgresControlPlaneStore` against an ephemeral database on the shared PostgreSQL cluster | Schema 10 initialization, tenant-scoped Goal/Task DAG lifecycle, schedule occurrence deduplication, task-run lease ownership/reclaim, atomic completion, and goal completion passed; the ephemeral database was removed after verification | Local PostgreSQL vertical-slice integration |
| `scripts/backup_control_plane.py create/validate --backend postgresql` with an ephemeral 32-byte key injected through `ZASI_BACKUP_KEY_B64` | Schema-10 encrypted archive created and validated from the shared PostgreSQL cluster; destination mode `600`. A new temporary PostgreSQL restore was not run in this pass because the deliberately least-privileged `zasi` role cannot create or drop validation databases; prior restore mechanics remain historical evidence. | Local encrypted PostgreSQL backup create/validate evidence; restore is a separate open gate for schema 10 |
| `ZASI_REDIS_URL` with `RedisRuntime` against the shared ACL user | Authenticated ping, atomic namespaced rate-limit, and ASGI request smoke passed; the live host ACL has `default` disabled and `zasi` limited to `~zasi:*` plus `PING`, `EVAL`, `INCRBY`, and `EXPIRE`; direct `CONFIG`/`GET`/`SET`, ACL introspection, outside-namespace keys, and unauthenticated access were denied | Local Redis integration and least-privilege ACL audit |
| Private `.env` service credential shape | Mode `600`; `zasi` PostgreSQL/Redis URLs and `PGPASSWORD`/`REDIS_PASSWORD` contain operator-supplied high-entropy hex material; the value is ignored by Git and absent from tracked source | Local secret-handling inspection |
| `npm audit --omit=dev --json` | 0 info/low/moderate/high/critical findings after the React Router 7.18.3 upgrade | Local dependency audit |
| Isolated project environment: `pip-audit --local --format json` after installing `.[dev]` | 0 vulnerable project packages; host-wide audit findings are outside the ZASI dependency environment | Local Python dependency audit |
| `docker compose config` | Passed with explicit local API key/CORS inputs | Local configuration rendering |
| ASGI smoke: session bootstrap, authenticated OpenAPI, header-based SSE resume, `/health/live`, `/health/ready`, `/`, and an unknown API route | Session `201`; authenticated OpenAPI `200`; SSE resume `200` with `stream.end`; liveness/readiness/root `200`; unknown API route returned JSON 404 | Local HTTP smoke |
| `docker build --pull -t zasi:architecture-implementation .` | Passed for the implementation branch | Local container build |
| `docker build --pull` plus isolated hardened container smoke | Current image returned HTTP `200` from `/health/ready` with `status=ready` and schema 10; UID `10001:10001`, read-only rootfs, all capabilities dropped, no-new-privileges, PID limit, memory limit, and CPU limit were verified; external egress, research execution, and physical actuation reported disabled; temporary container was removed | Local runtime/container evidence |
| `python3 scripts/generate_sbom.py --output dist/zasi-sbom.cdx.json --resolve-installed` in the isolated project environment | CycloneDX 1.5 SBOM generated with 376 components and a serial number | Local supply-chain evidence |
| `sha256sum --check dist/SHA256SUMS` and GPG verification of wheel, sdist, and SBOM signatures | Passed with the configured cvsz signing identity | Local artifact integrity evidence |
| PR #29 hosted checks for exact pushed verification head `e19d4de` | CodeQL actions/JavaScript-TypeScript/Python, Python 3.11/3.12 with the isolated dependency audit, React/TypeScript validation, distribution, Docker image, and Docker build checks passed; PR package publication skipped. This head contains signed worker commit `1c1dd62`, signed release-gate commit `eaf4c15`, and signed evidence commit `e19d4de`. | Hosted CI evidence; not release approval |
| GitHub Issue #18 | Remains `OPEN`; current status comments are maintained in the [roadmap thread](https://github.com/cvsz/zasi/issues/18) | External roadmap status, not release approval |

The `ResourceWarning` regression test is intentionally retained. The original
legacy hypergraph adapter used `with sqlite3.connect(...)`, which commits but
does not close the connection; it now uses explicit closing and passes under
warnings-as-errors. The legacy adapter remains a research/compatibility surface,
not the authoritative control-plane repository.

### 26.2 Current status against the live roadmap

The issue tracker is a planning input, not an approval or release certificate.
The following status is the honest reconciliation of the current checkout with
the acceptance criteria in [#9](https://github.com/cvsz/zasi/issues/9) through
[#18](https://github.com/cvsz/zasi/issues/18):

| Issue / phase | Current status | Evidence and remaining release gate |
|---|---|---|
| [#9 / P0](https://github.com/cvsz/zasi/issues/9) | Partial, local | `backend.app` is the authoritative ASGI owner; fail-closed settings, readiness, compatibility quarantine, and registry-derived status exist. Duplicate-port ownership detection and hosted runtime ownership evidence remain open. |
| [#10 / P1](https://github.com/cvsz/zasi/issues/10) | Partial, local PostgreSQL/Redis and encrypted backup mechanics | Tenant-scoped identity, hashed sessions, devices, audit, events, rate limits, schema-10 migrations, PostgreSQL repository, Redis coordination, authenticated API smoke, AES-GCM schema-10 archive create/validate, SQLite restore integrity, and historical temporary PostgreSQL restore checks exist. A fresh schema-10 temporary restore, external identity/managed secrets, multi-process restart proof, managed object-storage retention/key rotation, staging restore, and rollback operations remain open. |
| [#11 / P2](https://github.com/cvsz/zasi/issues/11) | Partial, local | Typed intents/plans, deterministic risk policy, exact-digest approval records, evidence provenance, and governed MCP calls exist. Full R0–R5 capability inventory, production verification procedures, and complete claim-to-evidence coverage remain open. |
| [#12 / P3](https://github.com/cvsz/zasi/issues/12) | Partial, local | Transactional events/outbox, bounded `zasi-outbox-worker` delivery loop, leased claims, authenticated SSE replay, cursor validation, retention gaps, and snapshot resync exist. A continuously deployed production worker, 10,000-event performance evidence, backpressure policy, and multi-process delivery proof remain open. |
| [#13 / P4](https://github.com/cvsz/zasi/issues/13) | Partial, durable reference worker | Stable tool registry, request digests, run idempotency, approval gating, immutable queued payloads, worker leases/tokens, atomic evidence/events, bounded local retry, timeout/cancellation/unknown semantics, explicit authenticated reconciliation, and the R0/R1 `zasi-action-worker` path exist. Certified isolation, higher-risk worker deployment, external-side-effect proof, multi-process recovery, and production worker evidence remain open. |
| [#14 / P5](https://github.com/cvsz/zasi/issues/14) | Partial, React 19 / Router 7 with checked TypeScript source | Dependencies are bundled and locked, the cockpit uses authenticated v2 transport, safe rendering, CSP, reconnect/resync state, and a strict TypeScript root entrypoint; the cockpit source is now checked in `cockpit.tsx` and `app.jsx` is only a compatibility export. Accessibility/performance evidence and broad event-driven workspace coverage remain open. |
| [#15 / P6](https://github.com/cvsz/zasi/issues/15) | Partial, local durable orchestration/reference connectors | SQLite/PostgreSQL goals, tasks, schedules, task runs, project-scoped memory, source-backed briefings, and connector health now provide tenant scope, dependency gating, occurrence/idempotency keys, worker leases, restart persistence, stale invalidation, authenticated routes, and atomic events. A continuously deployed production worker, real GitHub/email/calendar/files adapters, semantic retrieval, external-source freshness, and independent multi-process evidence remain open. |
| [#16 / P7](https://github.com/cvsz/zasi/issues/16) | Unavailable by design | Artifact quarantine and provenance contracts exist; real CAD/STEP, vision, STT/TTS, anti-replay speaker verification, and hardware integration are not enabled. |
| [#17 / P8](https://github.com/cvsz/zasi/issues/17) | Partial packaging and encrypted-backup hardening; NO-GO | Workflows, non-root container configuration, installer backup behavior, lockfiles, AES-GCM backup/restore mechanics, project-only Python/npm dependency audits, local signed wheel/sdist/SBOM/checksum evidence, a fail-closed protected-environment release-signing workflow, hosted CodeQL, and container builds exist. Dedicated source/container scanner provenance, managed retention/key rotation, hosted release provenance from an exercised tag, staging canary, rollback observation, and independent verification remain open. |
| [#18 roadmap](https://github.com/cvsz/zasi/issues/18) | Open roadmap | The phase order and release gates are captured here; issue completion must not be inferred from local test output. |

### 26.3 Release decision from the evidence

The local checkout is acceptable as a **conditional read-only/assistive
reference profile** when the operator supplies an API key, builds the frontend,
uses loopback/local SQLite, and accepts the explicit unavailable/disabled
disclosures. It is **NO-GO for public production, external writes, hardware,
self-evolution, formal/cryptographic assurance, or ASI/AGI claims**.

The next implementation work is finite and ordered: complete the missing P0/P1
ownership and production repository operations, complete Gate E for any
higher-risk action worker, then finish the remaining P6 production worker, real
connector adapters, semantic retrieval, and freshness evidence before the P8
signed staging release process. An open GitHub issue, a target architecture
diagram, a passing local test, or a historical badge cannot substitute for the
required evidence bundle.
