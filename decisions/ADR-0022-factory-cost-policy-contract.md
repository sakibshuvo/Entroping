---
title: ADR-0022 Factory Cost Policy Contract
type: decision
status: accepted
date: 2026-07-27
tags:
  - decision
  - factory
  - budget
  - security
  - architecture
---

# ADR-0022: Factory Cost Policy Contract

## Decision

Entroping's local software factory uses a versioned, closed JSON policy as the
declarative source for cash, subscription, price, quota, and automation-lane
limits. The concrete policy stays ignored at
`.entroping/factory-cost-policy.json`; only its schema, fake example, validator,
and operating guidance are committed.

Version 1 is deliberately narrow:

- USD is the only currency and one USD equals 100,000,000 integer microcents.
- The UTC calendar-month all-in cash cap is $200 with a $20 non-spendable
  emergency reserve inside that cap; renewal dates are also UTC.
- Deterministic thresholds stop experiments at 80%, restrict work to
  subscription or included-quota lanes at 90%, and stop paid dispatch at 100%.
- Subscription charges are recorded on their declared renewal event rather
  than amortized. Calendar, annual, and fixed-interval renewals have explicit
  boundary semantics.
- Rolling, calendar-month, and subscription-cycle quota windows are separate
  from cash accounting and cannot create additional spend authority.
- Automated top-up is disabled. Unknown pricing denies paid dispatch; unknown
  quota denies the affected paid lane.
- Policy and price checks use an injected offset-aware time and half-open
  validity windows. Validation never reads the wall clock implicitly.

## Boundary

The policy validator reads one bounded, regular, non-symlinked UTF-8 JSON file,
rejects ambiguous JSON and secret-like content, validates strict typed models,
and emits only a value-free summary. It performs no provider calls, credential
loading, balance scraping, spending, reservations, settlement, or dispatch.

The future cash ledger, reservations, scheduler, and provider observation
adapters may consume this contract only after their own issue-scoped security
and concurrency gates pass. Provider identifiers remain opaque; provider
business logic stays outside the policy model.

## Consequences

- Future budget decisions share one auditable unit and fail-closed declaration.
- Included quota cannot be mistaken for cash or double-counted as additional
  budget.
- A stale policy or stale enabled-lane price cannot authorize paid work.
- Currency conversion, automatic top-up, provider balance scraping, and
  autonomous Codex dispatch remain unsupported in version 1.
- Changes to policy semantics require a new schema version or an explicit
  backward-compatible revision with regenerated schema and boundary tests.

## Evidence

- GitHub issue #1559 defines the accepted scope and verification lane.
- `docs/meta/factory-cost-policy.v1.schema.json` is the committed authoring
  schema.
- `docs/meta/factory-cost-policy.example.json` demonstrates fake approved
  values and independent quota windows.
- `docs/meta/FACTORY_OPERATIONS.md` owns the operator-facing preflight.
