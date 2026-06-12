---
title: Security Review Prompt
type: prompt
status: active
tags:
  - security
  - review
  - threat-model
  - regression
---

# Security Review Prompt

Use this for scoped security review of a branch, PR, or issue.

```text
You are performing a security review of Entroping.

Repo:
cd /Users/sakibshuvo/projects/Entroping

Codex Cloud: if this macOS path does not exist, use the repository root provided
by the cloud task.

Scope:
<branch, PR, issue, or file list>

Mode:
Review first. Do not edit files unless explicitly asked to fix a validated finding.

Read:
- AGENTS.md
- docs/technical/THREAT_MODEL.md
- docs/meta/FEATURE_DELIVERY_CHECKLIST.md
- tests/test_architecture_boundaries.py
- changed files in scope

Threat areas:
1. subprocess execution and Hurl binary resolution,
2. YAML/QAnstitution parsing,
3. path traversal and symlink handling,
4. proxy capture and redaction,
5. reports leaking secrets or env values,
6. provider/model prompts and direct DeepSeek/OpenCode workers,
7. dependency or release script risk,
8. GitHub Actions permissions,
9. unsafe defaults in CI/examples,
10. architecture boundary bypasses.

Rules:
- Separate validated findings from plausible risks and hardening ideas.
- Do not report generic theoretical issues without a repo-specific attack path.
- Include source-to-sink reasoning.
- Include severity and exploitability.
- Check whether tests already cover the risk.
- Prefer regression tests for fixes.

Return:
- findings ordered by severity,
- attack path,
- affected files/lines,
- existing mitigations,
- missing tests,
- recommended fix,
- verification command.
```
