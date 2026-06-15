## Summary

- _Describe the feature, defect, or documentation change._

## Feature Scope

- [ ] One narrow feature, defect, or docs task.
- [ ] Command surface checked against `docs/technical/COMMAND_CHEAT_SHEET.md`.
- [ ] No unrelated refactors or generated noise.

## Test Pyramid

- [ ] Unit coverage added or updated for pure logic.
- [ ] Adapter/CLI/filesystem/subprocess coverage added or updated when relevant.
- [ ] Regression coverage added for bugs or risky edge cases.
- [ ] Integration or smoke coverage added when behavior crosses boundaries.
- [ ] Coverage gaps are explained below.

Coverage gaps:

- _List any intentional gaps, or write "None"._

## Verification

- [ ] `scripts/feature_gate.sh`
- [ ] `scripts/regression.sh`
- [ ] `scripts/feature_gate.sh --security` for dependency, subprocess, LLM, proxy, report, or filesystem-sensitive work.
- [ ] `git diff --check`
- [ ] `git diff --cached --check`
- [ ] CI passed.
- [ ] Sensitive-surface changes include `scripts/feature_gate.sh --security` or `scripts/regression.sh --security` evidence.

Commands run:

```text

```

## Architecture Review

- [ ] Hexagonal dependency direction preserved.
- [ ] Domain modules do not import CLI, core, brain, or studio adapters.
- [ ] `entroping run` remains deterministic and LLM-free.
- [ ] Hurl remains the API execution boundary.
- [ ] Docs do not claim unimplemented behavior as complete.

## Agent Autonomy Declaration

- [ ] Tier A autonomous lane: low-risk docs/tests/guard/script work only.
- [ ] Tier B assisted lane: implementation may be agent-generated, but merge requires human or Codex review.
- [ ] Tier C restricted lane: no autonomous merge.
- [ ] Merge authority:
- [ ] If autonomous, CI passed before merge and the PR includes `Closes #<issue>`.

## OpenCode Provider Lane Evidence

Complete this section for OpenCode/DeepSeek-produced or autonomous-lane PRs.
Before merge, strict validation can run with
`scripts/pr_body_check.py --body-file <body.md> --require-opencode-evidence --issue <issue>`.

- Provider lane:
- Provider host:
- Billing path:
- Model id:
- Autonomy tier:
- Merge authority:
- Commands run:

## Documentation Impact Declaration

- [ ] No docs update needed. Reason:
- [ ] User-facing docs updated:
- [ ] Technical docs updated:
- [ ] Roadmap/progress updated:
- [ ] ADR/spec/context updated:

## Security Review

- [ ] No secrets, credentials, tokens, cookies, raw traffic, or local env files committed.
- [ ] Boundary inputs are validated or explicitly out of scope.
- [ ] Subprocess/path/YAML/LLM/proxy/report risks reviewed when touched.
- [ ] Dependency audit result noted for changed dependencies or optional extras.

Security notes:

- _List security-relevant notes, or write "None"._

## Multi-Agent Review

- [ ] Helper agent outputs, if used, were validated against local files and deterministic checks.
- [ ] Conflicting suggestions were resolved by the parent integrator before patching.
- [ ] External/generated summaries were not treated as source of truth.

Reviewer notes:

- _List helper-agent or human-review notes, or write "None"._

## Documentation And Context

- [ ] User docs updated if behavior or commands changed.
- [ ] Technical docs updated if architecture, schemas, boundaries, or gates changed.
- [ ] `docs/meta/PROJECT_PROGRESS.md` updated for meaningful feature, bug, or roadmap changes.
- [ ] `.context/changelog.md` updated for meaningful changes.
- [ ] `.context/lessons-learned.md` updated for durable pitfalls or decisions.
- [ ] ADR added or updated if the decision should survive future context resets.

## Known Gaps

- _List known gaps, or write "None"._
