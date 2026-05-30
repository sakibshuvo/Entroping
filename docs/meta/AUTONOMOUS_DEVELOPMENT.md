---
title: Autonomous Development Workflow
type: runbook
status: active
tags:
  - codex
  - opencode
  - omlx
  - spec-kit
  - automation
---

# Autonomous Development Workflow

This runbook defines how to develop Entroping with high agent autonomy while keeping quality, security, and architecture under control.

## Operating Model

Use a controlled factory, not a free-running agent.

```text
Spec / issue -> Codex plan -> narrow branch -> implementation -> checks -> review -> commit -> context update
```

Rules:

- One branch or worktree per milestone.
- One narrow implementation target at a time.
- No direct agent work on unrelated files.
- No merge or push without deterministic checks.
- No generated context becomes canonical until a human or Codex promotes it into curated Markdown.
- Use `docs/meta/FEATURE_DELIVERY_CHECKLIST.md` as the per-feature execution checklist.
- Keep repo behavior deterministic through tracked scripts, tests, and CI. Do not rely on prompt reminders for rules that can be checked in code.

## Source of Truth

Before implementation, agents must read:

1. `AGENTS.md`
2. `.context/plan.md`
3. `docs/product/MVP_PLAN.md`
4. `docs/technical/TDS.md`
5. `docs/technical/COMMAND_CHEAT_SHEET.md`
6. The specific feature spec or issue being implemented

## Codex-First Loop

Use Codex as the primary architect, implementer, and final gatekeeper.

## Deterministic Local Guardrails

Entroping intentionally keeps `.codex/`, installed skills, plugins, and shell hooks out of the repository. Those are user-machine accelerators, not project truth.

Repository behavior belongs in:

- `AGENTS.md` for project-specific agent rules.
- `scripts/feature_gate.sh` for the local delivery gate.
- `scripts/repo_hygiene.sh` for tracked local/generated-state rejection.
- `scripts/regression.sh` for broader proof.
- `.github/workflows/ci.yml` for remote verification.
- GitHub Issues and PRs for work tracking and review.

Optional local hooks can be installed with:

```bash
scripts/install_hooks.sh
```

Hooks are convenience only. A skipped hook must still be caught by `scripts/feature_gate.sh` and CI.

## Issue Session Launcher

Use `scripts/start_issue.sh` to start parallel Codex, OpenCode, or review sessions from GitHub Issues. The script creates one isolated Git worktree per issue, updates issue tracking on a best-effort basis, and prints a deterministic session prompt that points the agent at the right source-of-truth files.

Dry-run first:

```bash
scripts/start_issue.sh 3 feat/gate-injection --dry-run
```

Start a write session:

```bash
scripts/start_issue.sh 3 feat/gate-injection
```

Start a read-only review session:

```bash
scripts/start_issue.sh 3 review/gate-injection --mode review
```

Session rules:

- One issue maps to one worktree and one branch.
- Use `--dry-run` before starting a large batch.
- Do not run two write agents on the same issue, branch, or file family.
- Use review-mode sessions for parallel critique; only the parent integrator applies fixes.
- Keep dependent issues in waves instead of launching them all at once.
- For a 10-20 session marathon, mix a small number of write sessions with mostly read-only review, docs, test-design, and issue-refinement sessions.

### 1. Intake

Define one task with a concrete outcome:

```text
Implement Phase 1A: entroping init creates minimal qanstitution.yaml and project skeleton.
```

Avoid broad requests such as:

```text
Build the MVP.
```

### 2. Planning

Codex should:

- Read the source-of-truth files.
- Inspect current code before editing.
- State the narrow plan.
- Identify touched modules and tests.
- Preserve command namespace and architecture rules.

### 3. Implementation

Codex owns final source edits for now. It may use subagents for independent review or file-family inspection, but the parent Codex thread owns integration.

Implementation must favor:

- Small commits.
- Focused tests.
- Explicit errors.
- No secret logging.
- No adapter imports from domain modules.
- No LLM calls inside `entroping run`.

For test-driven work, write or update the failing test before implementation when the behavior can be expressed deterministically. Coverage should follow the risk of the feature:

- Unit tests for pure domain and bridge behavior.
- Adapter tests for CLI, filesystem, subprocess, report, proxy, and LLM boundaries.
- Regression tests for fixed bugs and fragile edge cases.
- Integration or smoke checks when behavior crosses subsystem boundaries.
- Real Hurl smoke checks once the runner exists and `hurl` is available.

### 4. Verification

Always run:

```bash
scripts/feature_gate.sh
```

For dependency, subprocess, LLM, proxy, report, or filesystem-sensitive work, also run:

