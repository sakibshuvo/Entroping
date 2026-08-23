---
title: ADR-0036 Traffic Store v2 Run History
type: decision
status: accepted
date: 2026-08-22
tags:
  - decision
  - traffic
  - sqlite
  - run-history
  - reports
  - security
  - reliability
---

# ADR-0036: Traffic Store v2 Run History

## Decision

The local `.entroping/state.db` traffic store moves from schema version 1 to
version 2 by adding one bounded, value-free `run_history` projection. The
existing `traffic_store_metadata` row remains the only schema-version
authority: `key='schema_version'`, `value='2'`. `PRAGMA user_version` is not a
second authority. This issue changes architecture documentation only; schema
creation, migration, and workflow persistence are follow-up implementation
issues.

The version-2 database preserves the version-1 metadata and traffic tables,
columns, indexes, redaction behavior, and traffic rows. It never makes SQLite
the canonical run report and never stores raw report, Hurl, traffic, prompt,
credential, environment-variable, or provider content.

## Exact schema

Version 1 objects that a migration may recognize are exactly:

```sql
CREATE TABLE traffic_store_metadata (
    key VARCHAR NOT NULL PRIMARY KEY,
    value VARCHAR NOT NULL
);
CREATE TABLE traffic_events (
    id INTEGER NOT NULL PRIMARY KEY,
    captured_at VARCHAR NOT NULL,
    method VARCHAR NOT NULL,
    url VARCHAR NOT NULL,
    host VARCHAR NOT NULL,
    path VARCHAR NOT NULL,
    status_code INTEGER,
    duration_ms INTEGER,
    exchange_json VARCHAR NOT NULL
);
CREATE INDEX idx_traffic_events_captured_at
    ON traffic_events (captured_at);
CREATE INDEX idx_traffic_events_host_path
    ON traffic_events (host, path);
```

The no-metadata alpha legacy classifier also recognizes the same
`traffic_events` columns, types, nullability, and primary-key position when
`id` was historically declared as `INTEGER PRIMARY KEY`. SQLite exposes that
rowid-alias declaration through `PRAGMA table_info` with `notnull=0`, while
still enforcing a non-null integer primary key. This is the only accepted
nullability variation: metadata-v1 stores must use the explicit `NOT NULL`
shape above, and no other column or constraint may vary. After that legacy
shape is migrated to metadata `2`, v2 validation continues to accept the same
implicit integer-primary-key form so reopen is idempotent and traffic rows do
not need an unnecessary table rewrite.

The required version-2 addition is exactly this table and these indexes:

```sql
CREATE TABLE run_history (
    id INTEGER NOT NULL PRIMARY KEY,
    generated_at VARCHAR NOT NULL,
    project VARCHAR NOT NULL,
    environment VARCHAR NOT NULL,
    status VARCHAR NOT NULL CHECK (status IN ('passed', 'failed', 'blocked')),
    exit_code INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL CHECK (duration_ms >= 0),
    total INTEGER NOT NULL CHECK (total >= 0),
    passed INTEGER NOT NULL CHECK (passed >= 0),
    failed INTEGER NOT NULL CHECK (failed >= 0)
);
CREATE INDEX idx_run_history_generated_at_id
    ON run_history (generated_at, id);
CREATE INDEX idx_run_history_project_environment_generated_at_id
    ON run_history (project, environment, generated_at, id);
```

`id` is the SQLite integer primary-key insertion tie-breaker. There is no
unique run key and no implicit deduplication contract. Required table columns,
declared types (including explicit `NOT NULL` primary keys), `NOT NULL`/`CHECK`
constraints, and index names/column order must be validated before an existing
v2 store is accepted, subject only to the retained legacy
`traffic_events.id` integer-primary-key form above. The `run_history.id`
primary key always requires explicit `NOT NULL`. SQLite internal
indexes are not user schema. Harmless pre-existing non-required indexes may be
preserved when recognizing a legacy v1 store; if migration preserves them,
later idempotent v2 validation accepts those same harmless indexes. Required
v1/v2 index names and column order still validate exactly; unknown tables,
extra columns, duplicate required objects, or malformed `run_history` fail
closed.

The value-free allowlist is exactly the nine non-id columns above (ten table
columns including `id`):

- `generated_at`: the canonical report timestamp, parsed as an RFC-3339 UTC
  instant and stored as fixed-width `YYYY-MM-DDTHH:MM:SS.ffffffZ`; offsets in
  the report are normalized to UTC before the transaction. This fixed form
  makes the index's lexical order temporal.
