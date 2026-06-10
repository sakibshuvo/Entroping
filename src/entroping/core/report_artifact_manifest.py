"""Deterministic manifest for local report artifacts."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from entroping.core.path_safety import first_symlink_path_component
from entroping.core.safe_write import SafeWriteError, safe_write_text

REPORT_ARTIFACT_MANIFEST_SCHEMA_VERSION: Final = "entroping.report-artifact-manifest.v1"

ReportArtifactKind = Literal[
    "run_json",
    "run_plan",
    "junit",
    "run_html",
    "drift_json",
    "agent_bundle",
    "sarif",
    "review_summary",
]

_DEFAULT_OUTPUT_PATH: Final = Path("reports") / "artifact-manifest.json"


@dataclass(frozen=True, slots=True)
class _ReportArtifactDefinition:
    kind: ReportArtifactKind
    path: Path
    schema_hint: str | None


_DEFAULT_REPORT_ARTIFACTS: Final = (
    _ReportArtifactDefinition(
        kind="run_json",
        path=Path("reports") / "run-latest.json",
        schema_hint=None,
    ),
    _ReportArtifactDefinition(
        kind="run_plan",
        path=Path("reports") / "run-plan.json",
        schema_hint=None,
    ),
    _ReportArtifactDefinition(
        kind="junit",
        path=Path("reports") / "junit.xml",
        schema_hint="junit.xml",
    ),
    _ReportArtifactDefinition(
        kind="run_html",
        path=Path("reports") / "run-latest.html",
        schema_hint="entroping.run-report.html",
    ),
    _ReportArtifactDefinition(
        kind="drift_json",
        path=Path("reports") / "drift.json",
        schema_hint=None,
    ),
    _ReportArtifactDefinition(
        kind="agent_bundle",
        path=Path("reports") / "agent-bundle.json",
        schema_hint=None,
    ),
    _ReportArtifactDefinition(
        kind="sarif",
        path=Path("reports") / "entroping.sarif",
        schema_hint=None,
    ),
    _ReportArtifactDefinition(
        kind="review_summary",
        path=Path("reports") / "review-summary.md",
        schema_hint="entroping.review-summary.md",
    ),
)


class ReportArtifactEntry(BaseModel):
    """One present local report artifact."""

    model_config = ConfigDict(extra="forbid")

    kind: ReportArtifactKind
    path: str
    schema_version: str | None
    size_bytes: int
    sha256: str


class ReportArtifactMissing(BaseModel):
    """One expected local report artifact that was not present."""

    model_config = ConfigDict(extra="forbid")

    kind: ReportArtifactKind
    path: str


class ReportArtifactManifestSummary(BaseModel):
    """Aggregate counts for a report artifact manifest."""

    model_config = ConfigDict(extra="forbid")

    total_expected: int
    total_present: int
    total_missing: int


class ReportArtifactManifest(BaseModel):
    """Machine-readable integrity evidence for local report artifacts."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.report-artifact-manifest.v1"] = (
        "entroping.report-artifact-manifest.v1"
    )
    summary: ReportArtifactManifestSummary
    artifacts: tuple[ReportArtifactEntry, ...]
    missing_artifacts: tuple[ReportArtifactMissing, ...]


class ReportArtifactManifestError(ValueError):
    """Raised when a report artifact manifest cannot be written safely."""


@dataclass(frozen=True, slots=True)
class ReportArtifactManifestResult:
    """Result of a successful report artifact manifest workflow."""

    output_path: Path
    manifest: ReportArtifactManifest


