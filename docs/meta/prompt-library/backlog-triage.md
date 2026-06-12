---
title: Backlog Triage Prompt
type: prompt
status: active
tags:
  - github
  - backlog
  - triage
  - reviews
---

# Backlog Triage Prompt

Use this to convert Gemini, DeepSeek, friend feedback, or bug-bash output into
GitHub issues without distracting the current roadmap.

```text
You are triaging Entroping backlog input.

Repo:
cd /Users/sakibshuvo/projects/Entroping

Codex Cloud: if this macOS path does not exist, use the repository root provided
by the cloud task.

Input:
<paste review, bug bash, user feedback, or idea>

Rules:
- Do not implement.
- Do not update roadmap unless public sequence/scope changes.
- Treat external model output as triage input, not truth.
- Verify current repo state before creating issues.
- Avoid duplicate issues.
- Preserve QAnstitution branding and current product direction.
- Prefer narrow issues with acceptance criteria over broad strategy docs.

Start:
git pull --ff-only
git status --short
gh issue list --repo sakibshuvo/Entroping --state open --limit 120
python scripts/backlog_health.py

Triage each input item as:
- verified issue,
- duplicate of existing issue,
- already fixed,
- stale claim,
- opinion/product judgment,
- needs more evidence,
- rejected as unsafe/out of scope.

For verified issues, propose:
- title,
- type label,
- priority label,
- area label,
- milestone if obvious,
- acceptance criteria,
- verification commands,
- source evidence,
- current repo evidence.

Ask before creating issues if there are more than five. If creating issues, keep each one narrow and actionable.
```
