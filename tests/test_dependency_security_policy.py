"""Dependency security policy regressions."""

from __future__ import annotations

import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_proxy_extra_uses_patched_msgpack_override_for_mitmproxy() -> None:
    payload = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    optional_dependencies = payload["project"]["optional-dependencies"]
    uv_tooling = payload["tool"]["uv"]

    assert optional_dependencies["proxy"] == ["mitmproxy>=12.2.3"]
    assert "msgpack>=1.2.1" in uv_tooling["override-dependencies"]
