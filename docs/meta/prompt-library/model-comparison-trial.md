---
title: Model-Comparison Trial Prompt
type: prompt
status: active
tags:
  - models
  - opencode
  - deepseek
  - kimi
  - qwen
  - metrics
---

# Model-Comparison Trial Prompt

Use this when comparing Codex, OpenCode native DeepSeek, direct DeepSeek API,
OpenCode Go Kimi, OpenCode Go Qwen, OpenCode Go other models, and
local/offline models on Entroping work. The goal is evidence, not vibes.

No model output is source of truth. Repo files, GitHub issues, tests, CI,
ADRs, QAnstitution/Hurl evidence, and deterministic gates decide whether a
change is correct.

## Trial Prompt

```text
You are running an Entroping model-comparison trial.

Repo:
cd /Users/sakibshuvo/projects/Entroping

Codex Cloud or another host: if this macOS path does not exist, use the
repository root provided by the task, then continue with the same checks.

Issue:
#<issue-number> - <issue-title>

Trial identity:
- issue number: #<issue-number>
- provider lane: <codex/native | opencode/native-deepseek | deepseek-api/direct | opencode-go/kimi-k2.7-code | opencode-go/qwen3.7-max | opencode-go/other | local/offline>
- provider host: <Codex | OpenCode Desktop | OpenCode CLI | repo-local DeepSeek worker | OpenCode Go | local runtime>
- billing path: <Codex subscription | paid DeepSeek API | OpenCode Go subscription | local/offline>
- model id: <exact model id when known>
- role: <product_manager | architect | dev_agent | qa_agent | code_review_agent | security_agent | monitoring_agent>
- autonomy tier: <Tier A autonomous lane | Tier B assisted lane | Tier C restricted lane>

Rules:
- Do not score models by confidence or style alone.
- Score output quality through tests, diffs, CI, security/architecture review, and reviewer effort.
- Keep one issue per worktree.
- Treat all model output as advisory until local files, tests, and CI prove it.
- Stop if the issue touches forbidden runtime, Hurl runner, redaction, proxy,
  provider-boundary, dependency, release, secret, raw traffic, or audit-evidence scope.
- Do not paste secrets, provider transcripts, raw traffic, cookies, headers, or
  private data into prompts or committed docs.
- For OpenCode/DeepSeek trials, write `.entroping/ai-reviews/issue-<issue-number>-<short-slug>/`
  with `metadata.json`, `result.md`, `tests.txt`, and optional `proposal.diff`;
  report `python scripts/factory_review_packet.py --artifact-dir .entroping/ai-reviews/issue-<issue-number>-<short-slug> --json`.
  Set `metadata.json` `status` to `ready_for_codex` when complete so Codex can
  pick up the next trial artifact with
  `uv run python scripts/factory_inbox.py next --json`.
- Do not use `exec()`, dynamic source-file execution, import-time code
  generation, broad `type: ignore`, broad ruff ignores such as `F821` or `F811`,
  or `mypy ignore_errors`; use normal importable modules with explicit
  dependencies.

Start:
git pull --ff-only
git status --short
gh issue view <issue-number> --repo sakibshuvo/Entroping
scripts/start_issue.sh <issue-number> <type>/<short-kebab-description>
cd ../Entroping-issue-<issue-number>
scripts/context_pack.sh --mode implementation

Context/tool measurement:
Use `scripts/factory_metrics.py report` and any issue-specific scorecard
evidence already recorded under `.entroping/factory-metrics/`. Do not run or
require external generated-context tooling for this trial; it is not part of
active Entroping agent workflow. Obsidian graph views and generated summaries
are routing evidence only. They do not replace source reads, tests, PR review,
or CI.

Work:
1. Confirm allowed files, forbidden files, merge authority, and stop conditions.
2. Write or update a failing guard/test first when practical.
3. Make the smallest scoped change.
4. Record files changed.
5. Run focused tests/gates, then the issue's required gate.
6. Capture CI status before merge.
7. Record cost/token/context evidence when available, but do not infer missing values.
8. Record accepted findings, rejected findings, stale findings, and reviewer overrides.
9. Use `scripts/factory_metrics.py report` to inspect local per-issue model evidence when practical.
10. Record the artifact directory and factory review packet command when the
    trial used OpenCode/DeepSeek.

Output:
- issue number:
- provider lane:
- provider host:
- billing path:
- model id:
- role:
- autonomy tier:
- files changed:
- files read:
- context-pack mode:
- context-pack manifest:
- artifact directory:
- tests/gates:
- commands run:
- CI status:
- cost/token/context evidence:
- accepted findings:
- rejected findings:
- stale findings:
- reviewer overrides:
- final decision:
```

