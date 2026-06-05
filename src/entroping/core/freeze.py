"""Freeze redacted traffic state into generated artifacts."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from entroping.bridge.redaction_review import RedactionReviewCategory, compile_redaction_review
from entroping.bridge.traffic_sessions import (
    TrafficSessionError,
    TrafficSessionRecord,
    build_traffic_session_candidate,
)
from entroping.bridge.traffic_to_hurl import (
    GeneratedTrafficHurlFile,
    TrafficHurlCompilationError,
    compile_traffic_session_to_hurl,
)
from entroping.bridge.traffic_to_wiremock import (
    GeneratedWireMockMapping,
    TrafficWireMockCompilationError,
    compile_traffic_session_to_wiremock,
)
from entroping.core.hurl_validator import HurlValidationError, validate_hurl_content
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.safe_write import SafeWriteError, safe_write_text
from entroping.core.traffic_artifact_manifest import (
    TrafficArtifactApprovalError,
    TrafficArtifactKind,
    TrafficArtifactManifestArtifact,
    TrafficArtifactWorkflow,
    write_traffic_artifact_approval_manifest,
)
from entroping.core.traffic_filters import (
    TrafficCaptureFilters,
    TrafficFilterError,
    filter_traffic_exchanges,
)
from entroping.core.traffic_store import TrafficStore, TrafficStoreError
from entroping.models.traffic import TrafficExchange


class FreezeError(ValueError):
    """Raised when traffic cannot be frozen into generated Hurl safely."""


@dataclass(frozen=True, slots=True)
class FreezeResult:
    """Result of a successful freeze workflow."""

    output_path: Path
    manifest_path: Path
    record_count: int


@dataclass(frozen=True, slots=True)
class FreezeMockResult:
    """Result of a successful WireMock freeze workflow."""

    output_paths: tuple[Path, ...]
    manifest_path: Path
    record_count: int


@dataclass(frozen=True, slots=True)
class FreezePreviewArtifact:
    """One artifact that freeze would write."""

    kind: TrafficArtifactKind
    path: Path


@dataclass(frozen=True, slots=True)
class FreezePreviewRecord:
    """Safe traffic record preview without raw URL, header, query, or body values."""

    method: str
    path: str
    status_code: int | None
    role: str


@dataclass(frozen=True, slots=True)
class FreezePreviewResult:
    """Dry-run preview of a freeze workflow."""

    workflow: TrafficArtifactWorkflow
    name: str
    service: str | None
    golden: bool
    record_count: int
    artifacts: tuple[FreezePreviewArtifact, ...]
    records: tuple[FreezePreviewRecord, ...]
    redaction_categories: tuple[RedactionReviewCategory, ...]


HurlContentValidator = Callable[[str, str], None]


def preview_freeze(
    *,
    project_root: Path,
    name: str,
    golden: bool,
    capture_filters: TrafficCaptureFilters | None = None,
) -> FreezePreviewResult:
    """Preview the Hurl freeze workflow without writing artifacts."""

    root = project_root.expanduser().resolve()
    freeze_name = _validate_freeze_name(name)
    _ensure_traffic_state(root)

    try:
        store = TrafficStore.open_project(root)
        session = build_traffic_session_candidate(
            _filtered_exchanges(store.list_exchanges(), capture_filters),
            name=freeze_name,
            target_url=None,
        )
        generated = compile_traffic_session_to_hurl(session, golden=golden)
        output_path = _resolve_generated_hurl_path(generated, root=root)
    except (
        TrafficHurlCompilationError,
        TrafficFilterError,
        TrafficSessionError,
        TrafficStoreError,
    ) as exc:
        raise FreezeError(str(exc)) from exc

    return _freeze_preview_result(
        workflow="freeze-hurl",
        name=freeze_name,
        service=None,
        golden=golden,
        artifacts=(FreezePreviewArtifact(kind="hurl", path=output_path),),
        records=session.records,
    )


def preview_freeze_mock(
    *,
    project_root: Path,
    name: str,
    service: str,
    capture_filters: TrafficCaptureFilters | None = None,
) -> FreezePreviewResult:
    """Preview the WireMock freeze workflow without writing artifacts."""

    root = project_root.expanduser().resolve()
    freeze_name = _validate_freeze_name(name)
    mock_service = _validate_mock_service_name(service)
    _ensure_traffic_state(root)

    try:
        store = TrafficStore.open_project(root)
        session = build_traffic_session_candidate(
            _filtered_exchanges(store.list_exchanges(), capture_filters),
            name=freeze_name,
            target_url=None,
        )
        generated_mappings = compile_traffic_session_to_wiremock(
            session,
            service=mock_service,
        )
        output_paths = tuple(
            _resolve_wiremock_mapping_path(generated, root=root)
            for generated in generated_mappings
        )
        for generated in generated_mappings:
            json.loads(generated.content)
    except (
        json.JSONDecodeError,
        TrafficFilterError,
        TrafficSessionError,
        TrafficStoreError,
        TrafficWireMockCompilationError,
    ) as exc:
        raise FreezeError(str(exc)) from exc

    selected_records = _mock_service_records(session.records, service=mock_service)
    return _freeze_preview_result(
        workflow="freeze-wiremock",
        name=freeze_name,
        service=mock_service,
        golden=False,
        artifacts=tuple(
            FreezePreviewArtifact(kind="wiremock", path=output_path)
            for output_path in output_paths
        ),
        records=selected_records,
    )


def run_freeze(
    *,
    project_root: Path,
    name: str,
    golden: bool,
    capture_filters: TrafficCaptureFilters | None = None,
    hurl_validator: HurlContentValidator | None = None,
) -> FreezeResult:
    """Compile redacted local traffic into one validated generated Hurl file."""

    root = project_root.expanduser().resolve()
    active_validator = hurl_validator or validate_hurl_content
    freeze_name = _validate_freeze_name(name)
    _ensure_traffic_state(root)

    try:
        store = TrafficStore.open_project(root)
        exchanges = _filtered_exchanges(store.list_exchanges(), capture_filters)
        session = build_traffic_session_candidate(
            exchanges,
            name=freeze_name,
            target_url=None,
        )
        generated = compile_traffic_session_to_hurl(session, golden=golden)
        output_path = _resolve_generated_hurl_path(generated, root=root)
        active_validator(generated.content, generated.relative_path)
        _write_text_atomically(output_path, generated.content, root=root)
        manifest = write_traffic_artifact_approval_manifest(
            project_root=root,
            manifest_name=f"freeze-{freeze_name}",
            workflow="freeze-hurl",
            source_session_name=session.name,
            source_records=tuple(record.exchange for record in session.records),
            artifacts=(
                TrafficArtifactManifestArtifact(kind="hurl", path=output_path),
            ),
        )
    except (
        HurlValidationError,
        TrafficArtifactApprovalError,
        TrafficHurlCompilationError,
        TrafficFilterError,
        TrafficSessionError,
        TrafficStoreError,
    ) as exc:
        raise FreezeError(str(exc)) from exc

    return FreezeResult(
        output_path=output_path,
        manifest_path=manifest.manifest_path,
        record_count=len(session.records),
    )


def run_freeze_mock(
    *,
    project_root: Path,
    name: str,
    service: str,
    capture_filters: TrafficCaptureFilters | None = None,
) -> FreezeMockResult:
    """Compile redacted local traffic into WireMock-compatible mappings."""

    root = project_root.expanduser().resolve()
    freeze_name = _validate_freeze_name(name)
    mock_service = _validate_mock_service_name(service)
    _ensure_traffic_state(root)

    try:
        store = TrafficStore.open_project(root)
        session = build_traffic_session_candidate(
            _filtered_exchanges(store.list_exchanges(), capture_filters),
            name=freeze_name,
            target_url=None,
        )
        generated_mappings = compile_traffic_session_to_wiremock(
            session,
            service=mock_service,
        )
        output_paths = tuple(
            _resolve_wiremock_mapping_path(generated, root=root)
            for generated in generated_mappings
        )
        for generated in generated_mappings:
            json.loads(generated.content)
        for output_path, generated in zip(output_paths, generated_mappings, strict=True):
            _write_text_atomically(
                output_path,
                generated.content,
                artifact="WireMock mapping",
                root=root,
            )
        manifest = write_traffic_artifact_approval_manifest(
            project_root=root,
            manifest_name=f"freeze-{freeze_name}-mock-{mock_service}",
            workflow="freeze-wiremock",
            source_session_name=session.name,
            source_records=tuple(record.exchange for record in session.records),
            artifacts=tuple(
                TrafficArtifactManifestArtifact(kind="wiremock", path=output_path)
                for output_path in output_paths
            ),
        )
    except (
        json.JSONDecodeError,
        TrafficArtifactApprovalError,
        TrafficFilterError,
        TrafficSessionError,
        TrafficStoreError,
        TrafficWireMockCompilationError,
    ) as exc:
        raise FreezeError(str(exc)) from exc

    return FreezeMockResult(
        output_paths=output_paths,
        manifest_path=manifest.manifest_path,
        record_count=len(generated_mappings),
    )


def _filtered_exchanges(
    exchanges: tuple[TrafficExchange, ...],
    capture_filters: TrafficCaptureFilters | None,
) -> tuple[TrafficExchange, ...]:
    if capture_filters is None or not capture_filters.is_active:
        return exchanges
    filtered = filter_traffic_exchanges(exchanges, capture_filters)
    if not filtered:
        msg = "No traffic records matched capture filters."
        raise TrafficFilterError(msg)
    return filtered


def _ensure_traffic_state(root: Path) -> None:
    state_path = root / ".entroping" / "state.db"
    if not state_path.exists():
        msg = "No traffic state found. Run entroping watch before freeze."
        raise FreezeError(msg)


def _freeze_preview_result(
    *,
    workflow: TrafficArtifactWorkflow,
    name: str,
    service: str | None,
    golden: bool,
    artifacts: tuple[FreezePreviewArtifact, ...],
    records: tuple[TrafficSessionRecord, ...],
) -> FreezePreviewResult:
    exchanges = tuple(record.exchange for record in records)
    redaction_report = compile_redaction_review(exchanges)
    return FreezePreviewResult(
        workflow=workflow,
        name=name,
        service=service,
        golden=golden,
        record_count=len(records),
        artifacts=artifacts,
        records=_preview_records(records),
        redaction_categories=(
            *redaction_report.header_categories,
            *redaction_report.query_categories,
            *redaction_report.body_categories,
            *redaction_report.body_summary_categories,
        ),
    )


def _preview_records(
    records: tuple[TrafficSessionRecord, ...],
) -> tuple[FreezePreviewRecord, ...]:
    return tuple(_preview_record(record) for record in records)


def _preview_record(record: TrafficSessionRecord) -> FreezePreviewRecord:
    exchange = record.exchange
    parsed = urlsplit(exchange.request.url)
    status_code = exchange.response.status_code if exchange.response is not None else None
    return FreezePreviewRecord(
        method=exchange.request.method.upper(),
        path=parsed.path or "/",
        status_code=status_code,
        role=record.role,
    )


def _mock_service_records(
    records: tuple[TrafficSessionRecord, ...],
    *,
    service: str,
) -> tuple[TrafficSessionRecord, ...]:
    return tuple(record for record in records if _record_matches_mock_service(record, service))


def _record_matches_mock_service(record: TrafficSessionRecord, service: str) -> bool:
    host = urlsplit(record.exchange.request.url).netloc.lower()
    if host == service:
        return True
    first_label = host.split(".", maxsplit=1)[0]
    return "." not in service and first_label == service


def _validate_freeze_name(name: str) -> str:
    value = name.strip()
    if not value:
        msg = "freeze name must not be empty"
        raise FreezeError(msg)
    if _contains_control(value):
        msg = "freeze name must not contain control characters"
        raise FreezeError(msg)
    if "/" in value or "\\" in value or ".." in value or value.startswith("."):
        msg = "freeze name must be a safe file stem"
        raise FreezeError(msg)
    if not all(character.isalnum() or character in {"_", "-", "."} for character in value):
        msg = "freeze name must contain only letters, numbers, dots, dashes, or underscores"
        raise FreezeError(msg)
    return value


def _validate_mock_service_name(name: str) -> str:
    value = name.strip()
    if not value:
        msg = "mock service must not be empty"
        raise FreezeError(msg)
    if _contains_control(value):
        msg = "mock service must not contain control characters"
        raise FreezeError(msg)
    if "/" in value or "\\" in value or ".." in value or value.startswith("."):
        msg = "mock service must be a safe file stem"
        raise FreezeError(msg)
    if not all(character.isalnum() or character in {"_", "-", "."} for character in value):
        msg = "mock service must contain only letters, numbers, dots, dashes, or underscores"
        raise FreezeError(msg)
    return value.lower()


def _resolve_generated_hurl_path(generated: GeneratedTrafficHurlFile, *, root: Path) -> Path:
    if "\\" in generated.relative_path:
        msg = f"Generated Hurl path must use POSIX separators: {generated.relative_path}"
        raise FreezeError(msg)

    relative_path = PurePosixPath(generated.relative_path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        msg = f"Generated Hurl path must stay inside the project: {generated.relative_path}"
        raise FreezeError(msg)
    if (
        len(relative_path.parts) < 3
        or relative_path.parts[0] != "tests"
        or relative_path.parts[1] != "generated"
        or relative_path.suffix != ".hurl"
    ):
        msg = f"Generated Hurl path must stay under tests/generated: {generated.relative_path}"
        raise FreezeError(msg)

    candidate = root.joinpath(*relative_path.parts)
    _reject_symlink_path(candidate, root=root)
    output_path = candidate.resolve()
    generated_root = (root / "tests" / "generated").resolve()
    if not output_path.is_relative_to(generated_root):
        msg = f"Generated Hurl path must stay under tests/generated: {generated.relative_path}"
        raise FreezeError(msg)
    if output_path.exists() and not output_path.is_file():
        msg = f"Refusing to overwrite non-file generated Hurl target: {output_path}"
        raise FreezeError(msg)
    return output_path


def _resolve_wiremock_mapping_path(generated: GeneratedWireMockMapping, *, root: Path) -> Path:
    if "\\" in generated.relative_path:
        msg = f"WireMock mapping path must use POSIX separators: {generated.relative_path}"
        raise FreezeError(msg)

    relative_path = PurePosixPath(generated.relative_path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        msg = f"WireMock mapping path must stay inside the project: {generated.relative_path}"
        raise FreezeError(msg)
    if (
        len(relative_path.parts) != 3
        or relative_path.parts[0] != "mocks"
        or relative_path.suffix != ".json"
    ):
        msg = f"WireMock mapping path must stay under mocks/<service>: {generated.relative_path}"
        raise FreezeError(msg)

    candidate = root.joinpath(*relative_path.parts)
    _reject_symlink_path(candidate, root=root, artifact="WireMock mapping")
    output_path = candidate.resolve()
    mappings_root = (root / "mocks").resolve()
    if not output_path.is_relative_to(mappings_root):
        msg = f"WireMock mapping path must stay under mocks: {generated.relative_path}"
        raise FreezeError(msg)
    if output_path.exists() and not output_path.is_file():
        msg = f"Refusing to overwrite non-file WireMock mapping: {output_path}"
        raise FreezeError(msg)
    return output_path


def _reject_symlink_path(
    candidate: Path,
    *,
    root: Path,
    artifact: str = "generated Hurl file",
) -> None:
    symlink_component = first_symlink_path_component(candidate, root=root)
    if symlink_component is not None:
        msg = f"Refusing to write symlinked {artifact}: {symlink_component}"
        raise FreezeError(msg)


def _write_text_atomically(
    path: Path,
    content: str,
    *,
    root: Path,
    artifact: str = "generated Hurl file",
) -> None:
    try:
        safe_write_text(path, content, artifact=artifact, root=root)
    except SafeWriteError as exc:
        raise FreezeError(str(exc)) from exc


def _contains_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)
