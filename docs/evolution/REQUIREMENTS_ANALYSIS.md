---
title: Entroping v4.1 Requirements Analysis
type: evolution
status: historical
---

# Entroping v4.1 Requirements Analysis


**Purpose:** Extract and reconcile requirements from the original Gemini conversation, older local specs, the v4.1 slide deck, and the current consolidated notes.  
**Decision:** This document explains how the idea evolved and what the final v4.1 specification now treats as authoritative.

## 1. Sources Reviewed

| Source | Role in Analysis |
| --- | --- |
| `/Users/sakibshuvo/projects/entroping-specs/notebookLM/2026-05-29 NotebookLM Specs.md` | Final consolidated NotebookLM Markdown export and primary current source snapshot |
| `/Users/sakibshuvo/projects/entroping-specs/gemini chat exports exports /2026-05-29 Gemini-_33.md` | Original project evolution conversation and final command debates |
| `/Users/sakibshuvo/projects/entroping-specs/2025-12-26 gemini spec/PRODUCT_SPEC.md` | Older product concept |
| `/Users/sakibshuvo/projects/entroping-specs/2025-12-26 gemini spec/TDS.md` | Older technical architecture |
| `/Users/sakibshuvo/projects/entroping-specs/2025-12-26 gemini spec/USER_GUIDE.md` | Older user-facing workflow |
| `/Users/sakibshuvo/projects/entroping-specs/2025-12-26 gemini spec/MVP_PLAN.md` | Earlier implementation phasing |
| `/Users/sakibshuvo/projects/entroping-specs/notebookLM/2026-04-25 Entroping_Agentic_Integrity (1).pdf` | Recent slide framing before the final NotebookLM Markdown export |
| User-provided v4.1 Markdown block | Stable naming and philosophy later consolidated into the NotebookLM export |

## 2. Evolution Summary

Entroping did not start as a purely Hurl-native governance tool. It evolved through several design stages:

| Stage | Main Idea | What Changed |
| --- | --- | --- |
| v1 | Local AI testing assistant with Brain, Muscle, Face, Eye, Memory | Established local-first CLI, AI generation, Hurl execution, mitmproxy observation, SQLite memory |
| v2/v3 | Bruno as human-friendly Face, Hurl as machine Muscle | Introduced `.bru` to `.hurl` compiler idea, interactive workflows, and traffic-based testing |
| SpecKit/QualKit phase | `quality.yaml` as strategic QA manifest | Added explicit sources, stories, glossary, scenarios, gates, and governance thinking |
| v4 pivot | Hurl-native and QAnstitution-first | Shelved Bruno/JIT compiler, promoted Hurl files as first-class truth, renamed law file to `qanstitution.yaml` |
| v4.1 | Hurl-native governance plus restored Eye lifecycle | Reintroduced `watch`, `freeze`, `map`, mocks, golden masters, and dependency mapping |
| Market framing | CI/CD firewall for AI-generated code | Clarified Entroping as runtime governance, not just an AI test generator |

## 3. Final v4.1 Product Decision

The final stable direction is:

- Hurl files are the source format for executable tests.
- `qanstitution.yaml` is the source format for executable quality law.
- `mitmproxy` is the source of observed traffic truth.
- LiteLLM is the source of model-provider abstraction.
- The CLI is the primary interface; the TUI is local mission control.
- Bruno is not part of the MVP execution path.
- The solo-developer path is source install and fast iteration first; native packaging and Cloud come later.
- The Brain is local-first through LiteLLM/Ollama with explicit cloud fallback, not external provider CLIs.

## 4. Major Reconciliations

### 4.1 Bruno and the Face Layer

Older docs positioned Bruno as the human-friendly Face and proposed a Bruno-to-Hurl JIT compiler.

Final v4.1 decision:

- Bruno can still be used as an external client routed through `entroping watch`.
- Bruno is not the canonical test format.
- A `.bru` compiler is future/optional.
- Hurl is first-class and Git-native.

