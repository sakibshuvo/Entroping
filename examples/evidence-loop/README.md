# Evidence Loop Demo

This fixture demonstrates a local, value-free evidence loop for report packets that do not rely on
external services or provider keys.

## Files

```text
run-evidence-loop-demo.sh
```

## Purpose

Use this demo to generate a local report chain that is useful for PR/runtime reviews and
design-partner handoffs:

- `runtime-card` (stabilized launch path)
- `handoff` (stabilized launch path)
- `design-partner-feedback` (design-partner packet)
- `evidence-links` (experimental design-partner packet)
- `notification-packet` (experimental design-partner packet)
- `evidence-portal` (experimental design-partner packet)

The commands write artifacts to a temporary directory only; no generated files are committed.

## Quickstart

From the repository root:

```bash
./examples/evidence-loop/run-evidence-loop-demo.sh
```

To keep artifacts around longer for manual inspection, set:

```bash
export ENTROPING_DEMO_TMP_BASE=/tmp/entroping-evidence-loop
export ENTROPING_DEMO_KEEP_ARTIFACTS=1
```

The default path is `$HOME/.cache/entroping-demo`.
