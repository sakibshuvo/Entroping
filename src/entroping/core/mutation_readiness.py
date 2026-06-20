"""Deterministic local mutation/fuzz readiness reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from entroping.core.evidence_common import (
    LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES,
    contains_unredacted_evidence_secret,
    safe_evidence_text,
)
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.safe_write import SafeWriteError, safe_write_text
from entroping.models.hurl import (
    HurlMetadata,
    HurlMetadataSyntaxError,
    parse_hurl_exchanges,
    parse_hurl_metadata,
)

MUTATION_READINESS_SCHEMA_VERSION: Final = "entroping.mutation-readiness.v1"

MutationReadinessOutput = Literal["md", "json"]
MutationReadinessStatus = Literal["ready", "partial", "insufficient"]
MutationReadinessSourceState = Literal["present", "missing", "invalid", "unsafe"]
MutationReadinessSourceKind = Literal[
    "generated_hurl",
    "test_quality_report",
    "test_pyramid_report",
]
MutationCandidateCategory = Literal[
    "status_code",
    "schema",
    "auth",
    "latency",
    "request_shape",
    "response_shape",
]

_MAX_MUTATION_READINESS_ARTIFACT_BYTES: Final = LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES
_DEFAULT_OUTPUTS: Final[dict[MutationReadinessOutput, Path]] = {
    "md": Path("reports") / "mutation-readiness.md",
    "json": Path("reports") / "mutation-readiness.json",
}
_IGNORED_DIRECTORY_NAMES: Final[frozenset[str]] = frozenset(
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
    }
)
_ASSERTION_SECTION: Final = "[Asserts]"
_ASSERTION_PREFIXES: Final = (
    "body",
    "certificate",
    "cookie",
    "header",
    "jsonpath",
    "regex",
    "variable",
    "xpath",
)
_GENERATED_SOURCES: Final = frozenset({"architect", "openapi", "traffic"})
_OPTIONAL_REPORTS: Final[
    tuple[tuple[MutationReadinessSourceKind, Path, str], ...]
] = (
    (
        "test_quality_report",
        Path("reports") / "test-quality.json",
        "entroping.test-quality-report.v1",
    ),
    (
        "test_pyramid_report",
        Path("reports") / "test-pyramid.json",
        "entroping.test-pyramid-report.v1",
    ),
)
_CATEGORY_LABELS: Final[dict[MutationCandidateCategory, str]] = {
    "status_code": "Status-code mutation",
    "schema": "Schema mutation",
    "auth": "Auth/security mutation",
    "latency": "Latency boundary mutation",
    "request_shape": "Request-shape fuzz",
    "response_shape": "Response-shape mutation",
}
_CATEGORY_ACTIONS: Final[dict[MutationCandidateCategory, str]] = {
    "status_code": "Review status-code negative cases before adding deterministic mutations.",
    "schema": "Use schema-negative evidence as future mutation input.",
    "auth": "Keep auth/security cases explicit before future mutation execution.",
    "latency": "Use reviewed latency gates before adding timing mutations.",
    "request_shape": "Use request-shape negatives as seeded fuzz candidates.",
    "response_shape": "Use response assertions as response-shape mutation candidates.",
}


class MutationReadinessError(ValueError):
    """Raised when a mutation-readiness report cannot be generated safely."""


class MutationReadinessSummary(BaseModel):
    """Aggregate mutation/fuzz readiness state."""

    model_config = ConfigDict(extra="forbid")

    status: MutationReadinessStatus
    sources_total: int = Field(ge=0)
    sources_present: int = Field(ge=0)
    sources_missing: int = Field(ge=0)
    sources_invalid: int = Field(ge=0)
    sources_unsafe: int = Field(ge=0)
    generated_tests: int = Field(ge=0)
    negative_tests: int = Field(ge=0)
    security_tests: int = Field(ge=0)
    assertions_total: int = Field(ge=0)
    seed_metadata_tests: int = Field(ge=0)
    candidate_categories_total: int = Field(ge=0)
    optional_reports_present: int = Field(ge=0)
    optional_reports_invalid: int = Field(ge=0)
    optional_reports_unsafe: int = Field(ge=0)


class MutationReadinessSource(BaseModel):
    """One local source artifact used for mutation/fuzz readiness evidence."""

    model_config = ConfigDict(extra="forbid")

    kind: MutationReadinessSourceKind
    path: str
    state: MutationReadinessSourceState
    schema_version: str | None = None
    tags: tuple[str, ...] = ()
    candidate_categories: tuple[MutationCandidateCategory, ...] = ()
    assertions: int = Field(ge=0)
    seed_metadata: bool = False
    summary: str


class MutationReadinessCandidate(BaseModel):
    """Candidate evidence for one future deterministic mutation/fuzz lane."""

    model_config = ConfigDict(extra="forbid")

    category: MutationCandidateCategory
    label: str
    tests: int = Field(ge=0)
    source_paths: tuple[str, ...] = ()
    next_action: str


class MutationReadinessPacket(BaseModel):
    """Schema-versioned local mutation/fuzz readiness packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.mutation-readiness.v1"] = (
        MUTATION_READINESS_SCHEMA_VERSION
    )
    generated_at: str
    project: str
    summary: MutationReadinessSummary
    sources: tuple[MutationReadinessSource, ...]
    candidates: tuple[MutationReadinessCandidate, ...]


