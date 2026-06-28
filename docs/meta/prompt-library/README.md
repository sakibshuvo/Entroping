---
title: Prompt Library
type: prompt-library
status: active
tags:
  - agents
  - prompts
  - codex
  - opencode
  - deepseek
  - gemini
  - claude
---

# Prompt Library

This is the copy-paste shelf for Entroping agent work. It keeps reusable prompts
in one place so they do not get buried in chat history or duplicated across
strategy docs.

Use these prompts as launchers, not as source of truth. Every prompt should make
the receiving agent read local repo files, GitHub issue state, tests, and CI
before it claims facts or edits files.

This directory is for human copy-paste prompts. Machine-consumed worker
templates live under `prompts/` and are used by repo-local helpers such as
`scripts/opencode_worker.py` and `scripts/deepseek_worker.py`.

## Default Paths

These prompts are tuned for the maintainer workflow on this machine:

```text
Active repo: /Users/sakibshuvo/projects/Entroping
Source archive: /Users/sakibshuvo/projects/entroping-specs
Stale path: /Users/sakibshuvo/Documents/Entroping
```

Use those paths as-is for this project. Replace them only when sharing the
prompt with another contributor or running Entroping from a different checkout.

Codex Cloud note: if a prompt says `cd /Users/sakibshuvo/projects/Entroping`
and that path does not exist, use the repository root provided by the cloud
task, then continue with the same checks. If a prompt references
`/Users/sakibshuvo/projects/entroping-specs`, use it only when that source
archive is mounted or attached to the cloud task.

## Rules

- Do not paste secrets, API keys, raw traffic, cookies, headers, or private
  provider output into model prompts.
- Give one write agent one issue-scoped worktree.
- Keep Codex or the parent integrator responsible for final review, gates, PRs,
  and merge readiness for Tier B/Tier C work.
- Allow OpenCode/DeepSeek to merge only Tier A autonomous lane work after the
  PR declares merge authority, required local gates pass, and CI is green.
- Treat Gemini, DeepSeek, OpenCode, NotebookLM, and local
  models as evidence sources, not authorities.
- Declare the role from `docs/meta/AGENT_ROLE_REGISTRY.yaml` before starting
  worker prompts, and record local budget/context outcomes with
  `scripts/factory_metrics.py` when a session produces useful evidence.
- The portable software-factory protocol supports Codex, Claude Code,
  OpenCode, DeepSeek, Gemini, Spark, and local models, but prompts still make
  the receiving agent prove every claim against repo truth before edits or
  merge.
- For interactive OpenCode/DeepSeek handoffs without an `ai_jobs.py` job id,
  require `.entroping/ai-reviews/issue-<issue-number>-<short-slug>/` with
  `metadata.json`, `result.md`, `tests.txt`, and optional `proposal.diff`; Codex
  can pick it up with
  `python scripts/factory_review_packet.py --artifact-dir .entroping/ai-reviews/issue-<issue-number>-<short-slug> --json`.
- For marathon-style OpenCode runs, require `metadata.json` to include
  `status: ready_for_codex` when the handoff is complete. Codex can then avoid
  copy-paste pickup with `uv run python scripts/factory_inbox.py next --json`,
  or inspect the queue with `uv run python scripts/factory_inbox.py list --json`.
  After review, mark the artifact with
  `uv run python scripts/factory_inbox.py mark-reviewed <artifact-dir> --json`
  or the stricter `mark-accepted`, `mark-rejected`, or `mark-needs-review`.
- Refactor prompts must reject shortcut compatibility. Do not use `exec()`,
  dynamic source-file execution, import-time code generation, broad
  `type: ignore`, broad ruff ignores such as `F821` or `F811`, or
  `mypy ignore_errors`; require normal importable modules with explicit
  dependencies.

## Start Here

| Need | Use |
| --- | --- |
| Start or recover a Codex thread | [Codex session handoff](codex-session-handoff.md) |
| Give one agent one scoped issue | [Issue worker](issue-worker.md) |
| Add explicit allowed files, forbidden files, and stop conditions | [Architecture boundary brief](architecture-boundary-brief.md) |
| Ask Codex to choose issues and generate Spark/OpenCode/Codex prompts | [Multi-agent marathon](multi-agent-marathon.md), section `Credit-Aware Prompt Generator Flow` |
| Keep one Codex thread shipping issue after issue | [Codex persistent marathon](codex-persistent-marathon.md) |
| Spend Spark on low-risk docs/tests/hygiene | [Spark-safe worker](spark-safe-worker.md) |
| Start OpenCode Desktop/OpenCode Go implementation or verification | [OpenCode Desktop handoff](opencode-desktop-handoff.md) |
| Run one Tier A OpenCode Desktop conveyor | [OpenCode Desktop one-shot](opencode-desktop-one-shot.md) |
| Review OpenCode-produced work with Codex | [OpenCode Codex review request](opencode-codex-review-request.md) |
| Decide whether model output is trustworthy | [Model-output acceptance gate](model-output-acceptance-gate.md) |
| Decide whether a PR can merge | [PR review and merge gate](pr-review-merge-gate.md) |
| Debug red CI | [CI failure debug](ci-failure-debug.md) |
| Return after unattended work | [After-sleep status](after-sleep-status.md) |

