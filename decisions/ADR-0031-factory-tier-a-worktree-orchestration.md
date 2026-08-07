---
title: ADR-0031 Factory Tier A Worktree Orchestration
type: decision
status: accepted
date: 2026-08-03
tags: [decision, factory, orchestration, worktree, scheduler, security]
---

# ADR-0031: Factory Tier A Worktree Orchestration

## Decision

Tier A proposal integration uses a separate maintainer-only, plan-first
`factoryctl orchestrate` adapter. A strict frozen request binds one active
scheduler assignment and exact live lease owner (logical id, PID,
process-start token, and epoch) to a `completed-unsettled` execution whose
evidence digest equals the owner-only proposal file's SHA-256. The request also
matches the scheduler-persisted delivery-authority envelope: selector and
selection digests, tier, lane, scopes, and scope digest. It also binds
issue/worktree identity, canonical path, common Git directory, non-main
branch, current local main/base commit, sorted allowed scopes, and verification
lane. This adapter does not change the product `entroping` CLI.

Only scheduler-owned `factoryctl tick --select-live` may mint the delivery
envelope. It admits free-local write work only, fetches fresh GitHub state
without selector-cache I/O, derives the complete selection, and revalidates
active scheduler/local state plus the same result inside assignment commit.
Saved selector artifacts remain non-authorizing and generic tick exposes no
admission input. The selector digest binds the AST-derived transitive internal
import closure from fixed authority roots at canonical main, covering
selection, GitHub freshness/decoding, protected scopes, active queries, and
scheduler admission. The closure includes executed parent package initializers
and their imports, with fixed aggregate path, load, byte, AST, and depth
ceilings. The selection digest binds the full
canonical selection result. Live GitHub commands resolve `gh` only from the
fixed trusted system/Homebrew contract, canonical local Git operations use
`/usr/bin/git`, and both receive a minimal environment. Before mint and
transaction revalidation, canonical main must be clean and every loaded policy
closure module must match its commit-pinned blob. Active writer
issue numbers and scopes come from immutable persisted envelopes; missing or
malformed legacy authority makes selection incomplete. Generic scheduler and
transaction seams expose no admission parameter and reject free-local writes;
paid writes retain their reservation or authorization authority path. The sole
public admission entrypoint is `tick_selected_delivery`, which fetches its own
fresh snapshot and mints only private admission state. Orchestration recomputes
the policy digest.

Explicit apply may create a missing canonical issue worktree only through
`scripts/start_issue.sh` using the exact authorized local base without pulling
or advancing main. Reuse requires the sole matching clean registered worktree.
The adapter checks and applies the exact proposal bytes with bounded subprocess
stdin, marks new regular files intent-to-add so the canonical full-index binary
diff binds their content, and hashes raw Git bytes without decode/re-encode.
Without OS/container isolation, the adapter fails closed to regular Markdown
under `docs/product/` and `docs/user/` with only `tiny-docs` or
`docs-guardrail`. Source, tests, scripts, configuration, workflows, and
machine-consumed control documents escalate to Tier B/C or manual isolation.
Only the exact target-worktree command ids for those lanes may execute;
timeouts, output limits, cancellation with process-group cleanup, and
authority/worktree/main integrity checks apply after every gate.

A separate private SQLite journal persists prepared, applying, applied, gating,
accepted, failed, cancelled, and uncertain lifecycle states. Owner-only
storage, no-follow authorization, stable pathname identity checks, exact schema
allowlisting, sidecar rejection, and bounded storage reduce local replacement
and trigger risks within Python SQLite's pathname API. Exact terminal requests
replay the stored value-free receipt even after the scheduler lease ends;
active replay or any ambiguous post-intent failure becomes uncertain and needs
manual evidence reconciliation. Acceptance intentionally leaves scheduler
execution `completed-unsettled`; later trusted settlement/completion, PR, CI,
merge, and cleanup authority remain separate.

## Evidence

- GitHub issue #1574 owns the Tier C acceptance lane.
- `scripts/factory_orchestration_service.py` owns orchestration composition.
- `scripts/factory_orchestration_models.py` owns strict request and receipt schemas.
- `scripts/factory_orchestration_journal*.py` owns durable lifecycle state.
- `scripts/factory_orchestration_git*.py` owns exact Git/worktree truth.
- `scripts/factory_delivery_admission.py` owns live selection and policy digests.
- `docs/meta/FACTORY_OPERATIONS.md` owns operator behavior.
