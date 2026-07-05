# AsyncAPI Inventory Fixture

This fixture demonstrates local API inventory discovery for AsyncAPI contracts and
the deterministic webhook acknowledgement scaffold compiler without executing
Hurl tests or contacting brokers, queues, webhooks, or external APIs.

Use it to prove Entroping can discover AsyncAPI channels and emit inventory evidence
from local files in `contracts/` using only value-free reporting commands.

It is also used by `entroping.bridge.asyncapi_to_hurl` tests to compile a local,
reviewable POST/202 Hurl scaffold from the checked-in contract. The scaffold uses
only aggregate operation counts and an explicit local target URL; it does not render
channel names, message names, payload fields, payload examples, broker addresses,
credentials, webhook URLs, or raw event bodies.

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

## Scaffold Proof

The compiler proof is intentionally library-level for now:

```python
from pathlib import Path

from entroping.bridge.asyncapi_to_hurl import compile_asyncapi_webhook_to_hurl

generated = compile_asyncapi_webhook_to_hurl(
    Path("contracts/orders.asyncapi.yaml").read_text(encoding="utf-8"),
    target_url="http://127.0.0.1:18084/webhooks/orders",
)
```

The generated Hurl is reviewable local evidence. Running it still belongs behind
normal Entroping/Hurl review and an explicitly local target.

## Design Notes

- The fixture uses a local `qanstitution.yaml` only, with no external calls.
- Contract payload values are intentionally non-sensitive and example-only.
- This fixture does not claim broker, queue, webhook delivery, or AsyncAPI runtime
  execution support.