def write_report_artifact_manifest(
    *,
    project_root: Path,
    output_path: Path | None = None,
) -> ReportArtifactManifestResult:
    """Write checksum evidence for known local Entroping report artifacts."""

    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUT_PATH, root=root)
    artifacts: list[ReportArtifactEntry] = []
    missing_artifacts: list[ReportArtifactMissing] = []

    for definition in sorted(_DEFAULT_REPORT_ARTIFACTS, key=lambda item: item.path.as_posix()):
        resolved = _resolve_artifact_path(definition.path, root=root)
        display_path = _display_path(resolved, root=root)
        if not resolved.exists():
            missing_artifacts.append(
                ReportArtifactMissing(kind=definition.kind, path=display_path)
            )
            continue
        if not resolved.is_file():
            msg = f"report artifact path is not a file: {display_path}"
            raise ReportArtifactManifestError(msg)

        content = _read_artifact_bytes(resolved, artifact_path=display_path)
        artifacts.append(
            ReportArtifactEntry(
                kind=definition.kind,
                path=display_path,
                schema_version=_schema_version(
                    definition,
                    content,
                    artifact_path=display_path,
                ),
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
            )
        )

    manifest = ReportArtifactManifest(
        summary=ReportArtifactManifestSummary(
            total_expected=len(_DEFAULT_REPORT_ARTIFACTS),
            total_present=len(artifacts),
            total_missing=len(missing_artifacts),
        ),
        artifacts=tuple(artifacts),
        missing_artifacts=tuple(missing_artifacts),
    )

    try:
        safe_write_text(
            destination,
            json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            artifact="report artifact manifest",
            root=root,
        )
    except SafeWriteError as exc:
        raise ReportArtifactManifestError(str(exc)) from exc
    return ReportArtifactManifestResult(output_path=destination, manifest=manifest)


def _resolve_artifact_path(raw_path: Path, *, root: Path) -> Path:
    path = raw_path.expanduser()
    if path.is_absolute():
        msg = f"report artifact path must be project-relative: {raw_path}"
        raise ReportArtifactManifestError(msg)
    candidate = root / path
    _reject_symlink_path(candidate, root=root, artifact="report artifact")
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        msg = f"report artifact path must stay inside the project: {raw_path}"
        raise ReportArtifactManifestError(msg) from exc
    return resolved


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    path = raw_path.expanduser()
    if not path.is_absolute():
        path = root / path
    _reject_symlink_path(path, root=root, artifact="report artifact manifest output")
    resolved = path.resolve(strict=False)
    try:
        relative_parts = resolved.relative_to(root).parts
    except ValueError as exc:
        msg = f"report artifact manifest output path must stay inside the project: {raw_path}"
        raise ReportArtifactManifestError(msg) from exc
    if relative_parts and relative_parts[0] in {".entroping", "envs"}:
        msg = "report artifact manifest output must not be written into .entroping or envs"
        raise ReportArtifactManifestError(msg)
    return resolved


def _reject_symlink_path(path: Path, *, root: Path, artifact: str) -> None:
    try:
        symlink_path = first_symlink_path_component(path, root=root)
    except ValueError as exc:
        msg = f"{artifact} path must stay inside the project: {path}"
        raise ReportArtifactManifestError(msg) from exc
    if symlink_path is not None:
        msg = f"{artifact} path uses symlinked component: {symlink_path}"
        raise ReportArtifactManifestError(msg)


def _read_artifact_bytes(path: Path, *, artifact_path: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        msg = f"Could not read report artifact {artifact_path}: {exc}"
        raise ReportArtifactManifestError(msg) from exc


def _schema_version(
    definition: _ReportArtifactDefinition,
    content: bytes,
    *,
    artifact_path: str,
) -> str | None:
    if definition.kind == "sarif":
        return _sarif_schema_version(content, artifact_path=artifact_path)
    if definition.schema_hint is not None:
        return definition.schema_hint
    return _json_schema_version(content, artifact_path=artifact_path)


def _json_schema_version(content: bytes, *, artifact_path: str) -> str | None:
    document = _load_json_document(content, artifact_path=artifact_path)
    if not isinstance(document, dict):
        return None
    schema_version = document.get("schema_version")
    return schema_version if isinstance(schema_version, str) else None


def _sarif_schema_version(content: bytes, *, artifact_path: str) -> str | None:
    document = _load_json_document(content, artifact_path=artifact_path)
    if not isinstance(document, dict):
        return None
    version = document.get("version")
    return f"SARIF {version}" if isinstance(version, str) else None


def _load_json_document(content: bytes, *, artifact_path: str) -> object:
    try:
        return json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        msg = f"Could not read schema version from report artifact {artifact_path}: {exc}"
        raise ReportArtifactManifestError(msg) from exc


def _display_path(path: Path, *, root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
