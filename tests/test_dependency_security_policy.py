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


def test_locked_python_security_baseline_uses_patched_compatible_versions() -> None:
    policy = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((_REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))

    overrides = policy["tool"]["uv"]["override-dependencies"]
    locked_versions = {
        package["name"]: package["version"] for package in lock["package"]
    }

    assert "cryptography>=50.0.0" in overrides
    assert "h2>=4.4.1" in overrides
    assert "pyopenssl>=26.4.0" in overrides
    assert _version_tuple(locked_versions["cryptography"]) >= (50, 0, 0)
    assert locked_versions["h2"] == "4.4.1"
    assert _version_tuple(locked_versions["pyopenssl"]) >= (26, 4, 0)
    assert locked_versions["aiohttp"] == "3.14.3"


def _version_tuple(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    return int(parts[0]), int(parts[1]), int(parts[2])
