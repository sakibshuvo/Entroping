---
title: Architecture Boundary Brief Prompt
type: prompt
status: active
tags:
  - architecture
  - opencode
  - deepseek
  - guardrails
---

# Architecture Boundary Brief Prompt

Use this as an attachment to OpenCode/DeepSeek issue packets when a worker
needs an explicit boundary before editing. It is a brief, not a substitute for
`AGENTS.md`, `docs/meta/AGENT_CONTROL_PLANE.md`, local source files, tests, or
CI.

```text
You are receiving an Entroping architecture-boundary brief for one issue.

Repo:
cd /Users/sakibshuvo/projects/Entroping

Issue:
#<issue-number> - <issue-title>

## Ownership Boundary

- Parent integrator: <Codex | human | other named owner>
- Worker role: <Product Manager | Architect | Dev Agent | QA Agent | Code Review Agent | Security Agent | Monitoring Agent>
  Declare the role from `docs/meta/AGENT_ROLE_REGISTRY.yaml`.
- Autonomy tier: <Tier A autonomous lane | Tier B assisted lane | Tier C restricted lane>
- Merge authority: <Tier A autonomous after gates and green CI | Codex/human required | no merge authority>
  Merge authority must match the tier rules in `docs/meta/AGENT_CONTROL_PLANE.md`.
- Write authority: one issue-scoped worktree only.
- Source of truth: local files, tests, ADRs, and GitHub evidence, not model summaries.

## Allowed Files

- <exact file or directory>
- <exact test or guard file>
- <canonical docs/context file if needed>

## Forbidden Files

- Runtime code outside the issue scope.
- Hurl runner behavior.
- `entroping run`.
- redaction, proxy, traffic capture, raw traffic, or audit evidence paths.
- Provider boundary or LiteLLM routing.
- release publishing, dependencies, secrets, credentials, or local env files.
- architecture boundary changes unless the issue explicitly assigns them to Codex/human review.

## Architecture Invariants

- Preserve hexagonal architecture: domain and bridge code must not import CLI,
  core, brain, studio, or adapter-only modules.
- Preserve deterministic Hurl execution; do not replace Hurl with Python HTTP
  clients or model-generated runtime checks.
- Preserve QAnstitution branding and the Entroping philosophy: QAnstitution is
  Law, Traffic is Truth, Hurl is the Enforcer.
- Keep `entroping run` provider-free and LLM-free.
- Do not mutate source `.hurl` files during run-time gate injection.
- Treat paths, globs, YAML, Hurl metadata, captured traffic, and model output as
  untrusted boundary inputs.

## Provider And Runtime Constraints

- Product runtime model access must stay behind the documented LiteLLM boundary.
- Repo-local OpenCode/DeepSeek helpers are maintainer tooling only and must not
  move into product runtime behavior.
- Do not send secrets, raw traffic, cookies, tokens, credentials, provider
  transcripts, or env values to any model.
- Do not claim stable-core, package-index, enterprise, security, or adoption
  readiness without current repo and GitHub evidence.

## Tests To Run

- Focused tests for touched files:
  `<command>`
- Documentation governance if docs changed:
  `scripts/doc_governance_check.sh`
- Normal code gate:
  `scripts/feature_gate.sh` for repository hygiene, docs governance, shell
  quality, static checks, and tests.
- Security/provider/subprocess/path/dependency gate when relevant:
  `scripts/feature_gate.sh --security`
- Required issue gate:
  `<command from issue>`

## Architecture Tests

- `uv run pytest tests/test_architecture_boundaries.py -q` when source imports,
  package boundaries, or runtime architecture are touched.
- `uv run pytest tests/test_agent_workflow_docs.py -q` when agent workflow,
  prompt-library, or autonomous-lane guardrails are touched.
- `scripts/regression.sh --security` before Tier A autonomous merge or when the
  issue requires it.

## Stop Conditions

Stop and report before editing or merging if:

- The issue crosses from Tier A into Tier B or Tier C scope.
- A needed file is outside the Allowed Files list.
- A suggested change weakens hexagonal architecture, deterministic Hurl
  execution, QAnstitution branding, or `entroping run` provider-free behavior.
- Evidence comes only from model summaries instead of local repo files, tests,
  ADRs, GitHub issues, PRs, or CI.
- A test, docs governance check, security gate, or GitHub CI check fails.
- You find secrets, credentials, tokens, cookies, or local env files in the
  diff.
- You find raw traffic, provider transcripts, or audit evidence contents in the
  diff.
- You find generated local state such as `.entroping/`, generated context
  output, reports, or cache files in the diff.
```
