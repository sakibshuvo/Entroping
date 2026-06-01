---
title: Downstream Smoke Evidence
type: runbook
status: active
tags:
  - stable-core
  - downstream
  - evidence
---

# Downstream Smoke Evidence

Stable-core claims need evidence that Entroping works outside its own checkout.
The downstream smoke harness creates a temporary external API project, starts a
local fixture server, and runs Entroping through the public CLI against that
external project.

Run it from the Entroping repository:

```bash
uv run python scripts/downstream_smoke.py
```

For machine-readable output:

```bash
uv run python scripts/downstream_smoke.py --format json
```

To keep reviewed artifacts for a release or investigation:

```bash
uv run python scripts/downstream_smoke.py --artifact-dir /tmp/entroping-downstream-proof
```

The artifact directory receives:

- `downstream-smoke-evidence.json`
- `run-latest.json`
- `run-latest.html`
- `junit.xml`

## What It Proves

- Entroping can be invoked through `uv run --project <repo-root> entroping ...`
  while the current working directory is an external project.
- The external project owns its own `qanstitution.yaml`, Hurl test, reports, and
  `.entroping/` runtime state.
- Hurl remains the API assertion executor.
- QAnstitution gates are injected into temporary execution copies.

## What It Does Not Prove

This harness does not satisfy real downstream user feedback. It is a local,
maintainer-controlled integration proof. Stable-core remains blocked until at
least one project outside this repository runs Entroping, reports friction, and
that feedback is recorded as release evidence.

It also does not prove package-index installation. The package-index blocker
still requires TestPyPI/PyPI Trusted Publishing proof.
