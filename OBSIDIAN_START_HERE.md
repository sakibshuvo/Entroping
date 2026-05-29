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

## Open the Vault

1. Launch Obsidian from `/Applications/Obsidian.app`.
2. Click **Open folder as vault**.
3. Select `/Users/sakibshuvo/projects/Entroping`.
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

- Use [[00_INDEX]] as the map.
- Use ADRs for product decisions that should survive context resets.
- Use `.context/changelog.md` for short operational notes.
- Keep source files in `/Users/sakibshuvo/projects/entroping-specs`; this vault links to them but does not replace them.

## Graphify Later

Graphify can generate an external knowledge graph and report, but it is optional. Start with Obsidian's built-in graph first because it is local, simple, and already enough for the current Markdown set.

If you later want Graphify:

```bash
uv tool install graphifyy
graphify install
graphify /Users/sakibshuvo/projects/Entroping
```

Keep generated output under `graphify-out/`, which is ignored by Git.

