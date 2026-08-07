---
title: ADR-0024 Provider Capability Registry
type: decision
status: accepted
date: 2026-07-28
tags:
  - decision
  - factory
  - providers
  - security
  - architecture
---

# ADR-0024: Provider Capability Registry

## Decision

Entroping's maintainer factory uses
`docs/meta/provider-capability-registry.json` as the single versioned,
repository-owned source for recognized provider lanes, hosts, billing paths,
models, capabilities, autonomy ceilings, usage-accounting support, lifecycle,
queue defaults, and metered-cost join identities. A generated JSON Schema supports authoring, while strict
Pydantic models and a bounded loader are the runtime validation boundary.

Queue submission, routing audits, quarantine requeue, pre-dispatch checks, and
strict PR evidence validation resolve provider information through this
registry. An unknown paid lane, host, billing path, or model combination fails
closed until the exact route is reviewed and registered. A non-paid lane may
accept unlisted local models only when its registry policy explicitly allows
them.

Lifecycle is evidence-preserving. Active queue-bound lanes and models may
authorize new dispatch. Candidate entries can record reviewed trials without
claiming availability. Deprecated and retired entries remain resolvable as
historical evidence but cannot authorize new queue dispatch.

Queue-bound model `id` values are invocation identities: they are passed to the
selected worker engine without rewriting. An effectively metered model also
declares a provider-qualified `cost_model_id` under its lane's
`cost_provider_id`. Those two fields are deterministic join keys for the
separate cost-policy contract, not dispatch or spending authority. Capability
and autonomy checks still gate queue resolution before any job is written.

## Boundary

The registry is a maintainer-workflow contract, not product runtime
configuration. It contains no credentials, endpoints, provider keys, account
state, quota observations, prices, or automatic quality rankings. It makes no
provider calls and does not prove that a listed model is currently available.
Product Brain calls continue to use LiteLLM; `entroping run` remains
deterministic and provider-free.

The separate ignored factory cost policy and downstream ledger retain spending
authority. A route must be both registered and budget-authorized before a
future paid scheduler may dispatch it.

Existing factory metrics `provider` and `model` labels predate this registry and
are not canonical cost-policy keys. Issue #1573 delivers separate strict,
value-free provider-scorecard evidence for exact lane, host, billing, model,
autonomy, registry-derived cost-provider/model identity, job/reservation,
commit, diff, CI, merge, and regression correlation.
Consumers must not infer a registry or cost-policy join from legacy metric
labels; the scorecard does not extend or reinterpret them.

## Consequences

- Code and workflow projections no longer own independent paid-route allowlists.
- Registry edits require schema parity and boundary tests.
- CI correlates declared provider/autonomy evidence with bounded read-only
  metadata from the single closing GitHub issue. Tier A autonomous authority
  requires exactly one maintainer-owned `autonomy:tier-a` label and a diff
  outside protected, sensitive, and release/quality guardrail surfaces. Issue
  prose does not grant authority.
- Provider renames and deprecations preserve audit history without silently
  widening new-dispatch authority.
- Descriptive lane tables and prompts are non-authoritative projections and
  must point readers back to the registry.
- A new queue engine or schema shape requires an explicit typed-model change,
  generated-schema update, and architecture review.

## Evidence

- GitHub issue #1558 owns the release-CI-architecture acceptance lane; issue
  #1573 supplies the separate downstream evidence-correlation contract.
- `docs/meta/provider-capability-registry.v1.schema.json` is the committed
  authoring schema.
- `scripts/provider_capability_registry.py` exposes registry-backed routing and
  evidence resolution.
- `scripts/ai_jobs.py` and `scripts/pr_body_check.py` are the first enforcing
  consumers.
- `docs/meta/FACTORY_OPERATIONS.md` owns operator guidance.
