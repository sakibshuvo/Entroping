# Creator Intent Audit

**Purpose:** Re-parse the old Entroping material from multiple angles and identify requirements that were missing, misinterpreted, or intentionally excluded from the consolidated v4.1 docs.

## 1. Method

I ran separate passes over the source material instead of treating the final transcript section as the only truth.

| Pass | Evidence Target | What It Looked For |
| --- | --- | --- |
| Pass 1 | Old v1 `PRODUCT_SPEC.md`, `TDS.md`, `USER_GUIDE.md`, `MVP_PLAN.md`, `init_specs.sh` | Original product instincts and early MVP constraints |
| Pass 2 | Gemini transcript command sections | Frozen command surface and command drift caused by invented flags |
| Pass 3 | Gemini transcript architecture sections | Hexagonal boundaries, Hurl execution, state, proxy, mocks, and reports |
| Pass 4 | Gemini transcript UX/model sections | Local model loading, cloud fallback, provider abstraction, and credential handling |
| Pass 5 | Gemini transcript creator questions | What the creator corrected, resisted, or emphasized |
| Pass 6 | Current docs | Missing or weak coverage compared with the evidence |

## 2. Creator Intent Signals

### 2.1 The Creator Values Stable Requirements

The user repeatedly objected when new commands or flags appeared without first being added to requirements. The strongest intent is not just "include many features"; it is **do not move the target while building**.

Documentation implication:

- Keep the command namespace frozen.
- Put rejected names in a deprecated/future table.
- Do not add convenience flags such as `--dry-run`, `--verbose`, `auth`, or `report --type` without a spec change.

### 2.2 The Creator Is a Solo Developer First

The transcript explicitly rejects bloated enterprise planning with "you should know i am a solo developer." The intended build path is solo, local, fast, and debuggable.

Documentation implication:

- `uv tool install -e .` is the immediate workflow.
- Nuitka, Homebrew, PyPI, Docker, and Cloud are distribution phases, not day-one implementation requirements.
- The MVP should prove the CLI and Hurl/QAnstitution loop before Studio, Cloud, or GUI.

### 2.3 The Product Is a Governor, Not a Doer

Later reality-check prompts clarify that Entroping should not compete with Codex, Claude, Perplexity Computer, or other autonomous doers. It should govern them.

Documentation implication:

- The primary automation target is CI and autonomous-agent background workflows.
- The strongest pitch is "CI/CD firewall" and "AI containment system," not "AI writes tests."
- `entroping run --ci` is the real product core.

### 2.4 The Creator Wants AI-First, But Not AI-As-Judge

The user pressed for the AI role to be clearer. The correct split is:

- AI handles volume: generation, refactor, auditing, mock synthesis, edge-case ideation.
- Humans handle value: intent, risk, law, review, approval.
- Hurl and QAnstitution decide runtime truth.

Documentation implication:

- `run` must remain deterministic and should not call the LLM.
- Breaker output should become committed Hurl tests before it can block CI.
- Generated changes must remain reviewable Git diffs.

### 2.5 Local-First Includes the Brain

The old transcript spends significant time on model loading UX. The creator wanted local-first, cloud-second, with easy model setup and support for custom trained/local models.

Documentation implication:

- Ollama/local models are part of the intended developer experience.
- Cloud providers are explicit fallback or advanced config.
- Entroping must not depend on external Gemini/Claude CLIs.
- API keys must use env vars or OS credential storage.

### 2.6 Business Truth May Live Elsewhere

The user challenged the assumption that all business rules and stories live as repo Markdown/YAML when companies use Jira, Notion, monday.com, and similar systems.

Documentation implication:

- Entroping should be the executable cache, not the only business system.
- Entroping metadata comments in Hurl files should support `story_id` and `doc_url`.
- Sync scripts from Jira/Notion to `docs/stories/*.md` are scale-up workflows, not MVP requirements.

## 3. Missing or Weak Requirements Found

| Finding | Previous Coverage | Correction Applied |
| --- | --- | --- |
| Local-first Brain UX | Mentioned LiteLLM only | Added `BRAIN_PROVIDER_STRATEGY.md` and TDS/Product notes |
| Credential storage | General secret warnings | Added OS credential storage/keychain guidance |
| No external model CLIs | Not explicit | Added no Gemini/Claude CLI dependency rule |
| Source-bound AI generation | Understated | Added requirement that endpoints/assertions trace to sources or explicit prompts |
| AI must not run during `run` | Implied by deterministic execution | Added explicit requirement |
| Smart traffic filtering | Missing | Added static asset/analytics filtering requirement |
| Session stitching | Missing | Added session grouping before `freeze` |
| State retention | Missing | Added `.entroping/state.db` retention/rotation requirement |
| AI edit audit trail | Weak | Added `ai_edit_audit` state concept |
| Cross-service dependencies | Covered as prose only | Added `dependencies` schema field |
| External business truth | Missing | Added Jira/Notion executable-cache workflow |
| Solo-first distribution | Mentioned but not framed as creator intent | Added creator intent reconciliation |
| Report command conflict | Not explained | Resolved as `run --report` plus `report bug`; `report --type` is non-primary |

## 4. Misinterpretations Corrected

### 4.1 Bruno Was Over-Promoted in v1

Old docs said `.bru` files were the human source of truth and `.hurl` files were artifacts. Final v4.1 reverses this.

Current interpretation:

- Hurl is first-class.
- Bruno can be an API client through `watch`.
- Bruno-like visual QAnstitution management is future product vision.

### 4.2 Chaos Became Breaker-Driven Generation

Old docs used `entroping chaos`. Final command discipline removes it.

Current interpretation:

- Use `architect build --agent breaker --prompt "<breaker intent>" --tag security`.
- Run generated tests with `entroping run`.
- No separate `chaos` command in v4.1.

### 4.3 `report --type` Conflicted with `report bug`

Some transcript sections used `report --type`, while later and user-provided v4.1 docs use `report bug` and `run --report`.

Current interpretation:

- `run --report <html|junit|json|drift>` writes run artifacts.
- `report bug` writes bug handoff Markdown.
- `report --type` is not primary v4.1.

### 4.4 Global Flags Were Mentioned Too Late

The transcript mentioned `--verbose` and `--dry-run` after the strict command table. Since the creator objected to new flags, these should not be treated as v4.1 MVP flags.

Current interpretation:

- They are future convenience flags only after a spec update.

## 5. Requirements Intentionally Not Added to MVP

| Requirement | Reason |
| --- | --- |
| `entroping auth` | Useful future credential UX, but not in frozen command surface |
| Native `.bru` compiler | Contradicts final Hurl-native MVP focus |
| Full Bruno-style GUI | Good endgame, bad solo sprint priority |
| Native gRPC streaming | Hurl-native MVP can bridge, not fully own it |
| Hosted Cloud dashboard | Business future, not local-first CLI MVP |
| `sync notion` / `sync jira` commands | Valid scale-up idea, not part of locked commands |

## 6. Final Interpretation

The creator intent is best summarized as:

**Build a solo-developer-friendly local CLI that proves the core governance loop quickly, then evolve it into a CI/CD firewall for AI-generated backend systems. Keep the command surface stable, keep Hurl deterministic, keep QAnstitution executable, and use AI to create reviewable artifacts rather than to make final runtime judgments.**
