# API Baseline Policy Pack

This is a minimal reusable QAnstitution policy-pack example. It proves the pack
layout without adding registry, install, or remote-import behavior.

The `entroping-policy-pack.yaml` manifest records local provenance evidence:
pack source, license, supported Entroping version range, declared gates, gate
source files, final flags, and the command maintainers run to reproduce the
evidence:

```bash
uv run python scripts/policy_pack_smoke.py --strict
```

That proof confirms this local example manifest matches the loaded
QAnstitution gates. It does not prove package signing, remote-registry
authenticity, commercial policy review, or that every consumer project should
accept these gates unchanged.

Use it by vendoring this directory under a project root and importing the pack
entrypoint from the project's `qanstitution.yaml`:

```yaml
imports:
  - "./policy-packs/api-baseline/qanstitution.yaml"
```

Included gate groups:

- `api-security.*` for server-error and request-correlation checks.
- `api-reliability.*` for default latency expectations.

`api-security.no_5xx` is final because this example treats server errors as a
non-negotiable API baseline. Other gates are intentionally overrideable by the
consumer project.

This pack does not include agents, secrets, traffic state, source specs, or
provider configuration.