Reason:

- Hurl-native execution reduces moving parts.
- It avoids a fragile intermediate compiler.
- It aligns with deterministic enforcement.

### 4.2 `quality.yaml` to `qanstitution.yaml`

The conversation moved from a generic quality manifest to a branded governance document.

Final v4.1 decision:

- Use `qanstitution.yaml`.
- Treat it as executable law, not documentation.
- Keep agent persona prompts in Markdown files.
- Keep deterministic gates in YAML.

Reason:

- YAML is schema-validatable and mergeable.
- Markdown is better for LLM persona and guidance.
- Separating law from persona reduces ambiguity.

### 4.3 AI Tester to Runtime Governor

The early product was close to "AI writes tests." The final product is broader:

- Generate tests.
- Record traffic.
- Enforce policy.
- Detect drift.
- Produce reports.
- Govern multi-repo behavior.

Final positioning:

**Entroping is runtime governance for AI-generated backend code.**

### 4.4 Command Sprawl to Locked Namespace

The conversation considered or implied many names: `gen`, `fix`, `ui`, `scan`, `verify`, `explain`, `chaos`, and top-level `build`.

Final v4.1 decision:

```text
init, doctor, config
architect build, architect refactor, architect audit
watch, freeze, map
studio, run
report bug
```

Reason:

- Small command surface is easier to learn.
- Commands map cleanly to product pillars.
- It avoids implementation drift.

## 5. Requirements Extracted from Gemini Conversation

### 5.1 Governance Requirements

- `qanstitution.yaml` must support imports.
- Imports must support central governance repos.
- Local rules must override imported rules unless imported rules are final.
- QAnstitution must support optional dependency specs for cross-service compatibility and mock validation.
- Gate conditions must match tags, paths, methods, URLs, and metadata.
- Gate enforcement must distinguish `block`, `warn`, and `audit_only`.
- Known failures must require issue ID, reason, and expiry.
- Policy failures must be visible in local and CI reports.

### 5.2 Test Generation Requirements

- Generate Hurl tests from OpenAPI.
- Support prompt-directed test generation.
- Support negative and hostile test generation through Breaker role.
- Ground generated endpoints and assertions in specs, stories, observed traffic, dependency specs, or explicit prompt context.
- Keep Breaker as a generation/audit role; do not call the LLM during deterministic `run`.
- Support schema, status, header, latency, and body assertions.
- Link tests to user stories through metadata.
- Preserve manual edits during generation and refactoring.
- Validate generated Hurl before accepting.

### 5.3 Traffic Requirements

- Capture live traffic with mitmproxy.
- Store traffic locally in SQLModel-backed SQLite.
- Redact secrets before persistence.
- Filter static assets, analytics beacons, irrelevant hosts, and oversized/binary payloads where configured.
- Stitch related requests into sessions before freezing.
- Freeze traffic into Hurl regression tests.
- Support golden master assertions.
- Generate WireMock-compatible mocks for dependencies.
- Generate dependency maps from observed calls.

### 5.4 Execution Requirements

- Use Hurl subprocess execution only.
- Do not execute API tests with Python HTTP libraries.
- Inject gates at runtime without changing source tests.
- Support env selection.
- Support tag selection.
- Support parallel execution.
- Support CI mode and deterministic exit codes.
- Support HTML, JUnit, JSON, and drift reports.

### 5.5 AI Requirements

- Use LiteLLM, not direct provider SDKs.
- Do not shell out to external Gemini, Claude, or ChatGPT CLIs for intelligence.
- Prefer local Ollama-backed models for solo/local work, with explicit cloud fallback.
- Store cloud credentials in environment variables or OS credential storage, not plaintext config.
- Route Builder, Auditor, and Breaker through QAnstitution config.
- Load agent Markdown persona files.
- Separate prompt construction from invocation and parsing.
- Do not send secrets or raw traffic to LLMs.
- Track model, latency, token usage, and estimated cost where practical.

