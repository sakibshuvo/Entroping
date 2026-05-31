---
title: Threat Model
type: technical
status: active
tags:
  - security
  - threat-model
  - stable-core
---

# Threat Model

**Status:** refreshed on 2026-05-31 for stable-core review.

This is the repository-scoped threat model for the current Entroping alpha. It
updates the earlier Codex Security scan artifact under `/tmp` so future agents,
reviewers, and release checks have a tracked source of truth.

The model is intentionally local-first. Entroping is a developer CLI, not a
hosted service today. The main risks are local filesystem damage, CI compromise,
secret leakage, unsafe subprocess behavior, captured-traffic exposure, misleading
governance results, and future drift from the Hurl-native deterministic boundary.

## Current Runtime Surfaces

Implemented surfaces in the current repo:

- Typer CLI commands listed in `docs/technical/CLI_COMPATIBILITY_AUDIT.md`.
- QAnstitution YAML loading, local imports, typed condition parsing, gate
  matching, and policy-to-Hurl assertion compilation.
- Hurl discovery, Hurl metadata parsing, temporary gate-injected execution
  copies, and the **Hurl subprocess boundary** for deterministic `entroping run`.
- JSON, JUnit, HTML, drift, bug, and traceability reports.
- OpenAPI loading, OpenAPI-to-Hurl generation, and deterministic coverage audit.
- Brain/Architect flows through **LiteLLM/provider boundaries** with persona
  loading, prompt construction, structured output parsing, Hurl validation, and
  staged writes.
- Eye capture through mitmproxy, pre-persistence **Traffic capture and redaction**,
  SQLModel-backed SQLite state under `.entroping/state.db`, `freeze`, WireMock
  mocks, dependency maps, and value-free dependency drift.
- Read-only Studio TUI over local status, reports, and traffic-state visibility.
- Release, regression, community-profile, package, and issue-session scripts.

## Protected Assets

The assets Entroping must protect are:

- User source trees, committed Hurl tests, QAnstitution policy, and ADR/docs.
- Local env files, process environment values, API keys, model credentials,
  cookies, bearer tokens, and token-like strings.
- Captured HTTP traffic, redacted traffic summaries, and `.entroping/state.db`.
- Generated reports under `reports/` and latest runtime state under `.entroping/`.
- CI runners, GitHub Actions workflow trust, release artifacts, and package
  metadata.
- The deterministic governance invariant: AI may propose tests, but committed
  Hurl plus QAnstitution plus Hurl execution decides pass or fail.

## Trust Boundaries

### CLI Input Boundary

Attacker-controlled inputs include CLI args, globs, environment names, report
formats, policy paths, OpenAPI files, Hurl files, Hurl metadata comments,
captured traffic, and model output. Every boundary should fail closed with
actionable errors instead of best-effort parsing.

### File Writes and Symlinks

**File writes and symlinks** are high-risk because Entroping writes generated
tests, reports, drift artifacts, WireMock mappings, dependency maps, config
updates, and runtime state. The invariant is:

- reject traversal and absolute-path writes unless a design explicitly allows it;
- reject symlinked path components before resolving or replacing files;
- use same-directory temporary files and atomic replacement for artifacts;
- never mutate source `.hurl` files during `entroping run`.

### Hurl Subprocess Boundary

Hurl and Hurl parser calls cross into external binaries. The invariant is:

- use argument arrays, never shell interpolation;
- pass secrets through temporary variables files, not visible argv;
- run with a minimal child environment;
- apply timeouts, cleanup, bounded output capture, and output redaction;
- treat a user-controlled or compromised `hurl` binary as an operator-controlled
  local risk, not as trusted application code.

### Report And Markdown Boundary

Reports can be consumed by browsers, CI systems, GitHub, Obsidian, and humans.
Hurl output, paths, URLs, headers, metadata comments, OpenAPI values, and model
text are untrusted at render time. HTML, XML, Markdown, and table output must
escape or redact untrusted values.

### Traffic Capture And Redaction

