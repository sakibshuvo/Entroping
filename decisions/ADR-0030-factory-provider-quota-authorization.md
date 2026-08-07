---
title: ADR-0030 Factory Provider Quota Authorization
type: decision
status: accepted
date: 2026-07-29
tags: [decision, factory, quota, budget, providers, security]
---

# ADR-0030: Factory Provider Quota Authorization

## Decision

Factory remote-work admission uses schema version 3 of the existing private
budget ledger. One short `BEGIN IMMEDIATE` transaction validates prospective
cash thresholds, every referenced provider-quota dimension, and fresh
identity-bound disabled-top-up evidence, then reserves optional cash and all
quota holds in one commit. Quotas remain independent AND constraints and never
create cash authority.

Provider-neutral evidence uses a closed HMAC-SHA-256 maintainer envelope. The
fixed v1 key id resolves only through the supervisor-injected
`ENTROPING_FACTORY_PROVIDER_EVIDENCE_HMAC_KEY_V1`; the key never enters the
artifact, queue job, worker environment, repository, or ledger. The MAC covers
the envelope id and every provider, lane, policy, quota, source, timestamp,
window, usage, known-state, and disabled-top-up field. Admission stores the
computed unsigned-envelope digest rather than accepting record digests from
the file. Missing keys, unknown key ids, invalid MACs, unsafe ownership or
permissions, and production path overrides fail before ledger mutation.
OpenCode and DeepSeek wrapper processes receive an explicit environment
allowlist plus only their selected provider credential; configuring the
evidence-key variable as a provider credential is rejected before spawn.

Admission includes provider used units, every overlapping local settlement not
explicitly covered by the authenticated observation, and active or uncertain
holds. A signed, sorted inclusion boundary may name settled authorization ids
already represented by the provider used-unit total; an omitted or empty
boundary assumes none are represented. Timestamp ordering alone never proves
provider coverage. Inclusion identity, lifecycle, window, count, digest, and
unit totals are validated transactionally. Evidence, decision, and
authorization lifecycle clocks are also monotonic, so settlement, release, or
uncertainty cannot be backdated behind launch. Future, stale, expired,
uncertain, mismatched, regressing, malformed, busy, or conflicting evidence
fails closed.

Rolling evidence must equal the declared duration. UTC-month evidence must use
the exact UTC month, and subscription-cycle evidence must match the referenced
annual, monthly, or fixed-interval renewal plus the canonical UTC-start cycle
id. Provider evidence cannot redefine the policy accounting window.

The generic authorization keeps those authority fields immutable and adds a
durable lifecycle state for active, launched, settled, released, or uncertain
work. Exact replay binds the authenticated envelope and complete attestation
and observation payload and
is a no-op only when every authority field matches. Metered, included-quota,
and fixed-subscription lanes share this contract; offline/read-only work
remains outside it.

## Settlement and launch boundary

Verified cash-backed or quota-only settlement replaces quota holds with actual
bounded usage and stores a complete usage digest even when the authorization
has no quota rows. Ambiguous evidence preserves the hold; verified no-charge or a
pre-network authorization failure releases it. Manual cash
correction does not restore quota. The scheduler remains non-dispatching and
reports `paid_work_authorized: false`; scheduler handoff durably records the
authorization identity. Provider launch revalidates the current 80/90/100 cash
thresholds, quota, top-up, and expiry under one writer transaction that consumes
the authorization before network execution. A consumed authorization cannot
launch twice.

## Evidence

- GitHub issue #1570 owns the Tier C acceptance lane.
- `scripts/factory_quota_authorization.py` owns atomic admission.
- `scripts/factory_quota_schema.py` owns ledger schema version 3.
- `scripts/factory_paid_dispatch_reservation.py` owns provider and policy-window
  adaptation.
- `scripts/factory_paid_dispatch_launch.py` owns provider launch consumption.
- `docs/meta/FACTORY_OPERATIONS.md` owns operator behavior.
