---
title: Factory Operations
type: runbook
status: active
tags:
  - factory
  - docs
  - launchd
  - operations
---

# Factory Operations

## Current Safety State

This runbook defines the future local macOS scheduler contract. The tracked
template is inactive by default and must not be bootstrapped yet. Activation is
blocked until all of these repository-owned dependencies exist:

- the `factoryctl tick` scheduler surface, lease, and duplicate-tick guard
  tracked by issue #1569;
- the read-only `factoryctl status` diagnostics tracked by issue #1572;
- bounded artifact and stream-log retention implemented by issue #1562.

The template contains no credentials and performs no automatic installation.
Tests parse rendered template data only; they never invoke `launchctl`.

## Cost Policy Preflight

The factory's concrete cost policy belongs at
`.entroping/factory-cost-policy.json`. That path is local and ignored; never
commit real account, subscription, quota, or provider data. The repository
commits only the closed
[`factory-cost-policy.v1.schema.json`](factory-cost-policy.v1.schema.json) and
the fake [`factory-cost-policy.example.json`](factory-cost-policy.example.json).
The policy validator is read-only: it does not inspect provider accounts, call
models, reserve funds, or dispatch work.

Validate a reviewed local policy at an explicit offset-aware instant before a
future scheduler uses it:

```text
uv run python -m scripts.factory_cost_policy validate \
  --policy .entroping/factory-cost-policy.json \
  --as-of 2026-07-15T00:00:00Z
```

Use `uv run python -m scripts.factory_cost_policy schema` to inspect the runtime
schema export. `uv run python -m scripts.update_factory_cost_policy_schema`
regenerates the committed schema for review; its output must not drift from the
runtime model.

Version 1 has these fixed semantics:

- Currency is USD and every amount is an integer microcent, where one USD is
  100,000,000 microcents. The approved $200 cap is 20,000,000,000 microcents;
  the $20 emergency reserve is 2,000,000,000 microcents.
- Cash months and renewal dates use UTC. The reserve is a non-spendable floor
  inside the cap, not another charge, and must be positive.
  Experiments stop at 80%, only subscription/included-quota work remains at
  90%, and paid dispatch stops at 100%; validation rejects a reserve too large
  for the 90% transition to protect.
- Subscription charges use cash-basis renewal events. Calendar-month and
  annual renewals declare invalid-date behavior; non-calendar renewals declare
  an anchor date and fixed positive interval. The policy does not amortize an
  annual charge across months.
- Provider quotas are independent of cash. Rolling five-hour (18,000-second),
  rolling weekly (604,800-second), UTC calendar-month, and subscription-cycle
  windows do not add cash or reset the cash ledger.
- Automatic top-up is always `disabled`. Unknown cost blocks paid dispatch;
  unknown quota blocks only the affected paid lane. Safe offline work remains
  outside this policy surface.
- An enabled metered lane names one concrete `provider/model`; every referenced
  price snapshot must match both that model and the lane provider and must be
  observed, unexpired, and unique for its price unit.
  Policy and price validity windows are half-open: start is inclusive and
  expiry is exclusive.

The validator rejects unsupported currencies and billing modes, negative or
overflowing integers, zero charges, duplicate identifiers/references, broken
provider references, naive or reversed timestamps, stale policies/prices,
secret-like content, oversized or invalid UTF-8 files, non-regular files, and
symlinked path components. Validation success proves only that the declaration
is structurally safe and current at `--as-of`; the authoritative ledger,
reservation, settlement, and quota-observation behavior remains in downstream
factory issues.

## Authoritative Budget Ledger

The ignored `.entroping/factory-budget/ledger.sqlite3` database is the
authoritative local record of factory cash activity. Dashboard metrics and
worker receipts may summarize it, but they are not spending authority. Version
1 uses USD integer microcents at exactly 100,000,000 microcents per USD and UTC
calendar months. A period records the reviewed cash cap and an emergency
reserve allocation; that allocation is a non-spendable reserve inside the cap,
not a cash charge.

Ledger writes use a global idempotency key whose SHA-256 digest is stored and
bound to the complete normalized payload. An exact replay is a no-op; reuse
with different evidence fails closed. Fixed subscription and provider charges
are debits. A refund is a credit linked to its original charge, must match its
currency and source, and cannot make cumulative refunds exceed that charge. A
cross-month refund reduces net spend in the month it is received. A manual
adjustment must explicitly select debit or credit. Credits may make net spend
negative, but the reported immediately available paid balance never exceeds
the period's paid limit after the reserve.

