# Contributing to ZASI

Thank you for your interest in contributing to **ZASI (Zero-Entropy Autonomous Superintelligence Infrastructure)**!

---

## 🚀 Quick Development Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/cvsz/zasi.git
   cd zasi
   ```

2. **Run the automated builder and test suite**:
   ```bash
   ./install.sh
   ```

3. **Start the local development server**:
   ```bash
   make server
   # Access the J.A.R.V.I.S. Command Cockpit at http://localhost:8080
   ```

---

## 🧪 Testing Guidelines

Before opening a PR, ensure all 172 tests pass:
```bash
make test-all
```
This runs:
- 165 subsystem unit tests
- 7 REST/WebSocket API integration tests
- 11 React 18 / React Router v6 component structural assertions
- Code coverage analysis (minimum threshold: 60%, current: 81.31%)

---

## 🔒 Security & Code Standards

1. **Zero-Taint Logging**: Never print or log fields containing sensitive cryptographic materials, keys, or hardware attestation digests in plain text.
2. **First-Order SMT Invariants**: Every new subsystem must return a typed `@dataclass` report and define formal invariant bounds.
3. **Workflow Permissions**: Any new GitHub Actions workflows must declare explicit least-privilege permissions (`permissions: contents: read`).
