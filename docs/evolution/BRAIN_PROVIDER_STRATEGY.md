# Brain Provider Strategy

**Purpose:** Capture the local-first/cloud-second model strategy without bloating the product specification or TDS with educational LLM detail.

## 1. Decision

Entroping uses LiteLLM as the only model provider abstraction.

It must not depend on preinstalled Gemini, Claude, ChatGPT, or other model CLIs. Those tools produce unstable text interfaces, add dependency friction, and make structured output harder to enforce.

## 2. Default Mode

The intended default for solo/local development is an Ollama-backed local model.

Benefits:

- Works offline when the model is installed.
- Preserves local-first privacy.
- Fits the creator's Mac-first solo workflow.
- Avoids per-call API cost for routine generation.

## 3. Cloud Fallback

Cloud models are supported through LiteLLM model IDs and explicit configuration.

Illustrative examples:

```text
anthropic/<builder-model>
openai/<auditor-model>
gemini/<fast-model>
deepseek/<breaker-model>
ollama/<local-model>
```

Provider model names and access change over time. Verify the current model IDs in the provider or LiteLLM documentation before shipping defaults.

Use cloud providers when:

- The local machine cannot run a useful model.
- CI needs AI generation or auditing in a scheduled job.
- Complex auth or nested schema generation needs a stronger model.

Do not call cloud models with secrets or raw traffic unless the user explicitly opts in and redaction has run.

## 4. Agent Routing

QAnstitution maps roles to model IDs:

```yaml
agents:
  builder:
    source: "agents/builder.md"
    model: "ollama/<local-model>"
    temperature: 0.1
  auditor:
    source: "agents/auditor.md"
    model: "openai/<auditor-model>"
    temperature: 0.0
  breaker:
    source: "agents/breaker.md"
    model: "deepseek/<breaker-model>"
    temperature: 0.7
```

The model ID includes the provider prefix. This lets `entroping config set --agent <name> --model <provider/model>` switch models without adding a separate provider command to the frozen command surface.

## 5. Credential Handling

MVP credential sources:

- Environment variables read by LiteLLM.
- OS credential storage through a keyring adapter where practical.
- Gitignored local env files only for non-production local development.

Never store API keys in:

- `qanstitution.yaml`
- `agents/*.md`
- committed env files
- `.entroping/state.db`
- logs
- reports

An `entroping auth` command would be useful, but it is not part of the locked v4.1 command surface.

## 6. Local Model UX

The intended UX is a silent-partner Brain:

1. AI command starts.
2. Entroping checks whether the configured local provider is reachable.
3. If Ollama is not running or the model is missing, the CLI explains the missing dependency.
4. Future UX can offer explicit start/pull flows with Rich progress bars.
5. Long operations show useful step progress, not raw provider logs.

Useful future UX messages:

```text
Waking up the Brain: loading local model
Reading OpenAPI spec: found 12 endpoints
Generating Hurl test: tests/auth/login_negative.hurl
Validating generated Hurl syntax
```

## 7. Structured Output

The model provides raw reasoning and text generation. Entroping turns that into engineering output through:

1. Agent persona Markdown.
2. QAnstitution constraints.
3. Source context.
4. Structured response schema.
5. Pydantic validation.
6. Hurl syntax validation.

Generated files are accepted only after validation. The model is never the final judge.

Current implementation note: the Brain foundation now has strict Architect edit models,
root-bounded Markdown persona loading, deterministic prompt package assembly, and a
lazy LiteLLM adapter that can be tested without network calls. End-to-end
`architect build --prompt`, Architect-owned `architect refactor`, and managed-block
manual refactor paths are now available behind structured parsing and parser-backed
Hurl validation.

## 8. CI Strategy

CI should normally run deterministic tests only:

```bash
entroping run --env ci --ci --parallel --report junit
```

AI generation in CI should be reserved for scheduled jobs or explicit workflows because it is slower, costlier, and less deterministic. Any generated tests should be committed or attached as artifacts for human review before they become gates.

## 9. Custom Entroping Brain

A future custom local model can be distributed through the Ollama registry.

Recommended path:

1. Start with a Modelfile that wraps a strong coding model and Entroping-specific system prompt.
2. Fine-tune only if generic models fail repeatedly at Hurl or QAnstitution tasks.
3. Publish versioned tags, for example `entroping/brain:v1`.
4. Keep the same persona and schema constraints for local and cloud models.
