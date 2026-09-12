# CI Failure-Mode Evidence

This document records expected production-readiness failure modes and the operator response. A red gate is evidence that the control worked; do not bypass it merely to make CI green.

## Container or dependency vulnerability gate

**Signal:** Trivy exits non-zero for a fixable HIGH or CRITICAL vulnerability.

**Response:** identify the package and fixed version, upgrade or replace the dependency/base image, rebuild, and rerun. If no upstream fix exists, the non-fixable finding remains visible in the evidence artifact; do not silently suppress it. Any temporary exception must name the CVE, owner, rationale, and expiry.

## Secret gate

**Signal:** repository secret scan exits non-zero.

**Response:** revoke/rotate the credential first, remove it from current source, assess history exposure, and only then rerun. Never add the detected secret to an allow-list merely to pass CI.

## Publish skipped after security failure

This is expected fail-closed behavior. Repair the failing upstream security job. Do not change `needs`, `if`, or exit-code handling to publish a rejected artifact.

## Missing branch governance

**Signal:** `main` accepts direct commits or has no required status checks.

**Response:** enable a GitHub ruleset/branch protection requiring pull requests, conversation resolution, required CI/security checks, and blocking force-push/deletion. Repository CI cannot self-prove this control; verify it from the GitHub branch/ruleset API or settings UI.

## Backup/restore failure

**Signal:** clean restore, schema verification, integrity check, or application smoke test fails.

**Response:** reject the backup as DR evidence, preserve logs, determine whether the fault is backup creation, encryption/authentication, restore tooling, schema ownership, or application compatibility, then rerun from a newly-created clean target.

## Immutable rollback failure

**Signal:** previous image digest cannot be redeployed or health/World Room checks fail after rollback.

**Response:** stop rollout, preserve both image digests and deployment logs, inspect schema compatibility and stateful dependencies, and keep production GO blocked.

## Corpus/reference-set regression

`tests/test_reference_corpus.py` validates the checked-in analyzer, RAG ranking, PR salvage, discussion triage, harness compatibility, and CI failure-mode reference sets. A failure means the fixture contract changed or became incomplete; update expected behavior only with a reviewed reason rather than weakening the assertion.
