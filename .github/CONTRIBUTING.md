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

Before opening a PR, ensure the full Python suite and frontend checks pass:
```bash
make test-all
npm ci --ignore-scripts
npm run typecheck
npm run build
node tests/test_components.js
```
This runs:
- the repository's current Python unit and integration suite
- React 19 / React Router v7 component structural assertions
- the TypeScript entrypoint typecheck and Vite production build
- Code coverage analysis (minimum threshold: 60%, current: 81.31%)

---

## 🔒 Security & Code Standards

1. **Zero-Taint Logging**: Never print or log fields containing sensitive cryptographic materials, keys, or hardware attestation digests in plain text.
2. **First-Order SMT Invariants**: Every new subsystem must return a typed `@dataclass` report and define formal invariant bounds.
3. **Workflow Permissions**: Any new GitHub Actions workflows must declare explicit least-privilege permissions (`permissions: contents: read`).