```bash
scripts/feature_gate.sh --security
```

For Hurl-related work, add fixture validation and real Hurl smoke checks once the runner exists.

### 5. Review

Before commit:

- Review `git diff`.
- Run `git diff --check`.
- Ask for an independent review when the change touches shared architecture, subprocess execution, reports, proxy capture, LLM calls, or security-sensitive paths.
- Fix only findings that survive evidence-based validation.

### 6. Context Update

After a meaningful milestone:

- Update `.context/changelog.md`.
- Update `.context/lessons-learned.md` when there is a durable pitfall or decision.
- Update docs only when behavior, commands, or architecture changed.
- Add an ADR for decisions that should survive context resets.

## Spec Kit Pilot

Use GitHub Spec Kit for one feature at a time. Do not migrate the whole repo into Spec Kit at once.

Current local check:

```text
specify check
```

Result on 2026-05-29:

- Git available.
- Codex CLI available.
- OpenCode available.
- Specify CLI ready.
- Qwen Code not installed.
- Claude Code and Gemini CLI not installed.

When ready to pilot Spec Kit, use a clean branch and initialize for Codex:

```bash
git switch -c chore/spec-kit-pilot
specify init --here --ai codex --no-git
```

After initialization, inspect generated files before committing. If the template conflicts with `AGENTS.md`, `.context/`, or existing docs, keep Entroping's curated files as canonical and adapt the generated files.

Recommended first Spec Kit feature:

```text
Phase 1A: init + doctor + QAnstitution loading
```

## Future OpenCode Loop

OpenCode is available locally and can become a cheap worker/reviewer loop.

Use OpenCode for:

- Repo exploration.
- Test ideas.
- Documentation drafts.
- Diff review.
- Alternate implementation proposals.

Do not use OpenCode as the final authority for:

- Architecture changes.
- Security-sensitive code.
- Subprocess execution.
- Proxy capture.
- LLM prompt/data boundaries.
- Commits to `main`.

Recommended future pattern:

```text
Codex writes the task brief -> OpenCode explores or reviews -> Codex validates -> Codex applies final patch
```

OpenCode outputs should be treated as review evidence, not truth. Any finding must include file/line evidence and a plausible source/control/sink path before action.

Conflict controls:

- Only the parent Codex thread applies final patches.
- Helper agents receive bounded briefs with allowed files and output format.
- Two helper agents should not edit the same file family at the same time.
- If reviews conflict, resolve the disagreement against local files, tests, specs, and CI before changing code.
- Use `scripts/start_issue.sh --mode review` for read-only worker prompts once the issue exists.

## Future Local Qwen via oMLX Loop

oMLX is not currently installed in this environment. When installed, use it as an OpenAI-compatible or Anthropic-compatible local inference backend for low-risk work.

Use local Qwen through oMLX for:

- Summarizing docs.
- Drafting test cases.
- Reviewing diffs for maintainability.
- Producing alternate wording.
- Offline brainstorming when privacy matters.

Do not use local Qwen as the final gate for:

- Security review.
- Release decisions.
- Architecture boundary changes.
- Generated code that has not passed tests.

Future setup should stay outside the repo unless sanitized:

```text
oMLX local server -> OpenAI-compatible endpoint -> OpenCode custom/local provider -> read-only worker tasks
```

Keep provider credentials, endpoints, model paths, and local model cache settings out of Git.

## 24/7 Automation Rule

The machine can run continuously, but the repo advances only through verified commits.

Allowed unattended work:

- Generate review notes.
- Run tests and audits.
- Produce draft specs.
- Explore code and summarize.
- Generate Graphify reports into ignored output.

Not allowed unattended:

- Push to `main`.
- Modify secrets or local env files.
- Run destructive Git commands.
- Accept generated code without tests.
- Send raw captured traffic or secrets to cloud models.

## Hallucination Controls

Use these gates:

```text
No local file evidence -> no architecture claim.
No failing or targeted test -> no feature implementation start unless explicitly documented.
No deterministic checks -> no commit.
No CI -> no merge.
No context update -> no durable memory.
Generated graph or model summary -> navigation aid only, not truth.
No parent integrator approval -> no multi-agent patch lands.
```

## References

- GitHub Spec Kit: https://github.com/github/spec-kit
- Spec Kit docs: https://github.github.io/spec-kit/
- OpenCode docs: https://dev.opencode.ai/docs/agents/
- OpenCode CLI docs: https://dev.opencode.ai/docs/cli/
- oMLX: https://omlx.ai/
- oMLX GitHub: https://github.com/jundot/omlx
