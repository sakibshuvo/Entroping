from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from entroping.core.path_safety import first_symlink_path_component
from entroping.core.safe_write import SafeWriteError, safe_write_bytes

DemoFixtureSourceKind = Literal["source-checkout", "package-resource"]


class DemoFixtureError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DemoFixture:
    fixture_id: str
    relative_path: Path
    files: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class DemoFixtureSource:
    fixture: DemoFixture
    root: Path
    kind: DemoFixtureSourceKind


@dataclass(frozen=True, slots=True)
class DemoFixtureCopyResult:
    fixture: DemoFixture
    root: Path
    files: tuple[Path, ...]


_FIXTURES: Final[tuple[DemoFixture, ...]] = (
    DemoFixture(
        fixture_id="ai-regression-demo",
        relative_path=Path("ai-regression-demo"),
        files=(
            Path("README.md"),
            Path("demo_server.py"),
            Path("qanstitution.yaml"),
            Path("tests/missing_request_id.hurl"),
        ),
    ),
    DemoFixture(
        fixture_id="checkout-api",
        relative_path=Path("checkout-api"),
        files=(
            Path("README.md"),
            Path("demo_server.py"),
            Path("openapi.yaml"),
            Path("qanstitution.yaml"),
            Path("tests/checkout_smoke.hurl"),
        ),
    ),
    DemoFixture(
        fixture_id="support-api",
        relative_path=Path("support-api"),
        files=(
            Path("README.md"),
            Path("demo_server.py"),
            Path("openapi.yaml"),
            Path("qanstitution.yaml"),
            Path("tests/support_smoke.hurl"),
        ),
    ),
)

_FIXTURE_BY_ID: Final[dict[str, DemoFixture]] = {
    fixture.fixture_id: fixture for fixture in _FIXTURES
}


def list_demo_fixtures() -> tuple[DemoFixture, ...]:
    return _FIXTURES


def resolve_demo_fixture_source(
    fixture_id: str,
    *,
    source_examples_root: Path | None = None,
    package_root: Path | None = None,
) -> DemoFixtureSource:
    fixture = _fixture_for_id(fixture_id)
    if package_root is not None:
        source = _resolve_source_root(package_root, fixture=fixture, kind="package-resource")
        if source.root.exists():
            return source

    examples_root = (
        source_examples_root if source_examples_root is not None else _source_examples_root()
    )
    source = _resolve_source_root(examples_root, fixture=fixture, kind="source-checkout")
    if source.root.exists():
        return source

    msg = f"Demo fixture {fixture_id!r} is not available from package resources or source checkout"
    raise DemoFixtureError(msg)


def copy_demo_fixture(
    fixture_id: str,
    destination: Path,
    *,
    source_examples_root: Path | None = None,
    package_root: Path | None = None,
) -> DemoFixtureCopyResult:
    source = resolve_demo_fixture_source(
        fixture_id,
        source_examples_root=source_examples_root,
        package_root=package_root,
    )
    raw_destination = destination.expanduser()
    _reject_symlink_path_components(raw_destination, artifact="demo fixture destination")
    destination_root = raw_destination.resolve(strict=False)

    copied: list[Path] = []
    for relative_file in source.fixture.files:
        source_file = source.root / relative_file
        _validate_manifest_file(relative_file)
        _validate_source_file(source_file, source_root=source.root)
        target = destination_root / relative_file
        try:
            written = safe_write_bytes(
                target,
                source_file.read_bytes(),
                artifact="demo fixture file",
                root=destination_root,
            )
        except SafeWriteError as exc:
            raise DemoFixtureError(str(exc)) from exc
        copied.append(written)

    return DemoFixtureCopyResult(
        fixture=source.fixture,
        root=destination_root,
        files=tuple(copied),
    )


def _fixture_for_id(fixture_id: str) -> DemoFixture:
    try:
        return _FIXTURE_BY_ID[fixture_id]
    except KeyError as exc:
        choices = ", ".join(sorted(_FIXTURE_BY_ID))
        msg = f"Unknown demo fixture {fixture_id!r}; expected one of: {choices}"
        raise DemoFixtureError(msg) from exc


def _resolve_source_root(
    root: Path,
    *,
    fixture: DemoFixture,
    kind: DemoFixtureSourceKind,
) -> DemoFixtureSource:
    resolved_root = root.expanduser().resolve(strict=False)
    return DemoFixtureSource(
        fixture=fixture,
        root=resolved_root / fixture.relative_path,
        kind=kind,
    )


def _source_examples_root() -> Path:
    return Path(__file__).resolve().parents[3] / "examples"


def _validate_manifest_file(relative_file: Path) -> None:
    if relative_file.is_absolute() or ".." in relative_file.parts:
        msg = f"Demo fixture manifest path must be relative: {relative_file}"
        raise DemoFixtureError(msg)
    forbidden = {".entroping", "__pycache__", "envs", "reports"}
    if any(part in forbidden or part.startswith(".") for part in relative_file.parts):
        msg = f"Demo fixture manifest path is not package-safe: {relative_file.as_posix()}"
        raise DemoFixtureError(msg)


def _validate_source_file(path: Path, *, source_root: Path) -> None:
    root = source_root.resolve(strict=False)
    try:
        _ = path.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        msg = f"Demo fixture source path escapes fixture root: {path}"
        raise DemoFixtureError(msg) from exc
    if first_symlink_path_component(path, root=root) is not None:
        msg = f"Refusing to copy symlinked demo fixture path: {path}"
        raise DemoFixtureError(msg)
    if not path.is_file():
        msg = f"Demo fixture file is missing: {path}"
        raise DemoFixtureError(msg)


def _reject_symlink_path_components(path: Path, *, artifact: str) -> None:
    anchors: Iterable[Path] = (path.parent, path)
    for candidate in anchors:
        symlink = first_symlink_path_component(candidate)
        if symlink is not None:
            msg = f"Refusing to write {artifact} through symlinked path component: {symlink}"
            raise DemoFixtureError(msg)
