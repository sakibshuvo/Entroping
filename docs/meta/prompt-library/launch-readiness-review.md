---
title: Launch Readiness Review Prompt
type: prompt
status: active
tags:
  - launch
  - adoption
  - readme
  - packaging
---

# Launch Readiness Review Prompt

Use this to assess whether the public repo is ready for new developers.

```text
You are reviewing Entroping for public launch readiness.

Repo:
cd /Users/sakibshuvo/projects/Entroping

Codex Cloud: if this macOS path does not exist, use the repository root provided
by the cloud task. 

Do not implement. Review and return findings.

Read:
- README.md
- ROADMAP.md
- CHANGELOG.md
- docs/meta/PROJECT_PROGRESS.md
- docs/meta/RELEASE_EVIDENCE.md
- docs/meta/PUBLIC_REPO_SURFACE.md
- docs/meta/DISTRIBUTION_RECOMMENDATION.md
- docs/meta/INSTALL_SMOKE_MATRIX.md
- docs/user/USER_GUIDE.md
- docs/user/GITHUB_ACTIONS_STARTER.md
- examples/checkout-api/README.md
- scripts/demo.sh
- scripts/release_check.sh
- scripts/launch_readiness.py

Assess:
1. Can a new developer understand the use case in 60 seconds?
2. Can they run a demo in two minutes?
3. Is install guidance honest and current?
4. Are launch claims supported by evidence?
5. Is the public repo surface clean enough?
6. Are README, docs site, examples, and roadmap aligned?
7. Are alpha/stable boundaries honest?
8. Are there obvious adoption blockers?

Constraints:
- Do not suggest renaming Entroping or QAnstitution.
- Do not demand deletion of context-preservation material without a safer migration.
- Treat `stable_core_ready` as false unless hard evidence exists.
- Prefer small launch-blocking issues over broad cleanup.

Return:
- launch score,
- top launch blockers,
- first-five-minute critique,
- unsupported public claims,
- quick wins,
- issues to create with acceptance criteria,
- what is already strong.
```
