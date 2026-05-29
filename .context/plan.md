# Entroping Documentation Plan

**Date:** 2026-05-29  
**Status:** Documentation synthesis in progress

## Objective

Create a consolidated Entroping v4.1 documentation set from the Gemini evolution conversation, older local specs, the slide deck, and the latest v4.1 notes.

## Source Decisions

- Treat v4.1 as Hurl-native.
- Treat `qanstitution.yaml` as executable governance law.
- Treat `watch`, `freeze`, and `map` as restored v4.1 Eye lifecycle commands.
- Treat Bruno as historical/future context, not an MVP source format.
- Keep the command namespace frozen to the set documented in `COMMAND_CHEAT_SHEET.md`.

## Work Items

- Expanded product specification.
- Expanded technical design specification.
- Expanded user guide.
- Marketing and positioning note.
- Codex implementation prompt.
- Requirements and evolution analysis.
- QAnstitution reference.
- Command cheat sheet.
- User flows.
- Use cases.
- Mermaid and PlantUML diagrams.
- MVP implementation plan.
- Multi-pass creator intent audit.
- Brain provider strategy.

## Second-Pass Corrections

- Added local-first model/provider requirements from the Gemini UX discussion.
- Added source-grounding rules so AI generation cannot silently invent endpoints.
- Clarified that `run` is deterministic and does not call the LLM.
- Added traffic filtering, session stitching, state retention, and AI edit audit concepts.
- Added external business truth handling for Jira/Notion-style systems.
- Resolved `report --type` as non-primary in favor of `run --report` and `report bug`.

## Hard-Review Corrections

- Hurl metadata is now specified as Entroping-readable comments, not custom `[Options]` keys.
- Generated Hurl validation now uses parser-backed validation language instead of the earlier nonexistent validation command.
- `run --report` is explicitly repeatable anywhere multiple artifact examples are shown.
- Agent orchestration is a small typed router for MVP; external orchestration frameworks are later optional dependencies.
- Diagram aliases now avoid duplicate PlantUML object names.

## Constraints

- No implementation code in this pass.
- No invented v4.1 commands.
- Keep security, reliability, maintainability, and architectural consistency as release gates.
- Preserve local-first and Git-native product direction.
