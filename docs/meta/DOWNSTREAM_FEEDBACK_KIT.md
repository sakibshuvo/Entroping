---
title: Downstream Feedback Kit
description: "Collect reproducible feedback from a real external adopter without confusing local smoke with user proof."
type: runbook
status: active
tags:
  - stable-core
  - downstream
  - adoption
  - feedback
---

# Downstream Feedback Kit

Stable-core readiness needs real downstream user feedback from a project outside
this repository. The local downstream smoke harness is useful, but
maintainer-controlled local smoke is not real downstream user feedback.

Use this kit when a friend, early adopter, contributor, or another repository
tries Entroping and sends evidence back for review.

## Feedback Template

For every downstream trial, fill each section that applies. If a category has no
evidence, mark it *Not tested* rather than leaving it blank. This template maps
directly to the stable-core blockers tracked in #306 and #308.

```markdown
## Entroping Downstream Feedback

### Install Path
- Install method (source wheel / uv tool / pip / git clone):
- Entroping version or commit:
- Operating system and version:
- Python version:
- Hurl version:
- Install command used:
- Install success (yes / partial / no):
- Install friction (missing deps, docs gap, permission issue):

### CLI Compatibility
- First command attempted:
- Help output behavior (expected / unexpected):
- Command discovered from docs, --help, or trial:
- Compatibility concern (none / minor / blocks alpha):

### Deterministic Hurl Behavior
- Example Hurl file used (path or brief description):
- Command: entroping run ...
- Output matches expectation (yes / no):
- If not, what diverged (timing, error, missing report, unclear output):

### Docs Gaps
- Docs read before trying:
- Docs gap encountered:
- Search term that did not lead to the right doc:
- Doc that would have saved time:

### Product Clarity
- Did the user understand what Entroping does before installing (yes / no):
- Did the README demo path work for them (yes / partial / no):
- Was the value clear after the first run (yes / no):
- Product improvement suggestion:

### Success / Failure Summary
- Overall outcome:
- Time to first useful result:
- Sanitized logs (sanitized logs only):
- Most painful step:
- Most pleasant surprise:
```

### Issue Mapping

| Template section | Relevant issue | Blocker status |
|-----------------|---------------|----------------|
| Install Path | #306 real downstream feedback | blocked |
| CLI Compatibility | #308 compatibility decision | blocked |
| Docs Gaps | #306, #308 | blocked |
| Product Clarity | #306 | blocked |

Every filled template that includes sanitized install evidence counts toward
#306. Compatibility concerns (or absence of them) count toward #308.

## Sanitization Rules

Do not include secrets, API keys, credentials, tokens, cookies, private URLs,
raw traffic, proprietary API payloads, customer data, private endpoint names,
internal hostnames, or unredacted request/response bodies.

Good evidence:

- The operating system and version, for example `macOS 15.5` or `Ubuntu 24.04`.
- Python version from `python --version`.
- Hurl version from `hurl --version`.
- Entroping install path, for example `uv tool install git+...` or local wheel.
- The command used, with private paths and project names generalized.
- Sanitized logs with secrets replaced by `[REDACTED]`.
- A short description of success or failure.

Bad evidence:

- Raw `.env` files.
- API responses copied from a company service.
- Authorization headers, cookies, bearer tokens, or session IDs.
- Screenshots or logs containing private repository names or private URLs.
- Full traffic captures.

## GitHub User-Evidence Metadata

After human review and manual redaction, a concrete friction issue may use the
closed contract in [[docs/meta/ISSUE_TRACKING|ISSUE_TRACKING]]:

```yaml
user_evidence:
  schema_version: entroping.user-evidence.v1
  evidence_status: verified
  affected_journey: first_run
  severity: blocker
  source_classification: design_partner
  verification_receipt: sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
```

Generate `verification_receipt` from the canonical sanitized local artifact,
then have a maintainer compare the digest before applying
`evidence:user-verified`. The label and valid metadata are both required;
neither is verified user demand alone. Internal observations are not user
evidence.

Never put raw feedback, private conversations, direct quotes, private URLs,
identifiers, or unredacted logs in GitHub or provider prompts. Provider
dispatch may receive only the sanitized issue packet. Keep the original source
private and complete manual review before provider dispatch.

## Review Workflow

1. Ask the downstream user to fill the template.
2. Review and redact the evidence before copying it into a GitHub issue,
   discussion, release note, or `docs/meta/release-evidence.json`.
3. Link the feedback to the stable-core blocker issue for real downstream user
   feedback.
4. Convert concrete failures or friction into normal GitHub issues.
5. Keep the original private conversation out of Git unless the user explicitly
   approved publication and the evidence is sanitized.

## Evidence Boundary

One good report can reduce the real downstream user feedback blocker, but it
does not replace package-index proof, the stable-core compatibility decision,
reviewed release-evidence ledger entries, security review, or full regression
coverage. Treat downstream feedback as product evidence, not as a release gate
bypass.
