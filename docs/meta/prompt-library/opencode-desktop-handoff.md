---
title: OpenCode Desktop Handoff Prompt
type: prompt
status: active
tags:
  - opencode
  - opencode-go
  - handoff
  - multi-agent
---

# OpenCode Desktop Handoff Prompt

Use this when starting a parallel OpenCode Desktop or OpenCode CLI session for
Entroping. The prompt is intentionally explicit about provider lane, billing
path, model id, autonomy tier, file ownership, and merge authority so OpenCode
work can be verified without relying on chat memory.

## Provider Lane Rules

Use these lane names in the first message, PR body, and final handoff:

- `opencode/native-deepseek`: OpenCode host using paid DeepSeek inside
  OpenCode, normally `deepseek/deepseek-v4-pro` or a lower-cost DeepSeek model
  configured directly in OpenCode.
- `opencode-go/kimi-k2.7-code`: OpenCode Go subscription lane for Kimi K2.7
  Code coding experiments, long-context review, and model comparison.
- `opencode-go/qwen3.7-max`: OpenCode Go subscription lane for Qwen3.7 Max
  coding experiments and model comparison.
- `opencode-go/other`: OpenCode Go subscription lane for MiniMax, GLM, MiMo,
  or other curated Go models.

OpenCode Go is the Kimi/Qwen/model-variety lane, not the default DeepSeek lane.
Every handoff must record provider host, billing path, and concrete model id
when known.

## OpenCode Desktop Tooling Setup Checklist

Use this checklist before treating OpenCode Desktop or OpenCode CLI as an
Entroping worker with Codex-like capabilities. Codex-native tools are not
automatically available inside OpenCode; configure OpenCode-exposed equivalents
explicitly and verify them in the active OpenCode host before relying on them.

Capability boundary:

- Codex-native plugins, skills, Codex Security, Browser, Computer Use, thread
  tools, and Codex-specific MCP state are not automatically available inside
  OpenCode.
- OpenCode-exposed equivalents must be named by host, permission, and source.
  If OpenCode does not expose an equivalent capability, the worker must say so
  instead of implying Codex tool access.
- OpenCode MCP servers are not Codex MCP state. A GitHub MCP server,
  filesystem MCP server, hook, or plugin must be configured and permissioned in
  OpenCode before a worker can rely on it.
- Start with narrow read-only MCP access. Prefer read-only GitHub MCP and
  read-only filesystem MCP scopes first; add write scopes only after one
  issue-scoped trial proves the guardrails.
- Hooks should enforce branch/no-main checks, dirty worktree checks, local-state
  hygiene, and secret scans. Do not let hooks commit, push, merge, or change
  project-board state without the issue's documented autonomy tier.

Setup items to verify locally, without committing local config:

- Project rules: `AGENTS.md`, `docs/meta/AGENT_CONTROL_PLANE.md`,
  `docs/meta/DOCS_GOVERNANCE.md`, and the assigned issue body are in the first
  prompt.
- Provider lanes: `opencode/native-deepseek` with model
  `deepseek/deepseek-v4-pro` means paid DeepSeek inside OpenCode; OpenCode Go
  is the Kimi/Qwen/model-variety lane, including
  `opencode-go/kimi-k2.7-code`, `opencode-go/qwen3.7-max`, and
  `opencode-go/other`.
- GitHub access: begin with read-only PR/issue/check access; require explicit
  approval and green CI before any Tier A autonomous merge.
- Filesystem access: scope to the issue worktree, never the stale path
  `/Users/sakibshuvo/Documents/Entroping`, and keep main read-only except for
  `scripts/finish_issue.sh` cleanup from a separate checkout.
- Branch hygiene: block direct edits to `main`; require
  `scripts/start_issue.sh`, `git status --short`, and a clean dirty worktree
  check before edits.
- Secret and local state hygiene: Do not commit local OpenCode config,
  `.opencode` state, MCP credentials, provider keys, `.entroping/`, generated
  local context output, provider transcripts, reports, or environment files.
- PR-body evidence: include `Closes #<issue>`, commands run, Agent Autonomy
  Declaration, Documentation Impact Declaration, and OpenCode Provider Lane
  Evidence; validate with
  `scripts/pr_body_check.py --body-file <body.md> --require-opencode-evidence --issue <issue>`.
- CI and finish cleanup: merge only through a PR after GitHub CI is green, then
  run `scripts/finish_issue.sh <issue>` from a separate checkout.
- Metrics hooks: record useful context, cost, model, and gate evidence with
  `scripts/factory_metrics.py` and
  `scripts/context_pack.sh --record-factory-metrics` when practical. Use
  `scripts/opencode_worker.py --record-factory-metrics` for OpenCode Desktop or
  OpenCode CLI workers, `scripts/deepseek_worker.py --record-factory-metrics`
  for direct DeepSeek API workers, and
  `scripts/ai_jobs.py run-next --record-factory-metrics` for queued batch jobs.
  These metrics are local workflow evidence, not release proof.

