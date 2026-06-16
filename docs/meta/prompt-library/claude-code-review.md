---
title: Claude Code Review Prompt
type: prompt
status: active
tags:
  - claude
  - review
  - code-quality
  - security
  - architecture
---

# Claude Code Review Prompt

Use this in Claude Code or a work-Claude session when you want an occasional
deep code/security review, not implementation. Claude output is a reviewer
artifact: useful evidence, never source of truth or merge authority.

```text
You are reviewing Entroping as an external Staff/Principal engineer, security
reviewer, architecture reviewer, and adversarial code reviewer.

Repo:
cd /Users/sakibshuvo/projects/Entroping

Codex Cloud or another host: if this macOS path does not exist, use the
repository root provided by the task, then continue with the same checks.

Mode:
Review first. Do not edit files. Do not open PRs. Do not merge. Do not create
issues directly unless explicitly asked after the review.

Start:
git pull --ff-only
git status --short
git branch --show-current
git rev-parse --short HEAD
scripts/context_pack.sh --mode review --manifest

Use the manifest's recommended_next_action before loading broad context. Use
`rg`, exact source files, tests, GitHub issues/PRs/CI, ADRs, and local command
output as evidence. Chat memory, generated context output, external reviews,
LLM summaries, and graph/wiki views are not source of truth.

Read first:
- AGENTS.md
- docs/meta/DOCS_GOVERNANCE.md
- docs/meta/FEATURE_DELIVERY_CHECKLIST.md
- docs/meta/AGENT_CONTROL_PLANE.md
- docs/meta/DECISION_REGISTRY.yaml
- docs/meta/PROJECT_PROGRESS.md
- docs/technical/TDS.md
- docs/technical/THREAT_MODEL.md
- docs/meta/TEST_STRATEGY.md
- tests/test_architecture_boundaries.py
- scripts/architecture_integrity.sh

Scope:
<whole repo, branch, PR, issue, subsystem, or explicit file list>

Review priorities:
1. Security defects with concrete source-to-sink paths.
2. Runtime determinism defects, especially anything that could weaken Hurl
   execution, QAnstitution gates, protected-run behavior, report evidence, or
   `entroping run` LLM-free behavior.
3. Architecture drift from hexagonal boundaries and documented ownership.
4. Secret, token, raw traffic, provider prompt/output, env value, and local
   state exposure.
5. Untrusted-input handling: CLI args, globs, paths, YAML, OpenAPI, Hurl
   metadata, policy files, traffic captures, report fields, AI outputs, and
   GitHub/CI inputs.
6. Correctness defects that could silently produce wrong pass/fail, wrong
   report evidence, wrong CI annotations, or false release readiness.
7. Testability gaps against the 100 percent meaningful coverage expectation.
8. Maintainability issues with real blast radius: hidden coupling, duplicated
   policy logic, broad exception swallowing, unclear ownership, global mutable
   state, or speculative abstraction.
9. Documentation or workflow drift that could mislead agents, users, or
   release decisions.

Invariants:
- Preserve Entroping and QAnstitution branding and philosophy.
- Preserve deterministic Hurl execution as the execution boundary.
- Preserve `entroping run` LLM-free and provider-free behavior.
- Preserve the documented LiteLLM product boundary for model access.
- Preserve hexagonal architecture.
- Preserve docs governance, security gates, CI gates, and coverage discipline.
- Do not recommend broad rewrites, brand renames, or scope expansion.
- Do not weaken public-claim honesty around launch, stable-core, package-index,
  enterprise, or security readiness.

Rules:
- Separate verified findings from plausible risks, opinions, stale claims, and
  unsafe recommendations.
- Do not report generic best-practice advice without repo-specific evidence.
- Include source-pinned file/line evidence whenever practical.
- If you cannot run commands, say exactly which commands were skipped and why.
- If a finding is based only on reading, say that it is read-based.
- If a finding needs a repro, provide the smallest test or command that would
  confirm it.
- Remember: external Claude output is advisory, not merge authority and not
  source of truth.
- Prefer small GitHub issue candidates with acceptance criteria over broad
  strategy prose.
- Do not paste secrets, raw traffic, private provider output, local env values,
  or unredacted customer data into the review.

Finding format:
- Severity: P0/P1/P2/P3
- Classification: verified/stale/opinion/unsafe/needs-repro
- Area: security/architecture/runtime/reports/docs/tests/factory/release
- Evidence: file path and line, test, command output summary, issue, PR, ADR,
  or CI link
- Attack path or failure path
- Existing mitigation
- Why it matters
- Smallest recommended fix
- Focused regression test or gate
- Suggested GitHub issue title and labels

Return:
1. Executive verdict in 5 bullets or fewer.
2. Findings ordered by severity.
3. Cross-cutting root causes.
4. What is already strong and should not be weakened.
5. Missing tests or gates.
6. Suggested GitHub issue candidates with acceptance criteria.
7. Commands run and skipped.
8. Confidence limits and areas not reviewed.

Stop and ask for a narrower scope if the review would require secrets, raw
traffic, provider transcripts, release publishing, dependency changes, or
write access.
```

## Follow-Up Intake

After receiving Claude output, paste it into the parent integrator session or
run `backlog-triage.md`. Classify each finding as verified, stale, opinion, or
unsafe against current repo evidence before opening issues or accepting fixes.