## Batch And Worker Prompts

| Prompt | Use | Boundary |
| --- | --- | --- |
| [Multi-agent marathon](multi-agent-marathon.md) | Codex prepares Spark-only, OpenCode-only, or Spark + OpenCode batches and later reviews all outputs. | Parent/integrator prompt, not a worker shortcut. |
| [Codex persistent marathon](codex-persistent-marathon.md) | One Codex session repeats the issue-worktree-PR-CI-merge-finish loop. | Single integrator, not parallel workers. |
| [Issue worker](issue-worker.md) | One issue, one worktree, one branch, one PR. | Base packet for Codex, OpenCode, DeepSeek, or local workers. |
| [Spark-safe worker](spark-safe-worker.md) | Ad hoc low-risk Spark work. | For marathon issue batches, prefer the filled Spark prompt generated from `multi-agent-marathon.md`. |
| [OpenCode Desktop handoff](opencode-desktop-handoff.md) | OpenCode implementation or PR verification with provider, billing, model, preflight, and handoff evidence. | General OpenCode packet. |
| [OpenCode Desktop one-shot](opencode-desktop-one-shot.md) | One Tier A OpenCode Desktop issue conveyor. | Do not use for Tier B/Tier C without Codex review. |
| [OpenCode-only week monitoring](opencode-week-monitoring.md) | Read-only monitoring when Codex capacity is low. | Monitoring is not merge authority. |
| [Codex-outage daily operations](codex-outage-daily-operations.md) | Daily safe operations during low Codex capacity. | Selects/monitors safe work, does not lower gates. |

## Review And Intake

| Prompt | Use |
| --- | --- |
| [Model-output acceptance gate](model-output-acceptance-gate.md) | Accept, reject, escalate, or convert cheap-model output to issues. |
| [OpenCode Codex review request](opencode-codex-review-request.md) | Read-only Codex review of OpenCode-produced local diffs or PRs. |
| [PR review and merge gate](pr-review-merge-gate.md) | Final PR merge decision. |
| [Backlog triage](backlog-triage.md) | Turn reviews, feedback, and ideas into clean GitHub issues. |
| [Bug bash](bug-bash.md) | Find verified bugs and quality gaps. |
| [Engineering health review](engineering-health-review.md) | Broad engineering quality review. |
| [Security review](security-review.md) | Security-sensitive diff, branch, or issue review. |
| [CI failure debug](ci-failure-debug.md) | GitHub Actions failure diagnosis. |
| [Model-comparison trial](model-comparison-trial.md) | Compare model lanes with evidence, correction effort, and cost/context metrics. |

## Product And Context

| Prompt | Use |
| --- | --- |
| [Launch readiness review](launch-readiness-review.md) | README, install, demo, public surface, and first-five-minute UX. |
| [Stable-core audit](stable-core-audit.md) | Stable-core evidence before readiness claims. |
| [Roadmap and progress refresh](roadmap-progress-refresh.md) | Refresh project direction without docs sprawl. |
| [Context reconciliation](context-reconciliation.md) | Compare historical source material against current repo truth. |
| [Gemini review](gemini-review.md) | External product/engineering sanity check. |
| [Claude code review](claude-code-review.md) | Occasional source-pinned Claude review. |
| [DeepSeek/OpenCode review](deepseek-opencode-review.md) | Bounded review, bug bash, or patch proposal from DeepSeek/OpenCode. |
| [Thread steering](thread-steering.md) | Redirect a running thread without losing its safe checkpoint. |

## Overlap Notes

- `multi-agent-marathon.md` is the owner for credit-aware prompt generation:
  Spark-only batch, OpenCode-only batch, and Spark + OpenCode batch.
- `spark-safe-worker.md` remains a small one-off Spark launcher; do not use it
  as the marathon issue selector.
- `opencode-desktop-handoff.md` is the general OpenCode work packet.
  `opencode-desktop-one-shot.md` is only for a single Tier A conveyor.
- `codex-persistent-marathon.md` is for one Codex integrator, not parallel
  worker lanes.
- `codex-outage-daily-operations.md` and `opencode-week-monitoring.md` are
  low-capacity operating prompts. They monitor or select work, but do not
  change merge authority.
- `deepseek-opencode-review.md` is review or patch-proposal intake. Use
  `issue-worker.md` or `opencode-desktop-handoff.md` for implementation.

## Maintenance

Update this library when a prompt becomes reusable across at least two sessions.
Do not add one-off chat dumps. If a prompt encodes a durable workflow rule,
also update `docs/meta/AGENT_CONTROL_PLANE.md` or the relevant canonical doc.
