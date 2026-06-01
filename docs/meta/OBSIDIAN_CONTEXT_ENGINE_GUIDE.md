---
title: Obsidian Context Engine Guide
type: guide
status: active
tags:
  - obsidian
  - context
  - agents
  - graphify
  - llm-wiki
---

# Obsidian Context Engine Guide

Use this guide to make Entroping's Git-backed Markdown knowledge base work like
a context preservation engine for you and for coding agents.

## Position

Obsidian is worth using for Entroping, but not because the graph view is magic.
It is useful because it makes a local Markdown repo navigable, searchable, and
linkable.

The durable model is:

```text
GitHub/repo is canonical.
Obsidian is the local thinking interface.
Agents read and write curated Markdown through rules.
Graphify audits the graph, but never becomes truth.
```

If Obsidian is removed later, Entroping should still work. The project depends
on GitHub, Git history, Markdown docs, ADRs, `.context/`, issues, PRs, CI, and
release tags. Obsidian improves navigation and context recovery on top of those
assets.

## Second Brain Discipline

Obsidian is just linked Markdown unless the notes follow a repeatable loop.
For Entroping, the loop is:

```text
Capture -> connect -> distill -> retrieve -> promote
```

- **Capture:** write raw ideas, doubts, review notes, and source findings before
  they are clean enough for GitHub.
- **Connect:** link the note to source exports, ADRs, product docs, affected
  modules, tests, and related issues.
- **Distill:** reduce the note to a decision, open question, accepted finding,
  rejected finding, or follow-up.
- **Retrieve:** keep enough links and summary context that future you or an
  agent can recover the product reasoning quickly.
- **Promote:** move actionable work into a GitHub issue, durable decisions into
  ADRs, current behavior into canonical docs, and handoff facts into `.context/`.

The graph view is only a navigation aid. It does not decide truth, priority, or
implementation scope.

## Start Analyzing And Evolving

Use this short loop when you want to understand, evolve, or restart work on the
project:

1. Open the repository as the Obsidian vault.
2. Start from `docs/meta/VAULT_INDEX.md`.
3. Read `docs/meta/PROJECT_PROGRESS.md` and `ROADMAP.md` for current status.
4. Read this guide, `docs/meta/OBSIDIAN_VS_GITHUB.md`, and
   `docs/meta/DOCS_GOVERNANCE.md` for operating rules.
5. Use GitHub Issues as the execution backlog.
6. Use `docs/evolution/`, `sources/SOURCE_MAP.md`, `decisions/`, and
   `.context/lessons-learned.md` for idea evolution and historical context.

The operating loop is:

```text
Brainstorm in Obsidian
       ↓
Promote actionable work to GitHub issue
       ↓
Build on branch / agent session
       ↓
Run tests, security, and docs gates
       ↓
Merge through GitHub
       ↓
Update context only if product truth changed
```

Do not browse every Markdown file. Start from the index, progress note, roadmap,
and target issue. GitHub is the factory floor. Obsidian is the memory palace.

## What People Are Actually Doing

The useful Obsidian project patterns cluster around six practices:

1. **Local Markdown as memory.** Notes stay as portable files, so humans, Git,
   and agents can all inspect them.
2. **Maps of content.** A small number of index notes point to the right context
   instead of forcing people to browse every note.
3. **Backlinks and graph health.** Links, backlinks, local graph, and orphan
   checks reveal which ideas are central, weakly connected, or stale.
4. **Properties and query views.** YAML properties power filtered tables, lists,
   and dashboards through Obsidian Bases or community plugins.
5. **Raw-source to wiki loops.** Raw materials are captured separately, then
   summarized, linked, challenged, and promoted into curated pages.
6. **Periodic linting.** Healthy vaults are reviewed for contradictions, stale
   claims, missing links, orphan notes, and unsupported assertions.

For Entroping, use those ideas without turning Obsidian into a duplicate Linear
or GitHub Issues.

## Entroping Rules

Follow these rules for every note, agent session, and source import:

1. **GitHub tracks work.** Bugs, features, roadmap tasks, release blockers, and
   review status belong in GitHub issues, PRs, milestones, and projects.
2. **Obsidian explains why.** Use the vault for product evolution, decisions,
   source evidence, lessons learned, architecture reasoning, and context cards.
3. **Source material is evidence.** Gemini, NotebookLM, ChatGPT, PDFs, slides,
   and old brainstorms do not become current truth until promoted.
