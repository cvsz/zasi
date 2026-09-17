# ARIN Task 4 — backward-compatibility evidence

Status: **candidate — requires exact-head CI before verification**

This slice closes the repository-side supported-version compatibility test gap for the canonical ARIN v1.0.0 schema surface. It does not create runtime routes, expand authorization, enable tool execution, or claim external deployment readiness.

## Locked compatibility invariants

`tests/test_arin_contract_backward_compatibility.py` is intentionally discoverable by the repository's canonical `unittest discover` path and verifies that:

- the supported contract version remains `1.0.0`;
- all admitted v1 schema models remain present;
- required v1 fields are not silently removed;
- all admitted models remain fail-closed with `additionalProperties: false`;
- supported discriminator/decision/risk enum values are not silently dropped;
- versioned models remain bound to the supported contract version; and
- the generated OpenAPI artifact remains schema-only (`paths: {}`), preserving the no-runtime-authority boundary.

## Evidence boundary

This file records the intended verification contract only. Promotion to `verified` requires the exact branch head to pass the repository's required CI/security/evidence workflows. Production readiness additionally requires enforced main-branch governance and real immutable external staging, World Room, canary, rollback and DR evidence.
