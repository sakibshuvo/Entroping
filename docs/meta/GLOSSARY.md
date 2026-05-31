---
title: Glossary
type: reference
status: active
tags:
  - glossary
  - onboarding
---

# Glossary

Entroping uses a few product-specific names. This glossary keeps those names useful without forcing new users to learn them by guessing.

| Term | Plain meaning |
| --- | --- |
| Entroping | The local-first quality governance CLI and knowledge base. |
| QAnstitution | The executable quality policy in `qanstitution.yaml`. It defines gates, imports, agents, settings, and known failures. |
| Gate | A Hurl-compatible assertion injected into matching test executions. |
| Condition | The small match expression that decides which tests or requests receive a gate, for example `true` or `tags contains 'smoke'`. |
| Enforcement | Whether a gate blocks the run, warns without failing, or is tracked for audit only. |
| Architect | The AI-assisted subsystem for generating, refactoring, and auditing Hurl tests. |
| Builder | Architect role that creates positive-path and contract tests. |
| Auditor | Architect role that finds coverage, traceability, and policy gaps. |
| Breaker | Architect role that creates negative, hostile, boundary, auth, and IDOR tests. |
| Eye | Traffic observation subsystem built around `watch`, `freeze`, and `map`. |
| Enforcer | Deterministic execution path: `entroping run`, QAnstitution gates, Hurl, and reports. |
| Golden master | A known-good captured behavior baseline converted into regression assertions. |
| Source-bound intelligence | Rule that generated tests must trace back to specs, stories, dependency specs, redacted traffic, or explicit prompts. |
| Deterministic run boundary | Rule that `entroping run` never calls the LLM and must be reproducible in CI. |

## Naming Rule

Use product names in docs after introducing the plain meaning. In quick-start material, prefer the command and outcome first, then the branded term.

Example:

```text
Define your runtime policy in qanstitution.yaml.
Entroping calls that policy the QAnstitution.
```

Links: [[docs/product/PRODUCT_SPEC|PRODUCT_SPEC]], [[docs/technical/COMMAND_CHEAT_SHEET|COMMAND_CHEAT_SHEET]]
