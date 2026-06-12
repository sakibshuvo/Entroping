"""Load committed run suite manifests."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yaml
from pydantic import ValidationError

from entroping.core.path_safety import first_symlink_path_component
from entroping.models.run_suite import RunSuiteManifest


class RunSuiteManifestError(ValueError):
    """Raised when a run suite manifest cannot be loaded safely."""


@dataclass(frozen=True, slots=True)
class LoadedRunSuite:
    """Resolved run suite inputs for the deterministic workflow."""

    name: str
    environment: str | None
    tag_filters: tuple[str, ...]
    report_formats: tuple[str, ...]
    parallel: bool
    fail_fast: bool
    drift_check: bool
    protected: bool
    safety: str | None
    discovery_roots: tuple[Path, ...]


def load_run_suite_manifest(*, project_root: Path, suite_name: str) -> LoadedRunSuite:
    """Load and validate ``suites/<suite_name>.yaml`` from a project root."""

    root = project_root.expanduser().resolve()
    safe_name = _safe_suite_name(suite_name)
    manifest_path = root / "suites" / f"{safe_name}.yaml"
    _validate_manifest_path(manifest_path, root=root)
    document = _read_yaml_mapping(manifest_path)
    suite = _validate_manifest(document, manifest_path)
    if suite.name is not None and suite.name != safe_name:
        msg = f"Run suite manifest name {suite.name!r} must match requested suite {safe_name!r}"
        raise RunSuiteManifestError(msg)

    return LoadedRunSuite(
        name=safe_name,
        environment=suite.env,
        tag_filters=tuple(sorted(set(suite.tags))),
        report_formats=tuple(dict.fromkeys(suite.reports)),
        parallel=suite.parallel,
        fail_fast=suite.fail_fast,
        drift_check=suite.drift_check,
        protected=suite.protected,
        safety=suite.safety,
        discovery_roots=_resolve_suite_paths(root=root, path_globs=tuple(suite.paths)),
    )


def _safe_suite_name(value: str) -> str:
    name = value.strip()
    if (
        not name
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
    ):
        msg = f"Run suite name is not safe: {value!r}"
        raise RunSuiteManifestError(msg)
    return name


def _validate_manifest_path(path: Path, *, root: Path) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        msg = f"Run suite manifest must stay under project root {root}: {path}"
        raise RunSuiteManifestError(msg) from exc
    symlink_component = first_symlink_path_component(path, root=root)
    if symlink_component is not None:
        msg = f"Run suite manifest must not use symlinks: {symlink_component}"
        raise RunSuiteManifestError(msg)
    if not path.is_file():
        msg = f"Run suite manifest not found: {path}"
        raise RunSuiteManifestError(msg)


def _read_yaml_mapping(path: Path) -> dict[str, object]:
    try:
        loaded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        msg = f"Invalid YAML in run suite manifest {path}: {exc}"
        raise RunSuiteManifestError(msg) from exc
    except OSError as exc:
        msg = f"Could not read run suite manifest {path}: {exc}"
        raise RunSuiteManifestError(msg) from exc
    if not isinstance(loaded, Mapping):
        msg = f"Run suite manifest must contain a YAML mapping: {path}"
        raise RunSuiteManifestError(msg)
    document: dict[str, object] = {}
    for key, value in loaded.items():
        if not isinstance(key, str):
            msg = f"Run suite manifest keys must be strings in {path}"
            raise RunSuiteManifestError(msg)
        document[key] = value
    return document


def _validate_manifest(document: Mapping[str, object], path: Path) -> RunSuiteManifest:
    try:
        return RunSuiteManifest.model_validate(document)
    except ValidationError as exc:
        msg = f"Invalid run suite manifest in {path}: {exc}"
        raise RunSuiteManifestError(msg) from exc


def _resolve_suite_paths(*, root: Path, path_globs: tuple[str, ...]) -> tuple[Path, ...]:
    if not path_globs:
        return ((root / "tests").resolve(),)

    resolved: set[Path] = set()
    for path_glob in path_globs:
        normalized = _safe_suite_path(path_glob)
        try:
            matches = sorted(root.glob(normalized), key=lambda path: path.as_posix())
        except ValueError as exc:
            msg = f"Invalid run suite path glob {path_glob!r}: {exc}"
            raise RunSuiteManifestError(msg) from exc
        for match in matches:
            resolved_match = match.resolve()
            try:
                resolved_match.relative_to(root)
            except ValueError as exc:
                msg = f"Run suite path must stay inside project root {root}: {path_glob}"
                raise RunSuiteManifestError(msg) from exc
            symlink_component = first_symlink_path_component(match, root=root)
            if symlink_component is not None:
                msg = f"Run suite path must not use symlinks: {symlink_component}"
                raise RunSuiteManifestError(msg)
            if resolved_match.is_file() and resolved_match.suffix != ".hurl":
                msg = f"Run suite path must point to .hurl files or directories: {path_glob}"
                raise RunSuiteManifestError(msg)
            resolved.add(resolved_match)
    return tuple(sorted(resolved, key=lambda path: path.as_posix()))


def _safe_suite_path(value: str) -> str:
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        msg = f"Run suite path must not contain control characters: {value!r}"
        raise RunSuiteManifestError(msg)
    parsed = urlparse(value)
    if parsed.scheme:
        msg = f"Run suite path must be a local relative path: {value}"
        raise RunSuiteManifestError(msg)
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() in {"", "."}:
        msg = f"Run suite path must stay inside the project root: {value}"
        raise RunSuiteManifestError(msg)
    return path.as_posix()
