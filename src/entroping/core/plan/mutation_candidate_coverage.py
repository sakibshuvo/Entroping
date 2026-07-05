from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from entroping.core.evidence_common import (
    contains_unredacted_evidence_secret,
    read_local_evidence_artifact_bytes,
)
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.safe_write import SafeWriteError, safe_write_text

MUTATION_CANDIDATE_COVERAGE_SCHEMA_VERSION: Final = (
    "entroping.mutation-candidate-coverage.v1"
)

MutationCandidateCoverageOutput = Literal["md", "json"]
MutationCandidateCoverageStatus = Literal["ready", "partial", "insufficient"]
MutationCandidateCoverageManifestState = Literal["present", "missing", "invalid", "unsafe"]
MutationCandidateCoverageCategoryState = Literal["seeded", "partial", "missing"]

_MUTATION_READINESS_SCHEMA_VERSION: Final = "entroping.mutation-readiness.v1"
_DEFAULT_OUTPUTS: Final[dict[MutationCandidateCoverageOutput, Path]] = {
    "md": Path("reports") / "mutation-candidate-coverage.md",
    "json": Path("reports") / "mutation-candidate-coverage.json",
}
_MANIFEST_DEFINITIONS: Final[tuple[tuple[str, Path, str, bool], ...]] = (
    (
        "mutation-readiness-json",
        Path("reports") / "mutation-readiness.json",
        _MUTATION_READINESS_SCHEMA_VERSION,
        True,
    ),
    (
        "test-quality-json",
        Path("reports") / "test-quality.json",
        "entroping.test-quality-report.v1",
        False,
    ),
    (
        "test-pyramid-json",
        Path("reports") / "test-pyramid.json",
        "entroping.test-pyramid-report.v1",
        False,
    ),
)


class MutationCandidateCoverageError(ValueError):
    pass


class MutationCandidateCoverageSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: MutationCandidateCoverageStatus
    manifests_total: int = Field(ge=0)
    manifests_present: int = Field(ge=0)
    manifests_missing: int = Field(ge=0)
    manifests_invalid: int = Field(ge=0)
    manifests_unsafe: int = Field(ge=0)
    candidate_categories_total: int = Field(ge=0)
    candidate_tests_total: int = Field(ge=0)
    seeded_tests_total: int = Field(ge=0)
    missing_seed_tests_total: int = Field(ge=0)
    source_kinds_total: int = Field(ge=0)
    source_kinds_present: int = Field(ge=0)
    source_kinds_missing: int = Field(ge=0)
    next_actions_total: int = Field(ge=0)


class MutationCandidateCoverageManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    path: str
    state: MutationCandidateCoverageManifestState
    schema_version: str | None = None
    required: bool


class MutationCandidateCoverageCategory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    state: MutationCandidateCoverageCategoryState
    candidate_tests: int = Field(ge=0)
    seeded_tests: int = Field(ge=0)
    missing_seed_tests: int = Field(ge=0)
    source_paths: tuple[str, ...] = ()


class MutationCandidateCoverageSourceKind(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    present: int = Field(ge=0)
    missing: int = Field(ge=0)
    invalid: int = Field(ge=0)
    unsafe: int = Field(ge=0)


class MutationCandidateCoverageNextAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: Literal["high", "medium"]
    action: str
    manifest_ids: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()


class MutationCandidateCoveragePacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.mutation-candidate-coverage.v1"] = (
        MUTATION_CANDIDATE_COVERAGE_SCHEMA_VERSION
    )
    generated_at: str
    project: str
    summary: MutationCandidateCoverageSummary
    manifests: tuple[MutationCandidateCoverageManifest, ...]
    categories: tuple[MutationCandidateCoverageCategory, ...]
    source_kinds: tuple[MutationCandidateCoverageSourceKind, ...]
    next_actions: tuple[MutationCandidateCoverageNextAction, ...]


@dataclass(frozen=True, slots=True)
class MutationCandidateCoverageResult:
    output_path: Path
    packet: MutationCandidateCoveragePacket


class _MutationReadinessCategoryCoveragePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    category: str
    candidate_tests: int = Field(default=0, ge=0)
    seeded_tests: int = Field(default=0, ge=0)
    missing_seed_tests: int = Field(default=0, ge=0)


class _MutationReadinessSummaryPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    category_coverage: tuple[_MutationReadinessCategoryCoveragePayload, ...] = ()


