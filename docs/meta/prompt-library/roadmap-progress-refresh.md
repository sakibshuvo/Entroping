---
title: Roadmap And Progress Refresh Prompt
type: prompt
status: active
tags:
  - roadmap
  - progress
  - docs
  - governance
---

# Roadmap And Progress Refresh Prompt

Use this when project progress feels confusing or stale.

```text
You are refreshing Entroping roadmap and progress context.

Repo:
cd /Users/sakibshuvo/projects/Entroping

Codex Cloud: if this macOS path does not exist, use the repository root provided
by the cloud task.

Goal:
Make project direction and current progress clear without creating documentation sprawl.

Start:
git pull --ff-only
git status --short
gh issue list --repo sakibshuvo/Entroping --state open --limit 120
gh pr list --repo sakibshuvo/Entroping --state open --limit 40
python scripts/backlog_health.py

Read:
- docs/meta/DOCS_GOVERNANCE.md
- ROADMAP.md
- docs/meta/PROJECT_PROGRESS.md
- docs/product/MVP_PLAN.md
- docs/meta/RELEASE_EVIDENCE.md
- .context/changelog.md
- .context/plan.md

Rules:
- GitHub Issues are the backlog.
- ROADMAP.md changes only when release sequence or public scope changes.
- PROJECT_PROGRESS.md is a short dashboard, not a diary.
- Do not add a new strategy doc.
- Update existing lines where possible.
- Preserve stable-core honesty; do not claim stable readiness without package-index proof, repeated release evidence, compatibility discipline, and downstream feedback.

Return first:
1. stale or confusing progress claims,
2. mismatches between GitHub issues and docs,
3. docs that should change,
4. docs that should not change,
5. proposed minimal patch plan.

If approved to edit:
- update the smallest canonical surfaces,
- run scripts/doc_governance_check.sh,
- run python scripts/public_claims_audit.py if public claims changed,
- run focused release-doc tests if PROJECT_PROGRESS or release evidence changed.
```
