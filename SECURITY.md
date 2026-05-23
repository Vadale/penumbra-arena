# Security policy

Penumbra includes a real-ish crypto + chain stack used to teach
adversarial intuition. We take vulnerability reports seriously,
especially anything in `packages/crypto/`, `packages/chain/`, or
`packages/attacker/`.

## Supported versions

Penumbra is pre-1.0. Only the latest `main` is supported.

| Version | Status   |
|---------|----------|
| 0.1.x   | active   |
| < 0.1   | none     |

## Reporting a vulnerability

Email the maintainer with details and a clear reproduction:

- vadale93@gmail.com  (temporary; a dedicated address will be set
  closer to a stable release)

Please use plain text or a self-contained PoC. Do not open a public
GitHub issue for sensitive reports.

## Response SLA

- Acknowledgement within **7 days**.
- Fix or roadmap within **30 days** for `crypto/`, `chain/`,
  `attacker/`; **60 days** elsewhere.

## Scope

| Area                       | Severity priority |
|----------------------------|-------------------|
| `packages/crypto/**`       | HIGH              |
| `packages/chain/**`        | HIGH              |
| `packages/attacker/**`     | HIGH              |
| `packages/transport/**`    | MEDIUM            |
| Everything else            | MEDIUM            |

Penumbra is an educational lab. The threat model assumes a curious
local user, not a hardened production deployment. Findings that
require trivial code modifications (e.g. "I changed `True` to
`False` in `verify()` and it accepted") are still welcome but treated
as documentation issues rather than vulnerabilities.

## PGP key

(Maintainer to add a key block here before the OSS launch.)

## Coordinated disclosure

We follow standard 90-day coordinated disclosure for HIGH findings.
Public release of details only after a fix is merged + tagged.
