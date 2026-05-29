# Checkout API Demo Fixture

This fixture is a tiny first-run example for Entroping.

It exists to reduce terminology friction: a new user should be able to see `qanstitution.yaml`, Hurl metadata comments, an OpenAPI source, and a test file in one place.

## Files

```text
openapi.yaml
qanstitution.yaml
envs/local.env.example
tests/checkout_smoke.hurl
```

## Intended Flow

From the repository root:

```bash
uv sync --dev
uv run entroping doctor
```

Once the runtime runner is implemented, this fixture should support:

```bash
uv run entroping run --env local --tag smoke --report html
```

## Design Notes

- The example avoids real secrets.
- `smoke` tests should remain read-only or idempotent.
- Hurl metadata uses comments so the Hurl parser can safely ignore Entroping-specific data.
- The QAnstitution condition examples stay inside the supported small DSL.

