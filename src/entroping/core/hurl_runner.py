"""Subprocess boundary for the external Hurl binary."""

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HurlBinaryStatus:
    """Resolved availability of the Hurl executable."""

    available: bool
    path: str | None


def discover_hurl(binary: str = "hurl") -> HurlBinaryStatus:
    """Find the Hurl binary without executing HTTP requests."""

    resolved = shutil.which(binary)
    return HurlBinaryStatus(available=resolved is not None, path=resolved)


def validate_hurl_path(path: Path) -> Path:
    """Resolve a Hurl file path and reject non-Hurl inputs."""

    resolved = path.expanduser().resolve()
    if resolved.suffix != ".hurl":
        msg = f"Expected a .hurl file, got: {resolved}"
        raise ValueError(msg)
    return resolved
