# Aha Broken Endpoint Fixture

This fixture is a local, value-free proof that Entroping catches an endpoint that is
mentioned in Hurl but intentionally absent in the API contract before commit: the
`/products/ghost` request in `tests/broken_endpoint.hurl` must fail the
`no_missing_product_endpoint` QAnstitution gate because the demo server returns
`404` for that path.

## Quickstart

From the repository root:

```bash
cd examples/aha-broken-endpoint
cp envs/local.env.example envs/local.env
python demo_server.py --port 18110
```

In a second terminal:

```bash
cd examples/aha-broken-endpoint
uv run --project ../.. entroping doctor
uv run --project ../.. entroping run --env local --tag aha-endpoint --report json --report junit
```

Expected result:

```text
Hurl run: 0 passed, 1 failed
```

The failure should be a QAnstitution gate failure on `no_missing_product_endpoint`
for `GET /products/ghost`, demonstrating the missing-endpoint failure path.
