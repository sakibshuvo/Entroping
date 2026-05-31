# Support API Demo Fixture

This fixture is intentionally different from the checkout fixture. It models a
small support-ticket API with filtered list reads, required request headers,
path parameters, POST creation, PATCH mutation, and mutation audit headers.

Use it when you want to check that Entroping examples are not overfit to a
single checkout flow.

## Files

```text
demo_server.py
openapi.yaml
qanstitution.yaml
envs/local.env.example
tests/support_smoke.hurl
tests/generated/
```

## Quickstart

From the repository root:

```bash
uv sync --dev
brew install hurl
```

Terminal 1:

```bash
python examples/support-api/demo_server.py --port 18081
```

Terminal 2:

```bash
cd examples/support-api
uv run --project ../.. entroping doctor
uv run --project ../.. entroping run --tag support --report html --report json --report junit
```

Expected result:

```text
Hurl run: 1 passed, 0 failed
Wrote latest run state: .entroping/latest-run.json
Wrote report: reports/run-latest.html
Wrote report: reports/run-latest.json
Wrote report: reports/junit.xml
```

To regenerate Hurl tests from `openapi.yaml`:

```bash
uv run --project ../.. entroping architect build --new --tag support
cp envs/local.env.example envs/local.env
uv run --project ../.. entroping run --env local --tag support --report html --report json --report junit
```

## Design Notes

- The example avoids real secrets and real customer data.
- `support` tests should remain idempotent.
- POST requests require `X-Customer-Id`; PATCH requests require `X-Agent-Id`.
- QAnstitution gates exercise `path startswith`, `method ==`, and `tags contains` conditions.
- The demo server returns `X-Request-Id`, `Location`, and `X-Audit-Id` headers so governance rules can enforce observable runtime behavior.
- The checked-in `.hurl` file uses literal local URLs for a quick deterministic smoke path.
- `envs/local.env.example` is safe to commit; copy it to the gitignored `envs/local.env` before running generated tests.
- Generated OpenAPI tests are written under `tests/generated/` and use `{{base_url}}` from `--env local`.