Each write serializes the idempotency lookup, period and cap checks, immutable
entry insert, and cached balance update with `BEGIN IMMEDIATE`. The database
uses `journal_mode=DELETE`, `synchronous=EXTRA`, foreign keys, strict tables,
immutable-entry triggers, and a bounded busy timeout. The rollback journal was
chosen so reporting can use a genuinely read-only connection without creating
WAL sidecars. A no-follow header check rejects WAL-mode state before SQLite can
open it or create `-wal`/`-shm` files. Initialization builds and validates a
private temporary database,
syncs it, links it into place atomically, and syncs the containing directory.
Incomplete initialization state is never authoritative.

The ledger descriptor-walks the full repository path. Every ancestor must be
root-owned or owned by the effective user; a group/other-writable ancestor is
accepted only when sticky-directory protection covers a root/user-owned child.
The repository root and shared `.entroping` directory must be owned by the
effective user and not group/other writable. Existing owner-controlled 0755
shared state remains valid, while `.entroping/factory-budget/` is private 0700.
The ledger shares the factory retention lock and rejects symlinked, non-owner,
unsafe-writable, or special state, unsafe sidecars, persistent leaf replacement
during open, files above 512 MiB, malformed databases, schema drift, future or
partial schemas, more than 100,000 total entries, more than 600 periods, and
periods above 100,000 entries. A retry completes the narrow crash window where
the validated database inode was published but its reserved initialization hard
link was not yet removed. Integrity timestamp reads stream in bounded batches.
Rejected or corrupt state is preserved for operator inspection instead of
migrated or rewritten automatically. Entry values and cached balances remain
inside signed 64-bit bounds.

Ledger files and locks must remain owned by the effective user at mode 0600 in
the private mode-0700 ledger directory. The retention and ledger locks
coordinate Entroping processes. A noncooperating process already running as
that same user can race ordinary-file replacement because Python's standard
SQLite wrapper cannot open the main database from a previously validated file
descriptor. Same-UID host compromise is outside this maintainer-only local
trust boundary; use OS account or sandbox isolation where that threat applies.

Only sanitized read-only summaries are exposed on the command line:

```text
uv run python -m scripts.factory_budget_ledger summary \
  --repo /absolute/path/to/Entroping --period 2026-07-01
uv run python -m scripts.factory_budget_ledger balance \
  --repo /absolute/path/to/Entroping --period 2026-07-01
```

The Python API owns explicit period initialization and entry recording. This
ledger does not reserve or settle provider work, call providers, observe quota,
or authorize scheduler dispatch. Those integrations remain downstream and
must fail closed against this evidence rather than infer spend from metrics.

## Artifact and Log Retention

The committed example policy defines age limits per terminal state and aggregate
byte ceilings for terminal jobs, reviewed evidence, rotated factory logs,
verified finished-issue metrics archives, and terminal retention receipts.
Copy it to the ignored `.entroping/factory-retention-policy.json` only when a
reviewed local override is needed. The command never scans outside the current
repository and never follows symlinks.

Preview the exact deterministic plan first:

```text
uv run python -m scripts.factory_retention plan --json
```

`prune` remains plan-only unless `--apply` is present:

```text
uv run python -m scripts.factory_retention prune
uv run python -m scripts.factory_retention prune --apply --json
```

Apply re-inventories the managed roots, takes the shared factory-state lock
exclusively, rejects Git-tracked targets or descendants, verifies each content
fingerprint immediately before mutation, stages same-filesystem moves, and
records a durable recovery journal under `.entroping/retention-journal/`.
Recovery rolls back a moving journal that still has pending operations; a fully
staged or purging journal completes its recorded purge. A persisted journal is
never authority to stage new deletion work. Recovery rejects journals above
4,096 operations and any transaction-trash name outside the generated
six-digit-index plus digest shape before it can touch staged entries.

Matching managed entries with malformed metadata, symlinks, special files,
control-bearing names, changed fingerprints, unresolved reservations, active
reviews, orphaned reviews, legacy metrics without terminal provenance, or
unknown accepted issue/PR references fail closed. Unrelated factory-log names
are ignored. Traversal is bounded by per-directory, total-entry, depth,
metadata-read, hashed-byte, and operation limits. Policy class ceilings may
total at most 4 GiB; the 8 GiB inventory hash budget reserves equal headroom so
ordinary over-cap pressure remains prunable. Reports contain only artifact IDs,
classes, states, timestamps, relative paths, reason codes, counts, and byte
totals, never artifact contents.

