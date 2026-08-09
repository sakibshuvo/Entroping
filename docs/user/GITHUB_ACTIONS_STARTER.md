---
title: GitHub Actions Starter
description: "Gate downstream pull requests with the reviewed Entroping GitHub Actions workflow and pinned Hurl runtime."
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

Install the reviewed starter during project setup:

```bash
entroping init --github-actions
```

For the smallest local skeleton plus the CI starter:

```bash
entroping init --minimal --github-actions
```

The command writes `.github/workflows/entroping.yml` and refuses to overwrite an
existing workflow. If that file already exists, review it manually and copy the
starter only after deciding how to merge the workflows.

You can still copy the starter manually from a source checkout:

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
5. Installs Entroping from `ENTROPING_INSTALL_SPEC`, which defaults to the
   latest GitHub source branch:

```bash
uv tool install "${ENTROPING_INSTALL_SPEC}"
```

6. Runs setup diagnostics:

```bash
entroping doctor --ci
mkdir -p reports
entroping doctor --ci --output json > reports/doctor-health.json
```

7. Runs the deterministic CI gate and writes JSON, JUnit, and HTML reports:

```bash
entroping run --ci --report json --report junit --report html
```

8. Emits GitHub Actions annotations from local Entroping reports.
9. Writes SARIF 2.1.0 under `reports/` for optional code-scanning upload.
10. Writes a provider-neutral Markdown review summary from local artifacts.
11. Uploads `reports/` as a GitHub Actions artifact.

## Install Strategy

The reviewed starter defaults to the latest GitHub source branch:

```bash
ENTROPING_INSTALL_SPEC="git+https://github.com/sakibshuvo/Entroping.git"
```

This avoids new projects being silently pinned to an old alpha tag. If your
organization wants repeatability over latest-source updates, pin the workflow
explicitly:

```bash
ENTROPING_INSTALL_SPEC="git+https://github.com/sakibshuvo/Entroping.git@v0.1.1-alpha"
```

To migrate an existing starter workflow, replace a hardcoded install command
such as `uv tool install git+https://github.com/sakibshuvo/Entroping.git@v0.1.1-alpha`
with the `ENTROPING_INSTALL_SPEC` env value and
`uv tool install "${ENTROPING_INSTALL_SPEC}"`. Then choose whether the env
value should follow the latest source branch or pin a reviewed tag.

## Official Reusable Action Boundary

The current supported path is the generated starter workflow installed by
`entroping init --github-actions`. It is copyable, reviewable, and owned by the
downstream repository.

A future reusable `entroping/action` should live in a dedicated `entroping/action` repository
rather than this implementation repo. That keeps action release cadence,
marketplace metadata, and action-specific support separate from the Python
package while preserving this repo as the source for the CLI, tests, and starter
workflow.

The official action is blocked until package-index install proof exists. Before
PyPI/TestPyPI proof, a prototype may use a tagged GitHub release fallback only
when the tag is explicit and reviewable. The action contract should:

- install a released Entroping package, or an explicitly tagged fallback during
  prerelease validation;
- make setup explicit: the action installs or verifies Hurl with a pinned
  version and checksum/provenance check;
- run `entroping doctor --ci` before `entroping run --ci`;
- run `entroping run --ci` with local JSON, JUnit, and HTML reports;
- emit local annotations, SARIF, and review-summary artifacts from reports;
- ensure the action uploads `reports/` and does not upload `.entroping/` by
  default;
- must not call LLM providers, read model API keys, or run Architect commands;
- ensure default permissions remain `contents: read`.

Optional PR comment behavior must be opt-in. If enabled, it should require only
the narrow permission it needs, such as `pull-requests: write` for pull request
comments. The default action path must not require broad repository write
permissions, hosted-service coupling, or model-provider credentials.

Do not replace the generated starter workflow with the reusable action until the
action is proven on real downstream repositories. The generated starter remains
the transparent baseline for teams that want to inspect or customize every CI
step.

## Common Variants

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

## PR Evidence Card Example

Use `examples/github-actions/pr-evidence-card.yml` when you want a PR-only
workflow that writes the local PR evidence card without changing pull request
state. The example keeps `permissions: contents: read`.
It does not comment on or mutate pull requests.

## PR Evidence Card workflow walkthrough

The example workflow follows this exact sequence:

1. **Checkout and tool setup**
   - `actions/checkout@v6`
   - `actions/setup-python@v6`
   - `astral-sh/setup-uv@v8.2.0`

2. **Install pinned Hurl and Entroping**
   - Linux Hurl archive pinned with `HURL_VERSION` + `HURL_SHA256`
   - `uv tool install "${ENTROPING_INSTALL_SPEC}"` with reviewed branch/tag

3. **Gate preflight**
   - `entroping doctor --ci`
   - Persist JSON doctor evidence to `reports/doctor-health.json`

4. **Deterministic enforcement run**
   - `entroping run --ci --report json --report junit --report html`

5. **Evidence card generation (always-on)**
   - Generate runtime-card, artifact-manifest, evidence-index, and pr-evidence-card
   - Append markdown card to `GITHUB_STEP_SUMMARY`

6. **Artifact upload**
   - Upload only `reports/` paths that this workflow owns

The `if: always()` guard keeps post-run evidence output available for failure
forensics when the run gate fails.

The PR evidence card should run after local run and report artifacts exist. At
minimum, run the deterministic gate with report output:

```bash
entroping run --ci --report json --report junit --report html
```

Then write the fixed optional inputs that make the card more useful:

```bash
entroping report runtime-card --output json
entroping report artifact-manifest
entroping report evidence-index --output json
entroping report pr-evidence-card
entroping report pr-evidence-card --output json
```

The example appends `reports/pr-evidence-card.md` to the GitHub job summary and
uploads `reports/pr-evidence-card.md`, `reports/pr-evidence-card.json`,
`reports/runtime-card.json`, `reports/evidence-index.json`, and
`reports/artifact-manifest.json` as a workflow artifact. Missing optional
evidence remains local PR evidence-card state; the workflow does not call
GitHub APIs, post comments, publish packages, call model providers, upload
hosted evidence, or upload `.entroping/`.

## Expected Artifacts

The workflow writes the same report paths Entroping uses locally:

```text
reports/doctor-health.json
reports/junit.xml
reports/run-latest.json
reports/run-latest.html
reports/entroping.sarif
reports/review-summary.md
.entroping/latest-run.json
```

The separate PR evidence-card example also writes:

```text
reports/pr-evidence-card.md
reports/pr-evidence-card.json
reports/runtime-card.json
reports/evidence-index.json
reports/artifact-manifest.json
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
