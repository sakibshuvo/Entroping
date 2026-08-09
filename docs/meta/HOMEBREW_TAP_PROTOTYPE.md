---
title: Homebrew Tap Prototype
description: "Review the deferred Homebrew formula template and the package-index proof required before publication."
type: runbook
status: draft
tags:
  - distribution
  - packaging
  - homebrew
---

# Homebrew Tap Prototype

Prototype only. Do not publish a public tap until the PyPI alpha is proven by
the protected package-index workflow and a clean install smoke. The committed
prototype is a formula template, not a launch claim.

References:

- Homebrew Python formula guidance: https://docs.brew.sh/Python-for-Formula-Authors
- Homebrew formula cookbook: https://docs.brew.sh/Formula-Cookbook
- Entroping package-index runbook: PYPI_RELEASE_RUNBOOK.md

## Decision

The Homebrew tap should install from the PyPI sdist after the first package-index
alpha is stable. Do not install directly from an editable checkout, do not use
package-index credentials, and do not wrap `uv tool install` inside the formula.

Hurl is a required formula dependency because Entroping's deterministic executor
is the external Hurl binary. Hurl is not bundled into the Python package or the
formula.

mitmproxy, Graphviz, Studio, and AI extras stay out of the default formula.
Those features remain optional install paths until their onboarding value
justifies extra Homebrew dependencies or separate formula variants.

## Prototype Formula

The prototype template lives at:

```text
packaging/homebrew/Formula/entroping.rb.template
```

Before copying it into a tap, replace:

- `REPLACE_WITH_PYPI_SDIST_URL` with the PyPI sdist URL for the alpha.
- `REPLACE_WITH_PYPI_SDIST_SHA256` with the sdist SHA-256.
- Missing Python dependency `resource` stanzas generated from the published
  package metadata.

Generate or refresh resources from the tap checkout:

```bash
brew update-python-resources entroping
```

Review the generated resources before committing them. The formula must remain
small enough to install the default CLI, run `entroping doctor`, and execute
Hurl-backed tests without pulling in optional capture, rendering, Studio, or
model-provider dependency trees.

## Local Tap Smoke

Use a private local tap first:

```bash
brew tap-new sakibshuvo/entroping-local
cp packaging/homebrew/Formula/entroping.rb.template \
  "$(brew --repository sakibshuvo/entroping-local)/Formula/entroping.rb"
```

After replacing the PyPI URL, checksum, and resources, run:

```bash
HOMEBREW_NO_INSTALL_FROM_API=1 brew audit --strict --formula entroping
HOMEBREW_NO_INSTALL_FROM_API=1 brew install --build-from-source --verbose entroping
brew test entroping
entroping doctor
scripts/demo.sh
```

`scripts/demo.sh` remains the checkout smoke path. It starts the local checkout
fixture, generates Hurl tests, runs QAnstitution gates, and emits reports. Use it
from an Entroping source checkout after the formula install smoke proves the CLI
entry point and Hurl discovery.

## Public Tap Launch Gate

Do not publish or announce the tap until all of these are true:

- The PyPI alpha package has been uploaded through Trusted Publishing.
- Fresh install from PyPI starts the `entroping` console script.
- The local tap formula passes `brew audit --strict --formula`.
- The local tap formula passes `brew install --build-from-source`.
- `brew test entroping`, `entroping doctor`, and `scripts/demo.sh` pass on a
  clean macOS machine.
- The public README and install smoke matrix are updated in the same PR that
  promotes the tap from prototype to supported install path.
