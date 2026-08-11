---
title: AI Provider Setup
description: "Configure LiteLLM-backed Architect providers while keeping deterministic Entroping runs model-free."
type: guide
status: active
tags:
  - ai
  - litellm
  - qwen
  - omlx
  - local-first
---

# AI Provider Setup

This guide explains how to connect the Architect commands to LiteLLM-backed
providers without making deterministic Entroping runs depend on model access.

## The Boundary

Entroping has two separate paths:

- `entroping architect ...` can call a model through LiteLLM when you use
  prompt-backed build or refactor workflows.
- `entroping run --ci` is LLM-free. It executes committed Hurl files with the
  local Hurl binary and the effective QAnstitution.

That boundary is intentional. AI can suggest test changes, but CI should enforce
reviewed `.hurl` files and policy gates without API keys, network model calls,
or provider availability.

## Install The AI Extra

In a local development checkout:

```bash
uv sync --extra ai
```

For a tool install from this repository, include the `ai` extra when your
installer supports extras for Git installs. Keep the base CLI usable without
LiteLLM so deterministic runs stay lightweight.

Useful upstream references:

- LiteLLM Ollama provider: https://docs.litellm.ai/docs/providers/ollama
- LiteLLM OpenAI-compatible provider: https://docs.litellm.ai/docs/providers/openai_compatible
- oMLX: https://omlx.ai/
- oMLX GitHub: https://github.com/jundot/omlx

Provider model IDs and local runtime commands change over time. Verify the
current model name with the provider before committing a shared default.

## Local Qwen Through Ollama

Use this path when you want private local drafting and can run a useful Qwen
model on your machine.

1. Install and start Ollama outside Entroping.
2. Pull the Qwen model you want to use. Choose a model size your machine can
   run reliably.
3. Configure the Builder model route:

```bash
entroping config set --agent builder --model "ollama/<qwen-model>"
```

4. Confirm the non-secret routing metadata:

```bash
entroping config list
```

5. Run a prompt-backed Architect command:

```bash
entroping architect build --prompt "Generate checkout smoke coverage from the configured spec"
```

Select the Breaker role when you want hostile or security-focused test drafts:

```bash
entroping config set --agent breaker --model "ollama/<qwen-model>"
entroping architect build --agent breaker --prompt "Generate invalid-token and tenant-boundary tests" --tag security
```

Then review the generated files and run:

```bash
entroping run --ci
```

Ollama usually does not need `api_key_env`. If a local provider needs a base URL,
add `api_base` manually to `qanstitution.yaml`.

## Local Qwen Through oMLX

Use this path when oMLX is running a local OpenAI-compatible endpoint on Apple
Silicon.

Example `qanstitution.yaml` agent config:

```yaml
agents:
  builder:
    source: agents/builder.md
    model: openai/<local-qwen-model>
    api_base: http://127.0.0.1:8000/v1
    api_key_env: ENTROPING_OMLX_API_KEY
    temperature: 0.1
    max_tokens: 4096
```

`api_base` is the local OpenAI-compatible endpoint base URL and must target a
loopback host such as `localhost`, `127.0.0.1`, or `::1`. Entroping does not
accept arbitrary remote `api_base` overrides. `api_key_env` is the name of an
environment variable, not the key itself.

If the local server accepts unauthenticated requests, omit `api_key_env`. If it
expects a placeholder key, export a local-only environment variable:

```bash
export ENTROPING_OMLX_API_KEY="local-placeholder"
```

Then run:

```bash
entroping config list
entroping architect refactor --target "tests/**/*.hurl" --prompt "Add missing auth header variables where required"
entroping run --ci
```

## Cloud Providers

Cloud providers are explicit opt-in routes through LiteLLM model IDs, for
example:

```yaml
agents:
  auditor:
    source: agents/auditor.md
    model: openai/<auditor-model>
    temperature: 0.0
  breaker:
    source: agents/breaker.md
    model: deepseek/<breaker-model>
    temperature: 0.7
```

Use cloud models for harder generation, coverage audit, or negative-test
drafting. Do not send raw captured traffic, cookies, bearer tokens, or private
customer data to cloud providers. Run redaction first and review the context
being sent.

`architect build` defaults to the Builder route. Use
`architect build --agent breaker --prompt "<intent>"` for hostile test generation.
Use `architect audit --focus auditor --output md` or
`architect audit --focus auditor --output json` for explicit Auditor-backed
review findings. Auditor reviews do not modify Hurl or policy files.

Successful prompt-backed Architect commands write local value-free manifests
under `.entroping/agent-runs/`. Use them as audit evidence for role/model,
persona source, prompt hashes, output paths, validation status, latency, and
token counts. Do not treat them as model approval.

Provider-specific environment variable names are handled by LiteLLM and the
provider SDK stack. Entroping only stores non-secret routing metadata.

## No-Provider CI

The default CI posture is no provider at all:

```bash
entroping doctor --ci
entroping run --ci --report junit --report html
```

Agents and CI workers can use:

```bash
entroping doctor --ci --output json
```

The JSON output uses schema version `entroping.doctor.v1` and preserves the same
exit-code behavior as human doctor output.

This path should work with no LiteLLM installation and no model credentials.
When agents are configured, `doctor` verifies persona files and reports whether
named `api_key_env` variables are set, but it does not print values or call the
provider. Missing `api_key_env` values are readiness warnings for AI commands,
not blockers for deterministic `run`.
Commit generated Hurl files after review, then let CI run the deterministic
suite. If an automated workflow wants to generate new tests with AI, make it a
scheduled or manual workflow that uploads diffs for review instead of merging
provider output directly.

## Secret Rules

No API keys in qanstitution.yaml.

Do not store raw secrets in:

- `qanstitution.yaml`
- `agents/*.md`
- `.env.example`
- `.entroping/`
- reports
- committed Hurl files
- source-context documents sent to Architect

Use environment variables or an OS credential store. `api_key_env` may name an
environment variable such as `ENTROPING_OMLX_API_KEY`; it must never contain the
actual key.

## Troubleshooting

If Architect fails before calling the model:

- Run `entroping config list` and confirm the selected agent has a model.
- Run `entroping doctor` and fix any unsafe, missing, oversized, non-Markdown,
  or secret-like persona file warnings.
- Check that the persona file exists under the project root.
- Check that `api_base` is an `http` or `https` URL for a local loopback host,
  without userinfo, query parameters, or fragments.
- Check that `api_key_env` is a valid environment variable name.

If LiteLLM reports provider errors:

- Confirm the local server is running.
- Confirm the model name is installed and matches the provider's current model
  ID.
- Export the environment variable named by `api_key_env` if the provider needs
  one.
- Keep `entroping run --ci` as the final proof after generated files are
  reviewed.

If provider output reaches Entroping but fails validation:

- For schema/parser errors, retry with a narrower prompt that asks for only the
  Architect JSON object and no Markdown fences.
- For generated Hurl validation errors, retry with a prompt that asks for
  syntactically valid Hurl in the selected file only.
- Do not copy raw provider output, parser stdout, parser stderr, or prompt
  context into issues until it has been reviewed for secrets.
