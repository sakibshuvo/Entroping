# GraphQL API Demo Fixture

This fixture shows GraphQL as plain Hurl-over-HTTP. Entroping does not add a
GraphQL execution engine here; Hurl sends JSON POST requests to `/graphql`, and
QAnstitution gates assert observable HTTP and JSON response behavior.

Use it when you want a concrete example of catching body-level GraphQL failures,
especially top-level GraphQL `errors` that can appear even when the HTTP status
is `200`.

## Files

```text
demo_server.py
qanstitution.yaml
schema.graphql
envs/local.env.example
tests/graphql_smoke.hurl
```

## Quickstart

From the repository root:

```bash
uv sync --dev
brew install hurl
```

Terminal 1:

```bash
python examples/graphql-api/demo_server.py --port 18082
```

Terminal 2:

```bash
cd examples/graphql-api
uv run --project ../.. entroping doctor
uv run --project ../.. entroping run --tag graphql --report html --report json --report junit
```

Expected result:

```text
Hurl run: 1 passed, 0 failed
Wrote latest run state: .entroping/latest-run.json
Wrote report: reports/run-latest.html
Wrote report: reports/run-latest.json
Wrote report: reports/junit.xml
```

## Design Notes

- The checked-in Hurl file uses literal local URLs for a quick deterministic smoke path.
- `schema.graphql` is the local SDL fixture used by the deterministic scaffold compiler.
- `envs/local.env.example` is safe to commit and reserved for generated or copied variants.
- The governance rule `graphql_no_top_level_errors` proves that protocol-specific response semantics can be enforced without a protocol-specific runner.
- The fixture intentionally keeps queries small and avoids real user data, secrets, cookies, or tokens.