4. **Promotion is explicit.** Promote accepted findings into a GitHub issue,
   ADR, canonical doc, or `.context/` handoff note.
5. **Every factual claim needs a path.** Agents must cite local files, source
   exports, tests, command output, issues, or PRs.
6. **Generated graph output is advisory.** Graphify can suggest weak links or
   stale clusters, but its output stays ignored unless promoted into curated
   Markdown.

## Reading Order

Do not read the whole vault for every session.

For daily work, open:

1. `docs/meta/VAULT_INDEX.md`
2. `docs/meta/PROJECT_PROGRESS.md`
3. target GitHub issue
4. related ADR, if any
5. related feature context card, if any
6. `docs/meta/FEATURE_DELIVERY_CHECKLIST.md`

For agent implementation sessions, run:

```bash
scripts/context_pack.sh --mode implementation
```

For source reconciliation sessions, run:

```bash
scripts/context_pack.sh --mode source
```

## Note Types

### 1. Feature Context Card

Create this only for features that need repeated context across sessions.

```markdown
---
title: Feature - <name>
type: feature-context
status: active
related_issues:
  - "#123"
related_prs: []
related_adrs: []
tags:
  - feature
  - context
---

# Feature: <name>

## Current Decision

What is true today?

## Why It Exists

What user problem or product risk does this feature address?

## Relevant Files

- `src/...`
- `tests/...`
- `docs/...`

## Behavior Contract

What must not regress?

## Tests That Protect It

- `tests/...`
- `scripts/regression.sh`

## Known Risks

- Security:
- Reliability:
- UX:
- Architecture:

## Open Questions

- [ ] Question

## Session Notes

- YYYY-MM-DD: Short durable update.
```

### 2. Source Evidence Note

Use this for source imports from Gemini, NotebookLM, ChatGPT exports, slides, or
research.

```markdown
---
title: Source Evidence - <name>
type: source-evidence
status: archival
source_path: ../entroping-specs/...
source_date: YYYY-MM-DD
tags:
  - source
  - evidence
---

# Source Evidence: <name>

## What This Source Is

Short description.

## Claims Worth Considering

- Claim:
  - Evidence:
  - Confidence:
  - Promote to: issue / ADR / docs / none

## Rejected Or Archival Claims

- Claim:
  - Reason:

## Follow-Up

- [ ] GitHub issue:
- [ ] ADR:
- [ ] doc update:
```

### 3. Decision Note

Durable architecture or product decisions should usually be ADRs under
`decisions/`. Use a lightweight note only for pre-ADR thinking.

```markdown
---
title: Decision Draft - <name>
type: decision-draft
status: draft
tags:
  - decision
---

# Decision Draft: <name>

## Context

## Options

## Recommendation

## Evidence

## Promotion

- [ ] Create ADR
- [ ] Update TDS
- [ ] Update product docs
```

### 4. Weekly Context Review

Use this as a short review checklist, not a diary.

```markdown
# Weekly Context Review - YYYY-MM-DD

## GitHub

- Open release blockers:
- Stale issues closed:
- Next 1-3 ready issues:

## Docs

- Roadmap still accurate: yes/no
- Product specs changed: yes/no
- ADR needed: yes/no

## Obsidian

- Orphan notes worth linking:
- Stale notes archived:
- Source map updated:

## Agents

- Repeated mistakes:
- New guardrail needed:
- Context pack gap:
```

## Obsidian Features To Use

Start with core features:

- **Backlinks:** see what references the note you are reading.
- **Local graph:** inspect a feature, ADR, or source note in its neighborhood.
- **Properties:** keep note metadata small and machine-readable.
- **Templates:** make feature cards, source notes, and weekly reviews consistent.
- **Search:** find exact terms before assuming something is missing.
- **Bases:** create local database-like views over note properties when a simple
  Markdown table is not enough.
- **Canvas:** optional for launch strategy, architecture maps, or product-story
  boards. Do not use Canvas as the only copy of important information.

Optional plugins:

- **Web Clipper:** capture web sources as Markdown for later source review.
- **Dataview:** query Markdown/frontmatter when Bases is not expressive enough.
- **Tasks or Project Manager:** useful in personal vaults, but avoid them for
  Entroping execution because GitHub Issues are canonical.

## Graphify Workflow

Run Graphify weekly or after a large marathon.

Useful questions:

