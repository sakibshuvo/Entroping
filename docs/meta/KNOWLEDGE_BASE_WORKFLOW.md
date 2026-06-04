---
title: Knowledge Base Workflow
type: runbook
status: active
tags:
  - obsidian
  - notebooklm
  - gemini
  - graphify
  - context
  - hallucination-control
---

# Knowledge Base Workflow

The Git-backed Markdown knowledge base is the first brain for Entroping.
Obsidian is the preferred local interface for reading, linking, and navigating
that knowledge base after chat context disappears.

GitHub and the repository remain canonical. Obsidian should not contain private,
untracked project truth; promote important ideas into GitHub issues, ADRs,
canonical docs, or `.context/` handoff notes.

For the fuller operating model, read
[[docs/meta/OBSIDIAN_CONTEXT_ENGINE_GUIDE|OBSIDIAN_CONTEXT_ENGINE_GUIDE]].

## Ownership Split

OBSIDIAN_VS_GITHUB owns day-to-day placement rules: where bugs, feature ideas,
roadmap changes, and current work status go.

KNOWLEDGE_BASE_WORKFLOW owns source promotion: how Gemini, NotebookLM, Graphify,
source exports, and historical brainstorms become issues, ADRs, canonical docs,
or archival evidence.

When the two guides overlap, keep operational task status in
`OBSIDIAN_VS_GITHUB` and keep source-evidence/hallucination-control rules here.

## Vault Rule

The active vault is the repo:

```text
<repo-root>
```

The source archive stays separate. Use a sibling `../entroping-specs` checkout
or set `ENTROPING_SOURCE_ROOT`:

```text
<source-archive>
```

Do not merge source exports into the implementation repo as raw dumps. Curate links, analyses, decisions, and promoted requirements.

Use `docs/meta/DECISION_REGISTRY.yaml` as the retrieval layer across this
history. It compresses durable decisions with pointers back to ADRs, docs,
issues, and source exports; it does not replace those materials.

## Source Priority

Current source snapshot:

```text
<source-archive>/notebookLM/2026-05-29 NotebookLM Specs.md
```

Historical evidence:

- `gemini chat exports exports /2026-05-29 Gemini-_33.md`
- `2025-12-26 gemini spec/*.md`
- Dated NotebookLM PDFs/images under `notebookLM/2025-12-31/` and `notebookLM/2026-04-25/`

Historical source material is evidence, not automatic current truth.

Archive means lower default-reading priority, not deletion. Do not summarize and
remove the original export, note, ADR, or issue evidence.

## Promotion Gates

Promote source evidence through one of four gates:

1. GitHub issue: for actionable implementation, bug, regression, or docs work.
2. ADR: for durable architecture, product, licensing, or workflow decisions.
3. canonical product or technical doc: for current product behavior, command contract, schema, user flow, or roadmap.
4. `.context/` note: for current handoff state, changelog, or durable lesson.

If a source insight does not pass one of these gates, it stays archival.

When a promoted decision needs to survive context resets, add or update its
entry in `docs/meta/DECISION_REGISTRY.yaml`. Keep the registry concise and make
the source links stronger than the summary.

## Gemini And NotebookLM Loop

Use Gemini and NotebookLM as research assistants over source material, then bring the result back into the repo.

1. Put the export under `<source-archive>` with a dated filename.
2. If it is a final export, update `sources/SOURCE_MAP.md`.
3. Run:

```bash
scripts/context_pack.sh --mode source
```

If the source archive is not a sibling `../entroping-specs` directory, set:

```bash
ENTROPING_SOURCE_ROOT=/path/to/entroping-specs scripts/context_pack.sh --mode source
```

4. Ask the external tool to answer with source-file citations and uncertainty labels.
5. Convert accepted findings into issues, ADRs, or canonical docs.
6. Update `docs/meta/DECISION_REGISTRY.yaml` when the accepted finding changes
   a durable decision.
7. Run tests if any repo behavior changed.

Do not paste unbounded model output into the vault. Keep the vault curated.

## Obsidian Maintenance

Weekly, or after a large marathon:

- Open `docs/meta/VAULT_INDEX.md`.
- Review `docs/meta/PROJECT_PROGRESS.md`.
- Review `.context/plan.md`.
- Move completed work from "current" language to done or later.
- Add a short dated note to `docs/evolution/EVOLUTION_TIMELINE.md` only when the product story changed.
- Check `sources/SOURCE_MAP.md` when new Gemini or NotebookLM exports arrive.

## Graphify Role

Graphify is a generated analysis layer, not the project memory.

Use it to find central notes, weakly linked areas, and surprising relationships. Keep generated output ignored unless a finding is promoted into curated Markdown.

Recommended local flow:

```bash
uv tool install graphifyy
graphify install
graphify <repo-root>
```

Output belongs under `graphify-out/`, which is ignored by Git.

## Hallucination Prevention

- Ask every agent to cite local file paths or source-export paths.
- Reject claims about implemented behavior unless they point to source files, tests, docs, or command output.
- Reject source-history claims unless they point to `sources/SOURCE_MAP.md` or an export under `entroping-specs`.
- Keep old brainstorms out of current docs unless they are intentionally promoted.
- Use `scripts/context_pack.sh` instead of relying on old chat summaries.
- Keep one parent integrator responsible for resolving conflicting model suggestions.

## Recommended NotebookLM Questions

Use these after adding a new export:

```text
What requirements in this source are not represented in the current Entroping repo docs?
Separate direct evidence from interpretation. Cite source filenames.
```

```text
Which parts of the product idea changed between the earliest Gemini specs and the latest NotebookLM export?
List what should remain archival versus what should influence current docs or issues.
```

```text
Find contradictions around timeline, command names, state storage, QAnstitution schema, Hurl execution, traffic capture, and monetization.
Return only cited claims.
```
