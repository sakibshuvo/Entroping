---
title: Policy Pack Distribution
type: technical
status: active
tags:
  - qanstitution
  - policy-packs
  - open-core
  - distribution
  - provenance
---

# Policy Pack Distribution

This note defines how reusable QAnstitution policy packs can leave the
Entroping repository without turning `entroping run` into a registry client.
The path is deliberately local-first: distributed packs must become local,
inspectable QAnstitution imports before deterministic execution uses them.

## Decision

Policy packs are distributed as ordinary files with an
`entroping-policy-pack.yaml` provenance manifest and a `qanstitution.yaml`
entrypoint. Consumers import the local entrypoint from their project
`qanstitution.yaml`.

Distribution may happen through Git tags, release archives, vendored folders,
submodules, or future package artifacts, but the runtime contract stays the
same:

```text
review pack -> place files locally -> import local qanstitution.yaml -> run local evidence
```

There is no registry fetch, no telemetry, no paid-service dependency, and no
runtime manifest dependency in the deterministic run path.
Put another way: no runtime manifest dependency.

## Versioning

Policy packs use Semantic Versioning independent of Entroping Core:

- Patch: documentation, copy, examples, or metadata-only changes.
- Minor: additive gates, additive docs, less restrictive defaults, or new
  optional examples.
- Major: removed or renamed gates, stricter defaults, changed conditions,
  changed final-gate behavior, or any compatibility break likely to fail an
  existing consumer pipeline.

The manifest `version` is the pack version. The manifest `entroping` field is
the supported Entroping version range. Pack tags should include the pack ID and
version when practical, for example:

```text
entroping.api-baseline-v0.1.0-alpha
```

Consumers should pin an exact tag, commit, release archive checksum, or reviewed
vendor snapshot. Floating branch imports are acceptable only for experiments.

## Distribution Modes

Supported local-first modes:

| Mode | Status | Notes |
| --- | --- | --- |
| Vendored folder | Supported | Copy the pack into the consumer repo and review it like source. |
| Git submodule or subtree | Supported | Pin a commit and keep the local import path stable. |
| GitHub release archive | Supported after checksum review | Download outside Entroping, verify checksum, then import local files. |
| Package artifact | Future | Must install local files and preserve the same import contract. |
| Hosted catalog or registry | Future | May help discovery, but must not be called by `entroping run`. |

Every mode must leave a local directory containing the manifest, entrypoint,
rule files, README, and examples before it is used by Entroping Core.

## Import And Verification

Consumers import packs through local QAnstitution imports:

```yaml
imports:
  - "./policy-packs/api-baseline/qanstitution.yaml"
```

Pack verification should happen before advertising or upgrading a pack:

```bash
uv run python scripts/policy_pack_smoke.py --pack examples/policy-packs/api-baseline --strict
entroping report policy --output md
entroping doctor
```

The smoke command proves that manifest-declared gates, local gate files, final
flags, entrypoint imports, and the consumer example match the loaded
QAnstitution evidence. `entroping report policy` shows the effective gate
provenance in the consumer project.

Verification must preserve final-gate behavior. If a pack marks a gate
`final: true`, consumers cannot override it by redefining the same gate ID.
Temporary project exceptions should use `ignore_failures` with an issue ID,
expiry, and reason instead of weakening the pack.

## Provenance And Attribution

The manifest is attribution and review evidence. It should identify:

- pack ID and version;
- policy-pack source;
- license;
- maintainers or publisher;
- supported Entroping version range;
- evidence command;
- gate IDs, source files, and final flags;
- README or changelog location when available.

Consumers should retain license and attribution files when vendoring a pack.
The source path or URL is not trusted by itself; it helps humans trace the pack
back to a reviewed release, commit, or vendor snapshot.

## Open-Core And Premium Boundary

Open-core packs should remain useful enough to teach the policy-pack model:
starter security, reliability, latency, request-correlation, and example
governance packs belong in the public repo when they help developers understand
the core workflow.

In short: open-core packs teach and prove the local runtime model; premium packs
can add depth, maintenance, and support without weakening the core.

Premium packs can be commercial when their value comes from curated depth,
industry-specific controls, review cadence, support, hosted discovery, or
organization approval workflows. Premium packs must still produce local,
inspectable QAnstitution imports before deterministic execution. The Apache-2.0
core cannot depend on a paid catalog to run local tests, local reports, or
final-gate enforcement.

## Minimum Smoke Evidence

Do not advertise a policy pack until the maintainer can show:

- `scripts/policy_pack_smoke.py --strict` passes for the pack;
- the manifest has ID, version, policy-pack source, license, Entroping
  compatibility, evidence command, gate list, and final-gate declarations;
- the entrypoint loads through local imports only;
- a consumer example imports the pack and adds at least one local override or
  local project gate;
- final gates are documented in the README;
- no secrets, traffic state, customer data, credentials, or local machine paths
  are committed;
- attribution and license expectations are visible to consumers.

This smoke evidence proves local structure and compatibility. It does not prove
legal review, package signing, registry trust, security certification, or that a
consumer should accept the pack without reading the gates.

## Follow-Up Issues

Implementation work should stay issue-backed and separate from this decision.
Follow-up issues should cover:

- reusable pack verification command or report artifact for arbitrary external
  pack directories: [#329](https://github.com/sakibshuvo/Entroping/issues/329);
- checksum/signature guidance for release archives once package-index proof
  exists: [#330](https://github.com/sakibshuvo/Entroping/issues/330);
- external pack repository smoke evidence before claiming third-party pack
  distribution: [#331](https://github.com/sakibshuvo/Entroping/issues/331);
- premium-pack catalog boundaries, including how hosted discovery exports local
  QAnstitution files before runtime:
  [#332](https://github.com/sakibshuvo/Entroping/issues/332).
