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

Obsidian is the first brain for Entroping. It is where the product story, decisions, issues, source evidence, and implementation context stay navigable after chat context disappears.

## Vault Rule

The active vault is the repo:

```text
/Users/sakibshuvo/projects/Entroping
```

The source archive stays separate:

```text
/Users/sakibshuvo/projects/entroping-specs
```

Do not merge source exports into the implementation repo as raw dumps. Curate links, analyses, decisions, and promoted requirements.

## Source Priority

Current source snapshot:

```text
/Users/sakibshuvo/projects/entroping-specs/notebookLM/2026-05-29 NotebookLM Specs.md
```

Historical evidence:

- `gemini chat exports exports /2026-05-29 Gemini-_33.md`
- `2025-12-26 gemini spec/*.md`
- Dated NotebookLM PDFs/images under `notebookLM/2025-12-31/` and `notebookLM/2026-04-25/`

Historical source material is evidence, not automatic current truth.

## Promotion Gates

Promote source evidence through one of four gates:

1. GitHub issue: for actionable implementation, bug, regression, or docs work.
2. ADR: for durable architecture, product, licensing, or workflow decisions.
3. canonical product or technical doc: for current product behavior, command contract, schema, user flow, or roadmap.
4. `.context/` note: for current handoff state, changelog, or durable lesson.

If a source insight does not pass one of these gates, it stays archival.

## Gemini And NotebookLM Loop

Use Gemini and NotebookLM as research assistants over source material, then bring the result back into the repo.

1. Put the export under `/Users/sakibshuvo/projects/entroping-specs` with a dated filename.
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
6. Run tests if any repo behavior changed.

Do not paste unbounded model output into the vault. Keep the vault curated.

## Obsidian Maintenance

Weekly, or after a large marathon:

- Open `00_INDEX.md`.
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
graphify /Users/sakibshuvo/projects/Entroping
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
