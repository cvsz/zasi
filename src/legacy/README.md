# Legacy adapter quarantine

The modules under `src/legacy/` are retired prototype adapters that predate
the governed control plane. They are retained for compatibility and research
inspection only.

## Quarantine rules

1. `backend.app`, the Docker entrypoint, Electron, and the `zasi` console
   script MUST NOT import from `src.legacy`.
2. No module in `src/legacy` may be imported by the authoritative application
   unless it is wrapped by a typed adapter and listed in the capability registry.
3. Legacy modules MUST NOT be referenced from `src/control_plane/`.
4. Tests that must exercise legacy behavior are explicitly listed in
   `tests/test_legacy_truthfulness.py` and `tests/test_security_hardening.py`;
   all other tests must import from `src.control_plane` or `backend.app`.

## Admission criteria

Any future adapter that wishes to leave quarantine must:

- expose a typed interface in `src/control_plane/`;
- register a stable capability identifier;
- carry explicit `availability` and `evidence_state` metadata;
- pass policy, approval, audit, and broker tests;
- render truthful disclosure in the cockpit.

## Evidence boundary

These modules are not covered by the current release evidence. Their
implementation state, runtime state, and evidence state are individually
`research_only`, `disabled`, or `unavailable` unless explicitly upgraded
through the admission criteria above.
