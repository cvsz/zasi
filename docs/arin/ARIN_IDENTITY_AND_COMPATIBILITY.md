# ARIN Identity and Compatibility

## Scope

This document is the first bounded Task 3 identity inventory. It records legacy JARVIS/ZARVIS identifiers that ARIN must preserve or retire deliberately before any executable, API, package, storage, or event identifier is renamed.

Assessed sources are limited to:

- `cvsz/zasi@b0f5a5725fbcfaea53fb3e0135b35f5ca483d596`
- `cvsz/zworkforce@634599e02f85d42a63535eb8c5410d6383f64d36/packages/zarvis`

No source code is copied from ZARVIS and this inventory does not add a runtime dependency.

## Identity policy

ARIN is the product/display identity for new ARIN surfaces and contracts. Existing machine-facing identifiers are compatibility identifiers until a separately tested migration explicitly changes them.

The following rules apply:

1. Do not rename an executable, API route, package name, environment variable, database/storage key, event type, or persisted identifier merely to change branding.
2. New canonical contracts use ARIN-owned, versioned identifiers and must not require a legacy JARVIS/ZARVIS name.
3. Legacy identifiers remain aliases only where an existing compatibility surface requires them.
4. Retired legacy endpoints remain retired; an identity migration must not reactivate them.
5. Alias acceptance must never widen authorization, tenant scope, tool authority, or physical-actuation authority.
6. Physical actuation remains disabled until deterministic safety and hardware-in-the-loop release gates are independently proven.

## ZASI inventory

| Legacy identifier | Kind | Current evidence | Compatibility decision |
|---|---|---|---|
| `/api/jarvis/chat` | REST route | Existing architecture and API tests identify it as retired with HTTP 410. | Preserve the 410 compatibility response until an explicit removal window is approved. Do not redirect it to a new execution path. |
| `/api/jarvis/stream` | SSE route | Existing architecture identifies it as retired with HTTP 410. | Preserve retirement semantics. Do not restore demo/delay streaming. |
| `/jarvis` | historical UI route | Present in historical SPA/change documentation. | Treat as legacy UI compatibility only; any redirect or removal requires route regression coverage. |
| `JARVIS` persona/default | runtime/display value | Present in backend persona selection and legacy truthfulness tests. | Do not rename in-place in this slice. Separate display branding from the machine value before migration. |
| `jarvis-msg` | CSS/UI class | Present in cockpit UI types/styles. | Internal presentation identifier; rename only with UI regression evidence, not as an API migration. |
| `zasi-jarvis` | container/image identity | Present in Docker Compose image/container naming. | Operational identifier; keep stable until installer/deployment compatibility impact is assessed. |
| `jarvis` package keyword | package metadata | Present in `package.json`. | Non-authoritative metadata; may be deprecated later without changing runtime identity. |
| `BRITISH_JARVIS_RESONANT_BARITONE` | legacy acoustic profile | Present under legacy speech implementation. | Treat as a legacy profile identifier; do not silently map it to privileged capability or action authority. |

## ZARVIS source inventory

The selected ZARVIS scope identifies itself as the `packages/zarvis` package and as the Z.A.R.V.I.S. assistant suite. Its source-of-truth remains `cvsz/zworkforce`; ARIN does not take ownership of that package name or its internal product identity.

| Source identifier | Kind | ARIN decision |
|---|---|---|
| `packages/zarvis` | repository/package path | Preserve as source provenance. Never rename it from ZASI and never copy the package wholesale. |
| `Z.A.R.V.I.S.` / `ZARVIS` | source product identity | Keep as source/reference identity. ARIN adapters expose ARIN-owned contracts instead of leaking a requirement for this display name. |
| ZARVIS service/contracts | potential integration boundary | Reuse only through a future bounded API/service adapter or reference implementation after ARIN consent/session/retention contracts are defined. |

## Stable versus display identity

For Task 3, identity is split into two classes:

- **Display/product identity:** New ARIN user-facing surfaces should use `ARIN` where doing so does not alter a compatibility contract.
- **Stable/machine identity:** Existing routes, package paths, persisted keys, event names, operational container names, persona enum-like values, and external integration identifiers remain unchanged until their consumers and rollback behavior are evidenced.

A display rename is not evidence that a machine identifier is safe to rename.

## Compatibility and deprecation rules

Before changing any stable legacy identifier, the implementation PR must:

1. enumerate known producers and consumers;
2. add regression tests for the existing identifier and proposed alias/replacement;
3. define an explicit compatibility window or document why immediate removal is safe;
4. preserve tenant/session/authentication and authorization semantics across aliases;
5. prove rollback without rewriting persisted state unless a separately approved migration requires it;
6. keep retired endpoints fail-closed rather than redirecting them into active execution;
7. update the migration ledger with exact-head evidence.

No fixed calendar deprecation deadline is invented by this inventory. A deadline begins only when a concrete public-contract migration identifies affected consumers and release cadence.

## Safety boundary

Identity aliases are naming compatibility only. They grant no capability. In particular, no `JARVIS`, `ZARVIS`, or `ARIN` label can bypass policy, approval, tenant/session binding, deterministic safety, simulator, or HIL gates. Browser, mobile, LLM, voice, and perception paths retain zero direct raw-actuator authority.

## Task 3 status after this slice

This document completes the bounded inventory/policy foundation only. Task 3 remains incomplete until concrete stable-ID/display-name decisions are backed by consumer evidence and regression tests before any executable/API identifier rename.