## Evidence Rules

Record model-comparison evidence under `.entroping/factory-metrics/` when
practical. This evidence is local workflow telemetry, not release proof. It
must not contain raw prompts, provider transcripts, secrets, raw traffic,
product runtime evidence, request bodies, response bodies, cookies, headers, or
private user data.

Useful fields for comparison:

- issue number and PR number,
- provider lane, provider host, billing path, and model id,
- role and autonomy tier,
- files changed and files read,
- tests/gates and CI status,
- known cost/token/context evidence,
- accepted findings, rejected findings, stale findings, and reviewer overrides,
- reviewer effort, including how much Codex/human correction was needed.

Do not fill missing token, cost, or duration values with guesses. Unknowns must
stay unknown so `scripts/factory_metrics.py report` can show evidence gaps.

## Concrete OpenCode/DeepSeek Evidence Example

Use this concrete example format for OpenCode/DeepSeek evidence. Replace the
sample values with measured local evidence when it exists; leave unavailable
provider token or cost fields as `unknown` instead of guessing:

- issue: `774`
- provider lane: `opencode/native-deepseek`
- provider host: `OpenCode Desktop`
- billing path: `paid DeepSeek inside OpenCode`
- model id: `deepseek/deepseek-v4-pro`
- role: `code_review_agent`
- autonomy tier: `Tier A autonomous lane`
- files changed:
  - docs/meta/prompt-library/opencode-desktop-handoff.md
  - tests/test_agent_workflow_docs.py
- files read:
  - docs/meta/prompt-library/issue-worker.md
  - docs/meta/prompt-library/model-output-acceptance-gate.md
  - docs/meta/AGENT_CONTROL_PLANE.md
- context-pack mode: `implementation`
- context-pack manifest: `generated`
- artifact directory: `.entroping/ai-reviews/issue-774-opencode-deepseek-trial/`
- factory review packet:
  `python scripts/factory_review_packet.py --artifact-dir .entroping/ai-reviews/issue-774-opencode-deepseek-trial --json`
- factory inbox pickup:
  `uv run python scripts/factory_inbox.py next --json`
- context-pack estimated tokens: `<manifest-estimated-tokens>` from
  `scripts/context_pack.sh --mode implementation --manifest`
- context-pack bytes: `<manifest-context-bytes>` from
  `scripts/context_pack.sh --mode implementation --manifest`
- commands run:
  - git pull --ff-only
  - scripts/context_pack.sh --mode implementation --manifest
  - scripts/factory_metrics.py report --format json
  - scripts/factory_metrics.py report --format md --output .entroping/factory-metrics/factory-report.md
  - scripts/factory_metrics.py readiness --issue 774 --format json
- cost/token/context evidence:
  - provider_input_tokens: `unknown`
  - provider_output_tokens: `unknown`
  - cost_usd: `unknown`
  - duration_seconds: `unknown`
  - context_bytes: `<manifest-context-bytes>`
- accepted findings:
  - `P3 merge-authority wording clarified`
- rejected findings:
  - `No runtime or provider-boundary change requested`
- stale findings:
  - `none`
- reviewer overrides:
  - `kept issue-required scripts/regression.sh --security gate`
- final decision: `accepted after local tests, Codex review, and CI`
- review effort:
  - codex_review_rounds: `1`
  - reviewer_corrections: `2`
  - status: `accepted`

Unknown token/cost values are allowed, but they must be marked `unknown`; do not
infer, estimate, or backfill provider token or cost values when they are not
present in repo-native metrics, context-pack output, provider metadata, or
review artifacts.

## Scoring

A model trial is useful only when it improves at least one measurable outcome:

- fewer nonexistent file, command, symbol, or issue references,
- fewer mismatched or missing issue/PR references,
- fewer stale claims,
- fewer forbidden-scope incidents,
- higher accepted-finding ratio,
- lower reviewer correction count,
- lower context bytes or estimated tokens for the same grounded result,
- faster context recovery without lowering tests, security, or architecture
  standards.

For cost/token/context metrics, score the trial on whether it records concrete
evidence when available and leaves unknowns explicit. Unknown cost or token
values do not disqualify a trial from improving another measurable outcome.

Do not score models by confidence or style alone. Good prose without grounded
files, passing tests, clean diffs, CI, and security/architecture review is not a
shipping signal.
