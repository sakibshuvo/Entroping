---
title: ADR-0003 Local-First Brain
type: decision
status: accepted
date: 2026-05-29
tags:
  - decision
  - ai
  - litellm
  - local-first
---

# ADR-0003: Local-First Brain

## Decision

Entroping uses LiteLLM as the only model-provider abstraction. Local Ollama-backed models are preferred for solo/local workflows, and cloud models require explicit configuration.

## Context

The product should not depend on external Gemini, Claude, ChatGPT, or other model CLIs. Those tools create unstable text interfaces and make structured output harder to validate.

## Consequences

- Agent roles map to model IDs in QAnstitution or local config.
- Current-alpha API keys come from environment variables; OS credential storage
  requires a future keyring adapter.
- Secrets and unredacted traffic must not be sent to model providers.
- `entroping run` does not call the LLM.

Links: [[docs/evolution/BRAIN_PROVIDER_STRATEGY|BRAIN_PROVIDER_STRATEGY]], [[docs/technical/TDS|TDS]], [[docs/technical/CODEX_PROMPT|CODEX_PROMPT]]
