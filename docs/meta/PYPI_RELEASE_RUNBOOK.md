---
title: PyPI Release Runbook
type: runbook
status: active
tags:
  - release
  - packaging
  - pypi
  - testpypi
  - trusted-publishing
---

# PyPI Release Runbook

This runbook defines the package-index path for Entroping. The repository now
has an active protected manual workflow at
`.github/workflows/publish-python-package.yml`. The current alpha remains
source-distributed until a maintainer explicitly runs and reviews this process.

References:

- PyPI Trusted Publishing: https://docs.pypi.org/trusted-publishers/
- Publishing with a Trusted Publisher: https://docs.pypi.org/trusted-publishers/using-a-publisher/
- Adding a Trusted Publisher: https://docs.pypi.org/trusted-publishers/adding-a-publisher/
- PyPI attestations: https://docs.pypi.org/attestations/producing-attestations/
- PyPI yanking: https://docs.pypi.org/project-management/yanking/
- PEP 440 version scheme: https://packaging.python.org/en/latest/specifications/version-specifiers/

## Policy

TestPyPI first.

Use Trusted Publishing through GitHub Actions and PyPI OIDC. Do not use
long-lived package-index tokens for the default release path.

No PyPI or TestPyPI tokens in GitHub secrets. No `.pypirc` in Git. No package
index credentials, signing keys, or emergency tokens in repo files, docs,
examples, workflow inputs, or context packs.

Publishing must use separate GitHub environments:

- `testpypi` for TestPyPI dry runs.
- `pypi` for real PyPI publishes.

Both environments should have GitHub environment required reviewers before they
are allowed to publish. The publish job should request `id-token: write` only at
the job level and only in the job that uploads already-built distributions.

Active protected manual workflow:

- `.github/workflows/publish-python-package.yml` is manual-only through
  `workflow_dispatch`.
- `testpypi` and `pypi` GitHub environments require reviewer approval and are
  limited to the `main` branch.
- The build job has only `contents: read` and uploads `dist/` as a short-lived
  workflow artifact.
- The publish jobs request `id-token: write` only after the package artifacts
  are built and reviewed through the workflow.
- The workflow still depends on matching Trusted Publisher configuration in
  TestPyPI and PyPI before either package index will accept an upload.

## Preflight

Run these from a clean `main` checkout before any package-index attempt:

```bash
git status --short
git log -1 --oneline
scripts/release_check.sh --require-live-demo
uv run python scripts/package_index_readiness.py --strict
scripts/package_check.sh
uv run python scripts/local_wheel_install_smoke.py --skip-build
uv build
uvx twine check dist/*
```

`scripts/package_check.sh` already removes `dist/`, runs `uv build`, and checks
wheel/sdist metadata. The extra `uvx twine check dist/*` step validates package
metadata and README rendering with the upload toolchain before a registry sees
the artifacts.

`scripts/package_index_readiness.py --strict` validates the repo-owned
publishing guardrails: manual-only workflow dispatch, token-free Trusted
Publishing shape, job-level OIDC permissions, TestPyPI/PyPI environment names,
the source-distribution version guard, and the release-evidence package-index
boundary. It does not call TestPyPI or PyPI, inspect secrets, or prove that
package-index Trusted Publisher records exist.

`scripts/local_wheel_install_smoke.py --skip-build` must pass after
`scripts/package_check.sh`. It installs the locally built wheel into a temporary
venv using `uv pip install --offline` and runs the installed public CLI from a
temporary project, proving the wheel path without PyPI, TestPyPI, or network
registry access.

Do not publish if:

- `main` CI is red or still running.
- `scripts/audit_quality.sh` is below the 100 percent coverage gate.
- The release checklist or README claims features that are not implemented.
- Any local env files, `.entroping/`, reports, package-index credentials, or
  generated Obsidian or local context state appear in `git status --short`.

## Versioning And Prerelease Naming

