---
title: ADR-0028 Paid Cost Reservation and Settlement
type: decision
status: accepted
date: 2026-07-29
tags:
  - decision
  - factory
  - budget
  - providers
  - security
  - reliability
---

# ADR-0028: Paid Cost Reservation and Settlement

## Decision

A metered factory worker cannot launch until the version 2 factory budget
ledger has atomically reserved its worst-case cost from fresh, immutable price
terms. The reservation binds the queue job, provider lane, provider cost id,
provider-qualified cost model, worker model, cost-policy lane and revision,
usage ceiling, and price digest. The queue JSON is a recoverable projection;
the ledger remains authoritative.

The first supported metered lane is the repo-local direct DeepSeek worker. Its
request body and completion tokens have enforceable ceilings. Input and output
token prices are mandatory; minute pricing is unsupported for this lane.
Metered OpenCode dispatch stays denied until its host can enforce a usage
ceiling and produce an identity-bound accounting receipt. Included-quota and
fixed-subscription routes do not create cash holds, and worker dry runs do not
authorize paid work.

The direct worker emits a strict, sanitized receipt that binds the queue job,
requested and reported model, local run, hashed provider session, and exact
input/output/total token counts. Raw provider session ids are not projected
into queue state and are removed from persisted response artifacts. Actual cost
is recomputed from the reservation's immutable integer-microcent price terms;
provider-reported floats are not spending authority.

## State and Recovery

Reservations begin in `dispatching`. A complete, matching receipt settles the
actual debit and releases only the verified remainder in one transaction.
Malformed, partial, conflicting, mismatched, over-ceiling, interrupted, or
ambiguous evidence changes the reservation to `uncertain` without releasing
the hold. Exact event replays are no-ops; conflicting idempotency reuse fails.

Queue recovery looks up the authoritative reservation by job id, including the
crash window after ledger commit but before the queue projection is rewritten.
An unresolved stale worker becomes uncertain and is never redispatched. An
already settled stale queue record becomes terminal without charging again.
Retention protects queue and review evidence whose settlement is unresolved or
unknown.

Only two value-free actions can release an uncertain hold: explicit evidence
that the provider call never dispatched or that the provider confirmed no
charge, and a manual debit bounded by the original hold with a source id and
evidence digest. Missing usage is never guessed as zero.

## Schema and Trust Boundary

Ledger schema version 2 adds immutable reservation authority, price terms, and
append-only events plus the cached active-reservation total. Existing version 1
ledgers require the explicit `migrate` command. Migration validates the exact
legacy schema and the complete version 2 result in one exclusive transaction;
failure rolls back without rewriting the legacy authority.

This is a local maintainer control plane, not product runtime. It does not add
provider calls to `entroping run`, scrape balances, auto-top-up accounts, or
defend against a malicious same-UID process outside the ledger's documented
filesystem boundary.

## Consequences

- Concurrent jobs cannot reserve the same remaining cash.
- A crash cannot silently turn a possibly spent hold back into available cash.
- A stale or incomplete cost policy blocks before process launch.
- Operators must reconcile uncertain holds from evidence rather than inference.
- Supporting another metered host requires enforceable ceilings and a strict
  receipt adapter before that route can dispatch.

## Evidence

- GitHub issue #1568 owns the Tier C security-runtime acceptance lane.
- `scripts/factory_budget_ledger.py` owns authoritative reservation state.
- `scripts/factory_paid_dispatch.py` owns queue-to-ledger coordination.
- `scripts/deepseek_worker.py` owns the bounded direct-provider receipt.
- `docs/meta/FACTORY_OPERATIONS.md` owns operator behavior and recovery.
- `docs/technical/TDS.md` owns the component and trust boundaries.
