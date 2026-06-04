"""Filesystem discovery for Entroping Hurl tests."""

from collections.abc import Sequence
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
        "graphify-out",
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


def discover_hurl_tests(
    roots: Sequence[Path] | None = None,
    *,
    tag_filters: Sequence[str] | None = None,
) -> list[HurlTest]:
    """Discover Hurl tests under roots and parse Entroping metadata comments."""

    return list(discover_hurl_test_selection(roots, tag_filters=tag_filters).tests)


def discover_hurl_test_selection(
    roots: Sequence[Path] | None = None,
    *,
    tag_filters: Sequence[str] | None = None,
    tag_expression: CompiledTagExpression | None = None,
) -> HurlTestSelection:
    """Discover Hurl tests and return selected/skipped evidence."""

    filters = normalize_tag_filters(tag_filters)
    if filters and tag_expression is not None:
        msg = "cannot combine tag filters with tag expressions"
        raise ValueError(msg)

    candidates = _discover_hurl_files(roots or _DEFAULT_ROOTS)
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
            if _is_ignored_path(path, root):
                continue
            candidates.append(path.resolve())

    return sorted(set(candidates), key=lambda path: str(path))


def _is_ignored_path(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    for part in relative.parts[:-1]:
        if part in _IGNORED_DIRECTORY_NAMES or part.startswith("."):
            return True
    return False
