---
name: vistaverse-review
description: Perform an evidence-based cross-role review of the VISTAVERSE repository covering architecture, correctness, tests, security, supply chain, performance, observability, maintainability, and deployment reliability.
---

Use this skill for a full repository audit or a review of a VISTAVERSE change.

Review in parallel roles: architecture/data-flow, backend/frontend correctness, security/supply chain, test quality,
and deployment/operations. Then cross-check each finding against the other roles and local tests.

For every finding report:

1. Severity and repair priority.
2. Exact file path plus line, symbol, or configuration key.
3. Trigger or affected path.
4. Confirmed evidence and impact scope.
5. A minimal executable remediation that preserves business intent.

Treat build success as separate from runtime and business-path verification. Distinguish confirmed defects, measured
limitations, hardening suggestions, and unverified gaps. Do not report a style preference as a defect. Do not expose
secret values. Safe, narrow fixes may be applied after evidence is collected; destructive cleanup, data migration,
credential changes, or production actions require an explicit scope and rollback evidence.

Use the repository's own commands: backend `python -m pytest`, `python -m compileall -q app tests`, frontend/admin
`npm test`, `npm run lint`, `npm run build`, and the Compose `config --quiet` checks.
