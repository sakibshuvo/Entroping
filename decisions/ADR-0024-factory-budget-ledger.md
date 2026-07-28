---
title: ADR-0024 Transactional Factory Budget Ledger
type: decision
status: accepted
date: 2026-07-27
tags:
  - decision
  - factory
  - budget
  - sqlite
  - security
  - reliability
---

# ADR-0024: Transactional Factory Budget Ledger

## Decision

Entroping keeps one authoritative local cash ledger in the ignored
`.entroping/factory-budget/ledger.sqlite3` database. It is separate from the
product traffic store and from non-authoritative factory metrics. Version 1
uses USD integer microcents, UTC calendar periods, an internal non-spendable
reserve allocation, immutable entries, and a cached net balance validated by
the same transaction that appends an entry.

The reviewed cap, positive reserve, currency, month, policy identity, and
policy revision are immutable period authority. Only the cached entry count and
net balance may change after initialization.

Fixed subscription charges and provider charges are debits. Refunds are credits
bound to an original charge and cannot cumulatively exceed it. Manual
adjustments explicitly declare debit or credit. Global idempotency stores only
a SHA-256 digest and binds every key to the normalized payload: exact retries
return the original receipt, while conflicting reuse is rejected.

## Concurrency and Durability Boundary

Period initialization and entry recording use `BEGIN IMMEDIATE`, so the
idempotency lookup, refund and reference checks, period and cap decision,
immutable insert, and cached-balance update share one serialized transaction.
One-time schema bootstrap uses `BEGIN EXCLUSIVE`. SQLite uses
`journal_mode=DELETE`, `synchronous=EXTRA`, foreign-key enforcement, strict
tables, bounded waits, and immutable-entry triggers. This permits genuinely
read-only reporting without creating WAL sidecars.

Initialization constructs and validates a private same-directory database,
syncs it, publishes it atomically by hard link, removes the temporary name, and
syncs the directory. Unpublished interrupted state is discarded on retry; a
validated inode that was published before interruption has its reserved
temporary hard link removed safely on retry.

## Safety Boundary

Descriptor-based path checks require an owner-controlled repository root and
owner-only private state directories, and reject symlinks, special files,
unsafe sidecars, and oversized state. Existing opens use non-creating SQLite
URI modes and compare owner, mode, link count, device, and inode before and
immediately after connection. A published two-link initialization inode is
completed safely on retry after a crash. Exact schema and integrity checks
reject malformed, partial, future, or drifted databases without automatic
migration.
Signed 64-bit arithmetic, a 512 MiB file cap, a 100,000-entry global cap, a
600-period global cap, and streaming timestamp validation bound resource use.
The ledger shares the retention lock and exposes only sanitized, read-only CLI
summaries.

The owner-controlled repository root, private state directories, and
cooperative locks are the local trust boundary. Python's standard SQLite
wrapper cannot bind a connection to a descriptor-opened inode, so a
noncooperating process running as the same effective user could race an
ordinary-file replacement. Defending against same-UID host compromise would
require OS isolation or a custom/native SQLite VFS and is outside this local
maintainer-only component.

Provider reservation, settlement, quota observation, scheduler authorization,
and provider calls are deliberately outside this component. Downstream factory
control must use ledger evidence and fail closed rather than infer spend from
metrics.

## Consequences

- Concurrent writers cannot independently approve the same remaining cash.
- Retry safety is global and payload-bound without persisting operator keys.
- Credits preserve cash-basis history while reported immediate availability
  never exceeds the paid limit after the reserve.
- Operators must repair or explicitly migrate rejected schema or corrupt state;
  the runtime does not silently rewrite financial evidence.
- The factory still needs downstream reservation, settlement, and scheduler
  integration before it can authorize paid work.

## Evidence

- GitHub issue #1565 owns the security-runtime acceptance lane.
- `docs/meta/FACTORY_OPERATIONS.md` owns operator semantics and commands.
- `docs/technical/TDS.md` owns the component and durability boundaries.
- `scripts/factory_budget_ledger.py` owns the Python and read-only CLI facade.