The tick runner bounds and redacts output before persistence. It serializes tick
log writes under a shared retention lock, limits each captured stream to 256
KiB, and keeps only an active file plus one 4 MiB rotation for each stream. A
tick that exceeds its output ceiling is terminated with its process group and
fails closed. Retention inventories active stream files but protects them;
rotated logs can expire by policy. Active factory metrics share a locked 64 MiB
aggregate cap. `finish_issue.sh` adds verified terminal provenance to newly
archived metrics, including the canonical relative path, exact byte count, and
SHA-256 digest of every ledger. Inventory revalidates those digests before an
archive can become deletion-eligible; legacy archives without that sidecar
remain protected. The fully serialized provenance sidecar must fit its 64 KiB
reader ceiling before any destination ledger is copied.

## Contract

The source template is
`docs/meta/templates/com.entroping.factory-tick.plist`. It defines:

- one launchd label, `com.entroping.factory-tick`;
- an absolute `{{PYTHON_EXECUTABLE}}` that invokes the tracked
  `scripts.factory_tick_runner` module with an absolute
  `{{FACTORYCTL_EXECUTABLE}}`;
- an explicit working directory and minimal `PATH`;
- `RunAtLoad: false`, `KeepAlive: false`, and `Disabled: true`;
- a positive `StartInterval` placeholder; and
- `/dev/null` launchd streams; the runner writes bounded logs only under the
  repo-owned `.entroping/factory-logs` directory.

`StartInterval` requests one short idempotent tick. launchd does not start a
second copy when the previous interval is still running, but that is not a
replacement for the repository lease and idempotency contract. A separate
operator or duplicate service can still race without issue #1569's guard.

launchd's `StandardOutPath` and `StandardErrorPath` never receive factory output.
The runner captures each stream with a 256 KiB per-tick ceiling, terminates a
tick that floods either stream, and keeps each active log plus one rotation at
no more than 4 MiB per file. Retention planning additionally covers rotated
logs, terminal jobs, review evidence, finished metrics archives, and terminal
retention receipts under the repo-owned `.entroping/` roots.

## Render and Validate

Render the template into a temporary file before copying it to
`~/Library/LaunchAgents`. Replace every placeholder with an explicit value:

| Placeholder | Required value |
| --- | --- |
| `{{PYTHON_EXECUTABLE}}` | Absolute path to the validated project Python executable |
| `{{FACTORYCTL_EXECUTABLE}}` | Absolute path to the validated scheduler executable |
| `{{WORKING_DIRECTORY}}` | Absolute path to the clean Entroping checkout |
| `{{FACTORY_PATH}}` | Minimal executable search path, normally `/usr/bin:/bin:/usr/sbin:/sbin` plus the scheduler directory |
| `{{LOG_DIRECTORY}}` | `{{WORKING_DIRECTORY}}/.entroping/factory-logs` as an absolute path |
| `{{TICK_INTERVAL_SECONDS}}` | Integer interval approved by the scheduler design |

Do not put tokens, provider keys, credentials, shell expressions, `$HOME`, or
relative paths in the rendered plist. Review the rendered diff, confirm no
`{{...}}` placeholders remain, then validate without loading it:

```text
plutil -lint /absolute/path/to/rendered/com.entroping.factory-tick.plist
plutil -p /absolute/path/to/rendered/com.entroping.factory-tick.plist
```

The tracked template itself contains a placeholder inside an integer element,
so lint the rendered file, not the source template.

## Future Install and First Tick

Run this section only after issues #1569 and #1572 are merged and this retention
contract's acceptance gate passes.

1. Create the log directory with mode `0700` and install its bounded retention
   configuration.
2. Copy the reviewed rendered plist to
   `~/Library/LaunchAgents/com.entroping.factory-tick.plist` with mode `0600`.
3. Validate the installed file again with `plutil -lint`.
4. Inspect both launchd state and `factoryctl status`. If an old service is
   loaded, disable it, wait for a terminal tick and settled budget evidence,
   then boot it out. Do not terminate an active or uncertain tick.
5. Enable the label, bootstrap it into the current GUI domain, and inspect its
   state before requesting the first tick.

```text
launchctl print-disabled gui/$UID
launchctl print gui/$UID/com.entroping.factory-tick
factoryctl status
```