class _MutationReadinessSourcePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: str
    state: str


class _MutationReadinessCandidatePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    category: str
    source_paths: tuple[str, ...] = ()


class _MutationReadinessPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: str
    summary: _MutationReadinessSummaryPayload
    sources: tuple[_MutationReadinessSourcePayload, ...] = ()
    candidates: tuple[_MutationReadinessCandidatePayload, ...] = ()


@dataclass(frozen=True, slots=True)
class _ManifestReadResult:
    manifest: MutationCandidateCoverageManifest
    mutation_readiness: _MutationReadinessPayload | None = None


@dataclass(frozen=True, slots=True)
class _SourceCounts:
    present: int = 0
    missing: int = 0
    invalid: int = 0
    unsafe: int = 0


def run_mutation_candidate_coverage_report(
    *,
    project_root: Path,
    output: MutationCandidateCoverageOutput,
    output_path: Path | None = None,
) -> MutationCandidateCoverageResult:
    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported mutation-candidate-coverage output: {output}"
        raise MutationCandidateCoverageError(msg)
    root = project_root.expanduser().resolve()
    destination = output_path or _DEFAULT_OUTPUTS[output]
    packet = build_mutation_candidate_coverage(project_root=root)
    content = _render_packet_content(packet, output=output)
    if contains_unredacted_evidence_secret(content):
        msg = "Mutation candidate coverage contains secret-like content"
        raise MutationCandidateCoverageError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="mutation candidate coverage",
            root=root,
        )
    except SafeWriteError as exc:
        raise MutationCandidateCoverageError(str(exc)) from exc
    return MutationCandidateCoverageResult(output_path=written, packet=packet)


def build_mutation_candidate_coverage(
    *,
    project_root: Path,
) -> MutationCandidateCoveragePacket:
    root = project_root.expanduser().resolve()
    manifest_results = tuple(
        _read_manifest(
            root=root,
            manifest_id=manifest_id,
            path=path,
            schema=schema,
            required=required,
        )
        for manifest_id, path, schema, required in _MANIFEST_DEFINITIONS
    )
    manifests = tuple(result.manifest for result in manifest_results)
    mutation_readiness = next(
        (
            result.mutation_readiness
            for result in manifest_results
            if result.manifest.id == "mutation-readiness-json"
        ),
        None,
    )
    categories = _categories_from_mutation_readiness(mutation_readiness)
    source_kinds = _source_kinds_from_mutation_readiness(mutation_readiness)
    next_actions = _next_actions(
        manifests=manifests,
        categories=categories,
        source_kinds=source_kinds,
    )
    return MutationCandidateCoveragePacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=root.name,
        summary=_summary(
            manifests=manifests,
            categories=categories,
            source_kinds=source_kinds,
            next_actions=next_actions,
        ),
        manifests=manifests,
        categories=categories,
        source_kinds=source_kinds,
        next_actions=next_actions,
    )


