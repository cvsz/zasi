# AI Futures Project Superintelligence Design

## Goal

Build a no-license-cost, local-first reference platform for AI Futures Project Superintelligence. It gives AI platform developers a governed way to define, evaluate, and run agents while giving enterprise operators control over policy, approvals, budgets, evidence, and tenant-scoped audit history.

This release is a safe vertical slice, not a claim that artificial superintelligence exists. The ASI cognitive and compute blueprint is the long-term research direction. The first product must be runnable on a laptop or free-tier host and must keep real-world side effects disabled.

## Product Boundary

The primary workflow is:

```text
define agent -> sandbox test -> policy check -> publish version -> run job
-> request approval -> simulate approved write -> record evidence
```

The first tool set contains a read-only knowledge search and an approval-gated ticket update simulator. No credentials, browser automation, arbitrary code execution, robotics, financial actions, or live SaaS writes are included. The simulator makes the approval and audit lifecycle observable without creating external side effects.

## Architecture

The system has two logical trust zones:

- The SaaS control plane owns organizations, tenants, agent definitions and versions, policies, approvals, budgets, deployment metadata, audit projections, and operator-facing queries.
- The customer data plane owns prompts, working context, memory, documents, connectors, local models, tool execution, and customer secrets. It connects outbound through mTLS and signed deployment bundles in a production deployment.

The reference profile runs both zones locally in one Python process. It uses SQLite for durable state and an in-process subscriber bus. The event interface is CloudEvents-shaped and is designed to map to NATS JetStream in a distributed deployment. PostgreSQL, NATS JetStream, MinIO-compatible object storage, OpenTelemetry, and Docker/Kubernetes are deployment adapters, not prerequisites for the free-tier profile.

The event path is:

```text
HTTP command -> authorization and policy evaluation -> durable event
-> projection and runtime consumers -> approval or result event
-> audit projection and realtime browser update
```

Events use at-least-once delivery semantics. Every event carries an event ID, tenant ID, execution ID when applicable, agent version, actor, correlation ID, causation ID, sensitivity classification, and idempotency key. Consumers must be safe to replay.

## Cognitive Core

The first cognitive core is deliberately bounded:

- A planner converts a task into a typed plan containing preconditions, tool names, expected effects, and risk levels.
- A provenance-aware memory layer stores working context and explicit facts with source labels.
- A verifier rejects unknown tools, malformed plans, missing evidence, and writes without approval.
- The model gateway selects a local Ollama model when enabled and otherwise uses a deterministic simulator. It never silently sends data to a hosted model.
- The runtime emits events for planning, model selection, tool requests, approvals, results, and completion.

The RSI engine, architecture search, kernel generation, and self-deployment are research-only extension points. They are disabled in this release and cannot change policy, permissions, or deployed code.

## Three-Pillar Research Blueprint

### Recursive Self-Improvement Engine

The future RSI path is split from the active execution plane. Telemetry and profiling may identify bottlenecks, but candidate code, weights, graph rewrites, or kernels are generated only inside an isolated improvement plane. Candidates must be versioned, reproducible, formally checked, adversarially evaluated, and compared against the current version before reaching a gatekeeper. The gatekeeper requires explicit operator authorization, signed artifacts, an immutable provenance record, and a tested rollback path. Consensus and atomic hot swap are future deployment mechanisms; no component in this release can modify or replace itself.

### Neural-Symbolic Hybrid Core

Neural components may propose search branches, lemmas, plans, or program structures. A discrete verification plane must validate typed ASTs, policy rules, deterministic sandbox results, and eventually SMT/SAT or Lean/Coq proofs. Counterexamples become structured evidence for the next proposal rather than hidden chain-of-thought. The hypergraph and embedding layers are joined through provenance IDs and source timestamps; retrieval evidence is never treated as proof by itself.

### Distributed Compute and Memory Topology

The deployment contract separates inference, formal verification, and simulation pools. The research topology can map working context to high-bandwidth memory, shared graph state to a CXL-like pool, and durable artifacts to NVMe/object storage. Optical interconnects and specialized accelerators remain provider-neutral extension points. The local profile maps these tiers to process memory, SQLite projections, and the filesystem so the same workload contracts can be tested without hyperscale hardware.

## Web Console

The browser console is an operational surface, not a marketing page. It provides:

- Overview metrics for active executions, pending approvals, event volume, and policy outcomes.
- Agent registry with status, version, model policy, and allowed tools.
- Execution timeline showing plans, policy decisions, tool activity, and evidence.
- Approval queue with explicit approve and reject actions and operator identity.
- Audit stream filtered by tenant, execution, event type, sensitivity, and time.
- Model status showing local, simulator, and optional hosted fallback states.

The browser receives a query snapshot through JSON APIs and incremental updates through SSE. It never reads the event transport directly.

## Safety and Governance

The platform defaults to least privilege, simulation mode, localhost binding, and no external network calls. Consequential tools require an approval event whose decision is bound to the exact tenant, execution, agent version, tool, and action hash. Replays and duplicate requests must not execute an action twice.

Formal verification, interpretability probes, and adversarial debate are future evidence-producing components, not absolute guarantees. Each future component must expose its evidence and failure state to the same policy gate. A failed, unavailable, or ambiguous safety check fails closed.

## Acceptance Criteria

The release is complete when a developer can create an agent, run its supervised demo task, observe a read-only tool result, see a pending approval, approve or reject the simulated write, and inspect the complete tenant-scoped event history in the console. Automated tests must cover event durability, replay-safe projections, tenant isolation, policy rejection, approval idempotency, HTTP routes, and the simulator fallback. `make check` must pass from a clean checkout with only Python available.