- Which notes are central?
- Which notes are orphaned?
- Which docs are duplicated?
- Which source concepts never got promoted?
- Which ADRs are weakly linked to implementation docs?
- Which product claims lack evidence?

Keep generated output under ignored folders such as `graphify-out/`. Promote
only reviewed findings into issues, ADRs, canonical docs, or `.context/`.

## Agent Workflow

When starting an agent session:

```text
Repo: /Users/sakibshuvo/projects/Entroping
Read first:
- AGENTS.md
- docs/meta/VAULT_INDEX.md
- docs/meta/OBSIDIAN_CONTEXT_ENGINE_GUIDE.md
- docs/meta/OBSIDIAN_VS_GITHUB.md
- docs/meta/DOCS_GOVERNANCE.md
- docs/meta/PROJECT_PROGRESS.md
- target GitHub issue

Rules:
- GitHub/repo is canonical.
- Obsidian explains why.
- Cite local files or source exports for claims.
- Do not promote source-history claims without evidence.
- Run scripts/doc_governance_check.sh and scripts/regression.sh before completion.
```

After the session:

1. Update the GitHub issue or PR with status and verification.
2. Update `.context/changelog.md` for meaningful implementation changes.
3. Update `.context/lessons-learned.md` only for durable lessons.
4. Add or update an ADR only for durable decisions.
5. Update product, user, or technical docs only if behavior changed.
6. Leave Obsidian UI state and Graphify output out of Git.

## Anti-Hallucination Controls

Use these controls aggressively:

- No citation, no trust.
- No unreviewed AI output in canonical docs.
- No Obsidian-only backlog.
- No raw source dumps in the implementation repo.
- No roadmap edits unless release sequence or public promise changed.
- No claims about implemented behavior without source, tests, or command output.
- No source-history claims without `sources/SOURCE_MAP.md` or a file under
  `../entroping-specs`.
- One parent integrator resolves conflicts between models.

## 30-Day Adoption Plan

### Week 1: Basic Navigation

- Open the repo as the Obsidian vault.
- Start from `docs/meta/VAULT_INDEX.md`.
- Use backlinks and local graph on ADRs and product docs.
- Do not install extra plugins yet.

### Week 2: Context Cards

- Add feature context cards only for complex, recurring work.
- Link cards to GitHub issues, ADRs, tests, and docs.
- Use the cards as startup context for Codex/OpenCode/Claude sessions.

### Week 3: Source Loop

- Add new Gemini or NotebookLM exports to `../entroping-specs`.
- Create source evidence notes only for curated findings.
- Promote actionable findings to GitHub issues.
- Promote durable choices to ADRs.

### Week 4: Graph And Lint

- Run a graph review.
- Look for orphans, stale claims, duplicated docs, and missing backlinks.
- Fix the smallest set of links/docs that improves retrieval.
- Do not reorganize the whole vault unless daily retrieval is painful.

## When To Avoid Obsidian

Do not use Obsidian for:

- canonical issue status.
- sprint boards.
- detailed bug queues.
- CI status.
- release approval.
- private untracked product truth.
- secrets or credentials.
- generated reports that should remain ignored.

Use GitHub and CI for those.

## Research Notes

This guide adapts current Obsidian and agent-memory patterns:

- Andrej Karpathy's LLM Wiki pattern: raw sources, LLM-maintained Markdown wiki,
  schema/rules, index/log, linting, and Obsidian as the IDE.
  <https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f>
- Obsidian Bases: database-like local views over Markdown files and properties.
  <https://obsidian.md/help/bases>
- Obsidian Graph View: global/local graph, filters, groups, orphans, and link
  visualization.
  <https://obsidian.md/help/plugins/graph>
- Obsidian Properties: small machine-readable YAML metadata, useful with
  templates and views.
  <https://obsidian.md/help/properties>
- Obsidian Backlinks: linked and unlinked mentions for the active note.
  <https://obsidian.md/help/plugins/backlinks>
- Obsidian Web Clipper: browser capture into durable Markdown.
  <https://obsidian.md/help/web-clipper>
- Dataview: community plugin for querying vault metadata, tasks, tables, and
  lists.
  <https://community.obsidian.md/plugins/dataview>
- Obsidian Tasks and Project Manager show how people run task/project systems
  inside vaults, but Entroping should keep execution canonical in GitHub.
  <https://github.com/obsidian-tasks-group/obsidian-tasks>
  <https://community.obsidian.md/plugins/project-manager>
