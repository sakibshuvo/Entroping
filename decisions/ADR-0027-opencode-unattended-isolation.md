---
title: ADR-0027 OpenCode Unattended Isolation
type: decision
status: accepted
date: 2026-07-29
tags: [decision, factory, opencode, security, isolation]
---

# ADR-0027: OpenCode Unattended Isolation

## Decision

Every non-dry-run invocation through `scripts/opencode_worker.py` uses
`entroping.opencode-unattended-review.v1` for structured findings or
`entroping.opencode-unattended-patch-proposal.v1` for a textual unified-diff
proposal. Patch mode never receives write permission and never applies its
proposal.

The worker creates a private ephemeral `HOME`, `XDG_CONFIG_HOME`, data, state,
cache, temporary, and worker directory outside Git discovery. It starts the
selected executable with `--pure`, a fixed `--agent`, explicit `--dir`, JSON
format, and an active registered model. The inline config disables project and
Claude instructions, external skills, default plugins, model fetching,
updates, autocompaction, sharing, snapshots, LSP, MCP, and formatters. It sets
subagent depth zero and uses a deny-first tool and permission map. Every
model-issued tool, including read, glob, and grep, is denied. The trusted CLI
may ingest only explicit `--file` snapshots that the wrapper already validated
as regular non-symlink files; shell, edit/write, patch application,
task/subagent, skill, web, question, task-list, external path, MCP, custom, and
unknown tools remain denied.

The child environment is rebuilt from an explicit key allowlist with a
canonical system PATH, isolated HOME/XDG paths, deterministic
`OPENCODE_CONFIG_CONTENT`, and `OPENCODE_DISABLE_PROJECT_CONFIG=1` plus the
other defense-in-depth flags. A `deepseek/*` route may forward only the exact
`DEEPSEEK_API_KEY` key needed for the final attested dispatch; the worker never
inspects or persists its value. Proxy, Exa, shell-startup, runtime-injection, arbitrary
`OPENCODE_CONFIG*`, and unrelated environment keys are removed.

Before provider dispatch, the same selected executable and isolated config
environment run `--version`, `run --help`, and `--pure debug config` without
any provider credential. Only after the executable, CLI surface, and resolved
config are attested does final dispatch receive the allowed authentication key. The worker
accepts only a reviewed CLI version, validates required flags and dangerous-auto
semantics, parses the effective config into an extra-forbidden typed schema,
compares the complete deny-first contract, and performs digest and version
binding. All four probes use bounded output, process-group cleanup, and a
20-second maximum. It verifies executable and profile digests again immediately
before dispatch. Capability, schema, config, version, output, lifecycle, or
executable drift fails before a model run.

## Evidence Contract

Each real invocation writes `capability-receipt.json` with schema
`entroping.opencode-unattended-capability-receipt.v1`. The value-free receipt
contains only profile, mode, model, agent, output contract, executable version
and digest, profile digest, capability names, isolated root categories,
sanitized environment key names, and booleans. It never contains environment
values, raw config, raw prompts, tool arguments, raw events, or user-global
paths. Raw prompts are not written to `prompt.md`; metadata stores a redacted
command placeholder.

## Trust Boundary and Residual Risk

This design trusts the selected OpenCode executable after digest and version
binding. It does not claim that JSON permissions provide OS or container
isolation. A malicious executable already running as the same-UID user can
ignore the profile, access that account, or use unrestricted egress. Separate
accounts, sandboxing, containers, and network policy remain necessary where
that threat is in scope.

An executable wrapper is the selected trusted executable. Its digest does not
independently bind a downstream binary that the wrapper later launches, so
operators seeking single-binary identity assurance must pass the direct regular
OpenCode binary with `--opencode-bin`.

## Consequences

- User-global OpenCode config is not edited or loaded by unattended workers.
- Review and patch proposal profiles are equally tool-free but remain
  distinguishable in receipts and output validation.
- Isolated user-global auth storage is unavailable; auth must use an explicitly
  supported key or a future reviewed mechanism.
- `entroping run`, Brain, LiteLLM, Hurl, and QAnstitution behavior are unchanged.

## Evidence

- GitHub issue #1566 owns this Tier C security-runtime decision.
- `scripts/opencode_unattended_profile.py` builds the typed profile and receipt.
- `scripts/opencode_readiness.py` validates effective CLI capability.
- `scripts/opencode_worker.py` reuses the exact attested profile for dispatch.