def render_mutation_candidate_coverage_markdown(
    packet: MutationCandidateCoveragePacket,
) -> str:
    lines = [
        "# Entroping Mutation Candidate Coverage",
        "",
        "Deterministic local mutation-candidate coverage over existing manifests. "
        "This report records schema IDs, manifest states, candidate category "
        "counts, source-kind coverage, and missing seed-link counts only. It does "
        "not run mutations, fuzzers, Hurl, providers, or render raw test contents.",
        "",
        "## Summary",
        "",
        f"- Status: `{packet.summary.status}`",
        f"- Project: `{_inline_code(packet.project)}`",
        "- Manifests: "
        f"`{packet.summary.manifests_present}/{packet.summary.manifests_total}` present, "
        f"`{packet.summary.manifests_missing}` missing, "
        f"`{packet.summary.manifests_invalid}` invalid, "
        f"`{packet.summary.manifests_unsafe}` unsafe",
        "- Candidate tests: "
        f"`{packet.summary.seeded_tests_total}/{packet.summary.candidate_tests_total}` seeded, "
        f"`{packet.summary.missing_seed_tests_total}` missing seed links",
        "- Source kinds: "
        f"`{packet.summary.source_kinds_present}/{packet.summary.source_kinds_total}` present, "
        f"`{packet.summary.source_kinds_missing}` missing",
        f"- Next actions: `{packet.summary.next_actions_total}`",
        "",
        "## Manifests",
        "",
        "| ID | State | Schema | Required | Path |",
        "| --- | --- | --- | --- | --- |",
    ]
    for manifest in packet.manifests:
        lines.append(
            "| "
            f"{_markdown_cell(manifest.id)} | "
            f"{_markdown_cell(manifest.state)} | "
            f"{_markdown_cell(manifest.schema_version or 'n/a')} | "
            f"{_markdown_cell(str(manifest.required).lower())} | "
            f"{_markdown_cell(manifest.path)} |"
        )
    lines.extend(["", "## Candidate Categories", ""])
    if not packet.categories:
        lines.append("No deterministic mutation candidate categories were found.")
    else:
        lines.extend(
            [
                "| Category | State | Candidates | Seeded | Missing Seed Links |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for category in packet.categories:
            lines.append(
                "| "
                f"{_markdown_cell(category.category)} | "
                f"{_markdown_cell(category.state)} | "
                f"{category.candidate_tests} | "
                f"{category.seeded_tests} | "
                f"{category.missing_seed_tests} |"
            )
    lines.extend(["", "## Source Kinds", ""])
    if not packet.source_kinds:
        lines.append("No source-kind coverage was available.")
    else:
        lines.extend(
            [
                "| Kind | Present | Missing | Invalid | Unsafe |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for source_kind in packet.source_kinds:
            lines.append(
                "| "
                f"{_markdown_cell(source_kind.kind)} | "
                f"{source_kind.present} | "
                f"{source_kind.missing} | "
                f"{source_kind.invalid} | "
                f"{source_kind.unsafe} |"
            )
    lines.extend(["", "## Next Actions", ""])
    if not packet.next_actions:
        lines.append("No mutation candidate coverage actions are currently needed.")
    else:
        lines.extend(
            [
                "| Priority | Action | Manifests | Categories |",
                "| --- | --- | --- | --- |",
            ]
        )
        for action in packet.next_actions:
            lines.append(
                "| "
                f"{_markdown_cell(action.priority)} | "
                f"{_markdown_cell(action.action)} | "
                f"{_markdown_cell(', '.join(action.manifest_ids) or 'n/a')} | "
                f"{_markdown_cell(', '.join(action.categories) or 'n/a')} |"
            )
    return "\n".join(lines).rstrip() + "\n"


def _render_packet_content(
    packet: MutationCandidateCoveragePacket,
    *,
    output: MutationCandidateCoverageOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_mutation_candidate_coverage_markdown(packet)


def _read_manifest(
    *,
    root: Path,
    manifest_id: str,
    path: Path,
    schema: str,
    required: bool,
) -> _ManifestReadResult:
    full_path = _safe_manifest_path(root=root, path=path)
    if full_path is None:
        return _ManifestReadResult(_manifest(manifest_id, path, "unsafe", required=required))
    if not full_path.exists():
        return _ManifestReadResult(_manifest(manifest_id, path, "missing", required=required))
    content, error = read_local_evidence_artifact_bytes(full_path)
    if content is None:
        state: MutationCandidateCoverageManifestState = (
            "unsafe" if "symlink" in error else "invalid"
        )
        return _ManifestReadResult(_manifest(manifest_id, path, state, required=required))
    try:
        raw_text = content.decode("utf-8")
    except UnicodeDecodeError:
        return _ManifestReadResult(_manifest(manifest_id, path, "invalid", required=required))
    if contains_unredacted_evidence_secret(raw_text):
        return _ManifestReadResult(_manifest(manifest_id, path, "unsafe", required=required))
    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError:
        return _ManifestReadResult(_manifest(manifest_id, path, "invalid", required=required))
    try:
        schema_version = _schema_version(document)
    except MutationCandidateCoverageError:
        return _ManifestReadResult(_manifest(manifest_id, path, "invalid", required=required))
    if schema_version != schema:
        return _ManifestReadResult(
            _manifest(
                manifest_id,
                path,
                "invalid",
                schema_version=schema_version,
                required=required,
            )
        )
    if manifest_id != "mutation-readiness-json":
        return _ManifestReadResult(
            _manifest(
                manifest_id,
                path,
                "present",
                schema_version=schema_version,
                required=required,
            )
        )
    try:
        payload = _MutationReadinessPayload.model_validate(document)
    except ValidationError:
        return _ManifestReadResult(
            _manifest(
                manifest_id,
                path,
                "invalid",
                schema_version=schema_version,
                required=required,
            )
        )
    return _ManifestReadResult(
        _manifest(manifest_id, path, "present", schema_version=schema_version, required=required),
        mutation_readiness=payload,
    )


def _manifest(
    manifest_id: str,
    path: Path,
    state: MutationCandidateCoverageManifestState,
    *,
    required: bool,
    schema_version: str | None = None,
) -> MutationCandidateCoverageManifest:
    return MutationCandidateCoverageManifest(
        id=manifest_id,
        path=path.as_posix(),
        state=state,
        schema_version=schema_version,
        required=required,
    )


def _schema_version(document: object) -> str:
    if not isinstance(document, dict):
        msg = "manifest JSON must be an object"
        raise MutationCandidateCoverageError(msg)
    schema_version = document.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version.strip():
        msg = "manifest JSON is missing schema_version"
        raise MutationCandidateCoverageError(msg)
    return schema_version


def _safe_manifest_path(*, root: Path, path: Path) -> Path | None:
    if path.is_absolute():
        return None
    candidate = root / path
    try:
        candidate.resolve(strict=False).relative_to(root)
    except ValueError:
        return None
    if first_symlink_path_component(candidate, root=root) is not None:
        return None
    return candidate


def _categories_from_mutation_readiness(
    mutation_readiness: _MutationReadinessPayload | None,
) -> tuple[MutationCandidateCoverageCategory, ...]:
    if mutation_readiness is None:
        return ()
    source_paths_by_category = _candidate_source_paths_by_category(mutation_readiness)
    return tuple(
        MutationCandidateCoverageCategory(
            category=category.category,
            state=_category_state(category),
            candidate_tests=category.candidate_tests,
            seeded_tests=category.seeded_tests,
            missing_seed_tests=category.missing_seed_tests,
            source_paths=source_paths_by_category.get(category.category, ()),
        )
        for category in sorted(
            mutation_readiness.summary.category_coverage,
            key=lambda item: item.category,
        )
        if category.candidate_tests or category.seeded_tests or category.missing_seed_tests
    )


def _candidate_source_paths_by_category(
    mutation_readiness: _MutationReadinessPayload,
) -> dict[str, tuple[str, ...]]:
    source_paths: dict[str, set[str]] = {}
    for candidate in mutation_readiness.candidates:
        source_paths.setdefault(candidate.category, set()).update(candidate.source_paths)
    return {
        category: tuple(sorted(paths))
        for category, paths in sorted(source_paths.items())
    }


def _category_state(
    category: _MutationReadinessCategoryCoveragePayload,
) -> MutationCandidateCoverageCategoryState:
    if category.candidate_tests == 0:
        return "missing"
    if category.missing_seed_tests:
        return "partial"
    return "seeded"


def _source_kinds_from_mutation_readiness(
    mutation_readiness: _MutationReadinessPayload | None,
) -> tuple[MutationCandidateCoverageSourceKind, ...]:
    if mutation_readiness is None:
        return ()
    counts: dict[str, _SourceCounts] = {}
    for source in mutation_readiness.sources:
        current = counts.get(source.kind, _SourceCounts())
        counts[source.kind] = _increment_source_count(current, source.state)
    return tuple(
        MutationCandidateCoverageSourceKind(
            kind=kind,
            present=count.present,
            missing=count.missing,
            invalid=count.invalid,
            unsafe=count.unsafe,
        )
        for kind, count in sorted(counts.items())
    )


def _increment_source_count(count: _SourceCounts, state: str) -> _SourceCounts:
    if state == "present":
        return _SourceCounts(
            present=count.present + 1,
            missing=count.missing,
            invalid=count.invalid,
            unsafe=count.unsafe,
        )
    if state == "missing":
        return _SourceCounts(
            present=count.present,
            missing=count.missing + 1,
            invalid=count.invalid,
            unsafe=count.unsafe,
        )
    if state == "unsafe":
        return _SourceCounts(
            present=count.present,
            missing=count.missing,
            invalid=count.invalid,
            unsafe=count.unsafe + 1,
        )
    return _SourceCounts(
        present=count.present,
        missing=count.missing,
        invalid=count.invalid + 1,
        unsafe=count.unsafe,
    )


def _next_actions(
    *,
    manifests: tuple[MutationCandidateCoverageManifest, ...],
    categories: tuple[MutationCandidateCoverageCategory, ...],
    source_kinds: tuple[MutationCandidateCoverageSourceKind, ...],
) -> tuple[MutationCandidateCoverageNextAction, ...]:
    actions: list[MutationCandidateCoverageNextAction] = []
    missing_required = tuple(
        manifest.id for manifest in manifests if manifest.required and manifest.state != "present"
    )
    if missing_required:
        actions.append(
            MutationCandidateCoverageNextAction(
                priority="high",
                action="Generate a valid mutation-readiness manifest before coverage review.",
                manifest_ids=missing_required,
            )
        )
    unsafe_or_invalid = tuple(
        manifest.id for manifest in manifests if manifest.state in {"invalid", "unsafe"}
    )
    if unsafe_or_invalid:
        actions.append(
            MutationCandidateCoverageNextAction(
                priority="high",
                action="Repair invalid or unsafe local manifests before coverage review.",
                manifest_ids=unsafe_or_invalid,
            )
        )
    missing_seed_categories = tuple(
        category.category for category in categories if category.missing_seed_tests
    )
    if missing_seed_categories:
        actions.append(
            MutationCandidateCoverageNextAction(
                priority="medium",
                action="Add deterministic seed metadata for unseeded mutation candidates.",
                categories=missing_seed_categories,
            )
        )
    missing_source_kinds = tuple(kind.kind for kind in source_kinds if kind.missing)
    if missing_source_kinds:
        actions.append(
            MutationCandidateCoverageNextAction(
                priority="medium",
                action="Add or regenerate missing source evidence manifests.",
                categories=missing_source_kinds,
            )
        )
    return tuple(actions)


def _summary(
    *,
    manifests: tuple[MutationCandidateCoverageManifest, ...],
    categories: tuple[MutationCandidateCoverageCategory, ...],
    source_kinds: tuple[MutationCandidateCoverageSourceKind, ...],
    next_actions: tuple[MutationCandidateCoverageNextAction, ...],
) -> MutationCandidateCoverageSummary:
    candidate_tests_total = sum(category.candidate_tests for category in categories)
    seeded_tests_total = sum(category.seeded_tests for category in categories)
    missing_seed_tests_total = sum(category.missing_seed_tests for category in categories)
    source_kinds_present = sum(1 for source_kind in source_kinds if source_kind.present)
    source_kinds_missing = sum(1 for source_kind in source_kinds if source_kind.missing)
    return MutationCandidateCoverageSummary(
        status=_status(
            manifests=manifests,
            candidate_tests_total=candidate_tests_total,
            missing_seed_tests_total=missing_seed_tests_total,
            source_kinds_missing=source_kinds_missing,
        ),
        manifests_total=len(manifests),
        manifests_present=sum(1 for manifest in manifests if manifest.state == "present"),
        manifests_missing=sum(1 for manifest in manifests if manifest.state == "missing"),
        manifests_invalid=sum(1 for manifest in manifests if manifest.state == "invalid"),
        manifests_unsafe=sum(1 for manifest in manifests if manifest.state == "unsafe"),
        candidate_categories_total=len(categories),
        candidate_tests_total=candidate_tests_total,
        seeded_tests_total=seeded_tests_total,
        missing_seed_tests_total=missing_seed_tests_total,
        source_kinds_total=len(source_kinds),
        source_kinds_present=source_kinds_present,
        source_kinds_missing=source_kinds_missing,
        next_actions_total=len(next_actions),
    )


def _status(
    *,
    manifests: tuple[MutationCandidateCoverageManifest, ...],
    candidate_tests_total: int,
    missing_seed_tests_total: int,
    source_kinds_missing: int,
) -> MutationCandidateCoverageStatus:
    required_missing = any(
        manifest.required and manifest.state != "present" for manifest in manifests
    )
    unsafe_or_invalid = any(manifest.state in {"invalid", "unsafe"} for manifest in manifests)
    if required_missing or unsafe_or_invalid or candidate_tests_total == 0:
        return "insufficient"
    if missing_seed_tests_total or source_kinds_missing:
        return "partial"
    if any(manifest.state == "missing" for manifest in manifests):
        return "partial"
    return "ready"


def _inline_code(value: str) -> str:
    return _escape_backticks(escape(" ".join(value.split())))


def _markdown_cell(value: str) -> str:
    return _escape_backticks(escape(" ".join(value.split())).replace("|", "\\|"))


def _escape_backticks(value: str) -> str:
    return value.replace("`", "&#96;")
