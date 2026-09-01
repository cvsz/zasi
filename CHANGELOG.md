# Changelog

All notable changes to the **ZASI** (Zero-Entropy Autonomous Superintelligence Infrastructure) project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [32.0.0] - 2026-09-01
### Added
- **Subsystems #169–#176 (Hyper-Cosmology & Singularity Milestone)**:
  - #169: Tachyon-Mediated Retrocausal Error Mitigation Matrix
  - #170: Stellar-Mass Gravitational Wave Interferometer Array
  - #171: Ultra-Relativistic Plasma Wakefield Positron Accelerator
  - #172: Quantum Vacuum Casimir Force Actuator Core
  - #173: Trans-Galactic Dark Matter Axion Haloscope Detector
  - #174: Non-Hermitian Exceptional Point Sensor Lattice
  - #175: Hyperbolic Spacetime Geodesic Wormhole Router
  - #176: Infinite-Dimensional Hilbert Space Singularity Sovereign Supreme
- **Automated Package Ecosystem Deployment**:
  - Live PyPI publishing workflow via OIDC Trusted Publishing and `pypa/gh-action-pypi-publish`.
  - npm automated distribution workflow (`zasi-cockpit` on npm Registry).
  - GitHub Pages Command Cockpit live hosting (`cvsz.github.io/zasi`).
  - GitHub Container Registry (GHCR) Docker multi-platform builds.
- **Full Community & Agent Framework**:
  - 9 specialized domain skills in `.agents/skills/` (Quantum QEC, Formal SMT, RSI, Real Hardware, Security, MCP, etc.).
  - 7 specialized multi-agent personas in `.agents/agents/`.
  - GitHub Discussion templates for RFC subsystem proposals, Q&A, and community onboarding.

### Security
- Resolved all CodeQL static analysis alerts: DOM XSS (`textContent`), Subresource Integrity (SRI) hashes on CDN scripts, sensitive log filtering in `main.py`, and workflow least-privilege permissions.

---

## [31.0.0] - 2026-09-01
### Added
- **React 18 + React Router v6 SPA**: Complete browser-based command cockpit with 5 distinct routes (`/`, `/jarvis`, `/subsystems`, `/cockpit`, `/mcp`).
- **Command Palette (`Ctrl+K` / `Cmd+K`)**: Modal overlay for keyboard-driven navigation, state mutations, and daemon triggers.
- **Dark/Light Theme System**: CSS variable-driven theming engine with local storage persistence.
- **Toast Notification Engine**: Non-blocking asynchronous notifications for system actions and WebSocket state changes.
- **Web Speech Synthesis & Voice Recognition**: Two-way neural voice interface with pitch/rate modulation across J.A.R.V.I.S., F.R.I.D.A.Y., and E.D.I.T.H. personas.
- **WebSocket Server (RFC 6455)**: Real-time 2-second streaming telemetry and log broadcasts over `/ws`.
- **API Key & Rate Limiting Middleware**: Secure access control via `X-API-Key` headers and sliding-window 60 req/min throttles.
- **SQLite Persistence**: Local state synchronization to `data/zasi_state.db`.
- **OpenAPI 3.0 Auto-Documentation**: Live interactive endpoint specification served at `/api/openapi.json`.
- **Server-Sent Events (SSE)**: Word-by-word streaming chat completions on `/api/jarvis/stream`.
- **Google Gemini API Native Bridge**: Multi-turn conversation context grounding with Gemini 2.0 Flash fallback.
- **Docker & Docker Compose**: Automated containerized deployment stack.
- **Electron Desktop Application**: Cross-platform desktop shell wrapping the full Python/React stack.
- **Vite & npm Build Configuration**: Production bundler setup and structural testing suite.

---

## [30.0.0] - 2026-09-01
### Added
- Subsystems #161–#168 (Omniversal Apex Prime Milestone)
- Three.js 3D hypergraph visualization engine.
- 172-test comprehensive suite.