@dataclass(frozen=True, slots=True)
class MutationReadinessResult:
    """Result of writing one mutation-readiness packet."""

    output_path: Path
    packet: MutationReadinessPacket


@dataclass(frozen=True, slots=True)
class _SourceStateCounts:
    present: int
    missing: int
    invalid: int
    unsafe: int


@dataclass(frozen=True, slots=True)
class _HurlEvidenceCounts:
    generated_tests: int
    negative_tests: int
    security_tests: int
    assertions_total: int
    seed_metadata_tests: int


@dataclass(frozen=True, slots=True)
class _OptionalReportCounts:
    present: int
    invalid: int
    unsafe: int


def run_mutation_readiness_report(
    *,
    project_root: Path,
    output: MutationReadinessOutput,
    output_path: Path | None = None,
) -> MutationReadinessResult:
    """Write a local mutation/fuzz readiness report."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported mutation-readiness output: {output}"
        raise MutationReadinessError(msg)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUTS[output], root=root)
    packet = build_mutation_readiness(project_root=root)
    content = _render_packet_content(packet, output=output)
    if contains_unredacted_evidence_secret(content):
        msg = "Mutation readiness contains secret-like content"
        raise MutationReadinessError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="mutation readiness",
            root=root,
        )
    except SafeWriteError as exc:
        raise MutationReadinessError(str(exc)) from exc
    return MutationReadinessResult(output_path=written, packet=packet)


def build_mutation_readiness(*, project_root: Path) -> MutationReadinessPacket:
    """Build local mutation/fuzz readiness evidence without executing tests."""

    root = project_root.expanduser().resolve()
    sources = tuple(
        sorted(
            (
                *_generated_hurl_sources(root=root),
                *_optional_report_sources(root=root),
            ),
            key=lambda source: (source.path, source.kind),
        )
    )
    candidates = _candidate_summaries(sources)
    return MutationReadinessPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=root.name,
        summary=_summary(sources=sources, candidates=candidates),
        sources=sources,
        candidates=candidates,
    )


def render_mutation_readiness_markdown(packet: MutationReadinessPacket) -> str:
    """Render a human-readable mutation/fuzz readiness packet."""

    lines = [
        "# Entroping Mutation Readiness",
        "",
        "Local evidence for future deterministic mutation and seeded fuzz workflows. "
        "This report does not execute Hurl, generate tests, call providers, parse "
        "traffic state, or mutate source files.",
        "",
        "## Summary",
        "",
        f"- Status: `{packet.summary.status}`",
        f"- Generated tests: `{packet.summary.generated_tests}`",
        f"- Negative tests: `{packet.summary.negative_tests}`",
        f"- Security tests: `{packet.summary.security_tests}`",
        f"- Assertions: `{packet.summary.assertions_total}`",
        f"- Seed metadata tests: `{packet.summary.seed_metadata_tests}`",
        f"- Candidate categories: `{packet.summary.candidate_categories_total}`",
        "",
        "## Candidate Categories",
        "",
    ]
    if not packet.candidates:
        lines.append("No mutation or fuzz readiness candidates were detected.")
    else:
        lines.extend(
            [
                "| Category | Tests | Sources | Next Action |",
                "| --- | ---: | --- | --- |",
            ]
        )
        for candidate in packet.candidates:
            lines.append(
                "| "
                f"{_markdown_cell(candidate.category)} | "
                f"{candidate.tests} | "
                f"{_markdown_cell(', '.join(candidate.source_paths))} | "
                f"{_markdown_cell(candidate.next_action)} |"
            )

    lines.extend(
        [
            "",
            "## Sources",
            "",
            "| Kind | State | Path | Tags | Categories | Assertions | Seed Metadata | Summary |",
            "| --- | --- | --- | --- | --- | ---: | --- | --- |",
        ]
    )
    for source in packet.sources:
        lines.append(
            "| "
            f"{_markdown_cell(source.kind)} | "
            f"{_markdown_cell(source.state)} | "
            f"{_markdown_cell(source.path)} | "
            f"{_markdown_cell(', '.join(source.tags) or 'n/a')} | "
            f"{_markdown_cell(', '.join(source.candidate_categories) or 'n/a')} | "
            f"{source.assertions} | "
            f"{'yes' if source.seed_metadata else 'no'} | "
            f"{_markdown_cell(source.summary)} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_packet_content(
    packet: MutationReadinessPacket,
    *,
    output: MutationReadinessOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_mutation_readiness_markdown(packet)


def _generated_hurl_sources(*, root: Path) -> tuple[MutationReadinessSource, ...]:
    tests_root = root / "tests"
    if not tests_root.exists():
        return ()
    sources: list[MutationReadinessSource] = []
    for path in sorted(tests_root.rglob("*.hurl"), key=lambda candidate: str(candidate)):
        if _ignored(path, root=root):
            continue
        source = _load_hurl_source(root=root, raw_path=Path(_relative_path(path, root=root)))
        if source is None:
            continue
        sources.append(source)
    return tuple(sources)


def _load_hurl_source(
    *,
    root: Path,
    raw_path: Path,
) -> MutationReadinessSource | None:
    path_text = raw_path.as_posix()
    path = root / raw_path
    unsafe = _unsafe_path_summary(path, root=root)
    if unsafe is not None:
        if not _is_generated_path(raw_path):
            return None
        return _source(
            kind="generated_hurl",
            path=path_text,
            state="unsafe",
            summary=unsafe,
        )
    loaded = _read_text_artifact(
        path,
        artifact="Generated Hurl test",
        root=root,
        kind="generated_hurl",
    )
    if isinstance(loaded, MutationReadinessSource):
        return loaded if _is_generated_path(raw_path) else None
    raw_text = loaded
    try:
        metadata = parse_hurl_metadata(raw_text, source=raw_path)
    except HurlMetadataSyntaxError as exc:
        if not _is_generated_path(raw_path):
            return None
        return _source(
            kind="generated_hurl",
            path=path_text,
            state="invalid",
            summary=safe_evidence_text(str(exc)),
        )
    if not _is_generated_hurl(raw_path=raw_path, metadata=metadata):
        return None
    categories = _candidate_categories(metadata)
    assertions = _assertion_count(raw_text)
    return _source(
        kind="generated_hurl",
        path=path_text,
        state="present",
        tags=tuple(sorted(metadata.tags)),
        candidate_categories=categories,
        assertions=assertions,
        seed_metadata=_has_seed_metadata(metadata),
        summary=f"{len(parse_hurl_exchanges(raw_text))} generated Hurl exchanges.",
    )


def _optional_report_sources(*, root: Path) -> tuple[MutationReadinessSource, ...]:
    sources: list[MutationReadinessSource] = []
    for kind, report_path, expected_schema in _OPTIONAL_REPORTS:
        path = root / report_path
        if not path.exists():
            continue
        sources.append(
            _load_optional_report(
                root=root,
                raw_path=report_path,
                kind=kind,
                expected_schema=expected_schema,
            )
        )
    return tuple(sources)


def _load_optional_report(
    *,
    root: Path,
    raw_path: Path,
    kind: MutationReadinessSourceKind,
    expected_schema: str,
) -> MutationReadinessSource:
    path_text = raw_path.as_posix()
    path = root / raw_path
    unsafe = _unsafe_path_summary(path, root=root)
    if unsafe is not None:
        return _source(kind=kind, path=path_text, state="unsafe", summary=unsafe)
    loaded = _read_text_artifact(path, artifact=path_text, root=root, kind=kind)
    if isinstance(loaded, MutationReadinessSource):
        return loaded
    try:
        document = json.loads(loaded)
    except json.JSONDecodeError as exc:
        return _source(
            kind=kind,
            path=path_text,
            state="invalid",
            summary=safe_evidence_text(f"invalid JSON: {exc}"),
        )
    if not isinstance(document, dict):
        return _source(kind=kind, path=path_text, state="invalid", summary="invalid JSON")
    schema_version = document.get("schema_version")
    if schema_version != expected_schema:
        return _source(
            kind=kind,
            path=path_text,
            state="invalid",
            schema_version=schema_version if isinstance(schema_version, str) else None,
            summary=f"unexpected schema version; expected {expected_schema}",
        )
    return _source(
        kind=kind,
        path=path_text,
        state="present",
        schema_version=expected_schema,
        summary=_optional_report_summary(document, kind=kind),
    )


def _read_text_artifact(
    path: Path,
    *,
    artifact: str,
    root: Path,
    kind: MutationReadinessSourceKind,
) -> str | MutationReadinessSource:
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        return _source(
            kind=kind,
            path=_relative_path(path, root=root),
            state="invalid",
            summary=safe_evidence_text(f"Could not read {artifact}: {exc}"),
        )
    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        return _source(
            kind=kind,
            path=_relative_path(path, root=root),
            state="invalid",
            summary=safe_evidence_text(f"Could not decode {artifact} as UTF-8: {exc}"),
        )
    if contains_unredacted_evidence_secret(raw_text):
        return _source(
            kind=kind,
            path=_relative_path(path, root=root),
            state="unsafe",
            summary=f"{artifact} contains secret-like content.",
        )
    if len(raw_bytes) > _MAX_MUTATION_READINESS_ARTIFACT_BYTES:
        return _source(
            kind=kind,
            path=_relative_path(path, root=root),
            state="invalid",
            summary=(
                f"{artifact} exceeds {_MAX_MUTATION_READINESS_ARTIFACT_BYTES} bytes"
            ),
        )
    return raw_text


def _source(
    *,
    kind: MutationReadinessSourceKind,
    path: str,
    state: MutationReadinessSourceState,
    summary: str,
    schema_version: str | None = None,
    tags: tuple[str, ...] = (),
    candidate_categories: tuple[MutationCandidateCategory, ...] = (),
    assertions: int = 0,
    seed_metadata: bool = False,
) -> MutationReadinessSource:
    return MutationReadinessSource(
        kind=kind,
        path=path,
        state=state,
        schema_version=schema_version,
        tags=tags,
        candidate_categories=candidate_categories,
        assertions=assertions,
        seed_metadata=seed_metadata,
        summary=summary,
    )


def _candidate_categories(metadata: HurlMetadata) -> tuple[MutationCandidateCategory, ...]:
    normalized_tags = {tag.lower().replace("-", "_") for tag in metadata.tags}
    normalized_meta = {
        key.lower(): value.lower().replace("-", "_")
        for key, value in metadata.meta.items()
    }
    raw_categories = {
        normalized_meta.get("mutation_category", ""),
        normalized_meta.get("fuzz_category", ""),
        *normalized_tags,
    }
    negative_category = normalized_meta.get("negative_category", "")
    categories: set[MutationCandidateCategory] = set()
    if "invalid_auth" in raw_categories or "security" in raw_categories or "auth" in raw_categories:
        categories.add("auth")
    if negative_category == "invalid_auth":
        categories.add("auth")
    if negative_category == "schema_violations" or "schema" in raw_categories:
        categories.add("schema")
    if negative_category in {
        "malformed_json",
        "boundary_values",
        "sqli_like_strings",
        "idor_path_variants",
    } or "request_shape" in raw_categories:
        categories.add("request_shape")
    if "response_shape" in raw_categories:
        categories.add("response_shape")
    if "status_code" in raw_categories:
        categories.add("status_code")
    if "latency" in raw_categories:
        categories.add("latency")
    return tuple(sorted(categories))


def _candidate_summaries(
    sources: tuple[MutationReadinessSource, ...],
) -> tuple[MutationReadinessCandidate, ...]:
    candidates: list[MutationReadinessCandidate] = []
    present_hurl = [
        source
        for source in sources
        if source.kind == "generated_hurl" and source.state == "present"
    ]
    for category in _CATEGORY_LABELS:
        paths = tuple(
            source.path for source in present_hurl if category in source.candidate_categories
        )
        if not paths:
            continue
        candidates.append(
            MutationReadinessCandidate(
                category=category,
                label=_CATEGORY_LABELS[category],
                tests=len(paths),
                source_paths=paths,
                next_action=_CATEGORY_ACTIONS[category],
            )
        )
    return tuple(candidates)


def _summary(
    *,
    sources: tuple[MutationReadinessSource, ...],
    candidates: tuple[MutationReadinessCandidate, ...],
) -> MutationReadinessSummary:
    states = _source_state_counts(sources)
    hurl = _hurl_evidence_counts(sources)
    optional = _optional_report_counts(sources)
    return MutationReadinessSummary(
        status=_readiness_status(states=states, hurl=hurl, candidates=candidates),
        sources_total=len(sources),
        sources_present=states.present,
        sources_missing=states.missing,
        sources_invalid=states.invalid,
        sources_unsafe=states.unsafe,
        generated_tests=hurl.generated_tests,
        negative_tests=hurl.negative_tests,
        security_tests=hurl.security_tests,
        assertions_total=hurl.assertions_total,
        seed_metadata_tests=hurl.seed_metadata_tests,
        candidate_categories_total=len(candidates),
        optional_reports_present=optional.present,
        optional_reports_invalid=optional.invalid,
        optional_reports_unsafe=optional.unsafe,
    )


def _source_state_counts(
    sources: tuple[MutationReadinessSource, ...],
) -> _SourceStateCounts:
    return _SourceStateCounts(
        present=sum(1 for source in sources if source.state == "present"),
        missing=sum(1 for source in sources if source.state == "missing"),
        invalid=sum(1 for source in sources if source.state == "invalid"),
        unsafe=sum(1 for source in sources if source.state == "unsafe"),
    )


def _hurl_evidence_counts(
    sources: tuple[MutationReadinessSource, ...],
) -> _HurlEvidenceCounts:
    hurl_sources = _present_hurl_sources(sources)
    return _HurlEvidenceCounts(
        generated_tests=len(hurl_sources),
        negative_tests=sum(1 for source in hurl_sources if "negative" in source.tags),
        security_tests=sum(
            1
            for source in hurl_sources
            if "security" in source.tags or "auth" in source.candidate_categories
        ),
        assertions_total=sum(source.assertions for source in hurl_sources),
        seed_metadata_tests=sum(1 for source in hurl_sources if source.seed_metadata),
    )


def _present_hurl_sources(
    sources: tuple[MutationReadinessSource, ...],
) -> tuple[MutationReadinessSource, ...]:
    return tuple(
        source
        for source in sources
        if source.kind == "generated_hurl" and source.state == "present"
    )


def _optional_report_counts(
    sources: tuple[MutationReadinessSource, ...],
) -> _OptionalReportCounts:
    optional_reports = tuple(source for source in sources if source.kind != "generated_hurl")
    return _OptionalReportCounts(
        present=sum(1 for source in optional_reports if source.state == "present"),
        invalid=sum(1 for source in optional_reports if source.state == "invalid"),
        unsafe=sum(1 for source in optional_reports if source.state == "unsafe"),
    )


def _readiness_status(
    *,
    states: _SourceStateCounts,
    hurl: _HurlEvidenceCounts,
    candidates: tuple[MutationReadinessCandidate, ...],
) -> MutationReadinessStatus:
    if states.unsafe or states.invalid:
        return "partial"
    if (
        hurl.generated_tests
        and hurl.negative_tests
        and hurl.assertions_total
        and hurl.seed_metadata_tests
        and candidates
    ):
        return "ready"
    if hurl.generated_tests:
        return "partial"
    return "insufficient"


def _optional_report_summary(
    document: dict[str, object],
    *,
    kind: MutationReadinessSourceKind,
) -> str:
    summary = document.get("summary")
    if isinstance(summary, dict):
        status = summary.get("status")
        score = summary.get("score")
        if kind == "test_quality_report" and isinstance(status, str) and isinstance(score, int):
            return safe_evidence_text(f"test quality status {status}; score {score}")
        if isinstance(status, str):
            return safe_evidence_text(f"{kind} status {status}")
    return f"{kind} schema present"


def _is_generated_hurl(*, raw_path: Path, metadata: HurlMetadata) -> bool:
    source = metadata.meta.get("source")
    if source in _GENERATED_SOURCES:
        return True
    if "generated" in metadata.tags:
        return True
    return _is_generated_path(raw_path)


def _is_generated_path(path: Path) -> bool:
    return len(path.parts) >= 2 and path.parts[:2] == ("tests", "generated")


def _has_seed_metadata(metadata: HurlMetadata) -> bool:
    return any(key in metadata.meta for key in {"seed", "mutation_seed", "fuzz_seed"})


def _assertion_count(content: str) -> int:
    in_asserts = False
    count = 0
    for line in content.splitlines():
        stripped = line.strip()
        if stripped == _ASSERTION_SECTION:
            in_asserts = True
            continue
        if in_asserts and stripped.startswith("[") and stripped.endswith("]"):
            in_asserts = False
            continue
        if not in_asserts or not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith(_ASSERTION_PREFIXES):
            count += 1
    return count


def _unsafe_path_summary(path: Path, *, root: Path) -> str | None:
    try:
        symlink_path = first_symlink_path_component(path, root=root)
    except ValueError:
        return "mutation readiness source path must stay under the project root"
    if symlink_path is not None:
        return "mutation readiness source path uses symlinked component"
    if path.exists() and not path.is_file():
        return "mutation readiness source path is not a file"
    return None


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    path = raw_path.expanduser()
    if not path.is_absolute():
        path = root / path
    unsafe = _unsafe_path_summary(path, root=root)
    if unsafe is not None:
        msg = f"mutation readiness path is unsafe: {unsafe}"
        raise MutationReadinessError(msg)
    try:
        relative = path.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        msg = "mutation readiness path is unsafe: output must stay under project root"
        raise MutationReadinessError(msg) from exc
    if relative.parts and relative.parts[0] in {".entroping", "envs"}:
        msg = "mutation readiness path is unsafe: output must not target local state"
        raise MutationReadinessError(msg)
    return path


def _ignored(path: Path, *, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    for part in relative.parts[:-1]:
        if part in _IGNORED_DIRECTORY_NAMES or part.startswith("."):
            return True
    return False


def _relative_path(path: Path, *, root: Path) -> str:
    try:
        return path.expanduser().resolve(strict=False).relative_to(root).as_posix()
    except ValueError:
        return f"<outside-project>/{path.name}"


def _markdown_cell(value: str) -> str:
    return escape(value, quote=False).replace("|", "\\|").replace("\n", " ")
