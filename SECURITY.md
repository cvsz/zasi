# Security Policy

## Supported Versions

ZASI is under active development. Security fixes are provided for the current
major release line only.

| Version | Supported |
| --- | --- |
| 32.x | :white_check_mark: |
| < 32 | :x: |

Pre-release, research-only, and historical compatibility surfaces are not
production security commitments unless explicitly identified as supported in
the release notes.

## Reporting a Vulnerability

Please report suspected vulnerabilities privately through GitHub's
**Security > Report a vulnerability** flow for this repository when available.
Do not open a public issue for credentials, authentication bypasses, remote code
execution, sandbox escapes, cross-tenant access, SSRF, secret disclosure, or
other exploitable security defects.

A useful report should include:

- affected revision or release;
- impacted component and deployment profile;
- reproduction steps or a minimal proof of concept;
- expected versus observed behavior;
- known prerequisites and impact;
- any evidence that secrets or user data were exposed.

## Response Expectations

Maintainers should acknowledge a valid private report as soon as practical,
triage severity, reproduce the issue, and track remediation privately until a
safe disclosure can be made. Critical issues that can compromise credentials,
tenant isolation, policy enforcement, release integrity, or execution
boundaries take priority over feature work.

## Security Boundaries

The governed control plane is the authoritative supported runtime. Historical
prototype and compatibility code does not imply a production execution grant.
External writes, research execution, runtime self-modification, and physical
actuation remain disabled unless a release explicitly provides and verifies the
required policy, approval, audit, recovery, and deployment evidence.

Never commit real API keys, signing keys, database credentials, access tokens,
or production secrets. Local examples must use placeholders or generated
per-installation values.
