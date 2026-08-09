---
title: Studio Mutation Workflow Design
description: "Define the safety gate for any future Studio workflow that writes tests, config, or baselines."
type: technical
status: proposed
tags:
  - studio
  - mutation
  - safety
  - tui
---

# Studio Mutation Workflow Design

This is the design gate for any future Studio workflow that edits tests,
updates config, reruns suites, promotes baselines, or writes runtime state.
No Studio mutation implementation is planned for v0.3.

The current product boundary remains unchanged: read-only Studio remains the only shipped Studio behavior.

## Decision

Studio may eventually become an action surface, but only as a review-first
adapter over existing deterministic CLI and core workflows. Textual widgets must
not become independent writers, runners, or policy engines.

Use existing CLI/core writers instead of Textual widgets writing files directly.
Future Studio actions must call the same validated use cases as CLI commands,
produce the same reports, and preserve the same redaction, path-safety,
subprocess, and rollback behavior.

Mutation commands must produce reviewable file diffs before writing. Anything
that cannot be previewed, explained, confirmed, and rolled back should stay out
of Studio.

## User Flows

Future mutation candidates must be designed as separate issues before code:

| Flow | Possible future action | Required review artifact |
| --- | --- | --- |
| Rerun suite | Trigger the existing deterministic run workflow | Command preview, selected env/tags, expected report paths |
| Promote drift baseline | Promote a reviewed candidate baseline | Diff from candidate to active baseline and source run metadata |
| Edit QAnstitution | Apply a narrow policy edit | YAML diff, validation result, affected gate IDs |
| Edit Hurl test | Apply an Architect-owned or managed-block edit | Hurl diff, parser validation result, ownership mode |
| Freeze session | Convert selected redacted traffic into Hurl | Session summary, generated Hurl preview, parser validation result |

Every flow must preserve a CLI equivalent or report artifact. Studio can make
the review more ergonomic, but the CLI/report path remains the durable product
truth.

## Safety Boundaries

Future Studio mutation design must preserve these boundaries:

- `entroping run` stays deterministic and LLM-free.
- Hurl remains the only API execution engine.
- Studio must not perform Python HTTP execution.
- Studio must not call LLM providers while executing deterministic run actions.
- Studio must not bypass existing path-safety, symlink, parser-validation, or
  QAnstitution validation boundaries.
- Studio must not mutate source `.hurl` files during run; gate injection still
  uses temporary execution copies.
- Studio must not write `.entroping` state directly except through an accepted
  core use case.
- Studio must not create hidden background mutations. Every write has an
  explicit user action, preview, confirmation, result, and recovery path.

## Review And Confirmation Model

Future Studio actions need a two-step confirmation model:

1. Preview: show sanitized intent, selected files/state, generated artifacts,
   validation status, and a diff or equivalent structured change summary.
2. Confirm: require an explicit second action after preview. High-risk actions
   may require typing the target file, gate ID, or baseline name.

Confirmation output must record:

- action name;
- target paths or report paths;
- preflight validation result;
- changed files;
- generated reports;
- rollback instructions.

rollback must be part of the design for every write. Acceptable rollback
strategies include atomic replacement with kept previous content, generated
candidate files that require manual promotion, or clear Git recovery commands
when the project is under version control.

## Redaction And Secret Handling

Never render raw secrets, raw captured traffic, provider output, or unredacted Hurl output in Studio.

Studio mutation previews must use the same redaction and escaping boundaries as
CLI reports:

- redact token-shaped values and configured secret fields;
- show traffic counts, route identities, and body summaries, not raw bodies;
- show Hurl parser and provider failures as safe categories, not copied streams;
- escape all report-derived text before rendering in Textual widgets;
- avoid storing previews in tracked files or long-lived state unless they are
  sanitized artifacts intentionally produced by a core use case.

## Test Strategy

Any future mutation implementation must include unit tests, adapter tests, CLI tests, and end-to-end smoke coverage appropriate to the risk.

Minimum test expectations:

- pure view-model tests for preview rows and confirmation state;
- adapter tests proving Textual widgets do not write files directly;
- core/use-case tests proving validation, atomic writes, rollback, and
  redaction behavior;
- CLI parity tests proving the same action works outside Studio;
- regression tests proving raw secrets and raw captured traffic are not rendered;
- architecture tests proving Studio does not import provider SDKs or replace
  Hurl execution;
- local gate evidence with `scripts/regression.sh --security`.

Security-sensitive mutation flows should also run the full quality audit and a
targeted manual diff review before merge.

## v0.3 Non-Goals

The following remain out of scope for v0.3:

- rerun buttons;
- config editors;
- Hurl editors;
- baseline promotion buttons;
- freeze/map write actions from Studio;
- provider-backed Architect edits from Studio;
- background schedulers;
- cloud sync;
- telemetry;
- any mutation workflow without a separate issue and accepted design amendment.

## Future Acceptance Gate

Before any Studio mutation code lands, the implementing issue must show:

- the accepted user flow;
- the exact core or CLI use case being called;
- preview and confirmation behavior;
- redaction and no-raw-secret proof;
- rollback behavior;
- test coverage plan;
- documentation updates;
- security review scope.

If a proposed action cannot satisfy this gate, keep it in the CLI/report layer
until the underlying workflow is safer.
