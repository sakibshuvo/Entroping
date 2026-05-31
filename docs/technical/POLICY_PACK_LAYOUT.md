---
title: Policy Pack Layout
type: technical
status: proposed
tags:
  - qanstitution
  - policy-packs
  - open-core
  - imports
---

# Policy Pack Layout

This note defines the reusable QAnstitution policy-pack shape before community
or premium packs exist. It is intentionally a design and example-pack artifact.
No runtime behavior changes are introduced by this design note.

## Decision

A policy pack is a plain, reviewable directory or repository that exposes a
normal QAnstitution import entrypoint plus optional catalog metadata. Entroping
Core should be able to consume the entrypoint through the existing
`imports` mechanism when the pack is vendored into the project root. Future
pack discovery, registries, remote imports, or install commands must build on
this shape instead of inventing a second policy format.

The first supported contract is:

```text
policy pack = files + manifest + qanstitution.yaml import entrypoint
```

The runtime source of truth remains `qanstitution.yaml`. The manifest helps
humans, docs, catalogs, package managers, and future registries understand the
pack, but the current loader does not read it.

## Pack Layout

Recommended package shape:

```text
entroping-policy-pack-api-baseline/
  README.md
  entroping-policy-pack.yaml
  qanstitution.yaml
  rules/
    security.yaml
    reliability.yaml
  examples/
    consumer-qanstitution.yaml
```

Required files:

| Path | Purpose |
| --- | --- |
| `README.md` | Human-readable purpose, included gates, compatibility, and override guidance |
| `entroping-policy-pack.yaml` | Pack metadata for catalogs, package managers, and future validation |
| `qanstitution.yaml` | Runtime import entrypoint that imports pack-owned rule files |
| `rules/` | One or more schema-valid QAnstitution fragments containing gates |
| `examples/consumer-qanstitution.yaml` | Copyable consumer config showing how to import the pack |

`qanstitution.yaml` must be a valid QAnstitution document. It should normally
contain `project`, `version`, `imports`, and an empty `gates: []` list while the
actual gates live in focused files under `rules/`.

Policy packs should avoid:

- agent model routing;
- provider credentials;
- local environment values;
- captured traffic;
- generated reports;
- raw customer data;
- service-specific `sources` unless the pack is explicitly an example fixture.

## Manifest

`entroping-policy-pack.yaml` is metadata, not executable law.

Required manifest fields for the proposed layout:

| Field | Purpose |
| --- | --- |
| `id` | Stable pack identifier, for example `entroping.api-baseline` |
| `name` | Human-readable pack name |
| `version` | Pack version, independent from Entroping's package version |
| `license` | License for the pack content |
| `entrypoint` | Relative path to the importable QAnstitution file |
| `runtime_contract` | Current value: `qanstitution-import` |
| `entroping` | Compatible Entroping version range |
| `gate_prefixes` | Gate ID prefixes reserved by the pack |
| `final_gates` | Gate IDs that consumers cannot override |

Future validators may read this file, but current runtime behavior must not
depend on it.

## Import Semantics

Current alpha-safe usage vendors or checks out the pack under the consumer
repository and imports the pack entrypoint:

```yaml
imports:
  - "./policy-packs/api-baseline/qanstitution.yaml"
```

Local imports remain root-bounded. A pack import must resolve under the root
`qanstitution.yaml` directory, just like any other local QAnstitution import.
This keeps a malicious or accidental pack path from reading arbitrary files.

HTTP(S) policy-pack imports remain future work. The technical docs describe
remote imports as part of the architecture contract, but current local
validation rejects them so `doctor` and deterministic runs do not make network
calls.

Import merge order is unchanged:

1. Imported pack gates merge before local project gates.
2. Local project gates can override imported gate IDs unless the imported gate
   has `final: true`.
3. Duplicate gate IDs inside the same effective import graph are configuration
   errors unless they are intentional allowed overrides.
4. The effective policy must remain inspectable through `doctor`, reports, and
   future policy-pack audit tooling.

## Versioning

Policy packs use Semantic Versioning independently from Entroping Core:

- Patch: copy, description, examples, or non-behavioral metadata changes.
- Minor: additive gates or less restrictive changes.
- Major: renamed gate IDs, removed gates, stricter defaults, new `final: true`
  gates, changed condition scope, or any change likely to break existing CI.

Pack repositories should tag releases with the pack ID and version when
practical, for example:

```text
entroping.api-baseline-v0.1.0-alpha
```

Consumers should pin a reviewed pack version or commit. Floating imports are
acceptable only for local experiments.

## Conflict And Final-Gate Behavior

Gate IDs must be globally stable and prefixed by pack domain:

```text
api-security.no_5xx
api-security.request_id
api-reliability.latency
```

Conflict rules:

- A project can override non-final imported gates by defining the same `id`
  locally.
- A project cannot override an imported gate with `final: true`.
- Pack authors should use `final: true` sparingly, only for rules that are part
  of the pack's trust promise.
- Every final gate must be documented in the manifest and README with its
  rationale.
- If a consumer needs a temporary exception, use `ignore_failures` with an issue
  ID and expiry instead of weakening the pack.

## Open-Core Boundary

starter packs stay inspectable and runnable in the public core. Entroping Core
should keep enough examples for developers to understand pack authoring,
imports, conflict behavior, and final gates without a paid account.

Premium policy packs can be commercial. The commercial value may come from
curated depth, industry-specific controls, review cadence, hosted distribution,
approval workflow, and support. It must not come from making local QAnstitution
imports, local Hurl execution, or local reports incomplete.

Any hosted or premium pack surface must still produce local, auditable
QAnstitution files before `entroping run` enforces them.

## Runtime Non-Goals

This issue does not add:

- a `pack` command;
- remote policy-pack fetching;
- registry authentication;
- manifest validation;
- package installation;
- automatic update checks;
- telemetry;
- paid-service dependency in `entroping run`;
- a second policy language.

Follow-up implementation should be issue-backed and must preserve the current
QAnstitution import semantics unless a new ADR changes them.

## Example

See `examples/policy-packs/api-baseline/` for a minimal pack shape that can be
loaded through the current local import mechanism.