- `project` and `environment`: NFC-normalized UTF-8 identifiers, each 1..256
  bytes, with no NUL, C0/C1/control character, newline, tab, or secret-like
  token.
- `status`: exactly `passed`, `failed`, or `blocked`.
- `exit_code`: an exact Python `int` (never `bool`) in SQLite's signed
  64-bit range.
- `duration_ms`, `total`, `passed`, and `failed`: exact Python `int` values
  (never `bool`), non-negative and within SQLite's signed 64-bit range.

The identifier checks above are for this history projection only; they do not
narrow Qanstitution or `entroping.run-report.v1` validation and never make a
successful canonical run unsuccessful. Validate the projection before opening
or starting any history transaction. An unsafe or unbounded identifier yields
no row and a bounded value-free `history-unavailable` diagnostic; rejected
values never enter storage or diagnostics, and canonical JSON plus the primary
run result/exit code remain unchanged.

No scheduling counts (`selected`, `executed`, `not_scheduled`, `fail_fast`),
report schema version, report digest, `run_id`, test rows, source or execution
paths, URLs/hosts, headers/cookies/bodies, stdout/stderr, gate payloads,
explanations, or model/provider data may be added to v2. Any future field needs
an additive ADR and an explicit migration.

## Canonical report and workflow ownership

The versioned `entroping.run-report.v1` JSON at
`.entroping/latest-run.json` remains canonical. `reports/run-latest.json`, when
requested, is a projection for tooling and is not a prerequisite for history.
The history row is created once, after the canonical file has been written and
schema-validated; the writer maps `generated_at`, `project`, `environment`,
`summary.exit_code`, `summary.total`, `summary.passed`, and `summary.failed`
from that report and receives the bounded workflow elapsed duration separately.
It must not reconstruct, replace, or declare the report JSON. Existing report
JSON remains authoritative even if history persistence fails.

The workflow maps terminal branches as follows:

- a normal terminal suite is `passed` when `summary.exit_code == 0`, otherwise
  `failed`;
- a protected-run report that stopped before Hurl is `blocked`;
- no-match, dry-run, abort, or an error before a canonical terminal report
  writes no row;
- a failed suite may write one `failed` row, and a blocked protected run may
  write one `blocked` row;
- drift may change `RunWorkflowResult.exit_code`, but is not history content;
  history uses the canonical report summary exit code and therefore does not
  turn a passing Hurl report into a drift row.

Eligible successful, failed, and blocked terminal reports retain this mapping;
projection rejection suppresses only history and never rewrites the canonical
report or primary run result.

The writer/readers follow the existing traffic-store style: a typed
`RunHistoryRow`, `record_run_history(report_projection, status, duration_ms)`,
`list_run_history(limit=None)`, and a project-level
`list_project_run_history_readonly(project_root, limit=None)` boundary. Names
are implementation seams, not new CLI commands. `DEFAULT_RUN_HISTORY_LIMIT` is
100 and a positive constructor override is separate from `max_events`.
Append uses one `BEGIN IMMEDIATE` transaction for validation-backed insert,
retention deletion, and commit. Retention keeps the newest 100 (or override)
by `generated_at DESC, id DESC`. For positive `limit=N`, readers first select
the newest N by `generated_at DESC, id DESC`, then return that bounded selection
by `generated_at ASC, id ASC`; `limit=None` returns all chronologically in that
order. Insert and prune are never committed separately. A definite history
persistence failure rolls back with no row, leaves canonical JSON and the
primary run result/exit code unchanged, and emits a bounded value-free
`history-unavailable` diagnostic. An ambiguous writer commit is not retried or
deduplicated; the caller reopens/read-checks and emits a bounded value-free
`history-uncertain` diagnostic/uncertain history state without rewriting the
canonical outcome or appending a duplicate.

## Migration state machine

Every SQLite open applies ADR-0026's pre-connect boundary: before
SQLite opens an existing path, it inspects the validated header and rejects
WAL-mode headers or `-wal`/`-shm` sidecars. The path is never opened, so no
PRAGMA can convert journal mode or remove sidecars before store validation.
Then set `PRAGMA busy_timeout=5000`, `foreign_keys=ON`, `trusted_schema=OFF`
where supported, `journal_mode=DELETE`, and `synchronous=EXTRA`; for an
accepted existing file, `journal_mode=DELETE` is an unchanged
rollback-journal assertion, not a conversion, and must not make a rejected or
failed migration appear committed. Next inspect `sqlite_master`,
`PRAGMA table_info`, metadata, required indexes, and database integrity before
DDL. Do not call `SQLModel.metadata.create_all()` or use blind `IF NOT EXISTS`
as schema validation.

