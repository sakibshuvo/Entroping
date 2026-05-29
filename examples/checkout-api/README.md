# Checkout API Demo Fixture

This fixture is a tiny first-run example for Entroping's deterministic alpha loop.

It exists to reduce terminology friction: a new user should be able to see `qanstitution.yaml`, Hurl metadata comments, an OpenAPI source, and a test file in one place.

## Files

```text
demo_server.py
openapi.yaml
qanstitution.yaml
envs/local.env.example
tests/checkout_smoke.hurl
```

## Quickstart

From the repository root:

```bash
uv sync --dev
brew install hurl
```

Terminal 1:

```bash
python examples/checkout-api/demo_server.py --port 18080
```

Terminal 2:

```bash
cd examples/checkout-api
uv run --project ../.. entroping doctor
uv run --project ../.. entroping run --tag smoke --report json --report junit
```

Expected result:

```text
Hurl run: 1 passed, 0 failed
Wrote latest run state: .entroping/latest-run.json
Wrote report: reports/run-latest.json
Wrote report: reports/junit.xml
```

## Design Notes

- The example avoids real secrets.
- `smoke` tests should remain idempotent.
- Hurl metadata uses comments so the Hurl parser can safely ignore Entroping-specific data.
- The QAnstitution condition examples stay inside the supported small DSL.
- The checked-in `.hurl` file uses a literal local URL so the alpha quickstart does not depend on environment-variable loading.
- `envs/local.env.example` documents the intended future environment shape, but current alpha execution does not load it.
