from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from entroping.core.bounded_read import BoundedReadError, read_text_bounded
from entroping.core.path_safety import first_symlink_path_component

AhaArtifactState = Literal["present", "missing", "invalid", "unsafe"]
_MAX_SCHEMA_READ_BYTES: Final = 256 * 1024


@dataclass(frozen=True, slots=True)
class AhaArtifactDefinition:
    key: str
    label: str
    path: Path
    missing_hint: str
    schema_expected: bool = False


@dataclass(frozen=True, slots=True)
class AhaArtifactIndexItem:
    key: str
    label: str
    state: AhaArtifactState
    path: Path
    schema_version: str | None = None
    hints: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AhaArtifactIndex:
    items: tuple[AhaArtifactIndexItem, ...]

    @property
    def has_errors(self) -> bool:
        return any(item.state in {"invalid", "unsafe"} for item in self.items)


_ARTIFACT_DEFINITIONS: Final[tuple[AhaArtifactDefinition, ...]] = (
    AhaArtifactDefinition(
        key="run-json",
        label="Run JSON",
        path=Path("reports") / "run-latest.json",
        missing_hint="Run entroping demo --project <path> or entroping run --report json.",
        schema_expected=True,
    ),
    AhaArtifactDefinition(
        key="run-html",
        label="Run HTML",
        path=Path("reports") / "run-latest.html",
        missing_hint="Run entroping demo --project <path> or entroping run --report html.",
    ),
    AhaArtifactDefinition(
        key="junit-xml",
        label="JUnit XML",
        path=Path("reports") / "junit.xml",
        missing_hint="Run entroping run --report junit.",
    ),
    AhaArtifactDefinition(
        key="runtime-card-json",
        label="Runtime card JSON",
        path=Path("reports") / "runtime-card.json",
        missing_hint="Run entroping report runtime-card --output json after a local run.",
        schema_expected=True,
    ),
    AhaArtifactDefinition(
        key="evidence-index-json",
        label="Evidence index JSON",
        path=Path("reports") / "evidence-index.json",
        missing_hint="Run entroping report evidence-index --output json.",
        schema_expected=True,
    ),
    AhaArtifactDefinition(
        key="artifact-manifest-json",
        label="Report artifact manifest",
        path=Path("reports") / "artifact-manifest.json",
        missing_hint="Run entroping report artifact-manifest.",
        schema_expected=True,
    ),
    AhaArtifactDefinition(
        key="failure-bundle-manifest",
        label="Failure bundle manifest",
        path=Path("reports") / "failure-bundle" / "manifest.json",
        missing_hint="Run entroping report failure-bundle after a failing local run.",
        schema_expected=True,
    ),
)


def build_aha_artifact_index(*, project_root: Path) -> AhaArtifactIndex:
    root = project_root.expanduser().resolve()
    return AhaArtifactIndex(
        items=tuple(_inspect_artifact(root, definition) for definition in _ARTIFACT_DEFINITIONS)
    )


def _inspect_artifact(root: Path, definition: AhaArtifactDefinition) -> AhaArtifactIndexItem:
    absolute_path = root / definition.path
    symlink_path = first_symlink_path_component(absolute_path, root=root)
    if symlink_path is not None:
        return AhaArtifactIndexItem(
            key=definition.key,
            label=definition.label,
            state="unsafe",
            path=definition.path,
            hints=("Refusing symlinked artifact path.",),
        )
    if not absolute_path.exists():
        return AhaArtifactIndexItem(
            key=definition.key,
            label=definition.label,
            state="missing",
            path=definition.path,
            hints=(definition.missing_hint,),
        )
    if not absolute_path.is_file():
        return AhaArtifactIndexItem(
            key=definition.key,
            label=definition.label,
            state="unsafe",
            path=definition.path,
            hints=("Expected a file artifact.",),
        )
    if not definition.schema_expected:
        return AhaArtifactIndexItem(
            key=definition.key,
            label=definition.label,
            state="present",
            path=definition.path,
        )
    schema_version, error = _read_schema_version(absolute_path)
    if error:
        return AhaArtifactIndexItem(
            key=definition.key,
            label=definition.label,
            state="invalid",
            path=definition.path,
            hints=(error,),
        )
    return AhaArtifactIndexItem(
        key=definition.key,
        label=definition.label,
        state="present",
        path=definition.path,
        schema_version=schema_version,
    )


def _read_schema_version(path: Path) -> tuple[str | None, str]:
    try:
        raw_text = read_text_bounded(
            path,
            max_bytes=_MAX_SCHEMA_READ_BYTES,
            label="Aha artifact",
        )
    except BoundedReadError as exc:
        return None, str(exc)
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        return None, "Artifact JSON is invalid."
    if not isinstance(payload, dict):
        return None, "Artifact JSON must be an object."
    schema_version = payload.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version:
        return None, "Artifact JSON is missing schema_version."
    return schema_version, ""
