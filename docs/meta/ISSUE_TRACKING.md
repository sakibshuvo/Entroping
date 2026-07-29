---
title: Issue Tracking
type: runbook
status: active
tags:
  - issues
  - bugs
  - regression
  - github
---

# Issue Tracking

GitHub Issues are the canonical tracker for bugs, feature slices, regressions, and release blockers. Obsidian tracks strategy and progress; GitHub tracks work items.

Documentation ownership and roadmap update rules live in
[[docs/meta/DOCS_GOVERNANCE|DOCS_GOVERNANCE]]. Do not duplicate issue-level
backlog details into Obsidian.

## Labels

Use a small label system so the queue stays readable:

| Group | Labels |
| --- | --- |
| Type | `type:bug`, `type:feature`, `type:regression`, `type:security`, `type:docs`, `type:architecture`, `type:tests` |
| Priority | `priority:p0`, `priority:p1`, `priority:p2`, `priority:p3` |
| Area | `area:cli`, `area:qanstitution`, `area:hurl-runner`, `area:reports`, `area:brain`, `area:eye`, `area:tests`, `area:docs` |
| Status | `status:needs-triage`, `status:ready`, `status:blocked`, `status:in-progress` |

## Triage Rules

- Every bug needs observed behavior, expected behavior, reproduction steps, area, and priority.
- Every feature slice needs one-sentence outcome, source-of-truth link, proof of completion, and required gates.
- Every regression needs a last-known-good state and a regression test plan.
- Security vulnerabilities should use private security advisories, not public issues.
- A ticket is ready only when the next action is clear enough for a fresh agent to execute.

## User-Evidence Metadata Contract

When a ready issue is grounded in user feedback, place exactly one YAML block
under an `## User evidence` heading. The block has this versioned, closed
shape; unknown or repeated fields are invalid:

```yaml
user_evidence:
  schema_version: entroping.user-evidence.v1
  evidence_status: verified
  affected_journey: first_run
  severity: blocker
  source_classification: design_partner
  verification_receipt: sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
```

- `evidence_status`: `unverified` or `verified`.
- `affected_journey`: `install`, `first_run`, `author`, `run`, `report`,
  `integrate`, or `other`.
- `severity`: `blocker`, `major`, or `minor`. A blocker prevents completion of
  the supported journey, major impact requires a substantial workaround or
  loses reliability, and minor impact adds friction while completion remains
  practical. This describes user impact; `priority:p0` through `priority:p3`
  continue to describe scheduling urgency.
- `source_classification`: `design_partner`, `support`, `public_issue`, or
  `other_user_channel`. Every value means evidence supplied by a real user;
  internal observations are not user evidence.
- `verification_receipt`: `sha256:` plus the lowercase SHA-256 digest of the
  canonical sanitized local downstream-feedback artifact. It must not contain
  a path, URL, person, organization, project, quote, or source value.

The body cannot self-certify verification. `evidence_status: verified` counts
as verified user demand only while the issue also has the maintainer-controlled
`evidence:user-verified` label. A maintainer may apply that label only after
reviewing the canonical local artifact, confirming its digest matches the
receipt, and completing manual redaction. Remove the label when the claim,
metadata, or artifact changes.

Never put raw feedback, private conversations, direct quotes, private URLs,
identifiers, or unredacted logs in GitHub or provider prompts. Provider
dispatch may receive only the sanitized issue packet. The canonical local
downstream artifact remains product-learning evidence, not proof of market
validation.

Missing metadata leaves an issue in the ordinary ready-work bucket. Multiple
blocks, unknown keys, invalid enums, a malformed receipt, a verified body
without the verification label, or a label without matching valid metadata
must fail closed from user-evidence priority and surface a triage warning; the
issue is not rejected from ordinary ready work solely for that reason.

### Deterministic selection precedence

This contract defines precedence inside the selector safety boundary implemented
by issue #1567. The selector first enforces complete, fresh GitHub state; the
issue contract, milestone, verification lane, autonomy ceiling, ownership,
active branch, worktree, PR, lease, explicit file scope, overlap, and dependency gates. A
candidate must also be open, have exactly one `status:ready` label, and have no
unresolved `Blocked by` dependency. Only after every eligibility gate passes,
select the first non-empty bucket:

1. issues with `priority:p0`;
2. valid verified user evidence with `severity: blocker`;
3. valid verified user evidence with `priority:p1`;
4. all other eligible issues.

Within a bucket, sort by `priority:p0` through `priority:p3`, then by ascending
issue number. `status:blocked` is never a blocker bucket; it makes the issue
ineligible.

The repository owns the maintainer labels `evidence:user-verified`,
`work:product`, `work:factory`, and `work:mixed`. At initial successful lease
acquisition, snapshot exactly one `work:*` value into the immutable selection
receipt. Missing or conflicting work labels snapshot as `unclassified` and
surface a triage warning. Count a receipt in the work-mix metric only after its
issue reaches the normal finished/`status:done` boundary; retries and repeated
selections of the same issue receipt do not add observations. Report the 20
most recent counted receipts, or all available receipts when fewer than 20
exist, together with `sample_size`. Later GitHub label edits do not rewrite the
snapshot. The metric is informational only: it must not change selection,
define a target, or enforce a fixed percentage.

