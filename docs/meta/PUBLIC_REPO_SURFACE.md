---
title: Public Repo Surface
type: maintainer-guide
status: active
tags:
  - repo-hygiene
  - obsidian
  - context
---

# Public Repo Surface

This repository is both a public Python CLI project and a Markdown knowledge
base. The default GitHub clone should still look like a professional open-source
tool first: README, roadmap, docs, package code, tests, examples, ADRs, and CI.

## Classification

| Surface | Classification | Rule |
| --- | --- | --- |
| `README.md` | Public front door | Product pitch, demo proof, install path, links |
| `ROADMAP.md` | Public roadmap | Milestones and active issue sequencing |
| `docs/` | Public and maintainer docs | Curated Markdown source for MkDocs and Obsidian |
| `docs/meta/VAULT_INDEX.md` | Obsidian vault entry | Durable navigation map, not root-level public landing |
| `docs/meta/*.canvas` and `docs/meta/*.base` | Curated Obsidian helpers | Tracked only when they point at repo files and improve navigation |
| `.context/plan.md` | Maintainer/agent handoff | Tracked because Codex/OpenCode sessions need fast rehydration |
| `.context/changelog.md` | Maintainer/agent handoff | Tracked chronological implementation log |
| `.context/lessons-learned.md` | Maintainer/agent handoff | Tracked durable failure and decision memory |
| `.obsidian/` | Obsidian machine state | Local-only; do not track |
| `graphify-out/` | Generated graph output | Local-only; promote useful findings into docs |
| `.entroping/` and `reports/` | Runtime/generated artifacts | Local-only unless a curated asset is intentionally copied into docs |

## Decisions

- Keep the root `README.md` as the only product front door.
- Keep the Obsidian vault index, but store it as `docs/meta/VAULT_INDEX.md`
  instead of root `00_INDEX.md`.
- Keep `.context/` tracked for now because it is agent handoff material, not
  machine state. It stays out of MkDocs navigation and is not a product docs
  surface.
- Remove tracked Obsidian machine state. A user can reopen the repo as a vault
  and let Obsidian recreate `.obsidian/` locally.
- Track curated Canvas/Base files only when they are intentionally maintained
  as durable navigation aids under `docs/meta/`.
- Preserve durable knowledge by moving or documenting it before deleting
  anything. Machine/UI state does not count as durable product knowledge.

## Agent Rule

Agents may read `.context/` when it helps implementation, but user-facing docs
and public claims must be updated in `README.md`, `ROADMAP.md`, `docs/`,
`decisions/`, tests, or GitHub issues. Do not create new root-level knowledge
files unless they are conventional open-source entry points.
