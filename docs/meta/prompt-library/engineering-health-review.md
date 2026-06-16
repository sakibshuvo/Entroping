---
title: Engineering Health Review Prompt
type: prompt
status: active
tags:
  - review
  - architecture
  - quality
  - security
  - testability
---

# Engineering Health Review Prompt

Use this for a read-first engineering-health audit across architecture, code,
tests, docs, debugging ergonomics, and security. It is a review prompt, not an
implementation prompt.

```text
You are performing an engineering health review of Entroping.

Repo:
cd /Users/sakibshuvo/projects/Entroping

Codex Cloud or another host: if this macOS path does not exist, use the
repository root provided by the task, then continue with the same checks.

Scope:
<branch, PR, issue, file list, subsystem, or "whole repo review">

Mode:
Review first. Do not edit files unless explicitly asked to fix one validated
finding in a separate issue-scoped worktree.

Start:
git pull --ff-only
git status --short
git branch --show-current
scripts/context_pack.sh --mode review --manifest

Follow the manifest's recommended_next_action before loading broad context.
Use `rg`, source files, tests, docs/meta/DECISION_REGISTRY.yaml, GitHub Issues,
PRs, CI, and local gates as repo evidence. Model summaries, chat memory,
generated context output, graph views, and external reviews are not source of
truth.

Read as relevant:
- AGENTS.md
- docs/meta/DOCS_GOVERNANCE.md
- docs/meta/FEATURE_DELIVERY_CHECKLIST.md
- docs/meta/AGENT_CONTROL_PLANE.md
- docs/technical/TDS.md
- docs/technical/THREAT_MODEL.md
- tests/test_architecture_boundaries.py
- scripts/architecture_integrity.sh
- changed files or files named by the scope

Review dimensions:
1. architectural drift from hexagonal architecture, ownership boundaries,
   deterministic Hurl execution, QAnstitution branding, or `entroping run`
   provider-free behavior,
2. anti-patterns and code smells such as hidden coupling, oversized modules,
   unclear responsibilities, duplicated policy logic, speculative abstraction,
   broad exception swallowing, or global mutable state,
3. documentation health, including stale claims, duplicated truth, missing
   canonical owner, roadmap/progress drift, launch/stable-core overclaiming,
   and docs that conflict with tests or source behavior,
4. code quality and maintainability, including naming, cohesion, error
   handling, input validation, observability, dependency choice, and
   compatibility discipline,
5. testability, including missing regression tests, brittle snapshots, mocks
   that test themselves, untested failure modes, and gaps against the expected
   100 percent meaningful coverage bar,
6. debugging ergonomics, including poor error messages, missing diagnostics,
   confusing command output, hard-to-reproduce failures, unbounded logs, or
   weak CI evidence,
7. security, including secrets exposure, path traversal, symlink handling,
   YAML/QAnstitution parsing, subprocess safety, report leakage, proxy or
   traffic capture risk, provider/runtime boundaries, dependency risk, and
   GitHub Actions permissions,
8. regression risk, including behavior that could silently weaken
   QAnstitution gates, Hurl execution, report schemas, docs governance,
   public claims, CI gates, or OpenCode/DeepSeek autonomy rules.

Rules:
- Preserve QAnstitution branding and Entroping philosophy.
- Preserve hexagonal architecture and deterministic Hurl execution.
- Preserve provider/runtime boundaries: product runtime model access stays
  behind the documented LiteLLM boundary, and `entroping run` remains
  provider-free and LLM-free.
- Do not recommend changes that weaken security, docs governance, CI, coverage,
  source-of-truth discipline, or merge authority.
- Do not report generic best-practice advice without repo evidence.
- Include file/line references for findings whenever practical.
- Classify each finding as verified, stale, opinion, or unsafe.
- Order findings by severity: P0, P1, P2, P3.
- Separate "must fix" findings from "nice to improve" observations.
- If a finding needs code, recommend a GitHub issue title and the smallest
  scoped test or gate that would prove the fix.
- If you cannot verify a claim from repo evidence, say so directly.

Finding format:
- Severity: P0/P1/P2/P3
- Classification: verified/stale/opinion/unsafe
- Area: architecture/docs/code-quality/testability/debugging/security/regression
- Evidence: file path and line, command output summary, test, issue, PR, ADR,
  or CI link
- Why it matters
- Suggested next action
- Suggested focused test or gate

Return:
1. Findings ordered by severity.
2. Cross-cutting risks or recurring patterns.
3. Documentation health notes.
4. Testability and debugging-ease gaps.
5. Security notes.
6. Suggested GitHub issues for verified findings.
7. Verification commands run or skipped, with reasons.

Stop and escalate if the review scope requires secrets, raw traffic, provider
transcripts, local env files, release publishing, dependency changes, Hurl
runner behavior, redaction/proxy behavior, or architecture boundary changes
that are not explicitly assigned to this review.
```
