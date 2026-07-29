---
title: Backlog Triage Prompt
type: prompt
status: active
tags:
  - github
  - backlog
  - triage
  - reviews
---

# Backlog Triage Prompt

Use this to convert Gemini, DeepSeek, friend feedback, or bug-bash output into
GitHub issues without distracting the current roadmap.

```text
You are triaging Entroping backlog input.

Repo:
cd /Users/sakibshuvo/projects/Entroping

Codex Cloud: if this macOS path does not exist, use the repository root provided
by the cloud task.

Input:
<paste review, bug bash, user feedback, or idea>

Rules:
- Do not implement.
- Do not update roadmap unless public sequence/scope changes.
- Treat external model output as triage input, not truth.
- Verify current repo state before creating issues.
- Avoid duplicate issues.
- Preserve QAnstitution branding and current product direction.
- Prefer narrow issues with acceptance criteria over broad strategy docs.

Start:
git pull --ff-only
git status --short
gh issue list --repo sakibshuvo/Entroping --state open --limit 120
python scripts/backlog_health.py

Triage each input item as:
- verified issue,
- duplicate of existing issue,
- already fixed,
- stale claim,
- opinion/product judgment,
- needs more evidence,
- rejected as unsafe/out of scope.

For verified issues, propose:
- title,
- type label,
- priority label,
- area label,
- milestone if obvious,
- acceptance criteria as deterministic pass/fail bullets,
- verification commands,
- source evidence,
- current repo evidence.

Ask before creating issues if there are more than five. If creating issues, keep each one narrow and actionable.

## OpenCode/DeepSeek Status-Ready Issue Guard

For `status:ready` OpenCode/DeepSeek items, include a constrained handoff
packet with this exact field list:

- provider lane,
- model id (when known; use `unknown` if not known),
- autonomy tier,
- allowed files,
- forbidden scope, including the minimum Tier A exclusions below,
- required focused tests,
- required full gate,
- merge authority,
- stop conditions.

Guidance:

- Prefer `gh issue create` and use GitHub Issues for actionable backlog.
- Avoid Markdown backlog sprawl; do not create or mutate Markdown issue
  trackers as a backlog system.
- Tier A cannot include `Hurl runner`, `entroping run`, redaction/proxy,
  provider runtime, dependencies, release publishing, secrets, raw traffic,
  audit evidence, or architecture boundary changes.
- The packet's `forbidden scope` must include at least those Tier A exclusions;
  add narrower exclusions for the specific issue when needed.

Use this packet shape for `status:ready` OpenCode/DeepSeek issues:

```yaml
provider lane: <lane>
model id: <id or unknown>
autonomy tier: <Tier A autonomous lane | Tier B assisted lane | Tier C restricted lane>
allowed files: <exact files>
forbidden scope: <exact exclusions, including the minimum Tier A exclusions>
required focused tests: <focused commands>
required full gate: <lane gate>
merge authority: <who can merge>
stop conditions: <conditions>
```

## Sanitized User-Evidence Packet

For a verified issue derived from user feedback, human-review and redact the
canonical local downstream artifact before creating the issue or dispatching
it to a provider. Under one `## User evidence` heading, add exactly this closed
metadata shape:

```yaml
user_evidence:
  schema_version: entroping.user-evidence.v1
  evidence_status: verified
  affected_journey: first_run
  severity: blocker
  source_classification: design_partner
  verification_receipt: sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
```

Use only the enums and receipt format defined in `ISSUE_TRACKING.md`. Internal
observations are not user evidence. A maintainer must compare the receipt with
the sanitized local artifact before applying `evidence:user-verified`; valid
metadata or the label alone never establishes verified user demand.

Never put raw feedback, private conversations, direct quotes, private URLs,
identifiers, or unredacted logs in GitHub or provider prompts. Provider
dispatch may receive only the sanitized issue packet.

Apply this precedence only after issue #1567's complete fresh-state, issue
contract, milestone, verification, autonomy, ownership, active unmerged branch,
PR, lease, explicit-file-scope, overlap, and dependency gates pass. Then select
the first non-empty bucket: `priority:p0`;
verified `severity: blocker` user evidence; verified `priority:p1` user
evidence; other eligible work. Within a bucket, use priority then ascending
issue number. Malformed, repeated, unlabelled-verified, or unknown metadata
receives no user-evidence priority and must surface a triage warning.

At initial lease acquisition, snapshot exactly one of `work:product`,
`work:factory`, or `work:mixed`; missing or conflicting labels become
`unclassified`. Count each issue receipt once after normal finish, ignore
retries, and report the most recent 20 or the smaller available sample plus
`sample_size`. Later label edits do not rewrite receipts. This signal must not
affect selection or enforce a target or fixed percentage.