The pre-DDL classifier has these only-accepted states:

| Existing state | One transaction and result |
| --- | --- |
| No user tables (only SQLite internals) | `BEGIN EXCLUSIVE`; create the recognized v1 objects, v2 table/indexes, and metadata `2`; validate an empty history; commit. |
| Metadata `1` plus recognized v1 traffic state | `BEGIN EXCLUSIVE`; create only v2 objects, update the existing schema row to `2`; validate; commit, preserving every v1 traffic row/index. |
| No metadata plus a recognized legacy `traffic_events` state | `BEGIN EXCLUSIVE`; create metadata/indexes that are missing from the recognized v1 shape and all v2 objects; validate; commit, preserving traffic and the supported implicit integer-primary-key declaration. Missing required v1 indexes may be created; harmless extra indexes remain. |
| Metadata `2` plus complete v1 or retained legacy-compatible traffic state and complete v2 state | Validate shape, values, required indexes, and integrity; perform no DDL and return an idempotent no-op. |

An empty metadata table, arbitrary no-metadata database, unknown table,
unknown column, malformed traffic table, partially present/malformed
`run_history`, duplicate required object, invalid metadata text, schema `0` or
other older version, and any version greater than `2` fail closed before
mutation. A recognized v1/no-metadata migration never copies traffic or report
content into `run_history`. DDL, metadata update, required-index creation,
row/value validation, and `PRAGMA quick_check` are in the same transaction.

Any DDL, validation, integrity, or definite commit error rolls back the active
transaction; the original schema/data must remain readable. If commit outcome
is ambiguous, close the connection and classify using a fresh bounded reopen:
valid complete v2 means committed success; valid original v1/no-metadata means
retryable original state; neither is an uncertain hard failure with no repair
attempt. A retry is a new bounded invocation, never an in-transaction guess.
`BEGIN EXCLUSIVE` serializes migration/openers. A competing opener waits at
most five seconds, then revalidates v2 once if the winner is visible; otherwise
it raises a value-free `TrafficStoreError` without fallback DDL or an
unbounded retry. The run-event lock is not the migration lock.

## Read-only compatibility and downgrade posture

The read-only reader requires an existing regular `.entroping/state.db`, opens
SQLite with `mode=ro` and `query_only=ON`, validates schema before selecting
rows, and never creates directories/metadata/tables, migrates, prunes, or
creates WAL/SHM sidecars. A recognized v1 or no-metadata legacy store without
`run_history` returns an empty history result while preserving existing traffic
read compatibility. A validated v2 store returns only typed allowlisted rows in
the ordering above. Future, older, malformed, unknown, or integrity-failing
stores fail before rows are read. A missing state file remains an error, not an
implicit fresh database.

There is no v2-to-v1 downgrade. A v1 binary sees metadata `2` as newer and
rejects it without dropping `run_history`, rewriting metadata, or mutating the
file. Recovery from a future schema is an explicit reviewed upgrade or local
state replacement, never an automatic destructive downgrade.

## Consequences and non-goals

- History is a bounded local index for summaries, not an event log, report
  archive, traffic store replacement, or hosted product database.
- Migration and append are SQLite-serialized and fail closed under schema,
  integrity, lock, and commit uncertainty.
- Existing read-only Studio/status access remains non-mutating, including
  recognized no-metadata v1 compatibility.
- No CLI surface, provider call, Hurl execution, report format, traffic
  redaction policy, or canonical report path changes in this ADR.
- Row-level retry/deduplication, scheduling telemetry, report digests, and
  additional history fields require a future ADR and migration.

## References

- `src/entroping/core/traffic_store.py` (current v1 schema and read-only path)
- `src/entroping/core/run_workflow.py` (canonical report boundary and drift exit)
- `src/entroping/core/report_writer.py` and `src/entroping/models/report.py`
- [ADR-0005: Deterministic Run Boundary](ADR-0005-deterministic-run-boundary.md)
- [ADR-0026: Transactional Factory Budget Ledger](ADR-0026-factory-budget-ledger.md)
- [Technical Design Specification](../docs/technical/TDS.md)
- [Issue #1655](https://github.com/sakibshuvo/Entroping/issues/1655)
- [Issue #1660](https://github.com/sakibshuvo/Entroping/issues/1660)
- [Issue #1661](https://github.com/sakibshuvo/Entroping/issues/1661)