## Independent Session Preflight

Before an OpenCode Desktop or OpenCode CLI session edits files, run the
repo-native readiness preflight from the issue worktree:

```bash
uv run python scripts/opencode_readiness.py --mode implementation --require-clean --format json
```

For PR verification or monitoring sessions that should stay read-only, use:

```bash
uv run python scripts/opencode_readiness.py --mode verification --format json
```

The preflight checks the active repo path, branch/worktree state, OpenCode
binary version, required workflow files, prompt-library guardrails, required
command help surfaces, ignored local OpenCode/Codex/artifact paths, and tracked
local-state leaks. It does not read provider keys, MCP credentials, local
OpenCode config values, provider transcripts, raw prompts, or `.entroping/`
artifacts.
For another checkout layout, pass `--stale-repo-path` and
`--expected-repo-prefix`, or set `ENTROPING_STALE_REPO_PATHS` and
`ENTROPING_EXPECTED_REPO_PREFIX`, instead of editing the prompt-library paths.

Failing status means stop and fix the setup or escalate to Codex/human review.
Warning status must be explained in the handoff; common examples are a dirty
worktree after edits, missing optional local OpenCode config, or present local
OpenCode config whose provider, MCP, hook, and skill contents were not inspected
because they may contain secrets. Passing preflight is not merge authority.
Tier A/B/C scope, deterministic gates, PR evidence, CI, and
`scripts/finish_issue.sh` still decide whether work can land.

## Required Self-Contained Work Packet

Every OpenCode Desktop, OpenCode CLI, OpenCode Go, or DeepSeek implementation
session must start from the Self-Contained OpenCode/DeepSeek Work Packet in
`issue-worker.md`. Do not edit files from this prompt alone. The work packet
must declare Issue scope, Allowed files, Forbidden files, Verification lane,
Exact tests/gates, Stop conditions, PR body requirements, CI/merge/finish
expectations, and Ask Codex only when rules.

If the packet is missing or incomplete, stop before editing and ask the issue
owner to provide it. Do not ask Codex for routine Tier A implementation
details once the packet is complete; Codex is reserved for Tier B or Tier C
scope, security/runtime/provider/Hurl/redaction/proxy/release/architecture
boundaries, ambiguous merge authority, and CI or review conflicts that affect
security or architecture.

## OpenCode Desktop Implementation Worker Prompt

