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
- bounded artifact and stream-log retention tracked by issue #1562.

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
  inside the cap, not another charge.
  Experiments stop at 80%, only subscription/included-quota work remains at
  90%, and paid dispatch stops at 100%.
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

## Contract

The source template is
`docs/meta/templates/com.entroping.factory-tick.plist`. It defines:

- one launchd label, `com.entroping.factory-tick`;
- an absolute `{{FACTORYCTL_EXECUTABLE}}` placeholder followed by the single
  `tick` argument;
- an explicit working directory and minimal `PATH`;
- `RunAtLoad: false`, `KeepAlive: false`, and `Disabled: true`;
- a positive `StartInterval` placeholder; and
- dedicated `StandardOutPath` and `StandardErrorPath` values under one log
  directory.

`StartInterval` requests one short idempotent tick. launchd does not start a
second copy when the previous interval is still running, but that is not a
replacement for the repository lease and idempotency contract. A separate
operator or duplicate service can still race without issue #1569's guard.

The log paths are dedicated, not size-bounded by launchd. `StandardOutPath`
and `StandardErrorPath` append without rotation. Do not activate the agent
until issue #1562 provides a tested retention policy for both files and the
factory artifact directory.

## Render and Validate

Render the template into a temporary file before copying it to
`~/Library/LaunchAgents`. Replace every placeholder with an explicit value:

| Placeholder | Required value |
| --- | --- |
| `{{FACTORYCTL_EXECUTABLE}}` | Absolute path to the validated scheduler executable |
| `{{WORKING_DIRECTORY}}` | Absolute path to the clean Entroping checkout |
| `{{FACTORY_PATH}}` | Minimal executable search path, normally `/usr/bin:/bin:/usr/sbin:/sbin` plus the scheduler directory |
| `{{LOG_DIRECTORY}}` | Absolute path to a dedicated directory with mode `0700` |
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

Run this section only after issues #1562, #1569, and #1572 are merged and their
acceptance gates pass.

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
