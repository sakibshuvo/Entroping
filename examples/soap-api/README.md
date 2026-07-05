# SOAP API Demo Fixture

This fixture shows SOAP as plain Hurl-over-HTTP. Entroping does not add a SOAP
execution engine here; Hurl sends an XML request with `SOAPAction`, and
QAnstitution gates assert observable HTTP headers and XML response behavior.

Use it when you want a concrete legacy-protocol example without changing the
deterministic runtime boundary.

## Files

```text
demo_server.py
contracts/orders.wsdl
qanstitution.yaml
envs/local.env.example
tests/soap_smoke.hurl
```

## Quickstart

From the repository root:

```bash
uv sync --dev
brew install hurl
```

Terminal 1:

```bash
python examples/soap-api/demo_server.py --port 18083
```

Terminal 2:

```bash
cd examples/soap-api
uv run --project ../.. entroping doctor
uv run --project ../.. entroping run --tag soap --report html --report json --report junit
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
- `contracts/orders.wsdl` is a local-only contract fixture for inventory and scaffold generation.
- `envs/local.env.example` is safe to commit and reserved for generated or copied variants.
- The request demonstrates `SOAPAction` and a SOAP XML envelope.
- The governance rule `soap_envelope_success` proves that XML response semantics can be enforced through Hurl `xpath` assertions.
- The fixture intentionally avoids real order, customer, credential, cookie, or token data.
- `entroping.bridge.soap_to_hurl.compile_wsdl_to_soap_hurl()` can produce a deterministic smoke scaffold from the WSDL without rendering WSDL operation names, service addresses, SOAPAction URLs, or XML payload contents.
