"""Filesystem discovery for Entroping Hurl tests."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path

from entroping.core.tag_expression import CompiledTagExpression
from entroping.models.hurl import (
    HurlMetadataSyntaxError,
    HurlTest,
    parse_hurl_exchanges,
    parse_hurl_metadata,
)

_DEFAULT_ROOTS = (Path("tests"),)
_IGNORED_DIRECTORY_NAMES = frozenset(
    {
        ".entroping",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "reports",
        "venv",
    },
)


@dataclass(frozen=True, slots=True)
class HurlTestSelection:
    """Discovered Hurl tests plus deterministic selection evidence."""

    tests: tuple[HurlTest, ...]
    discovered_count: int

    @property
    def selected_count(self) -> int:
        """Return the number of tests selected for execution."""

        return len(self.tests)

    @property
    def skipped_count(self) -> int:
        """Return the number of discovered tests excluded by selection filters."""

        return self.discovered_count - self.selected_count


def normalize_tag_filters(tag_filters: Sequence[str] | None) -> frozenset[str]:
    """Normalize user-provided tag filters and reject empty values."""

    if tag_filters is None:
        return frozenset()

    normalized: set[str] = set()
    for raw_filter in tag_filters:
        tag_filter = raw_filter.strip()
        if tag_filter == "":
            msg = "Tag filters must not be empty"
            raise ValueError(msg)
        normalized.add(tag_filter)

    return frozenset(normalized)


def normalize_operation_id_filters(operation_ids: Collection[str] | None) -> frozenset[str]:
    """Normalize operation ID filters and reject unsafe values."""

    if operation_ids is None:
        return frozenset()

    normalized: set[str] = set()
    for raw_filter in operation_ids:
        operation_id = raw_filter.strip()
        if operation_id == "":
            msg = "Operation ID filters must not be empty"
            raise ValueError(msg)
        if any(ord(character) < 32 or ord(character) == 127 for character in operation_id):
            msg = "Operation ID filters must not contain control characters"
            raise ValueError(msg)
        normalized.add(operation_id)

    return frozenset(normalized)


def discover_hurl_tests(
    roots: Sequence[Path] | None = None,
    *,
    tag_filters: Sequence[str] | None = None,
    operation_id_filters: Collection[str] | None = None,
) -> list[HurlTest]:
    """Discover Hurl tests under roots and parse Entroping metadata comments."""

    return list(
        discover_hurl_test_selection(
            roots,
            tag_filters=tag_filters,
            operation_id_filters=operation_id_filters,
        ).tests
    )


def discover_hurl_test_selection(
    roots: Sequence[Path] | None = None,
    *,
    tag_filters: Sequence[str] | None = None,
    tag_expression: CompiledTagExpression | None = None,
    operation_id_filters: Collection[str] | None = None,
) -> HurlTestSelection:
    """Discover Hurl tests and return selected/skipped evidence."""

    filters = normalize_tag_filters(tag_filters)
    operation_filters = normalize_operation_id_filters(operation_id_filters)
    if filters and tag_expression is not None:
        msg = "cannot combine tag filters with tag expressions"
        raise ValueError(msg)
    if operation_filters and filters:
        msg = "cannot combine operation ID filters with tag filters"
        raise ValueError(msg)
    if operation_filters and tag_expression is not None:
        msg = "cannot combine operation ID filters with tag expressions"
        raise ValueError(msg)

    candidates = _discover_hurl_files(roots if roots is not None else _DEFAULT_ROOTS)
    discovered: list[HurlTest] = []
    discovered_count = 0

    for path in candidates:
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            msg = f"{path}: file is not valid UTF-8"
            raise HurlMetadataSyntaxError(msg) from exc

        metadata = parse_hurl_metadata(content, source=path)
        discovered_count += 1
        if filters and metadata.tags.isdisjoint(filters):
            continue
        if tag_expression is not None and not tag_expression.matches(metadata.tags):
            continue
        if operation_filters and metadata.operation_id not in operation_filters:
            continue
        discovered.append(
            HurlTest(
                path=path,
                metadata=metadata,
                exchanges=parse_hurl_exchanges(content),
            ),
        )

    return HurlTestSelection(tests=tuple(discovered), discovered_count=discovered_count)


def _discover_hurl_files(roots: Sequence[Path]) -> list[Path]:
    candidates: list[Path] = []

    for raw_root in roots:
        root = raw_root.expanduser().resolve()
        if not root.exists():
            msg = f"Hurl discovery root does not exist: {root}"
            raise FileNotFoundError(msg)

        if root.is_file():
            if root.suffix != ".hurl":
                msg = f"Expected a .hurl file or directory, got: {root}"
                raise ValueError(msg)
            candidates.append(root)
            continue

        for path in root.rglob("*.hurl"):
            if not path.is_file() or path.is_symlink():
                continue
            resolved_path = path.resolve()
            if not _is_within_root(resolved_path, root):
                continue
            if _is_ignored_path(path, root) or _is_ignored_path(resolved_path, root):
                continue
            candidates.append(resolved_path)

    return sorted(set(candidates), key=lambda path: str(path))


def _is_within_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _is_ignored_path(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    for part in relative.parts[:-1]:
        if part in _IGNORED_DIRECTORY_NAMES or part.startswith("."):
            return True
    return False
