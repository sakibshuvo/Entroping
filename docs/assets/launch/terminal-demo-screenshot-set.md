---
title: Terminal Demo Screenshot Set
type: demo-assets
status: active
tags:
  - launch
  - terminal
  - demo
---

# Terminal Demo Screenshot Set

Captured from the real checkout fixture path:

```bash
artifact_dir="$(mktemp -d /Users/sakibshuvo/projects/entroping-demo-artifacts.XXXXXX)"
workdir="$(mktemp -d /Users/sakibshuvo/projects/entroping-demo-work.XXXXXX)"
ENTROPING_LIVE_DEMO_ARTIFACT_DIR="$artifact_dir" \
  ENTROPING_LIVE_DEMO_WORKDIR="$workdir" \
  scripts/live_demo_smoke.sh
```

Use these frames for a terminal GIF or a screenshot carousel.

## Frame 1: OpenAPI Becomes Hurl

```text
Generated 3 Hurl tests under tests/generated.
Wrote Hurl test: tests/generated/get_health.hurl
Wrote Hurl test: tests/generated/create_checkout.hurl
Wrote Hurl test: tests/generated/get_checkout.hurl
```

## Frame 2: Runtime Governance Passes

```text
Hurl run: 4 passed, 0 failed
Wrote latest run state: .entroping/latest-run.json
Wrote report: reports/run-latest.json
Wrote report: reports/junit.xml
Wrote report: reports/run-latest.html
```

## Frame 3: Reviewable Evidence

```text
run-latest.json  - machine-readable run summary
junit.xml        - CI-compatible test report
run-latest.html  - human-readable report screenshot source
```

## Screenshot Notes

- Show the command and output together; do not crop away `scripts/live_demo_smoke.sh`.
- Keep `4 passed, 0 failed` visible.
- Avoid showing local temp directory names in external posts.
- Do not show `.entroping/` internals except the latest-run path printed by the CLI.
