"""Filesystem-backed local OpenAPI document loading."""

from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse

import yaml


class OpenApiLoadError(ValueError):
    """Raised when a local OpenAPI document cannot be loaded safely."""


def load_openapi_document(path: str | Path) -> Mapping[str, object]:
    """Load a local OpenAPI YAML or JSON file as a string-keyed mapping."""

    raw_path = str(path).strip()
    parsed = urlparse(raw_path)
    if parsed.scheme in {"http", "https"}:
        msg = f"Remote OpenAPI specs are not supported yet: {raw_path}"
        raise OpenApiLoadError(msg)
    if parsed.scheme:
        msg = f"Unsupported OpenAPI spec scheme {parsed.scheme!r}: {raw_path}"
        raise OpenApiLoadError(msg)

    candidate = Path(raw_path).expanduser()
    if candidate.is_symlink():
        msg = f"Refusing to load symlinked OpenAPI spec: {candidate}"
        raise OpenApiLoadError(msg)

    resolved = candidate.resolve()
    if not resolved.is_file():
        msg = f"OpenAPI spec file not found: {resolved}"
        raise OpenApiLoadError(msg)

    try:
        with resolved.open(encoding="utf-8") as handle:
            loaded: object = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        msg = f"Invalid OpenAPI YAML in {resolved}: {exc}"
        raise OpenApiLoadError(msg) from exc
    except OSError as exc:
        msg = f"Could not read OpenAPI spec {resolved}: {exc}"
        raise OpenApiLoadError(msg) from exc

    if loaded is None:
        loaded = {}
    if not isinstance(loaded, Mapping):
        msg = f"OpenAPI spec must contain a YAML mapping: {resolved}"
        raise OpenApiLoadError(msg)

    document: dict[str, object] = {}
    for key, value in loaded.items():
        if not isinstance(key, str):
            msg = f"OpenAPI spec keys must be strings in {resolved}"
            raise OpenApiLoadError(msg)
        document[key] = value
    return document
