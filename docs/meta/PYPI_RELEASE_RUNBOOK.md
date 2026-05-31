---
title: PyPI Release Runbook
type: runbook
status: draft
tags:
  - release
  - packaging
  - pypi
  - testpypi
  - trusted-publishing
---

# PyPI Release Runbook

This runbook defines the package-index path for Entroping before the first
TestPyPI or PyPI publish. It is intentionally not an active publishing workflow.
The current alpha remains source-distributed until a maintainer explicitly runs
and reviews this process.

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

## Preflight

Run these from a clean `main` checkout before any package-index attempt:

```bash
git status --short
git log -1 --oneline
scripts/release_check.sh --require-live-demo
scripts/package_check.sh
uv build
uvx twine check dist/*
```

`scripts/package_check.sh` already removes `dist/`, runs `uv build`, and checks
wheel/sdist metadata. The extra `uvx twine check dist/*` step validates package
metadata and README rendering with the upload toolchain before a registry sees
the artifacts.

Do not publish if:

- `main` CI is red or still running.
- `scripts/audit_quality.sh` is below the 100 percent coverage gate.
- The release checklist or README claims features that are not implemented.
- Any local env files, `.entroping/`, reports, package-index credentials, or
  generated Obsidian/Graphify state appear in `git status --short`.

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
3. Create the GitHub environment `testpypi` with required reviewers.
4. Add a reviewed publishing workflow only when ready to test the publish path.

Future workflow shape:

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
      - uses: astral-sh/setup-uv@v8.1.0
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
      - uses: actions/download-artifact@v7
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
2. Create the GitHub environment `pypi` with required reviewers.
3. Extend the reviewed workflow with a `publish-pypi` job that mirrors the
   TestPyPI job but omits `repository-url`.
4. Publish only from the reviewed release commit, never from a dirty local tree.

Future PyPI publish job:

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
    - uses: actions/download-artifact@v7
      with:
        name: python-distributions
        path: dist/
    - name: Publish package distributions to PyPI
      uses: pypa/gh-action-pypi-publish@release/v1
```

The PyPA action is expected to produce PyPI attestations automatically for
Trusted Publishing flows. Keep the build job unprivileged and the publish job
small so the OIDC identity is exposed to as little code as possible.

## Rollback And Yank Notes

Package-index releases are immutable. If a version is published with a bad file,
do not try to overwrite it.

Preferred response order:

1. If the package is unusable, incompatible with its own claim, or vulnerable,
   Yank the release in PyPI/TestPyPI and provide a reason.
2. Publish a new fixed version.
3. Update GitHub release notes and `docs/meta/PROJECT_PROGRESS.md` with the
   correction.
4. Open a GitHub issue for the root cause and add a regression test or release
   checklist item before the next publish.

Deletion is a last resort. Yanking is the normal non-destructive rollback path
because downstream users can still diagnose what happened while installers avoid
the yanked version in ordinary resolution.

## Open Decisions Before Activation

- Choose whether the first PyPI upload is `0.2.0a1` or a later alpha.
- Decide whether the GitHub release tag should switch from `vX.Y.Z-alpha` to
  PEP 440-like `vX.Y.ZaN` for package-index releases.
- Add the inactive workflow only after the TestPyPI trusted publisher and
  GitHub environment protection are configured.
- Decide whether to attach package artifacts to GitHub releases before or after
  TestPyPI smoke succeeds.
