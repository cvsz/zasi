# ARIN ↔ ZCoder Tool Boundary

## Scope

This document records the minimum security requirements ARIN must preserve when integrating bounded tool/MCP capabilities from the curated `cvsz/zcoder` source. It is an evidence/contract extraction only: it does not add a runtime dependency, copy ZCoder source, enable unrestricted shell/file/network access, or grant physical actuation authority.

Pinned source for this assessment: `cvsz/zcoder@7153e8b7a48e9d7f9f1976fae2b23f270ac44dab`.

## Required ARIN invariants

ARIN tool adapters MUST fail closed and MUST NOT inherit ambient authority from ZCoder or the host process.

1. **Filesystem containment** — every model/user-controlled path is canonicalized and proven to remain inside an explicitly configured workspace before any read, write, edit, glob, grep, list, or equivalent operation. Traversal and symlink escapes are denied.
2. **Network containment** — outbound access is denied unless the individual capability explicitly permits it. Fetch-style tools require HTTPS validation plus SSRF/redirect/proxy/DNS/IP-boundary review; a read-only label does not make network access safe.
3. **Secret isolation** — tool subprocesses, hooks, MCP servers, and status commands do not inherit credential-named environment variables, agent sockets, provider secrets, or unrelated service credentials. Credentials are scoped to the minimum tenant, operation, repository, and lifetime.
4. **Approval boundary** — mutating or otherwise privileged operations require an explicit ARIN policy decision and approval where the capability risk class requires it. Non-interactive mode must fail closed rather than silently auto-approve.
5. **Untrusted inputs** — model output, tool arguments, MCP responses, retrieved content, repository content, provider responses, web content, and user files remain untrusted until validated at the privileged sink.
6. **Tenant/session isolation** — no tool may use caller-controlled identifiers to cross tenant/session/workspace boundaries; authorization is checked at execution time, not inferred from UI visibility.
7. **Bounded resources** — adapters enforce explicit input/output size, timeout, retry, concurrency, and error-disclosure limits appropriate to the tool.
8. **Subprocess safety** — executable surfaces use explicit commands/arguments and bounded working directories/environment; shell interpretation is not inherited by default.
9. **Auditability** — privileged attempts produce structured evidence sufficient to identify tenant/session, capability, policy/approval result, bounded target, outcome, and failure class without logging secrets.
10. **No actuator authority** — tool/MCP output is evidence or a proposed high-level action only. It cannot directly address raw actuators; physical actuation remains disabled until the independent deterministic safety and HIL gates pass.

## Capability descriptor requirements

Every future ARIN tool capability descriptor must declare at least:

- stable capability ID and version;
- operation class (`read`, `write`, `execute`, `network`, or a deliberately narrower class);
- filesystem roots and access mode, defaulting to none;
- network destinations/protocol policy, defaulting to none;
- subprocess authority, defaulting to none;
- required credential/scope names without embedding credential values;
- tenant/session binding requirements;
- approval requirement and risk class;
- timeout, input/output and retry bounds;
- audit/evidence fields;
- deterministic denial behavior.

An omitted privilege is denied. Descriptor metadata cannot expand authority beyond server-side ARIN policy.

## Evidence basis

The pinned ZCoder security policy documents canonical path containment for CodeAgent filesystem operations, secret/environment isolation for child processes, HTTPS/outbound-network review, sandbox escape regression coverage, explicit permission/approval boundaries, loopback-safe API defaults, non-root containers, and hosted security/release checks. ARIN reuses these requirements as constraints, not ZCoder implementation code.

## Next bounded implementation

Define the ARIN-owned capability descriptor schema and risk classes with tests first. The tests must prove omitted filesystem/network/subprocess authority is denied and that privileged classes cannot execute without the required policy/approval evidence. Runtime service integration remains later and requires its own ADR/evidence.
