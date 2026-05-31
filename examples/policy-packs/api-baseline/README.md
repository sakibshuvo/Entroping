# API Baseline Policy Pack

This is a minimal reusable QAnstitution policy-pack example. It proves the pack
layout without adding registry, install, or remote-import behavior.

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
