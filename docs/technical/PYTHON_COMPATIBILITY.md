---
title: Python Compatibility
description: "See the supported Python versions and the CI evidence for core and optional adapter boundaries."
type: technical
status: active
tags:
  - python
  - compatibility
  - ci
  - release
---

# Python Compatibility

Entroping Core supports Python 3.12 or 3.13 for the current alpha line.
CI proves Python 3.12 and 3.13 with the security regression suite, and the
optional-extras smoke lane proves the LiteLLM, mitmproxy, and Textual adapter
boundaries on both versions.

Python 3.12 remains the syntax and mypy floor. Ruff targets `py312`, mypy runs
with `python_version = "3.12"`, and application code must stay compatible with
the lowest supported runtime.

Entroping is not claimed for Python 3.14 until a compatibility issue adds CI
evidence and updates `pyproject.toml`, this document, and release docs.

Package metadata intentionally uses:

```toml
requires-python = ">=3.12,<3.14"
```

That cap is a release-truth boundary, not a prediction that Python 3.14 will be
incompatible. Remove or move the cap only after tests and optional dependency
smokes pass under the new runtime.