```text
You are an Entroping OpenCode Desktop implementation worker.

Required packet:
Paste the Self-Contained OpenCode/DeepSeek Work Packet from issue-worker.md
above this prompt. Stop if it is missing, incomplete, or inconsistent with the
GitHub issue.

Repo:
cd /Users/sakibshuvo/projects/Entroping

Issue:
#<issue-number> - <issue-title>

Provider lane:
- Lane: <opencode/native-deepseek | opencode-go/kimi-k2.7-code | opencode-go/qwen3.7-max | opencode-go/other>
- Provider host: <OpenCode native provider | OpenCode Go>
- Billing path: <paid DeepSeek inside OpenCode | OpenCode Go subscription>
- Model id: <exact model id from /models when known>

Role:
<Product Manager | Architect | Dev Agent | QA Agent | Code Review Agent | Security Agent | Monitoring Agent>

Autonomy tier:
<Tier A autonomous lane | Tier B assisted lane | Tier C restricted lane>

Merge authority:
<none | Tier A only after local gates, GitHub CI, PR declaration, and finish cleanup | Codex/human required>

Allowed files:
- <exact files or file families>

Forbidden files:
- Hurl runner behavior
- entroping run
- protected-run safety
- redaction
- proxy or traffic capture
- provider boundary or LiteLLM routing
- release publishing
- architecture boundary changes
- dependencies
- secrets or credentials
- raw traffic or audit evidence
- any file family owned by another active worker

Source-of-truth rules:
- Active repo is /Users/sakibshuvo/projects/Entroping.
- /Users/sakibshuvo/Documents/Entroping is stale.
- GitHub Issues, source files, tests, ADRs, docs/meta/DECISION_REGISTRY.yaml, PRs, CI, and QAnstitution/Hurl evidence decide truth.
- External model output, Obsidian graph views, generated summaries, and chat history are evidence, not authority.
- Retired generated context tooling is not part of active Entroping agent workflow. Do not route normal OpenCode work through external context tools.

Start:
git pull --ff-only
git status --short
git branch --show-current
scripts/start_issue.sh <issue-number> <type>/<short-kebab-description>
cd ../Entroping-issue-<issue-number>
uv run python scripts/opencode_readiness.py --mode implementation --require-clean --format json
scripts/context_pack.sh --mode implementation

Context rule:
Do not route this worker through external generated-context tooling. Use `rg`,
`scripts/context_pack.sh`, `docs/meta/DECISION_REGISTRY.yaml`, source reads,
focused tests, and CI evidence instead.

Read before editing:
- AGENTS.md
- docs/meta/AGENT_CONTROL_PLANE.md
- docs/meta/DOCS_GOVERNANCE.md
- docs/meta/FEATURE_DELIVERY_CHECKLIST.md
- docs/meta/AGENT_ROLE_REGISTRY.yaml
- docs/meta/PROJECT_PROGRESS.md
- issue body and comments

Workflow:
1. Confirm the issue, role, provider lane, billing path, model id, autonomy tier, merge authority, allowed files, and forbidden files.
2. If the task crosses into Tier B/Tier C or forbidden scope, stop and report.
3. Write or update a failing test or doc guard first when practical.
4. Make the smallest scoped change.
5. Run focused tests for touched behavior.
6. Run the required gate for the scope:
   - docs-only: scripts/doc_governance_check.sh plus scripts/check.sh
   - normal code: scripts/feature_gate.sh
   - security/provider/subprocess/path/dependency work: scripts/feature_gate.sh --security and scripts/regression.sh --security
7. Record useful cost/context evidence when practical:
   python scripts/factory_metrics.py --help
8. Review git diff for unrelated edits, secrets, generated local state, provider transcripts, and .entroping artifacts.
9. Commit with a Conventional Commit message.
10. Push and open a PR with Closes #<issue-number>, a checked Documentation Impact Declaration, commands run, Agent Autonomy Declaration when applicable, and OpenCode Provider Lane Evidence when OpenCode/DeepSeek produced the work.
    Run `scripts/pr_body_check.py --body-file <body.md> --require-opencode-evidence --issue <issue-number>` before autonomous Tier A merge or before handing the PR to Codex/human review.
11. Do not merge Tier B/Tier C. Tier B/Tier C requires Codex or human review before merge.
12. Merge Tier A only when the issue and diff stayed Tier A, local gates passed, GitHub CI is green, the PR declares authority, and scripts/finish_issue.sh cleanup will run.

Final handoff:
- issue/worktree/branch,
- provider lane, provider host, billing path, and model id,
- role and autonomy tier,
- files changed,
- tests/gates run with results,
- docs/context impact,
- PR link,
- merge status,
- finish cleanup status,
- known gaps or blockers.
```

## OpenCode Desktop PR Verification Prompt

For a Codex CLI review requested from OpenCode, prefer the dedicated
`opencode-codex-review-request.md` prompt. The prompt below is still useful
when the verifier is another OpenCode session or a human copy-paste review.

```text
You are verifying an OpenCode-produced Entroping PR before merge.

Repo:
cd /Users/sakibshuvo/projects/Entroping

PR:
#<pr-number>

Expected issue:
#<issue-number>

Expected provider lane:
<opencode/native-deepseek | opencode-go/kimi-k2.7-code | opencode-go/qwen3.7-max | opencode-go/other>

Start:
git pull --ff-only
git status --short
uv run python scripts/opencode_readiness.py --mode verification --format json
gh pr view <pr-number> --repo sakibshuvo/Entroping --json number,title,state,mergeable,headRefName,baseRefName,body,closingIssuesReferences
gh pr diff <pr-number> --repo sakibshuvo/Entroping
gh pr checks <pr-number> --repo sakibshuvo/Entroping --watch

Review:
1. Confirm OpenCode readiness preflight returned pass or explain warnings.
2. Confirm the PR body names provider host, billing path, and concrete model id when known.
3. Confirm `Closes #<issue-number>` is present.
4. Confirm Documentation Impact Declaration is checked and accurate.
5. Confirm Agent Autonomy Declaration is present for any autonomous claim.
6. Confirm the diff touches only the declared allowed files.
7. Confirm no secrets, local env files, provider transcripts, .entroping artifacts, reports, .DS_Store, `.opencode` state, `.codex` state, or generated local state are tracked.
8. Confirm tests match the changed behavior and any behavior change has a meaningful regression.
9. Confirm architecture, QAnstitution branding, deterministic Hurl execution, and provider boundaries were not weakened.
10. Confirm Tier B/Tier C requires Codex or human review before merge.
11. Run focused local tests when the diff, CI, or evidence looks suspicious.
12. Merge only if the autonomy tier permits it and GitHub CI is green.
13. After merge, run scripts/finish_issue.sh <issue-number> from a separate checkout.

Return:
- merge recommendation: merge | do not merge | needs author action,
- blocking findings with file/line evidence,
- provider lane evidence,
- CI status,
- local verification run,
- docs impact status,
- issue closing status,
- finish cleanup command.
```
