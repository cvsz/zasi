# Alignment and safety boundaries

This document describes controls that are implemented in the reference
control plane. It does not certify alignment, formal proof, cryptography,
hardware safety, or AGI/ASI capability.

## Implemented control boundary

- Authentication fails closed when `ZASI_API_KEY` is absent; sessions are
  opaque and stored by token digest.
- Every v2 request resolves a server-owned tenant, principal, session, and
  scope before dispatch.
- Intent input is untrusted. Models, voice input, UI modes, and MCP payloads
  cannot authorize a tool or raise a risk tier.
- Only code-registered stable tool identifiers reach the action broker.
- Plans bind a canonical digest and scope digest; risk-bearing plans require
  an exact approval before execution.
- Domain state, audit, event, and outbox records commit atomically.
- Evidence carries adapter, version, origin, timestamps, freshness, digests,
  method reference, artifact reference, verification status, and disclosure.
- GET/read routes are side-effect free; retired legacy mutation routes return
  typed retirement responses.

## Explicitly unavailable

The following are not established by fixed values, hashes, local arithmetic, or
tests that only inspect object shape:

- Plan A compute governance, hardware attestation, or global wattage limits.
- ZK-STARK/SNARK, Lean-kernel, cryptographic-assurance, or treaty compliance.
- Physical robotics, FPGA/QPU control, actuation, or emergency-stop safety.
- Autonomous recursive self-improvement, hot swap, or model-generated code
  execution. The sandbox rejects work when isolation is unavailable.
- Voice biometrics. Voice is an input signal; caller-provided confidence and
  verification flags are never authorization.
- Live telemetry, competitor superiority, consciousness, energy, or fixed
  “all systems online” claims.

## Risk tiers

`R0` is authenticated read-only observation. `R1` is disclosed local
calculation/simulation. `R2` local writes require a capability and approval;
`R3` external writes additionally require brokered egress and durable retry;
`R4` code/credential/runtime changes are disabled; `R5` physical actuation is
disabled in the reference profile. A passing test is evidence for the tested
behavior, not a blanket guarantee for an entire tier.

See [the implementation specification](ZASI_IMPLEMENTATION_SPECIFICATION.md)
for threat model, evidence requirements, and release gates.
