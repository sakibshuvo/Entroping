# AsyncAPI Inventory Fixture

This fixture demonstrates local API inventory discovery for AsyncAPI contracts without
executing Hurl tests or asserting runtime behavior.

Use it to prove Entroping can discover AsyncAPI channels and emit inventory evidence
from local files in `contracts/` using only value-free reporting commands.

## Files

```text
qanstitution.yaml
contracts/orders.asyncapi.yaml
```

## Quickstart

From the repository root:

```bash
uv sync --dev
```

From this fixture:

```bash
cd examples/asyncapi-events
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

- The fixture uses a local `qanstitution.yaml` only, with no external calls.
- Contract payload values are intentionally non-sensitive and example-only.
- This is an **inventory-only** fixture and does not claim any AsyncAPI execution
  runtime support.
