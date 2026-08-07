---
title: ADR-0032 Factory Tier A PR Delivery Controller
type: decision
status: accepted
date: 2026-08-06
tags: [decision, factory, delivery, github, scheduler, sqlite, security]
---

# ADR-0032: Factory Tier A PR Delivery Controller

## Decision

ADR-0031 authorizes exact Tier A worktree orchestration but explicitly withholds
PR, CI, merge, cleanup, and scheduler-completion authority. This decision adds
a separate maintainer-only `factoryctl deliver` adapter. It is plan-first and
read-only unless explicit `--apply`; the product `entroping` CLI is unchanged.
The controller is disabled by default and grants no launchd activation,
provider dispatch, public command, or broad automation authority.

The controller accepts one strict owner-only bounded request. Callers cannot
supply repository, issue, branch, base, title, commands, snapshot, provider,
CI, merge, force, admin, SSH, credential, or cleanup authority. Its private
SQLite journal persists intent before each mutation and binds exact local
commit/diff, push, PR, CI, merge, and head evidence. Canonical terminal
value-free receipts replay byte- and semantically-identically across fresh
service instances without repeating proven effects. Drift or ambiguity remains
safe pending, blocked, failed, or uncertain.

Strict cleanup is bound to the recorded issue, worktree, branch, PR, and head;
it safely replays partial local cleanup. Remote deletion uses only the exact
authorized branch/head under an expected-value lease and persists absence
before later cleanup proof. Scheduler completion consumes the persisted owner,
epoch, phase version, and one stored completion timestamp only after cleanup
proof. An accepted terminal completion remains valid after lease expiry without
renewing a worker heartbeat or lease and without weakening authority, CAS, or
fencing checks.

## Evidence

- `scripts/factory_pr_delivery_service.py` owns delivery composition.
- `scripts/factory_pr_delivery_journal*.py` own durable intent, receipt, and
  cleanup-proof persistence.
- `scripts/factory_pr_delivery_cleanup.py` and
  `scripts/factory_pr_delivery_terminal_completion.py` own strict cleanup and
  one-step replay composition.
- `scripts/factory_pr_delivery_scheduler_completion.py` and
  `scripts/factory_scheduler_completion_transaction.py` own fenced scheduler
  completion and stored-heartbeat preservation.
