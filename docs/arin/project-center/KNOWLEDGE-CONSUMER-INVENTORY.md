# ARIN knowledge consumer inventory

## Scope

This inventory is the bounded Task 5 evidence step after acceptance of ADR-ARIN-0003. It records actual ARIN/zknowbase consumers before any canonical promotion or consumer migration. It does not enable a live service endpoint, write transport, new repository dependency, or physical actuation.

## Current direct zknowbase boundary

Repository search on the Task 5 baseline identified the ARIN-owned zknowbase boundary in:

- `backend/arin/knowledge.py` — bounded read contract/transport and normalized failures.
- `backend/arin/knowledge_write.py` — fail-closed authorization gate for a future write path; it performs no ingestion/network mutation.
- `tests/test_arin_zknowbase_contract.py` — read-contract/transport regression evidence.
- `tests/test_arin_zknowbase_write_policy.py` — write-policy regression evidence.
- `docs/arin/integrations/ZKNOWBASE.md` and ADR/project-center records — documentation/evidence consumers only.

No separate production ARIN runtime consumer of the zknowbase adapter was identified by the repository search used for this bounded inventory. Legacy modules containing generic `knowledge` terminology are not treated as zknowbase consumers without an explicit adapter import/call or zknowbase service reference.

## Migration implication

There is therefore no existing production consumer that can truthfully be marked migrated in this slice. `ARIN-MIG-0008` remains `verified`, not `canonical`. Canonical promotion still requires a bounded consumer to use the accepted adapter contract and evidence that proves:

1. tenant/session scope is propagated server-side and mismatches fail closed;
2. service credentials remain server-held and are never inherited by browser/mobile/generic tool callers;
3. provenance survives successful search/query responses;
4. required knowledge failures fail closed while explicitly optional knowledge can degrade without fabricating grounding;
5. rollback can disable the consumer integration and restore its prior behavior without zknowbase mutation or data loss;
6. exact-head tests and required CI gates pass for the migration slice.

## Rollback for this inventory

Documentation-only: revert the inventory commit/PR. No runtime configuration, data, schema, service credential, source repository, or deployment state changes.

## Safety boundary

This inventory grants no action authority. Knowledge output cannot reach raw joint, torque, velocity, PWM, vendor actuator, or equivalent physical-control APIs. Physical actuation remains disabled pending deterministic safety-supervisor and hardware-in-the-loop release evidence.
