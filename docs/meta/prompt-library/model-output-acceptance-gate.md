---
title: Model-Output Acceptance Gate Prompt
type: prompt
status: active
tags:
  - agents
  - opencode
  - deepseek
  - kimi
  - qwen
  - review
  - metrics
---

# Model-Output Acceptance Gate Prompt

Use this when a cheap or local model produced a large review, patch, PR, or
implementation draft and a maintainer or reviewer needs to decide what enters
Entroping. The operating rule is simple: cheap models may generate
aggressively; deterministic gates accept selectively.

No model output is source of truth. Repo files, GitHub issues, PRs, CI, tests,
ADRs, QAnstitution/Hurl evidence, docs governance, and local gates decide what
is accepted.

```text
You are applying the Entroping model-output acceptance gate.

Repo:
cd /Users/sakibshuvo/projects/Entroping

Codex Cloud or another host: if this macOS path does not exist, use the
repository root provided by the task, then continue with the same checks.

Input to evaluate:
- issue: #<issue>
- PR or local branch: <pr-number-or-branch>
- provider lane: <opencode/native-deepseek | deepseek-api/direct | opencode-go/kimi-k2.7-code | opencode-go/qwen3.7-max | opencode-go/other | local/offline>
- provider host: <OpenCode Desktop | OpenCode CLI | repo-local DeepSeek worker | OpenCode Go | local runtime>
- billing path: <paid DeepSeek API | OpenCode Go subscription | local/offline | other>
- model id: <exact model id when known>
- autonomy tier: <Tier A autonomous lane | Tier B assisted lane | Tier C restricted lane>
- merge authority: <autonomous Tier A worker | Codex review required | human review required | no merge authority>

Start:
git pull --ff-only
git status --short
gh issue view <issue> --repo sakibshuvo/Entroping
scripts/context_pack.sh --mode implementation --manifest

Worktree rule:
The accepted output must come from an issue-scoped branch created with
`scripts/start_issue.sh <issue> <type>/<short-kebab-description>` unless the
input is a read-only review. Do not accept a write diff made directly on main.

Evaluate:
1. Confirm the work has one issue, one worktree, one branch, and no unrelated
   changes.
2. Confirm the provider lane, provider host, billing path, model id, autonomy
   tier, and merge authority are explicit.
3. Confirm the diff stayed inside the issue scope and the declared autonomy
   tier.
4. Confirm source-of-truth evidence comes from local files, tests, GitHub
   issue/PR/CI state, ADRs, and canonical docs, not model summaries.
5. Confirm focused tests cover touched behavior.
6. For Tier A autonomous lane output, require all of:
   - PR body evidence validates with
     `scripts/pr_body_check.py --body-file <body.md> --require-opencode-evidence --issue <issue>`.
   - `scripts/regression.sh --security` passed locally.
   - GitHub CI is green.
   - The PR includes `Closes #<issue>`.
   - Cleanup can run with `scripts/finish_issue.sh <issue>` after merge.
7. For Tier B assisted lane output, require Codex or human review before merge.
8. For Tier C restricted lane output, accept only review findings or issue
   proposals; do not merge implementation changes.
9. If factory metrics are part of the claim, inspect `scripts/factory_metrics.py
   report` and do not infer missing token or cost values.

Forbidden autonomous acceptance:
- architecture boundary changes,
- `entroping run`,
- Hurl runner behavior,
- protected-run safety,
- redaction,
- proxy or traffic capture,
- provider runtime or LiteLLM boundary changes,
- dependencies,
- release publishing,
- secrets or credentials,
- raw traffic,
- audit evidence,
- security fixes,
- destructive filesystem behavior,
- QAnstitution branding changes,
- deterministic Hurl execution changes.

Classify each model output item as one of:
- accepted: grounded in repo evidence, in scope, covered by tests/gates, and
  allowed by the autonomy tier.
- needs Codex or human review: useful but Tier B/Tier C, security-sensitive,
  architecture-sensitive, ambiguous, or missing reviewer judgment.
- convert to GitHub issue: valid concern or idea, but outside the current issue
  or too large for the current branch.
- reject as stale, opinion, or unsafe: contradicted by repo evidence, lacks
  file/line/test support, weakens guardrails, leaks sensitive material, or asks
  for forbidden scope.

Output:
- issue:
- source artifact or PR:
- provider lane:
- provider host:
- billing path:
- model id:
- autonomy tier:
- merge authority:
- files read:
- files changed:
- tests/gates:
- CI status:
- factory metrics evidence:
- accepted:
- needs Codex or human review:
- convert to GitHub issue:
- reject as stale, opinion, or unsafe:
- final decision:
```

## Reviewer Notes

Use this prompt after model generation, not before. Worker-launch prompts such
as `issue-worker.md`, `opencode-desktop-handoff.md`, and
`model-comparison-trial.md` tell workers how to start; this prompt tells a
reviewer how to ingest the output without treating volume as correctness.

Keep partial value. A large cheap-model output can still be productive when
only one regression test, one bug report, or one docs correction is accepted.
Rejecting the rest is part of the acceptance gate, not a failure to use the
model.
