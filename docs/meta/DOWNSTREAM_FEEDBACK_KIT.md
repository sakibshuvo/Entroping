---
title: Downstream Feedback Kit
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

```markdown
## Entroping Downstream Feedback

- Project type:
- Install path:
- Entroping version or commit:
- Operating system:
- Python version:
- Hurl version:
- Install command used:
- Entroping command used:
- Success or failure:
- Time to first useful result:
- Friction:
- What was confusing:
- What worked well:
- Sanitized logs:
- Suggested next fix:
```

`command used` can be the exact `entroping ...` invocation, the install command,
or both. `success or failure` should say whether the user reached a useful
`entroping doctor`, `entroping run`, report artifact, or understandable error.
`friction` should capture setup confusion, docs gaps, missing dependency
guidance, Hurl installation problems, unclear errors, or workflow mismatch.
Keep sanitized logs short and focused on the Entroping command output.

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

One good report can reduce the real-user-feedback blocker, but it does not
replace package-index proof, compatibility discipline, repeated release
evidence, security review, or full regression coverage. Treat downstream
feedback as product evidence, not as a release gate bypass.
