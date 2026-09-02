# Legacy adapter quarantine

The modules under `src/` that predate the governed control plane are retained
for compatibility and research inspection only. They are not imported by
`backend.app`, the Docker entrypoint, Electron, or the `zasi` console script.

Any future adapter must expose a typed interface, register a stable capability,
carry an explicit availability/evidence state, and pass the same policy,
approval, audit, and broker tests before it can be reachable from v2.
