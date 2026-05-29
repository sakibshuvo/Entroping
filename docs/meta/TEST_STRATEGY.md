---
title: Test Strategy
type: runbook
status: active
tags:
  - testing
  - regression
  - tdd
  - coverage
---

# Test Strategy

Entroping uses a risk-based test pyramid. The goal is not decorative coverage; the goal is deterministic evidence that the governance loop works.

## Test Pyramid

| Layer | Purpose | Examples |
| --- | --- | --- |
| Unit | Prove pure logic and schemas | QAnstitution models, condition parser, bridge compilers, gate matching |
| Adapter | Prove boundary behavior without live systems | CLI commands, filesystem writes, subprocess stubs, YAML loading, report writers |
| Integration | Prove multiple Entroping subsystems work together | policy load -> gate compile -> temp Hurl execution copy -> result model |
| Smoke | Prove installed CLI still boots | `entroping --help`, `entroping --version`, `entroping doctor` |
| Regression | Freeze bugs and risky behaviors | import cycles, redaction gaps, path traversal, source Hurl mutation |
| Security | Prove sensitive boundaries stay controlled | secret redaction, path handling, subprocess args, dependency audits |

## Required Commands

Fast feature gate:

```bash
scripts/feature_gate.sh
```

Regression suite:

```bash
scripts/regression.sh
```

Security-sensitive work:

```bash
scripts/feature_gate.sh --security
scripts/regression.sh --security
```

## Coverage Expectations

- New pure logic needs unit tests.
- New CLI, filesystem, subprocess, YAML, report, proxy, or LLM behavior needs adapter tests.
- Bug fixes need regression tests when the bug is reproducible.
- Features crossing subsystem boundaries need integration or smoke coverage.
- Hurl runner work needs fixture `.hurl` files and real Hurl smoke checks once `hurl` is available.
- Security-sensitive behavior needs negative tests for unsafe input, redaction, or failure mode.

## Pytest Markers

Use these markers as the suite grows:

- `unit`: pure logic and schema tests.
- `adapter`: CLI, filesystem, subprocess, YAML, report, proxy, and LLM boundary tests.
- `integration`: cross-subsystem tests.
- `smoke`: boot and command-surface checks.
- `regression`: tests added for fixed bugs or fragile behavior.
- `security`: security-sensitive negative tests.

## Regression Suite Growth

Today `scripts/regression.sh` runs the feature gate plus CLI smoke checks. As the deterministic core lands, add:

1. QAnstitution import and merge fixtures.
2. Hurl discovery and metadata fixtures.
3. Gate injection fixtures proving source files are not mutated.
4. Hurl subprocess stubs and real Hurl smoke checks.
5. JSON/JUnit report fixtures.
6. Redaction tests for reports and future proxy capture.

Keep the regression suite boring, deterministic, and local-first.
