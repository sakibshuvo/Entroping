---
title: CI Provider Recipes
type: guide
status: active
tags:
  - ci
  - gitlab
  - buildkite
  - circleci
  - hurl
---

# CI Provider Recipes

GitHub Actions remains the only committed provider-specific template for now.
The reviewed, copyable workflow lives in
[GITHUB_ACTIONS_STARTER.md](GITHUB_ACTIONS_STARTER.md) and
`examples/github-actions/entroping-ci.yml`.

This page gives the portable command sequence for GitLab CI, Buildkite,
CircleCI, and other Linux CI runners. Native provider templates should be added
only after someone validates them in that provider's real runner environment;
untested native templates are not copied into `examples/`.

## Generic Shell Recipe

Use this sequence inside a Linux CI job that has `bash`, `curl`, `tar`,
`sha256sum`, and Python 3.12 available:

```bash
set -euo pipefail

HURL_VERSION="8.0.1"
HURL_SHA256="cac7c4670d69444db120edb21fe06c97ba8c80dcc52279957c8dd18f05fb0c06"
archive="hurl-${HURL_VERSION}-x86_64-unknown-linux-gnu.tar.gz"
base_url="https://github.com/Orange-OpenSource/hurl/releases/download/${HURL_VERSION}"

curl --fail --location --silent --show-error --output "/tmp/${archive}" \
  "${base_url}/${archive}"
test "${HURL_SHA256}" = "$(sha256sum "/tmp/${archive}" | awk '{print $1}')"
tar -xzf "/tmp/${archive}" -C /tmp
export PATH="/tmp/hurl-${HURL_VERSION}-x86_64-unknown-linux-gnu/bin:${PATH}"

curl --fail --location --silent --show-error \
  https://astral.sh/uv/install.sh | sh
export PATH="${HOME}/.local/bin:${PATH}"

uv tool install git+https://github.com/sakibshuvo/Entroping.git@v0.1.1-alpha
entroping doctor
entroping run --ci --report json --report junit --report html
entroping report review-summary
```

Upload `reports/` as the provider artifact directory. Keep `.entroping/` out of
artifacts unless you have reviewed the exact files being uploaded.

No provider secrets are required by Entroping itself. If your API tests need
real credentials, inject them through the CI provider's secret store and keep
them out of `qanstitution.yaml`, Hurl files, committed env files, and uploaded
reports.

## GitLab CI

Use the generic shell recipe in a Linux job with `artifacts: paths: [reports/]`.
GitLab can parse `reports/junit.xml` with `artifacts: reports: junit`, but only
after the Entroping command has written the JUnit report.

Do not commit a `.gitlab-ci.yml` template until it is exercised in GitLab
against a real downstream Entroping fixture.

## Buildkite

Use the generic shell recipe in a command step, then upload `reports/**/*` with
Buildkite artifacts. Keep Hurl installation and checksum verification in the
same step that runs Entroping so the path is deterministic.

Do not commit a Buildkite `pipeline.yml` template until it is exercised in
Buildkite against a real downstream Entroping fixture.

## CircleCI

Use a Python 3.12 Linux executor, run the generic shell recipe, store
`reports/` as artifacts, and store `reports/junit.xml` as test results if the
project wants native CircleCI test summaries.

Do not commit a CircleCI `config.yml` template until it is exercised in CircleCI
against a real downstream Entroping fixture.

## Template Promotion Gate

Promote a native provider template into `examples/` only when all of these are
true:

- a public or reviewer-accessible downstream fixture has run the template;
- Hurl is pinned and checksum-verified;
- Entroping is installed from a tag or reviewed source ref;
- `entroping doctor` runs before `entroping run`;
- `entroping run --ci --report json --report junit --report html` is the deterministic gate;
- `entroping report review-summary` writes provider-neutral Markdown from local artifacts;
- `reports/` is uploaded and `.entroping/` is not uploaded by default;
- provider secrets are optional and never required by Entroping itself.
