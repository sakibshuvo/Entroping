---
title: Obsidian Start Here
type: guide
status: stable
tags:
  - obsidian
  - onboarding
  - graph
---

# Obsidian Start Here

This vault is a local folder of Markdown files. Obsidian adds navigation, backlinks, graph view, search, and local editing on top of it.

Obsidian makes context preservation easier when the notes are curated. It does not mean every idea should become a permanent file or that every agent should read every note.

## Open the Vault

1. Launch Obsidian from `/Applications/Obsidian.app`.
2. Click **Open folder as vault**.
3. Select the Entroping repository checkout, shown elsewhere as `<repo-root>`.
4. Open [[00_INDEX]].

## First Graph View

Open Graph view from the left ribbon or command palette.

Recommended first settings:

- Turn on arrows if you want directionality.
- Turn off orphans when the graph feels noisy.
- Search for `tag:#decision` to focus on ADRs.
- Search for `tag:#source` to focus on source-material notes.
- Open Local Graph from a specific note when the full graph is too busy.

## Daily Editing Workflow

- Open [[docs/meta/PROJECT_PROGRESS|PROJECT_PROGRESS]] first.
- Use [[00_INDEX]] as the map when you need to navigate beyond current work.
- Use [[docs/meta/GLOSSARY|GLOSSARY]] when product terms feel unfamiliar.
- Use [[docs/meta/CONTEXT_MANAGEMENT|CONTEXT_MANAGEMENT]] before starting a new Codex thread.
- Use [[docs/meta/OBSIDIAN_CONTEXT_ENGINE_GUIDE|OBSIDIAN_CONTEXT_ENGINE_GUIDE]] when you want to use the vault as a context preservation engine.
- Use [[docs/meta/ISSUE_TRACKING|ISSUE_TRACKING]] to understand what belongs in GitHub Issues versus Obsidian.
- Use [[docs/meta/TEST_STRATEGY|TEST_STRATEGY]] to understand regression and test-pyramid expectations.
- Use ADRs for product decisions that should survive context resets.
- Use `.context/changelog.md` for short operational notes.
- Keep source files in `<source-archive>`; this vault links to them but does not replace them. Use `ENTROPING_SOURCE_ROOT` when the archive is not the sibling `../entroping-specs` folder.
- Keep project-agent rules in `AGENTS.md`; new Codex threads should read it before implementation.

## Graphify Later

Graphify can generate an external knowledge graph and report, but it is optional. Start with Obsidian's built-in graph first because it is local, simple, and already enough for the current Markdown set.

If you later want Graphify:

```bash
uv tool install graphifyy
graphify install
graphify <repo-root>
```

Keep generated output under `graphify-out/`, which is ignored by Git.

Do not treat Graphify output as canonical. Promote useful findings back into curated Markdown docs, ADRs, or `.context/` notes.

## Systematic Updates

Update Obsidian-facing Markdown when the project state changes:

- `docs/meta/PROJECT_PROGRESS.md` for phase-level progress.
- `docs/product/MVP_PLAN.md` for roadmap or scope changes.
- ADRs for durable product or architecture decisions.
- `.context/changelog.md` for meaningful implementation changes.
- `.context/lessons-learned.md` for durable pitfalls, not every small bug.
