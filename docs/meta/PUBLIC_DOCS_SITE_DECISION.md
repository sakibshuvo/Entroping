---
title: Public Docs Site Decision
type: decision
status: active
tags:
  - docs
  - public-site
  - mkdocs
---

# Public Docs Site Decision

## Problem

The repository is useful in Obsidian, but first-time open-source visitors should
not need Obsidian to read core docs. The site should publish a curated public
path without copying or forking the canonical Markdown.

## Options

| Option | Fit | Cost | Decision |
| --- | --- | --- | --- |
| MkDocs Material | Strong fit for Python projects, Markdown docs, search, GitHub Pages, and low-friction local preview | Adds one Python docs-site tool when publishing is activated | Chosen |
| VitePress | Strong static docs UX and fast builds | Adds a Node toolchain and a separate docs mental model to a Python-first repo | Defer |
| GitHub Pages/Jekyll | Native GitHub Pages path and minimal setup | Ruby/Jekyll conventions are less aligned with the existing Python/uv workflow | Defer |

## Decision

Decision: MkDocs Material.

Use `mkdocs.yml` at the repository root, keep `docs_dir: docs`, and add a small
`docs/index.md` public landing page. Do not duplicate canonical docs into a
second docs tree. The canonical docs stay in `docs/`, while root `README.md`,
`ROADMAP.md`, and `00_INDEX.md` remain repository and Obsidian entry points.

Obsidian links remain source-friendly. Public-site pages should prefer normal
Markdown links when they are meant for first-time readers, but the vault does
not need to give up wiki links in internal notes just to satisfy the public
site. Keep internal Obsidian-heavy notes under `docs/meta/` and exclude them
from the first public navigation unless they are useful to maintainers.

## Scaffold

Current scaffold:

- `mkdocs.yml` defines the public site metadata, Material theme, selected
  Markdown extensions, and curated navigation.
- `docs/index.md` is the public landing page.
- `docs/meta/PUBLIC_DOCS_SITE_DECISION.md` records this decision.

Local preview/build command:

```bash
uvx --with 'mkdocs-material==9.*' mkdocs build --strict
```

Use `mkdocs serve` only for local preview:

```bash
uvx --with 'mkdocs-material==9.*' mkdocs serve
```

No active deployment workflow yet. Add GitHub Pages deployment only after the
curated navigation builds cleanly and the maintainer enables Pages settings for
the repository.

## Guardrails

- Do not duplicate canonical docs.
- Do not move product, technical, user, or meta docs out of `docs/` for the site.
- Do not make the docs site the project tracker; GitHub Issues and milestones
  remain the tracker.
- Do not publish Obsidian UI state, Graphify output, reports, `.entroping/`, or
  generated site output.
- Keep `site/` ignored when local builds are introduced.