### 5.6 Microservice Requirements

- Support one QAnstitution per service repo.
- Support central rules through imports.
- Support dependency spec pointers for provider/consumer compatibility.
- Support a central quality-gate repo for cross-service flows.
- Support service dependency maps.
- Support environment-specific URLs through env files.
- Support API-driven E2E flows across services.

### 5.7 Report Requirements

- JUnit XML for CI.
- HTML for human review.
- JSON for automation.
- Markdown bug reports for issue trackers.
- Drift JSON for baseline comparison.
- Audit Markdown/JSON for coverage and governance gaps.

## 6. Gaps Found in Earlier Consolidated Docs

The shorter v4.1 docs were directionally correct but missed important requirements:

| Missing Area | Required Addition |
| --- | --- |
| Locked command flags | Full command cheat sheet with exact flags |
| QAnstitution schema | Imports, agents, gates, ignore failures, settings |
| Import semantics | Local override and final imported gates |
| Traffic lifecycle | Watch, freeze, golden, mock, map behavior |
| Test management | Tags, folders, story metadata, env files, dynamic captures |
| Reports | HTML, JUnit, JSON, drift, audit, bug templates |
| Protocols | REST, GraphQL, SOAP, webhooks, gRPC bridge, WebSocket limits, MCP future |
| Microservices | Per-service law, central governance repo, central E2E repo |
| Security | Redaction, no secret logs, no raw traffic to LLMs |
| Implementation boundaries | Hexagonal dependency rules and Hurl-only execution |
| Market positioning | Runtime governor / CI firewall, not only test generator |
| Creator intent | Solo-first implementation path, stable requirements, and AI-governed-not-AI-judged workflow |
| Brain provider UX | Local-first Ollama, explicit cloud fallback, no external model CLIs, secure credential handling |
| Traffic fidelity | Smart filtering, session stitching, state retention, and AI edit audit trail |
| External requirements systems | Jira/Notion/etc. remain business truth; Entroping stores trace IDs and optional Markdown cache |

## 7. Deprecated or Future Concepts

| Concept | Status | Notes |
| --- | --- | --- |
| Bruno as canonical test format | Deprecated for MVP | Bruno can still be a client through proxy |
| `.bru` to `.hurl` JIT compiler | Future/optional | Not in v4.1 core |
| `entroping gen` | Alias only if needed | Primary command is `architect build` |
| `entroping fix` | Alias only if needed | Primary command is `architect refactor` |
| `entroping ui` | Alias only if needed | Primary command is `studio` |
| `entroping scan` | Not v4.1 | Use `architect audit` |
| `entroping chaos` | Not v4.1 | Use Breaker through `architect build --agent breaker --prompt` |
| `entroping report --type` | Not primary v4.1 | Use `run --report` for artifacts and `report bug` for bug templates |
| `entroping auth` | Future | Useful credential UX, but not in the frozen command set |
| `--verbose` / global `--dry-run` | Future | Mentioned after the strict table, so treat as spec-update-only; command-scoped `freeze --dry-run` was later accepted for safe artifact preview |
| Native gRPC streaming | Future | Bridge support first |
| Hosted SaaS dependency | Future optional | CLI must work locally |

## 8. Final Source of Truth

The implementation should follow these documents in order:

1. `PRODUCT_SPEC.md`
2. `TDS.md`
3. `QANSTITUTION_REFERENCE.md`
4. `BRAIN_PROVIDER_STRATEGY.md`
5. `CREATOR_INTENT_AUDIT.md`
6. `COMMAND_CHEAT_SHEET.md`
7. `USER_FLOWS.md`
8. `USE_CASES.md`
9. `CODEX_PROMPT.md`

If a future conversation conflicts with the locked command surface, update the product spec before implementing code.

## 9. Key Product Sentence

Entroping v4.1 is a local-first runtime governance system that lets AI create and maintain Hurl tests while QAnstitution gates and deterministic Hurl execution decide whether backend behavior is allowed to ship.
