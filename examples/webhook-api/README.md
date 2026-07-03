# Webhook API Event-Contract Fixture

This fixture demonstrates how API inventory discovers webhook/event contracts from
local files before you execute any Hurl run or external service.

It is intentionally minimal and value-free:

- a local `qanstitution.yaml` with project metadata, and
- a sample `.event-contract.yaml` fixture under `contracts/`.

Use it with `entroping report api-inventory` to confirm event contracts are
visible to inventory evidence without external calls.

## Files

```text
qanstitution.yaml
contracts/order-events.event-contract.yaml
```

## Quickstart

From the repository root:

```bash
uv sync --dev
```

From this fixture:

```bash
cd examples/webhook-api
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

## Design Notes

- The fixture contains no real endpoints, no generated traffic, and no external URLs.
- Values in the event contract are limited to API artifact names and non-sensitive
  sample metadata.
- Run the command above before running any Hurl tests to establish contract
  evidence for webhook and event-driven API surfaces.