If the old label is loaded, disable future ticks and inspect status again:

```text
launchctl disable gui/$UID/com.entroping.factory-tick
factoryctl status
```

Stop here until the tick is terminal and reservation/cost settlement is
reconciled. After that explicit operator checkpoint, boot out the old service:

```text
launchctl bootout gui/$UID/com.entroping.factory-tick
```

Skip the disable and bootout commands only when `launchctl print` confirms the
label is not loaded. When the prior state is terminal and settled, activate the
reviewed agent:

```text
launchctl enable gui/$UID/com.entroping.factory-tick
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.entroping.factory-tick.plist
launchctl print-disabled gui/$UID
launchctl print gui/$UID/com.entroping.factory-tick
launchctl kickstart gui/$UID/com.entroping.factory-tick
```

Do not use `kickstart -k` for a routine tick because it terminates an already
running process. The plist's `Disabled: true` is only a default: `launchctl
enable` stores an external override that can persist across boots. Always use
`launchctl print-disabled gui/$UID` to inspect effective enablement.

## Status and Logs

Use both launchd state and the future factory status CLI. Neither is sufficient
alone.

```text
launchctl print-disabled gui/$UID
launchctl print gui/$UID/com.entroping.factory-tick
factoryctl status
tail -n 100 "/absolute/path/to/logs/factory-tick.out.log"
tail -n 100 "/absolute/path/to/logs/factory-tick.err.log"
```

Inspect the service state and last exit status, then correlate them with the
factory lease, queue, budget, and last-settled-cost evidence. Never paste raw
provider output or secrets into an issue. Confirm retention is rotating both
stream logs and factory artifacts before trusting unattended operation.

## Disable, Restart, and Uninstall

Disable future scheduling, then inspect the current tick:

```text
launchctl disable gui/$UID/com.entroping.factory-tick
launchctl print-disabled gui/$UID
factoryctl status
```

Wait until the tick is terminal and its reservation/cost settlement is
reconciled. Only then stop the loaded service:

```text
launchctl bootout gui/$UID/com.entroping.factory-tick
```

For a reviewed plist or executable update, complete that safe stop sequence,
validate the installed plist, enable the label, bootstrap it again, then
inspect both effective enablement and status. Do not mix deprecated `load` or
`unload` commands into this lifecycle.

Uninstall only after confirming no tick is running:

```text
launchctl bootout gui/$UID/com.entroping.factory-tick
launchctl print-disabled gui/$UID
rm -f ~/Library/LaunchAgents/com.entroping.factory-tick.plist
```

Keep logs and receipts until their retention and incident-review requirements
are satisfied; uninstall must not erase evidence automatically.

## Recovery Boundaries

### Sleep, reboot, and clock changes

- A sleeping laptop is not a true 24x7 host. `StartInterval` firings missed
  during sleep are not replayed on wake.
- If a tick is still running when an interval fires, that firing is skipped.
- A user LaunchAgent becomes available only after its user session is active;
  after reboot or login, inspect `launchctl print` and `factoryctl status`.
- Treat large clock changes as an operator event. Confirm the last settled tick
  and budget window before manually requesting another tick.

### Network or provider outage

- One tick should record a bounded failure and exit; it must not spin or retry
  forever inside launchd.
- The next scheduled tick may retry only through the scheduler's idempotent
  state machine and budget policy.
- Disable the label when authentication, rate-limit, or settlement state is
  ambiguous. Resume only after status evidence is consistent.

### Disk full or unbounded log growth

- Disable the service before cleaning disk pressure. If status remains
  available, wait for terminal and settled evidence before bootout.
- If an emergency bootout is unavoidable, record the reservation and cost as
  uncertain and reconcile it before any future enable or bootstrap.
- Preserve receipts and cost evidence needed for reconciliation.
- Restore tested retention, verify free space and file ownership, then
  revalidate the plist before bootstrap.
- A dedicated log directory limits cleanup scope; it does not cap bytes by
  itself.

### Stale lease or duplicate tick

- Inspect `factoryctl status` before changing launchd state.
- Do not delete a lease by hand. Disable future scheduling, verify whether the
  recorded process is still healthy, and use the scheduler's documented
  recovery command after issue #1571 is implemented. Boot out only after that
  process is terminal or the recovery procedure records uncertain settlement.
- Re-enable only when the prior tick is terminal and budget settlement is
  reconciled.