## Bug Fix Flow

```text
Issue -> reproduce -> failing regression test -> narrow fix -> regression suite -> docs/context update -> commit -> close issue
```

Bug-fix requirements:

- Reproduce before fixing when possible.
- Add a failing regression test before or with the fix.
- Keep the fix scoped to the defect.
- Run `scripts/regression.sh`.
- Run `scripts/feature_gate.sh --security` if the bug touches paths, subprocesses, YAML, dependencies, reports, proxy capture, credentials, or LLM data boundaries.
- Update `.context/changelog.md` for meaningful fixes.
- Update `.context/lessons-learned.md` only when the bug reveals a durable pitfall.

## Feature Slice Flow

```text
Feature issue -> branch -> checklist -> TDD -> implementation -> review -> regression suite -> docs/context update -> commit
```

Feature-slice requirements:

- One issue should map to one narrow branch.
- Use `docs/meta/FEATURE_DELIVERY_CHECKLIST.md`.
- Do not expand the command surface unless `docs/technical/COMMAND_CHEAT_SHEET.md` and product docs are updated first.
- Close the issue from the commit or PR with `Closes #<number>`.

## Starting A Session

For a first contribution, start with
[[docs/meta/GOOD_FIRST_ISSUE_WALKTHROUGH|GOOD_FIRST_ISSUE_WALKTHROUGH]].

Use the launcher from the repo root so every agent starts with the same issue context, worktree isolation, and guardrails:

```bash
scripts/start_issue.sh <issue-number> <type>/<short-kebab-description> --dry-run
scripts/start_issue.sh <issue-number> <type>/<short-kebab-description>
```

Examples:

```bash
scripts/start_issue.sh 3 feat/gate-injection --dry-run
scripts/start_issue.sh 3 feat/gate-injection
scripts/start_issue.sh 3 review/gate-injection --mode review
```

The launcher:

- Reads the issue title, URL, and state from GitHub.
- Creates `../Entroping-issue-<number>` unless `--dry-run` is used.
- Creates the requested branch from `main`.
- Refuses branch names that already exist locally or on `origin`.
- Saves a prompt under `.entroping/session-prompts/` in the worktree.
- Best-effort moves the issue to `status:in-progress`, adds missing issues to
  the GitHub Project board, and moves the project item to `In Progress`.
  Project item lookup is retried briefly after add because GitHub Project
  updates can be eventually consistent. If GitHub Project GraphQL quota is
  exhausted or below `ENTROPING_PROJECT_GRAPHQL_MIN_REMAINING` (default `50`),
  the launcher skips only the Project-board update and keeps the worktree
  creation flow intact.

Do not use this script to bypass planning. The generated prompt still requires `docs/meta/FEATURE_DELIVERY_CHECKLIST.md`, tests, regression checks, security review where relevant, and docs/context updates before merge.

## Finishing A Session

After the issue PR is merged and CI is green, use the finish script from a
separate checkout so local cleanup follows the same deterministic checks every
time:

```bash
scripts/finish_issue.sh <issue-number> --dry-run
scripts/finish_issue.sh <issue-number>
```

The finish script:

- Reads the closed issue and its closing pull request from GitHub.
- Verifies the pull request is merged and all reported checks passed.
- Verifies the issue worktree path belongs to this repository.
- Refuses to remove dirty or branch-mismatched worktrees.
- Removes the local issue worktree and deletes squash-merged local branches only
  after those checks pass.
- Best-effort removes active status labels, adds missing issues to the GitHub
  Project board, and moves the project item to `Done`.
  Project item lookup is retried briefly after add because GitHub Project
  updates can be eventually consistent. If GitHub Project GraphQL quota is
  exhausted or below `ENTROPING_PROJECT_GRAPHQL_MIN_REMAINING` (default `50`),
  the finish script skips only the Project-board update after verified local
  cleanup.

Use `--dry-run` first when cleaning up a batch of sessions.

## Backlog Health

Before starting or ending a marathon, check that open issues still have the
minimum labels and milestone context needed for multi-session handoff:

```bash
python scripts/backlog_health.py
```

The script shells out to `gh issue list` by default. For reviews or tests, pass
a fixture exported from GitHub:

```bash
python scripts/backlog_health.py --input /path/to/issues.json
```

Open issues should have at least one `type:*`, one `priority:*`, one
`status:*`, and a milestone. The script is intentionally about queue hygiene,
not product priority judgment.

## Obsidian Boundary

Do not duplicate every GitHub issue in Obsidian. Update Obsidian only for:

- Current phase and milestone progress in `docs/meta/PROJECT_PROGRESS.md`.
- Roadmap or scope changes in `docs/product/MVP_PLAN.md`.
- Architecture decisions in ADRs.
- Durable failures and fixes in `.context/lessons-learned.md`.
- User-facing behavior changes in user docs.

Run `scripts/doc_governance_check.sh` before merging changes that affect the
documentation control plane.
