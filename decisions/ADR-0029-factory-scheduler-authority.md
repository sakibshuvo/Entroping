---
title: ADR-0029 Factory Scheduler Authority
type: decision
status: accepted
date: 2026-07-29
tags:
  - decision
  - factory
  - scheduler
  - concurrency
  - security
  - reliability
---

# ADR-0029: Factory Scheduler Authority

## Decision

Factory scheduling uses a dedicated private SQLite authority under
`.entroping/factory-scheduler/` at the Git common root. Linked issue worktrees
therefore share one lease, one paid-work slot, one optional free/local
read-only review slot, and one writer slot per issue/worktree scope.

Each applied tick serializes clock validation, lease acquisition, concurrency
checks, and assignment insertion in the scheduler database with
`BEGIN IMMEDIATE`. Partial unique indexes enforce the initial concurrency
ceilings independently of application checks. Assignment identity and request
replay evidence are immutable and durable.

A paid applied tick first acquires the separate budget ledger's writer guard
with `BEGIN IMMEDIATE`, validates the matching `dispatching` reservation, and
holds that guard through the scheduler transaction commit. The empty ledger
transaction then rolls back without mutating financial state. The fixed lock
order is retention, budget ledger, then scheduler. This lock-coupled handoff
prevents a ledger writer from invalidating the reservation between validation
and durable assignment, but it is not a cross-database mutation or a dispatch
claim. The eventual provider boundary must revalidate current budget authority.

Lease ownership binds a value-free owner id, PID, process-start digest, and
monotonic epoch. Expiry is necessary but not sufficient for takeover: the old
process must be dead and no active assignment may remain. Healthy or unknown
process state blocks; dead expired ownership with active work requires the
separate recovery workflow.

Recovery extends the same authority instead of creating a second scheduler.
One versioned execution row records the current phase, attempt count,
heartbeat, per-execution lease expiry, retry deadline, failure code, evidence
digest, and mutable fenced owner/epoch for each immutable assignment.
Append-only request-bound receipts
make recovery idempotent across replacement CLI processes. Exact replay does
not transfer PID/start-token execution authority to the replacement process.
Only scheduler state that durably remains never-dispatched may return to retry
reconsideration; ambiguous dispatch remains active and cannot
release capacity or financial holds. A paid uncertain or settled transition
requires the separate ledger to prove that state before the scheduler changes.
Paid completion and paid recovery acquire the ledger writer guard first, read
the exact current settlement state, and hold that guard through scheduler
commit. Completion additionally requires the `completed-unsettled` phase and
its expected phase version; launched quota authority is never treated as unused
dispatch authority.
Per-execution expiry lets a new coordinator recover sibling assignments one at
a time after a shared owner dies; replacing the global lease for one assignment
does not make the remaining execution rows unrecoverable or grant them to the
new process.

## Boundaries

The scheduler consumes an already validated candidate. It does not select
GitHub issues, mutate queue jobs, invoke a provider, apply patches, or authorize
spending. Paid candidates must bind the authoritative budget ledger's matching
`dispatching` reservation, but every scheduler receipt still reports
`paid_work_authorized: false`; a later dispatch adapter must revalidate current
budget and provider authority.

Plan-only ticks are read-only and create no state when none exists. Scheduler
recovery is also plan-first and read-only. Neither plan nor apply dispatches a
provider. State uses owner-only, no-follow filesystem handling, exact schema
validation, bounded locking, monotonic UTC evidence, and value-free receipts.
Caller-declared external snapshot metadata is bounded and time-checked only; it
is not authenticated authority and must be revalidated by the future dispatch
orchestrator.
This is a same-user maintainer control plane, not a defense against malicious
code already running with the maintainer's OS identity.

## Consequences

- Concurrent ticks cannot independently claim the same paid, review, or writer
  capacity.
- Sibling worktrees cannot evade global factory limits.
- PID reuse and stale owner actions are fenced by process-start identity and
  epoch.
- Deterministic capped backoff avoids outage hot loops, while stale authority
  snapshots and retry exhaustion remain durable actionable state.
- Ambiguous recovery stops new work instead of guessing that capacity or
  financial authority is free.
- Status aggregation and end-to-end controller proof remain separate downstream
  issues.

## Evidence

- GitHub issues #1569 and #1571 own the Tier C implementation and recovery
  acceptance lanes.
- `scripts/factory_scheduler.py` owns the scheduler facade.
- `scripts/factory_scheduler_reservation.py` owns the lock-coupled budget
  reservation handoff.
- `scripts/factory_scheduler_transactions.py` owns atomic lease and assignment
  transitions.
- `scripts/factory_scheduler_execution_transaction.py` owns phase-version and
  execution-authority transitions.
- `scripts/factory_scheduler_recovery.py` owns recovery decisions without
  provider dispatch.
- `scripts/factoryctl.py` owns the plan-first maintainer command.
- `docs/meta/FACTORY_OPERATIONS.md` owns operator behavior and recovery limits.
- `docs/technical/TDS.md` owns the component and trust boundaries.