PyPI versions follow PEP 440. GitHub release labels can say "alpha", but package
index versions should use PEP 440 pre-release spelling when the package is not
intended to be treated as a final release by installers.

Preferred first package-index alpha:

```toml
version = "0.2.0a1"
```

Preferred matching Git tag:

```text
v0.2.0a1
```

Do not upload the current `0.1.1` package version to PyPI as an alpha without an
explicit release decision. `0.1.1` is a final public version according to normal
installer ordering, even if the project classifier says alpha. Existing
`v0.1.1-alpha` GitHub release naming is acceptable for source distribution but
should not be copied as a PyPI version string.

For repeated package-index tests, increment the pre-release version:

```text
0.2.0a1 -> 0.2.0a2 -> 0.2.0a3
```

Never reuse a published version. Package-index releases are immutable.

## TestPyPI First

Use TestPyPI to prove the workflow, metadata, install command, and CLI entry
point before touching PyPI.

1. Create or confirm a TestPyPI project for `entroping`.
2. Configure a TestPyPI Trusted Publisher for:
   - owner: `sakibshuvo`
   - repository: `Entroping`
   - workflow filename: `.github/workflows/publish-python-package.yml`
   - environment: `testpypi`
3. Confirm the GitHub environment `testpypi` still has required reviewers and a
   `main` deployment branch policy.
4. Run the reviewed manual publishing workflow with `target: testpypi`.

Active workflow shape:

```yaml
name: Publish Python package

on:
  workflow_dispatch:
    inputs:
      target:
        description: Package index target
        required: true
        type: choice
        options:
          - testpypi
          - pypi

permissions:
  contents: read

jobs:
  build-dist:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - uses: astral-sh/setup-uv@v8.2.0
      - run: uv sync --dev
      - run: scripts/regression.sh --security
      - run: scripts/package_check.sh
      - run: uvx twine check dist/*
      - uses: actions/upload-artifact@v7
        with:
          name: python-distributions
          path: dist/
          if-no-files-found: error

  publish-testpypi:
    if: github.event.inputs.target == 'testpypi'
    needs: build-dist
    runs-on: ubuntu-latest
    environment: testpypi
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/download-artifact@v8
        with:
          name: python-distributions
          path: dist/
      - name: Publish package distributions to TestPyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          repository-url: https://test.pypi.org/legacy/
```

After TestPyPI publish, install from TestPyPI in a fresh environment:

```bash
python -m venv /tmp/entroping-testpypi
/tmp/entroping-testpypi/bin/python -m pip install --upgrade pip
/tmp/entroping-testpypi/bin/python -m pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  entroping==0.2.0a1
/tmp/entroping-testpypi/bin/entroping --help
```

The `--extra-index-url` is needed because TestPyPI may not contain every runtime
dependency. Do not treat a TestPyPI upload as successful until the installed
`entroping` command starts from a clean virtual environment.

## PyPI Publish

Only proceed after TestPyPI proves the artifact and install path.

1. Configure a PyPI Trusted Publisher for:
   - owner: `sakibshuvo`
   - repository: `Entroping`
   - workflow filename: `.github/workflows/publish-python-package.yml`
   - environment: `pypi`
2. Confirm the GitHub environment `pypi` still has required reviewers and a
   `main` deployment branch policy.
3. Publish only from the reviewed release commit, never from a dirty local tree.

Active PyPI publish job:

```yaml
publish-pypi:
  if: github.event.inputs.target == 'pypi'
  needs: build-dist
  runs-on: ubuntu-latest
  environment: pypi
  permissions:
    contents: read
    id-token: write
  steps:
    - uses: actions/download-artifact@v8
      with:
        name: python-distributions
        path: dist/
    - name: Publish package distributions to PyPI
      uses: pypa/gh-action-pypi-publish@release/v1
```

The PyPA action is expected to produce PyPI attestations automatically for
Trusted Publishing flows. Keep the build job unprivileged and the publish job
small so the OIDC identity is exposed to as little code as possible.

