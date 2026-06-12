---
title: Stable Core Audit Prompt
type: prompt
status: active
tags:
  - stable-core
  - release
  - evidence
  - audit
---

# Stable Core Audit Prompt

Use this before claiming stable-core readiness.

```text
You are auditing Entroping stable-core readiness.

Repo:
cd /Users/sakibshuvo/projects/Entroping

Codex Cloud: if this macOS path does not exist, use the repository root provided
by the cloud task.

Default assumption:
stable_core_ready is false until proven otherwise.

Read:
- scripts/stable_core_readiness.py
- scripts/release_check.sh
- scripts/launch_readiness.py
- docs/meta/RELEASE_EVIDENCE.md
- docs/meta/release-evidence.json
- docs/meta/PROJECT_PROGRESS.md
- docs/meta/DOWNSTREAM_SMOKE_EVIDENCE.md
- docs/meta/DOWNSTREAM_FEEDBACK_KIT.md
- docs/meta/INSTALL_SMOKE_MATRIX.md
- docs/technical/CLI_COMPATIBILITY_AUDIT.md
- docs/technical/REPORT_SCHEMAS.md
- ROADMAP.md

Check evidence for:
1. package-index proof,
2. repeated release evidence,
3. compatibility discipline,
4. downstream feedback,
5. install smoke evidence,
6. real Hurl integration evidence,
7. report schema compatibility,
8. deterministic run boundary,
9. known external blockers,
10. unsupported stable claims.

Run if safe:
python scripts/stable_core_readiness.py
python scripts/launch_readiness.py
scripts/release_check.sh

Return:
- stable_core_ready: true/false,
- blockers with evidence,
- stale evidence,
- unsupported claims,
- next issues to close,
- commands run and results,
- what can be called alpha-ready versus stable-ready.
```
