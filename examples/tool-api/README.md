# Tool API Contract Fixture (MCP-style example)

This fixture is a minimal tool-style REST API contract for local API evidence
inventory. It demonstrates that tool APIs can be governed through normal Entroping
workflows without requiring MCP server/runtime dependencies.

It includes:

- a local `qanstitution.yaml`, and
- a local OpenAPI contract `openapi.yaml`.

## Files

```text
qanstitution.yaml
openapi.yaml
```

## Quickstart

From this fixture:

```bash
cd examples/tool-api
uv run --project ../.. entroping doctor
uv run --project ../.. entroping report api-inventory --output md
```

Expected proof:

```text
Wrote API inventory: reports/api-inventory.md
```

For machine-readable evidence:

```bash
uv run --project ../.. entroping report api-inventory --output json
```

Expected proof:

```text
Wrote API inventory: reports/api-inventory.json
```

## Design notes

- This fixture is inventory-first and does not add MCP runtime, provider SDKs, or
  server dependencies.
- Run `entroping architect build` only for generated test needs after this inventory
  proves the contract shape.
- `entroping run` is for executed checks only and uses generated/annotated Hurl
  files.
