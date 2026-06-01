# OWASP API Top 10 Starter Policy Pack

This is an OWASP API Security Top 10 2023-inspired starter pack for Entroping
QAnstitution imports. It gives policy-pack authors and early users a concrete,
inspectable example that maps recognizable API security concerns to runtime
Hurl assertions.

Reference: <https://owasp.org/API-Security/editions/2023/en/0x11-t10/>

This pack is not official OWASP endorsement, not complete OWASP compliance, and
not certification evidence. These are starter examples, not certification
evidence. Read every gate before adopting it.

Validate the pack locally:

```bash
uv run python scripts/policy_pack_smoke.py --pack examples/policy-packs/owasp-api-top-10 --strict
```

Use it by vendoring this directory under a project root and importing the pack
entrypoint from the project's `qanstitution.yaml`:

```yaml
imports:
  - "./policy-packs/owasp-api-top-10/qanstitution.yaml"
```

## Included Starter Gates

| Gate | Inspired by | Intent |
| --- | --- | --- |
| `owasp-api.authz.object_access_denied` | API1 Broken Object Level Authorization and API5 Broken Function Level Authorization | Tests tagged `authz` should prove unauthorized object or tenant access does not succeed. |
| `owasp-api.authn.unauthenticated_denied` | API2 Broken Authentication | Tests tagged `authn` should prove unauthenticated calls do not succeed. |
| `owasp-api.resources.no_server_errors` | API4 Unrestricted Resource Consumption and API6 Unrestricted Access to Sensitive Business Flows | Governed API tests should not return server errors. |
| `owasp-api.resources.latency_budget` | API4 Unrestricted Resource Consumption | Governed responses should stay inside a starter latency budget. |
| `owasp-api.misconfig.request_id` | API8 Security Misconfiguration | Responses should include a request ID for incident review. |
| `owasp-api.inventory.deprecated_endpoint_header` | API9 Improper Inventory Management | Tests tagged `deprecated` should expose a `Deprecation` header. |

`owasp-api.resources.no_server_errors` is final because this starter pack treats
server errors as outside the acceptable baseline for governed tests. Other gates
are intentionally overrideable because teams differ on authentication status
codes, deprecation policy, latency targets, and request-correlation headers.

## Scope

This pack demonstrates how to encode a small runtime baseline. It does not
cover every OWASP API Security Top 10 category, prove design-time authorization
correctness, replace threat modeling, replace manual review, or certify an API.

Premium or separately maintained packs can add deeper coverage, review cadence,
organization controls, reports, and support while still exporting local,
inspectable QAnstitution files before `entroping run` enforces anything.
