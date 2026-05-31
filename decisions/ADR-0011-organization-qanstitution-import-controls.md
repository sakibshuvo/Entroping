---
title: ADR-0011 Organization QAnstitution Import Controls
type: decision
status: accepted
date: 2026-05-31
tags:
  - decision
  - qanstitution
  - governance
  - imports
  - enterprise
---

# ADR-0011: Organization QAnstitution Import Controls

## Decision

Organization QAnstitution imports are not a separate runtime authority.

Entroping has one effective QAnstitution for a run. Organization governance,
central policy packs, and future remote registries must all compile into that
same effective policy before Hurl gate injection begins. The deterministic
execution boundary stays unchanged: `entroping run` loads policy, injects
compiled Hurl assertions into temporary execution copies, and never calls an
LLM or policy server while deciding pass/fail.

Local repositories may import organization-owned policy, but they do not gain a
second override channel. Imported gates are merged before local gates. Local
repos may add stricter gates, narrower conditions, or extra warnings, but they
must not weaken imported `final: true` gates.

In short: local repos may add stricter gates but must not weaken imported `final: true` gates.

## Import Provenance

Every imported policy source must be traceable in future effective-policy and
run evidence. Provenance should include:

- source URI as declared by the importing file;
- resolved path for local imports or resolved immutable URL for remote imports;
- content digest of the validated imported document;
- import chain from root `qanstitution.yaml` to the imported document;
- whether the document came from local files, a committed policy pack, a cache,
  or a future organization registry;
- gate IDs, enforcement mode, and `final: true` status contributed by that
  source.

Reports should make this reviewable without exposing secrets, raw captured
traffic, or private repository paths beyond the project-relative path needed for
debugging.

## Override Rules

The merge model is intentionally conservative:

- imported gates merge before local gates;
- duplicate gate IDs in the same local document remain invalid;
- a local gate with the same ID may replace an imported gate only when the
  imported gate is not final;
- local overrides should be recorded as overrides in effective-policy evidence;
- final imported gates should produce an explicit configuration error if a local
  document tries to replace them;
- future organization import controls may add allowlists, required signatures,
  or pinned versions, but those controls must not weaken the final-gate rule.

This keeps central governance useful while preserving local-first ergonomics:
teams can add product-specific rules without silently weakening organization
minimums.

## Final Gate Behavior

`final: true` means "not locally weakenable" across the entire import chain.

If a final gate is imported directly or through multiple nested imports, later
imports and the root policy may not replace that gate ID with weaker or
different Hurl assertions. Future tooling can allow an administrator-approved
exception workflow, but that workflow must create auditable evidence and cannot
be a silent local YAML override.

Final gates are still deterministic Hurl assertions. They do not create a
remote runtime dependency, a proprietary policy engine, or an LLM judgment path.

## Offline And Local-First Behavior

Remote imports remain disabled in deterministic `entroping run` until remote
fetching, cache validation, provenance, and failure behavior are implemented as
reviewed features.

Offline validation must use committed or reviewed local files. Future remote
organization imports must be version-pinned or digest-pinned before they become
eligible for CI. A cache may improve availability, but cache use must be visible
in provenance and must not silently replace a reviewed policy version.

For testable policy: remote imports remain disabled in deterministic `entroping run`, and offline validation must use committed or reviewed local files.

When a remote source is unreachable, Entroping should fail closed for blocking
governance unless the run is explicitly using a reviewed cached or vendored
policy. The default local development loop should continue to work from files
checked into the repository or a local policy-pack checkout.

## Audit And Report Evidence

Future organization-policy work should add an effective-policy report before
adding remote fetch behavior. The effective-policy report should show:

- import source and digest for each imported document;
- merged gate list in execution order;
- local overrides of non-final imported gates;
- rejected attempts to override final gates;
- skipped or warning-only gates;
- policy cache source when a cache is used;
- enough issue/document links for governance review.

Run reports should reference the effective policy version or digest so a CI
failure can be reproduced from committed Hurl tests, environment data, and the
policy evidence.

## Non-Goals

This decision does not implement remote imports, a policy registry, policy
signing, organization RBAC, approval workflows, hosted audit history, or paid
enterprise controls.

This decision also does not make Entroping Cloud part of the local runtime. Any
future cloud or registry feature must preserve deterministic local execution and
must fail safely when unavailable.

## Consequences

- Current local root-bounded imports and `final: true` protection remain the
  correct MVP implementation.
- Remote HTTP(S) imports stay documented as architecture, but not active runtime
  behavior.
- Policy-pack and organization-governance features should be built in this
  order: provenance and effective-policy report first, reviewed local pack
  consumption second, remote/cache/signature features later.
- Open-core monetization can offer managed policy registries, approvals, audit
  history, and enterprise dashboards without making the Apache-2.0 local core
  dependent on hosted services.

Links: [[docs/technical/QANSTITUTION_REFERENCE|QANSTITUTION_REFERENCE]], [[docs/technical/TDS|TDS]], [POLICY_PACK_LAYOUT.md](../docs/technical/POLICY_PACK_LAYOUT.md), [OPEN_CORE_BOUNDARIES.md](../docs/product/OPEN_CORE_BOUNDARIES.md), [#202](https://github.com/sakibshuvo/Entroping/issues/202)
