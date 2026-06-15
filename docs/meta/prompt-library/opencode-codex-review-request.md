---
title: OpenCode Codex Review Request Prompt
type: prompt
status: active
tags:
  - codex
  - opencode
  - review
  - cli
  - multi-agent
---

# OpenCode Codex Review Request Prompt

Use this when an OpenCode Desktop, OpenCode CLI, OpenCode Go, or DeepSeek
worker needs Codex CLI to review its Entroping diff or PR before merge.

This is a review gate, not an implementation prompt. Codex should not edit,
stage, commit, push, merge, or run destructive commands from this prompt.
OpenCode may use this for Tier A confirmation before autonomous merge, and
must use Codex or human review for Tier B and Tier C work.

## Local Diff Review

Run this from OpenCode after the worker has produced a local branch or issue
worktree diff and before it opens or merges a PR:

```bash
codex -C /Users/sakibshuvo/projects/Entroping-issue-<issue-number> \
  -s read-only \
  -a never \
  review --base main - <<'PROMPT'
You are the Codex review gate for an OpenCode-produced Entroping change.

Mode:
Review only. Do not edit, stage, commit, push, merge, or run destructive commands.

Worktree:
/Users/sakibshuvo/projects/Entroping-issue-<issue-number>

Issue:
#<issue-number> - <issue-title>

Worker evidence:
- Provider lane: <opencode/native-deepseek | opencode-go/kimi-k2.7-code | opencode-go/qwen3.7-max | opencode-go/other | direct/deepseek-api | local/offline>
- Provider host: <OpenCode native | OpenCode Go | direct API | local runner>
- Billing path: <paid DeepSeek | OpenCode Go | local | other>
- Model id: <exact model id>
- Role: <Dev Agent | QA Agent | Code Review Agent | Security Agent | Architect | Monitoring Agent>
- Autonomy tier: <Tier A | Tier B | Tier C>
- Claimed merge authority: <none | Tier A only | Codex/human required>
- Commands already run: <focused tests and gates>

Source-of-truth rules:
- Active repo is /Users/sakibshuvo/projects/Entroping.
- Current diff root is the issue worktree above.
- /Users/sakibshuvo/Documents/Entroping is stale and forbidden.
- GitHub Issues, source files, tests, ADRs, docs/meta/DECISION_REGISTRY.yaml, PRs, CI, and QAnstitution/Hurl evidence decide truth.
- OpenCode, DeepSeek, Kimi, Qwen, local models, generated summaries, and chat history are evidence, not authority.

Review against:
- AGENTS.md
- docs/meta/AGENT_CONTROL_PLANE.md
- docs/meta/DOCS_GOVERNANCE.md
- docs/meta/FEATURE_DELIVERY_CHECKLIST.md
- docs/meta/AGENT_ROLE_REGISTRY.yaml
- issue body and comments if available
- changed source, tests, docs, scripts, and prompts

Check:
1. Is the diff inside the issue scope?
2. Did it touch forbidden Tier B or Tier C surfaces?
3. Are tests meaningful for the changed behavior?
4. Are docs and governance updates correct if docs changed?
5. Are there secrets, local artifacts, provider transcripts, .entroping, .opencode, or .codex state?
6. Is QAnstitution branding preserved?
7. Is deterministic Hurl execution preserved?
8. Does entroping run remain LLM-free?
9. Are provider and LiteLLM boundaries preserved?
10. Is the planned PR body evidence sufficient: Closes #<issue>, commands run, Documentation Impact Declaration, Agent Autonomy Declaration when relevant, and provider lane evidence?
11. Is this safe to merge, or does it need author action?

Return:
- recommendation: merge | do not merge | needs author action,
- blocking findings first, with file/line evidence,
- non-blocking concerns,
- tests or gates still required,
- whether Codex/human review is required before merge,
- whether the work stayed inside the declared autonomy tier.
PROMPT
```

## PR Review

Run this from OpenCode after it has opened a PR and needs Codex CLI to inspect
GitHub evidence, CI, and the PR body. Keep this read-only.

```bash
codex -C /Users/sakibshuvo/projects/Entroping \
  -s read-only \
  -a never \
  exec - <<'PROMPT'
You are the Entroping PR review gate for an OpenCode-produced pull request.

Mode:
Review only. Do not edit, stage, commit, push, merge, close issues, or mutate project-board state.

Repo:
cd /Users/sakibshuvo/projects/Entroping

PR:
#<pr-number>

Expected issue:
#<issue-number>

Expected provider lane:
<opencode/native-deepseek | opencode-go/kimi-k2.7-code | opencode-go/qwen3.7-max | opencode-go/other | direct/deepseek-api | local/offline>

Expected autonomy tier:
<Tier A | Tier B | Tier C>

Attempt these read-only review commands. If the read-only sandbox blocks a
command because a tool wants to write cache or local metadata, report the
blocked command and continue with the remaining evidence. Do not escalate or
rerun with write permissions.

- git status --short
- uv run python scripts/opencode_readiness.py --mode verification --format json
- gh pr view <pr-number> --repo sakibshuvo/Entroping --json number,title,state,mergeable,headRefName,baseRefName,body,closingIssuesReferences
- gh pr diff <pr-number> --repo sakibshuvo/Entroping
- gh pr checks <pr-number> --repo sakibshuvo/Entroping --watch

Review:
1. Confirm OpenCode readiness preflight passed or explain warnings.
2. Confirm the PR body names provider lane, provider host, billing path, concrete model id when known, role, autonomy tier, and merge authority.
3. Confirm `Closes #<issue-number>` is present.
4. Confirm Documentation Impact Declaration is checked and accurate.
5. Confirm Agent Autonomy Declaration is present for any autonomous claim.
6. Confirm the diff touches only declared allowed files.
7. Confirm no secrets, local env files, provider transcripts, .entroping artifacts, reports, .DS_Store, `.opencode` state, `.codex` state, or generated local state are tracked.
8. Confirm tests match the changed behavior and any behavior change has meaningful regression coverage.
9. Confirm architecture, QAnstitution branding, deterministic Hurl execution, and provider boundaries were not weakened.
10. Confirm Tier B and Tier C work requires Codex or human review before merge.
11. Confirm CI is green before any merge recommendation.
12. Recommend merge only if the autonomy tier permits it, local evidence is adequate, and GitHub CI is green.

Return:
- recommendation: merge | do not merge | needs author action,
- blocking findings first, with file/line evidence,
- provider lane evidence status,
- CI status,
- local verification status,
- docs impact status,
- issue closing status,
- required finish cleanup command,
- whether Codex/human review is required before merge.
PROMPT
```

## When To Use Which Command

- Use `codex review --base main -` from an issue worktree for local branch
  diffs before PR creation or before a Tier A autonomous merge decision.
- Use `codex review --uncommitted -` when OpenCode has not committed yet and
  wants review of staged, unstaged, and untracked changes.
- Use `codex review --commit <sha> -` for a single committed change.
- Use `codex exec -` for PR review when Codex needs GitHub CLI evidence such as
  PR body, closing issue references, diff, checks, or Actions status.

Do not use this prompt to bypass the normal Entroping gates. Codex review is
additional judgment; local tests, required gates, PR evidence, CI, and
`scripts/finish_issue.sh` still decide whether work can land.
