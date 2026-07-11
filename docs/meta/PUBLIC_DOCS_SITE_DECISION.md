---
title: Public Docs Site Decision
type: decision
status: active
tags:
  - docs
  - public-site
  - astro
  - starlight
---

# Public Docs Site Decision

## Problem

The repository is useful in Obsidian, but first-time open-source visitors should
not need Obsidian to read core docs. The site must publish a curated public path
without copying or forking the canonical Markdown.

## Original decision

The original decision selected MkDocs Material after comparing it with
VitePress and GitHub Pages/Jekyll. MkDocs fit the Python-first repository,
provided search and strict builds, and kept the canonical docs in `docs/`.

The original scaffold used `mkdocs.yml`, `docs/index.md`, and this decision
record. It built with:

```bash
uvx --with 'mkdocs-material==9.*' mkdocs build --strict
```

That decision established durable requirements that still apply:

- Do not duplicate canonical docs.
- The canonical docs stay in `docs/`.
- Obsidian links remain source-friendly.
- Public navigation stays curated instead of exposing maintainer memory by
  default.
- GitHub Issues and milestones remain the project tracker.

## Superseding decision

As of 2026-07-11, GitHub issue #1507 supersedes the site implementation while
preserving the original curation and source-of-truth rules.

Use one Astro 7 static build with Starlight for documentation:

- `src/pages/index.astro` owns the branded launch page.
- Starlight renders documentation under `/docs/`.
- `site/public-docs.json` owns public labels, canonical source paths, and route
  slugs.
- Astro's content loader reads those exact Markdown files directly from
  `docs/`.
- `DESIGN.md` and `src/styles/tokens.css` own the shared launch and docs visual
  system.
- The configured `/Entroping/` base path remains valid on GitHub Pages.

Astro and Starlight replace executable MkDocs configuration. They do not create
a second docs tree or change the role of README, the roadmap, the vault index,
or GitHub Issues.

## Current implementation

Install, check, build, validate, and preview with:

```bash
npm ci
npm run format:check
npm run check
npm run build
npm run test:site
npm run preview
```

The `docs-site` CI job runs the same deterministic checks. The Pages workflow
publishes only the generated `dist/` artifact from `main` after its own checked
build. GitHub Pages deployment is active at
`https://sakibshuvo.github.io/Entroping/`.

## Guardrails

- Do not move product, technical, user, or meta docs out of `docs/` for the
  site.
- Do not make the public site a project tracker.
- Do not publish Obsidian UI state, generated local context output, reports,
  `.entroping/`, provider output, or generated site output.
- Keep `node_modules/`, `.astro/`, `.pagefind/`, and `dist/` ignored.
- Keep Obsidian-only notes, source exports, evolution history, prompt libraries,
  and private implementation context out of first-level public navigation.
