---
title: ADR-0023 Factory Artifact Retention
type: decision
status: accepted
date: 2026-07-27
tags:
  - decision
  - factory
  - retention
  - security
  - reliability
---

# ADR-0023: Factory Artifact Retention

## Decision

Entroping applies one versioned, fail-closed retention policy to repo-owned
ignored factory artifacts. The policy covers terminal job records, review
bundles, rotated scheduler logs, finished-issue metrics archives with verified
terminal provenance, per-ledger byte counts and SHA-256 digests, and terminal
retention journals. It defines each class's
terminal-state age limits and aggregate byte ceiling. Active metrics have a
separate locked 64 MiB aggregate cap, while active tick logs are inventoried and
protected from deletion.

Plan-only is the default. Deletion requires an explicit apply against a fresh
inventory under an exclusive lock. Inventory and apply use descriptor-relative,
non-symlink traversal with finite entry, depth, read, hash, output, and operation
limits. Git-tracked targets and tracked descendants are never eligible.

## Recovery Boundary

The current explicit apply is the only authority to stage new deletions. A
persisted moving journal with pending operations is recovery evidence, not new
deletion authority, so recovery rolls its staged entries back. A journal whose
operations are fully staged, or which has entered purging, completes the
recorded purge. Fingerprints and placement are checked at each safe transition;
completed and rolled-back receipts remain auditable until their own retention
policy expires. Adopted journals use the same 4,096-operation ceiling and
canonical transaction-trash names as newly created journals.

## Safety Boundary

Malformed or ambiguous metadata, symlinks, special files, control-bearing
names, traversal-limit breaches, unknown external references, unresolved
settlements, legacy metrics without terminal provenance, tracked paths, and
content drift fail closed. The command never scans outside the repository,
calls providers, interprets artifact contents as instructions, or renders those
contents in its report.

## Consequences

- Long-running factory operation has finite live metrics, tick-log, evidence,
  archive, and receipt growth.
- Legacy metrics archives remain protected until explicit trusted provenance
  exists; their presence cannot become retroactive deletion authorization.
- A crash can leave recoverable local state, but cannot silently widen the
  selected deletion set.
- Operators must inspect the deterministic plan and opt into apply.

## Evidence

- GitHub issue #1562 owns the security-runtime acceptance lane.
- `docs/meta/factory-retention-policy.example.json` is the committed safe
  example.
- `docs/meta/FACTORY_OPERATIONS.md` owns the operator commands and recovery
  contract.
- `docs/technical/TDS.md` owns the architectural boundary.
