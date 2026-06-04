---
title: GitHub Actions Starter
type: guide
status: active
tags:
  - github-actions
  - ci
  - onboarding
  - hurl
---

# GitHub Actions Starter

Use this when you want a downstream repository to gate pull requests with
Entroping without adopting the full Entroping development workflow.

Copy the starter workflow:

```bash
mkdir -p .github/workflows
cp examples/github-actions/entroping-ci.yml .github/workflows/entroping.yml
```

If you are copying from this repository page instead of a local checkout, copy
`examples/github-actions/entroping-ci.yml` into your repository as
`.github/workflows/entroping.yml`.

## Required Files

The downstream repository should already contain:

- `qanstitution.yaml` with the project policy and gates.
- `tests/**/*.hurl` with committed Hurl tests.
- `envs/ci.env` only if CI needs non-secret defaults such as `base_url`.

No GitHub secrets are required by the starter workflow. If a suite needs real
credentials, inject them as environment variables in a project-specific step and
keep them out of `qanstitution.yaml`, Hurl files, reports, and committed
`envs/*.env` files.

## What The Workflow Does

The starter workflow:

1. Runs on pull requests and pushes to `main`.
2. Uses read-only `contents` permission.
3. Installs Python 3.12 and `uv`.
4. Installs Hurl `8.0.1` after checking `HURL_SHA256`.
5. Installs Entroping from the alpha tag:

```bash
uv tool install git+https://github.com/sakibshuvo/Entroping.git@v0.1.1-alpha
```

6. Runs setup diagnostics:

```bash
entroping doctor
mkdir -p reports
entroping doctor --output json > reports/doctor-health.json
```

7. Runs the deterministic CI gate and writes JSON, JUnit, and HTML reports:

```bash
entroping run --ci --report json --report junit --report html
```

8. Emits GitHub Actions annotations from local Entroping reports.
9. Writes SARIF 2.1.0 under `reports/` for optional code-scanning upload.
10. Writes a provider-neutral Markdown review summary from local artifacts.
11. Uploads `reports/` as a GitHub Actions artifact.

## Common Variants

To use the latest GitHub source branch instead of the alpha tag, change the
install step to:

```bash
uv tool install git+https://github.com/sakibshuvo/Entroping.git
```

To use a committed CI environment file, change the run step to:

```bash
entroping run --env ci --ci --report json --report junit --report html
```

To run only a tagged suite:

```bash
entroping run --ci --tag smoke --report json --report junit --report html
```

To include story traceability findings as PR annotations after you have adopted
`# entroping: story_id=...` metadata, change the annotation step to:

```bash
entroping report github-annotations --traceability
```

To write SARIF for code scanning from the same local JUnit, drift, and optional
traceability findings, add:

```bash
entroping report sarif --traceability
```

To upload that SARIF file to GitHub code scanning, the workflow needs
`security-events: write` in `permissions`, and then an upload step such as:

```yaml
permissions:
  contents: read
  security-events: write

steps:
  - name: Write Entroping SARIF
    if: always()
    run: entroping report sarif --traceability

  - name: Upload Entroping SARIF
    if: always()
    uses: github/codeql-action/upload-sarif@v4
    with:
      sarif_file: reports/entroping.sarif
```

Use this only where code scanning is enabled and the workflow has the right
repository permissions. Keeping the default starter to `contents: read` is the
least-privilege path for teams that only need artifacts and annotations.

To publish provider-neutral Markdown that a GitHub Action, GitLab job, Buildkite
step, or CircleCI command can upload or post itself, add:

```bash
entroping report review-summary --traceability
```

## Expected Artifacts

The run writes the same report paths Entroping uses locally:

```text
reports/junit.xml
reports/run-latest.json
reports/run-latest.html
reports/entroping.sarif
reports/review-summary.md
.entroping/latest-run.json
```

The annotation step reads local reports and prints GitHub workflow-command
annotations to stdout. The SARIF step writes `reports/entroping.sarif` but does
not upload it to code scanning unless you add the optional upload step above.
The review-summary step writes provider-neutral Markdown under `reports/`.
The workflow uploads `reports/`. It does not upload
`.entroping/` because that directory is local runtime state and can contain
baselines or machine-local history.

## Hurl Checksum Updates

When bumping Hurl:

1. Update `HURL_VERSION`.
2. Download the matching Linux archive from the Hurl release page.
3. Compute the SHA-256 checksum locally.
4. Update `HURL_SHA256` in the same pull request.
5. Let CI prove the new archive and Entroping run path.