Traffic capture processes live URLs, headers, cookies, bodies, status codes, and
dependency topology. The invariant is:

- redact before persistence;
- refuse unredacted records in the store;
- keep body summaries bounded;
- strip URL userinfo and token-like query/body/header values;
- keep captured state under `.entroping/state.db` and out of Git;
- never send raw captured traffic to Brain or model providers.

### LiteLLM/provider Boundaries

Architect commands can call LiteLLM, but deterministic runtime cannot. The
invariant is:

- keep `entroping run` LLM-free;
- use LiteLLM as the only provider abstraction;
- keep provider API keys out of `qanstitution.yaml`, logs, reports, prompts, and
  committed examples;
- validate model output before filesystem writes;
- redact provider errors and prompt context before CLI output.

### Dependency Policy

The **Dependency policy** is local-first and conservative:

- default install stays lightweight;
- AI, proxy, and Studio dependencies remain optional extras;
- default and all-extras dependency audits run in security gates;
- optional extras need runtime smoke coverage before stable claims, enforced by
  the `optional-extras-smoke` CI lane added for issue #227;
- standalone binaries remain deferred because bundling native dependencies
  increases update and signing responsibility.

## Security Controls Already In Place

| Surface | Current controls |
| --- | --- |
| CLI compatibility | Locked command audit plus tests prevent accidental aliases and command drift. |
| Architecture | AST boundary tests prevent domain/bridge imports from adapters, direct provider SDK imports, and Brain imports in deterministic run core. |
| QAnstitution | Pydantic models forbid extras, validate condition DSL at load time, and reject malformed policies. |
| Hurl execution | Subprocess adapter uses argument arrays, timeouts, redaction, minimal environment, temp execution copies, and deterministic report ordering. |
| Filesystem | Safe writes reject symlinked path components and preserve existing artifacts on atomic-write failure. |
| Reports | JSON, JUnit, HTML, Markdown, audit, redaction, and traceability outputs escape or redact untrusted values. |
| Brain | Prompt builder rejects secret-like context, provider errors are redacted, output is parsed before write, and Hurl validation runs before generated files land. |
| Traffic | Redaction covers sensitive headers, URL userinfo/query values, JSON fields, token-like text, and bounded body summaries before SQLModel persistence; `report redaction` lets users inspect counts-only coverage before freezing or mapping. |
| CI | Pull requests run `scripts/regression.sh --security`, `scripts/audit_quality.sh`, optional-extras runtime smoke, and live demo smoke. |

## Validated Findings And Remediation Status

The last full post-alpha security review was issue #96. It validated 14
candidates and fixed all 14 before merge. **No open validated security findings**
remain from that scan.
The remediation tracked by issue #198 implemented the counts-only
captured-traffic redaction review report so users can inspect redaction coverage
before freezing or mapping traffic.

Important follow-up issues that keep residual risk visible:

| Issue | Residual risk tracked |
| --- | --- |
| issue #206 | Build a cross-platform install and smoke matrix so release claims are not macOS-only. |
| issue #203 | Stabilize report artifact schemas before downstream consumers depend on them. |

No new remediation issue is required by this refresh because the current residual
risks already map to open GitHub issues.

## Stable-Core Security Bar

Before stable-core claims:

1. `scripts/regression.sh --security` and `scripts/audit_quality.sh` must pass on
   the release commit.
2. Dependency audits must cover default and all-extras trees.
3. CLI command, exit-code, and report-artifact claims must match
   `docs/technical/CLI_COMPATIBILITY_AUDIT.md`.
4. The threat model must be reviewed against new runtime surfaces.
5. Any validated security finding must either be fixed, suppressed with concrete
   evidence, or tracked as a release-blocking GitHub issue.

## Out Of Scope Today

These are not current product surfaces and should not dominate current severity
calibration:

- hosted multi-tenant cloud;
- remote user authentication;
- browser-hosted report sharing;
- enterprise policy approval workflows;
- Studio mutation workflows;
- automatic package-index publishing;
- standalone signed binaries.

They become in scope when implementation or release claims make them real.
