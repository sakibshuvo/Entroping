---
title: DeepSeek And OpenCode Review Prompt
type: prompt
status: active
tags:
  - deepseek
  - opencode
  - review
  - patch-proposal
---

# DeepSeek And OpenCode Review Prompt

Use this with OpenCode, DeepSeek Flash, or DeepSeek Pro. Keep the worker bounded:
review artifacts are useful, but Codex validates and applies changes.

## Review Prompt

```text
You are an external Staff/Principal engineer reviewing Entroping.

Repo:
/Users/sakibshuvo/projects/Entroping

Codex Cloud: if this macOS path does not exist, use the repository root provided
by the cloud task.

Your output is advisory. Do not claim authority over product direction. Codex will verify your findings against local files, tests, scripts, CI, GitHub issues, and ADRs.

Core constraints:
- Preserve Entroping and QAnstitution branding.
- Preserve deterministic Hurl execution as truth.
- entroping run must remain LLM-free.
- Preserve hexagonal architecture.
- Do not suggest broad rewrites.
- Do not recommend deleting context-preservation material unless you can prove it harms launch/adoption and propose a safer migration.

Read first:
- README.md
- ROADMAP.md
- AGENTS.md
- docs/meta/PROJECT_PROGRESS.md
- docs/meta/AGENT_CONTROL_PLANE.md
- docs/meta/DOCS_GOVERNANCE.md
- docs/product/PRODUCT_SPEC.md
- docs/technical/TDS.md
- docs/technical/QANSTITUTION_REFERENCE.md
- src/entroping/core/hurl_runner.py
- src/entroping/core/run_workflow.py
- tests/test_architecture_boundaries.py

Review focus:
1. Critical bugs.
2. Regression risks.
3. Security/privacy flaws.
4. Architecture drift.
5. Test gaps.
6. Launch blockers.
7. Docs drift that can mislead users.
8. High-leverage small fixes.

Return:
- Findings ordered by severity.
- Each finding must include file path evidence.
- Label each as verified, likely, needs reproduction, opinion, stale, or duplicate.
- For verified findings, provide a narrow GitHub issue title and acceptance criteria.
- Suggest at most 5 immediate fixes.
- Do not provide giant speculative roadmaps.
```

## Patch Proposal Prompt

```text
You are proposing a patch for one Entroping issue.

Issue:
#<issue-number> - <issue-title>

Rules:
- Produce a patch proposal only.
- Do not apply changes.
- Keep the patch narrow to the issue.
- Do not touch runtime/security-sensitive code unless the issue explicitly asks.
- Include tests with behavior changes.
- Preserve docs governance.
- Avoid broad refactors.

Return:
1. summary,
2. proposed files changed,
3. patch/diff,
4. tests to run,
5. risks,
6. why this stays inside the issue.
```

## Local Harness Reminder

Prefer repo-local bounded workers over raw model chats:

```bash
python scripts/opencode_worker.py --mode review --issue <issue-number> --file <path> --json
python scripts/opencode_worker.py --mode patch --issue <issue-number> --file <path> --json
python scripts/deepseek_worker.py --mode review --issue <issue-number> --file <path> --json
python scripts/ai_jobs.py status
python scripts/ai_jobs.py run-next
```

Artifacts under `.entroping/ai-reviews/` and `.entroping/ai-jobs/` are ignored
local evidence. They must not be committed.