## Rollback And Yank Notes, Abort, and Failure Modes

Package-index releases are immutable. Once a version is published to TestPyPI or
PyPI, its artifact content cannot be changed or deleted in a way that downstream
installers can silently ignore. This section defines the abort path before
publish, failure recovery after publish, and the limits of rollback on each index.

Related issues: #303, #304, #305, #587.

### Pre-Publish Abort

Before `workflow_dispatch` is approved or the publish job runs:

1. **Stop condition: any local gate fails.**
   If `scripts/package_index_readiness.py --strict` exits non-zero,
   `scripts/package_check.sh` fails, `scripts/local_wheel_install_smoke.py
   --skip-build` fails, `uvx twine check dist/*` fails, or `scripts/release_check.sh
   --require-live-demo` fails, abort immediately. Correct the failure and re-run
   all preflight checks from a clean `main` checkout before attempting publish
   again.

2. **Stop condition: dirty working tree.**
   If `git status --short` shows uncommitted changes (excluding `.entroping/`
   artifacts), abort. Only published commits should be uploaded to a package
   index.

3. **Stop condition: CI is red.**
   If the `main` branch CI is red, still running, or has not completed a full
   regression run for the commit being published, abort. Package publishes must
   carry CI evidence for the exact commit being released.

4. **Stop condition: environment reviewer blocks.**
   If the GitHub environment required reviewer rejects the workflow run, abort.
   Do not bypass the review gate. Record the rejection reason in the release
   evidence ledger and open a GitHub issue if the rejection reveals a product or
   process gap.

5. **Abort cleanup:** No package-index state was mutated. Reset the version string
   in `pyproject.toml` only if the abort was due to version choice. Otherwise,
   leave the source tree as-is for the next attempt.

### Failed TestPyPI Publish

If the TestPyPI publish job fails after `build-dist` succeeded:

- **Evidence to collect:** The workflow run URL, the failed step log, the
  `scripts/package_index_readiness.py --format json` output from the preflight.
- **Recovery:** TestPyPI failure does not block PyPI because the artifact was
  never uploaded. Fix the publish-job configuration error and re-attempt with
  the same or an incremented alpha version.
- **Version reuse constraint:** If the upload succeeded but the job reports
  failure (e.g., a post-upload validation step failed), the version is consumed
  on TestPyPI. Increment to the next alpha version before re-publishing.
