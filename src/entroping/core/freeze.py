"""Freeze redacted traffic state into generated artifacts."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from entroping.bridge.traffic_sessions import (
    TrafficSessionError,
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
from entroping.core.safe_write import SafeWriteError, safe_write_text
from entroping.core.traffic_store import TrafficStore, TrafficStoreError


class FreezeError(ValueError):
    """Raised when traffic cannot be frozen into generated Hurl safely."""


@dataclass(frozen=True, slots=True)
class FreezeResult:
    """Result of a successful freeze workflow."""

    output_path: Path
    record_count: int


@dataclass(frozen=True, slots=True)
class FreezeMockResult:
    """Result of a successful WireMock freeze workflow."""

    output_paths: tuple[Path, ...]
    record_count: int


HurlContentValidator = Callable[[str, str], None]


def run_freeze(
    *,
    project_root: Path,
    name: str,
    golden: bool,
    hurl_validator: HurlContentValidator | None = None,
) -> FreezeResult:
    """Compile redacted local traffic into one validated generated Hurl file."""

    root = project_root.expanduser().resolve()
    active_validator = hurl_validator or validate_hurl_content
    freeze_name = _validate_freeze_name(name)
    state_path = root / ".entroping" / "state.db"
    if not state_path.exists():
        msg = "No traffic state found. Run entroping watch before freeze."
        raise FreezeError(msg)

    try:
        store = TrafficStore.open_project(root)
        exchanges = store.list_exchanges()
        session = build_traffic_session_candidate(
            exchanges,
            name=freeze_name,
            target_url=None,
        )
        generated = compile_traffic_session_to_hurl(session, golden=golden)
        output_path = _resolve_generated_hurl_path(generated, root=root)
        active_validator(generated.content, generated.relative_path)
        _write_text_atomically(output_path, generated.content, root=root)
    except (
        HurlValidationError,
        TrafficHurlCompilationError,
        TrafficSessionError,
        TrafficStoreError,
    ) as exc:
        raise FreezeError(str(exc)) from exc

    return FreezeResult(output_path=output_path, record_count=len(session.records))


def run_freeze_mock(
    *,
    project_root: Path,
    name: str,
    service: str,
) -> FreezeMockResult:
    """Compile redacted local traffic into WireMock-compatible mappings."""

    root = project_root.expanduser().resolve()
    freeze_name = _validate_freeze_name(name)
    mock_service = _validate_mock_service_name(service)
    state_path = root / ".entroping" / "state.db"
    if not state_path.exists():
        msg = "No traffic state found. Run entroping watch before freeze."
        raise FreezeError(msg)

    try:
        store = TrafficStore.open_project(root)
        session = build_traffic_session_candidate(
            store.list_exchanges(),
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
    except (
        json.JSONDecodeError,
        TrafficSessionError,
        TrafficStoreError,
        TrafficWireMockCompilationError,
    ) as exc:
        raise FreezeError(str(exc)) from exc

    return FreezeMockResult(output_paths=output_paths, record_count=len(generated_mappings))


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
    current = root
    for part in candidate.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            msg = f"Refusing to write symlinked {artifact}: {current}"
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