- **What cannot be rolled back:** Published package files on TestPyPI. TestPyPI
  supports yanking (see [Yanking After Publish](#yanking-after-publish)) but
  does not support deletion through the web UI in the general case.

### Failed Install Smoke After TestPyPI Publish

If `entroping` was published to TestPyPI but the install smoke fails:

- **Evidence to collect:** The exact install command, Python version, platform,
  and error output. The wheel and sdist filenames that were published.
- **Root-cause checklist:**
  - Does the wheel contain the expected CLI entry point? Run `unzip -l
    dist/*.whl | grep entroping` locally on the build artifact.
  - Does the install command use the correct `--index-url` and
    `--extra-index-url`? TestPyPI may not carry transitive dependencies.
  - Is the published version string PEP 440-compliant and not already
    consumed by a final release?
  - Does `scripts/local_wheel_install_smoke.py --skip-build` pass on the
    same wheel locally? If yes, the issue is in the publish or install
    environment, not the artifact.
- **Recovery:** If the artifact is correct but install failed due to index
  resolution, fix the install instructions and retry. If the artifact is
  defective (missing entry point, wrong metadata, missing dependency), yank
  the version from TestPyPI and publish a corrected alpha.
- **What cannot be rolled back:** TestPyPI yanked releases remain in the
  index history and can be installed with an explicit `--yanked` flag.

### Failed PyPI Publish

If the PyPI publish job fails:

- **Evidence to collect:** Workflow run URL, failed step log, the TestPyPI
  smoke evidence from the previous step.
- **Recovery path when upload failed (job error, network timeout, OIDC
  rejection):** No PyPI state was mutated. Fix the configuration and
  re-attempt from the same commit.
- **Recovery path when upload succeeded but validation failed:** If `twine`
  or the PyPA action reported upload success but a post-validation step
  (e.g., a metadata check, attestation check) failed, the version is
  consumed on PyPI. Do not attempt to re-upload the same version.
  Increment the alpha version and re-publish.
- **PyPI-specific constraints:** PyPI does not permit version deletion after
  any external download has been recorded. Yanking is the supported path.
  PyPI yanked releases are hidden from normal resolution but remain
  visible in index history and can still be installed when users explicitly
  request that exact version.

### Post-Publish Docs Correction

After a publish that reached a package index:

1. **Release evidence ledger:** Update `docs/meta/release-evidence.json` with
   the published version, CI run URL, publish workflow run URL, install smoke
   evidence output, and the commit hash.
2. **GitHub release:** Create or update the GitHub release for the published
   tag. Link the package-index page and the install smoke evidence.
3. **ROADMAP.md and PROJECT_PROGRESS.md:** Update the stable-core blocker
   status for the relevant issue (#304 or #305) only when evidence is proven,
   not when publish was attempted.
4. **Correction after wrong-claim publish:** If a post-publish review finds
   that the package metadata, README, or project classifiers overclaim (e.g.,
   imply a stability level the project has not proven), correct the claim in
   `pyproject.toml`, increment the version, and publish a correction.
   Document the overclaim in a GitHub issue and add a release checklist or
   public-claims audit item before the next publish.

### Yanking After Publish

Yanking is the recommended non-destructive rollback for published releases.

- **When to yank:** The release is unusable, incompatible with its own public
  claims, contains a security vulnerability, or was published with incorrect
  metadata that misleads downstream installers.
- **Yank command (PyPA action or through the index UI):** Provide a yank
  reason. The reason is public and should be factual: "broken entry point",
  "incorrect dependency upper bound", "published wrong version string".
- **What yanking does not fix:** Yanking does not remove the artifact from
  the index, does not prevent users who already installed the version from
  continuing to use it, and does not withdraw the artifact from mirrors or
  caches.
- **After yanking:** Publish a new fixed version. Update the GitHub release
  notes to reference the yanked version and the fix. Add a regression test or
  release checklist item before the next publish.

### What Cannot Be Rolled Back

| Surface | Cannot be rolled back | Mitigation |
|---------|----------------------|------------|
| TestPyPI | Published package files | Yank + increment version |
| PyPI | Published package files, version strings | Yank + increment version |
| GitHub release tags | Published tags (rewriting causes clone conflicts) | Create a new release; deprecate old tag in release notes |
| Downstream caches | pip/uv/poetry caches, mirror indexes | Version increment is the only guaranteed path |
| Public claims in README/docs | `git push` of wrong claims | Force-push with extreme care only if zero external references exist; otherwise correct in a follow-up commit |

### After-Action Evidence Checklist

For every publish attempt (success or failure), record in the release evidence
ledger or the relevant issue:

- [ ] Preflight gates passed and their output captured.
- [ ] Workflow run URL and result (success/failure/cancelled).
- [ ] Install smoke result with environment details.
- [ ] Any yank action taken with reason and replacement version.
- [ ] GitHub release updated or annotated.
- [ ] `docs/meta/PROJECT_PROGRESS.md` updated if stable-core blocker status changed.
- [ ] Regression issue opened for any failure that required recovery.

## Open Decisions Before First Publish

- Choose whether the first PyPI upload is `0.2.0a1` or a later alpha.
- Decide whether the GitHub release tag should switch from `vX.Y.Z-alpha` to
  PEP 440-like `vX.Y.ZaN` for package-index releases.
- Configure the TestPyPI and PyPI Trusted Publishers in the package indexes
  before running the workflow against either target.
- Decide whether to attach package artifacts to GitHub releases before or after
  TestPyPI smoke succeeds.
