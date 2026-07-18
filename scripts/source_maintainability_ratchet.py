#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Annotated, Final, Literal, Never, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.script_safety import (  # noqa: E402
    ScriptSafetyError,
    read_text_file,
    write_json_file,
)

REPORT_SCHEMA: Final = "entroping.source-maintainability-ratchet-report.v1"
TRACKED_BASELINE: Final = PurePosixPath("docs/meta/source-maintainability-ratchet-baseline.json")
RANKS: Final[tuple[Rank, ...]] = ("A", "B", "C", "D", "E", "F")
PROTECTED_RANKS: Final[tuple[Rank, ...]] = ("D", "E", "F")
WEIGHTS: Final[dict[Rank, int]] = {"A": 0, "B": 1, "C": 3, "D": 8, "E": 13, "F": 21}
MAX_CONTRIBUTORS: Final = 20
JSON_MAX_BYTES: Final = 10_000_000
JSON_INTEGER_MAX_DIGITS: Final = 64

Rank = Literal["A", "B", "C", "D", "E", "F"]
Status = Literal["passed", "regressed"]
Family = Literal["cc", "mi", "hotspot"]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]
Sha256 = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]
CommitSha = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{40}$")]
ReviewDate = Annotated[str, Field(strict=True, pattern=r"^\d{4}-\d{2}-\d{2}$")]


class MaintainabilityInputError(ValueError):
    pass


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class RankValues(StrictModel):
    a: NonNegativeInt = Field(alias="A")
    b: NonNegativeInt = Field(alias="B")
    c: NonNegativeInt = Field(alias="C")
    d: NonNegativeInt = Field(alias="D")
    e: NonNegativeInt = Field(alias="E")
    f: NonNegativeInt = Field(alias="F")

    def value(self, rank: Rank) -> int:
        return {"A": self.a, "B": self.b, "C": self.c, "D": self.d, "E": self.e, "F": self.f}[rank]


class RankCounts(RankValues):
    @property
    def calculated_score(self) -> int:
        return sum(self.value(rank) * WEIGHTS[rank] for rank in RANKS)

    @property
    def calculated_worst_rank(self) -> Rank:
        for rank in reversed(RANKS):
            if self.value(rank) > 0:
                return rank
        return "A"


class RankWeights(RankValues):
    pass


class MetricFamily(StrictModel):
    rank_counts: RankCounts
    weighted_score: NonNegativeInt
    worst_rank: Rank

    @model_validator(mode="after")
    def validate_derived_values(self) -> Self:
        if self.weighted_score != self.rank_counts.calculated_score:
            raise MaintainabilityInputError("weighted_score does not match rank_counts")
        if self.worst_rank != self.rank_counts.calculated_worst_rank:
            raise MaintainabilityInputError("worst_rank does not match rank_counts")
        return self


class HotspotMetric(StrictModel):
    threshold_lines: PositiveInt
    count: NonNegativeInt

    @model_validator(mode="after")
    def validate_threshold(self) -> Self:
        if self.threshold_lines != 500:
            raise MaintainabilityInputError("source hotspot threshold must remain 500")
        return self


class Metrics(StrictModel):
    cyclomatic_complexity: MetricFamily
    maintainability_index: MetricFamily
    source_hotspots: HotspotMetric


class BaselineEvidence(StrictModel):
    issue_url: Annotated[str, Field(strict=True, min_length=1)]
    from_commit: CommitSha
    through_commit: CommitSha
    cc_command: Annotated[str, Field(strict=True, min_length=1)]
    mi_command: Annotated[str, Field(strict=True, min_length=1)]
    hotspot_definition: Annotated[str, Field(strict=True, min_length=1)]

    @model_validator(mode="after")
    def validate_issue_url(self) -> Self:
        if re.fullmatch(r"https://github\.com/[^/]+/[^/]+/issues/[1-9]\d*", self.issue_url) is None:
            raise MaintainabilityInputError("evidence issue_url must name a GitHub issue")
        return self


class Baseline(StrictModel):
    schema_version: Literal["entroping.source-maintainability-ratchet-baseline.v1"]
    revision: PositiveInt
    owner: Annotated[str, Field(strict=True, min_length=1)]
    reviewed_on: ReviewDate
    evidence: BaselineEvidence
    weights: RankWeights
    metrics: Metrics

    @model_validator(mode="after")
    def validate_weights(self) -> Self:
        if any(self.weights.value(rank) != WEIGHTS[rank] for rank in RANKS):
            raise MaintainabilityInputError("baseline weights do not match the protected policy")
        return self


class EvidenceArtifact(StrictModel):
    path: Annotated[str, Field(strict=True, min_length=1)]
    sha256: Sha256


class RebaseRequest(StrictModel):
    schema_version: Literal["entroping.source-maintainability-rebase-request.v1"]
    current_revision: PositiveInt
    proposed_revision: PositiveInt
    issue_url: Annotated[str, Field(strict=True, min_length=1)]
    pull_request_url: Annotated[str, Field(strict=True, min_length=1)]
    rationale: Annotated[str, Field(strict=True, min_length=20)]
    before_evidence: EvidenceArtifact
    after_evidence: EvidenceArtifact

    @model_validator(mode="after")
    def validate_urls_and_revision(self) -> Self:
        issue = r"https://github\.com/[^/]+/[^/]+/issues/[1-9]\d*"
        pull = r"https://github\.com/[^/]+/[^/]+/pull/[1-9]\d*"
        if re.fullmatch(issue, self.issue_url) is None:
            raise MaintainabilityInputError("rebase issue_url must name a GitHub issue")
        if re.fullmatch(pull, self.pull_request_url) is None:
            raise MaintainabilityInputError(
                "rebase pull_request_url must name a GitHub pull request"
            )
        if self.proposed_revision != self.current_revision + 1:
            raise MaintainabilityInputError(
                "proposed_revision must increment current_revision by one"
            )
        if self.rationale != self.rationale.strip():
            raise MaintainabilityInputError("rebase rationale must not contain edge whitespace")
        return self


class RebaseValidation(StrictModel):
    status: Literal["passed"]
    current_revision: PositiveInt
    proposed_revision: PositiveInt
    issue_url: str
    pull_request_url: str
    before_evidence: str
    after_evidence: str


class RatchetReport(StrictModel):
    schema_version: Literal["entroping.source-maintainability-ratchet-report.v1"]
    baseline_revision: PositiveInt
    status: Status
    baseline: Metrics
    current: Metrics
    violations: tuple[str, ...]
    contributors: tuple[str, ...]
    rebase_validation: RebaseValidation | None


@dataclass(frozen=True, slots=True)
class Contributor:
    family: Family
    path: str
    rank: Rank | None
    detail: str

    def render(self) -> str:
        if self.rank is None:
            return f"{self.family}: {self.path} ({self.detail})"
        return f"{self.family}: {self.path} rank {self.rank} ({self.detail})"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare source-only maintainability metrics with an immutable tracked baseline."
        )
    )
    parser.add_argument("--repo-root", default=".", help="Repository root for safe path checks.")
    parser.add_argument("--radon-cc", required=True, help="Radon CC JSON from `src tests`.")
    parser.add_argument("--radon-mi", required=True, help="Radon MI JSON from `src`.")
    parser.add_argument("--baseline", required=True, help="Tracked immutable baseline JSON.")
    parser.add_argument("--output", required=True, help="Ignored deterministic report JSON.")
    parser.add_argument(
        "--rebase-request",
        help="Validate a reviewed baseline rebase request without changing the baseline.",
    )
    return parser.parse_args(argv)


def _root_path(raw: str) -> Path:
    candidate = Path(raw).expanduser()
    if candidate.is_symlink():
        raise MaintainabilityInputError("repository root must not be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise MaintainabilityInputError(f"repository root is unavailable: {candidate}") from exc
    if not resolved.is_dir():
        raise MaintainabilityInputError("repository root must be a directory")
    return resolved


def _relative_path(raw: str, *, label: str) -> PurePosixPath:
    if not raw or "\\" in raw:
        raise MaintainabilityInputError(f"{label} must be a canonical relative POSIX path")
    path = PurePosixPath(raw)
    if path.is_absolute() or path.as_posix() != raw:
        raise MaintainabilityInputError(f"{label} must be a canonical relative POSIX path")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise MaintainabilityInputError(f"{label} contains a forbidden path alias")
    return path


def _checked_input(root: Path, raw: str, *, label: str) -> Path:
    relative = _relative_path(raw, label=label)
    current = root
    for part in relative.parts:
        current /= part
        try:
            mode = current.lstat().st_mode
        except OSError as exc:
            raise MaintainabilityInputError(f"{label} is unavailable: {relative}") from exc
        if stat.S_ISLNK(mode):
            raise MaintainabilityInputError(f"{label} must not traverse a symlink")
    if not stat.S_ISREG(current.stat().st_mode):
        raise MaintainabilityInputError(f"{label} must be a regular file")
    return current


def _checked_output(
    root: Path,
    raw: str,
    *,
    baseline_path: Path,
    protected_paths: tuple[Path, ...],
) -> Path:
    relative = _relative_path(raw, label="output")
    output = root.joinpath(*relative.parts)
    tracked_baseline = root.joinpath(*TRACKED_BASELINE.parts)
    if (
        relative == PurePosixPath(baseline_path.relative_to(root).as_posix())
        or relative == TRACKED_BASELINE
    ):
        raise MaintainabilityInputError("normal audit cannot overwrite the tracked baseline")
    if output.exists() and (
        output.samefile(baseline_path)
        or (tracked_baseline.exists() and output.samefile(tracked_baseline))
    ):
        raise MaintainabilityInputError("output must not alias the tracked baseline")
    if not relative.parts or relative.parts[0] != "reports":
        raise MaintainabilityInputError("output must be under reports")
    for protected_path in protected_paths:
        if output == protected_path or (output.exists() and output.samefile(protected_path)):
            raise MaintainabilityInputError("output must not alias an input or source file")
    return output


def _parse_bounded_int(raw: str) -> int:
    if len(raw.removeprefix("-")) > JSON_INTEGER_MAX_DIGITS:
        raise MaintainabilityInputError("JSON integer exceeds safe digit limit")
    return int(raw)


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise MaintainabilityInputError("duplicate JSON key is forbidden")
        result[key] = value
    return result


def _reject_non_finite_number(raw: str) -> Never:
    raise MaintainabilityInputError(f"non-finite JSON number is forbidden: {raw}")


def _parse_json(content: str, *, label: Path) -> object:
    try:
        return json.loads(
            content,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_non_finite_number,
            parse_int=_parse_bounded_int,
        )
    except json.JSONDecodeError as exc:
        raise MaintainabilityInputError(f"invalid JSON in {label}: {exc.msg}") from exc


def _json_value(path: Path) -> object:
    return _parse_json(
        read_text_file(path, max_bytes=JSON_MAX_BYTES),
        label=path,
    )


def _baseline(path: Path) -> Baseline:
    return Baseline.model_validate_json(json.dumps(_json_value(path)))


def _metric_path(
    root: Path,
    raw: str,
    *,
    roots: frozenset[str],
    identities: dict[tuple[int, int], str],
) -> tuple[Path, PurePosixPath]:
    relative = _relative_path(raw, label="Radon file key")
    if relative.suffix != ".py" or not relative.parts or relative.parts[0] not in roots:
        raise MaintainabilityInputError(f"Radon file key is outside the allowed scope: {raw}")
    path = _checked_input(root, raw, label="Radon source")
    metadata = path.stat()
    identity = (metadata.st_dev, metadata.st_ino)
    prior = identities.get(identity)
    if prior is not None and prior != raw:
        raise MaintainabilityInputError(f"Radon file aliases are forbidden: {prior}, {raw}")
    identities[identity] = raw
    return path, relative


def _rank(raw: object, *, label: str) -> Rank:
    if not isinstance(raw, str) or raw not in RANKS:
        raise MaintainabilityInputError(f"{label} must be one of A, B, C, D, E, F")
    return raw


def _positive_int(raw: object, *, label: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        raise MaintainabilityInputError(f"{label} must be a positive integer")
    return raw


def _non_negative_number(raw: object, *, label: str) -> float:
    if (
        isinstance(raw, bool)
        or not isinstance(raw, (int, float))
        or not math.isfinite(raw)
        or raw < 0
    ):
        if isinstance(raw, float) and not math.isfinite(raw):
            raise MaintainabilityInputError(f"non-finite {label}")
        raise MaintainabilityInputError(f"{label} must be a non-negative number")
    return float(raw)


def _family(counts: dict[Rank, int]) -> MetricFamily:
    rank_counts = RankCounts.model_validate(counts)
    return MetricFamily(
        rank_counts=rank_counts,
        weighted_score=rank_counts.calculated_score,
        worst_rank=rank_counts.calculated_worst_rank,
    )


def _cc_metrics(
    root: Path,
    path: Path,
    source_files: tuple[Path, ...],
) -> tuple[MetricFamily, tuple[Contributor, ...]]:
    payload = _json_value(path)
    if not isinstance(payload, dict):
        raise MaintainabilityInputError("Radon CC JSON must be an object")
    counts: dict[Rank, int] = dict.fromkeys(RANKS, 0)
    contributors: list[Contributor] = []
    identities: dict[tuple[int, int], str] = {}
    source_blocks: set[tuple[str, str, str, int]] = set()
    for raw_path in sorted(payload):
        entries = payload[raw_path]
        _, relative = _metric_path(
            root,
            raw_path,
            roots=frozenset({"src", "tests"}),
            identities=identities,
        )
        if not isinstance(entries, list):
            raise MaintainabilityInputError(f"Radon CC entries must be an array: {raw_path}")
        for entry in entries:
            if not isinstance(entry, dict):
                raise MaintainabilityInputError(f"Radon CC entry must be an object: {raw_path}")
            block_type = entry.get("type")
            if block_type not in {"class", "function", "method"}:
                raise MaintainabilityInputError("Radon CC type must name a code block")
            rank = _rank(entry.get("rank"), label="Radon CC rank")
            name = entry.get("name")
            complexity = _positive_int(entry.get("complexity"), label="Radon CC complexity")
            line = _positive_int(entry.get("lineno"), label="Radon CC lineno")
            if not isinstance(name, str) or not name:
                raise MaintainabilityInputError("Radon CC name must be a non-empty string")
            if relative.parts[0] == "src":
                block = (relative.as_posix(), block_type, name, line)
                if block in source_blocks:
                    raise MaintainabilityInputError(
                        f"duplicate Radon CC block evidence: {relative.as_posix()}:{line} {name}"
                    )
                source_blocks.add(block)
                counts[rank] += 1
                contributors.append(
                    Contributor("cc", f"{relative.as_posix()}:{line} {name}", rank, str(complexity))
                )
    expected_blocks = _expected_cc_blocks(root, source_files)
    if source_blocks != expected_blocks:
        raise MaintainabilityInputError(
            "Radon CC must include source evidence and must exactly match source code blocks"
        )
    return _family(counts), tuple(contributors)


def _mi_metrics(
    root: Path,
    path: Path,
    source_files: tuple[Path, ...],
) -> tuple[MetricFamily, tuple[Contributor, ...]]:
    payload = _json_value(path)
    if not isinstance(payload, dict):
        raise MaintainabilityInputError("Radon MI JSON must be an object")
    counts: dict[Rank, int] = dict.fromkeys(RANKS, 0)
    contributors: list[Contributor] = []
    identities: dict[tuple[int, int], str] = {}
    source_paths: set[str] = set()
    for raw_path in sorted(payload):
        raw_entries = payload[raw_path]
        _, relative = _metric_path(
            root,
            raw_path,
            roots=frozenset({"src"}),
            identities=identities,
        )
        if not isinstance(raw_entries, dict):
            raise MaintainabilityInputError(f"Radon MI entry must be an object: {raw_path}")
        source_paths.add(relative.as_posix())
        rank = _rank(raw_entries.get("rank"), label="Radon MI rank")
        raw_mi = raw_entries.get("mi", raw_entries.get("maintainability_index"))
        mi = _non_negative_number(raw_mi, label="Radon MI value")
        counts[rank] += 1
        contributors.append(Contributor("mi", relative.as_posix(), rank, f"{mi:g}"))
    expected_paths = {path.relative_to(root).as_posix() for path in source_files}
    if source_paths != expected_paths:
        raise MaintainabilityInputError(
            "Radon MI must include source evidence for every Python file"
        )
    return _family(counts), tuple(contributors)


def _source_python_files(root: Path) -> tuple[Path, ...]:
    source_root = root / "src"
    if not source_root.is_dir() or source_root.is_symlink():
        raise MaintainabilityInputError("src must be a regular directory")
    pending = [source_root]
    identities: dict[tuple[int, int], str] = {}
    files: list[Path] = []
    while pending:
        current = pending.pop()
        try:
            children = sorted(current.iterdir())
        except OSError as exc:
            raise MaintainabilityInputError(f"could not inspect source tree: {current}") from exc
        for child in children:
            try:
                metadata = child.lstat()
            except OSError as exc:
                raise MaintainabilityInputError(f"could not inspect source path: {child}") from exc
            if stat.S_ISLNK(metadata.st_mode):
                raise MaintainabilityInputError(f"source tree symlinks are forbidden: {child}")
            if stat.S_ISDIR(metadata.st_mode):
                pending.append(child)
            elif stat.S_ISREG(metadata.st_mode) and child.suffix == ".py":
                identity = (metadata.st_dev, metadata.st_ino)
                relative = child.relative_to(root).as_posix()
                prior = identities.get(identity)
                if prior is not None:
                    raise MaintainabilityInputError(
                        f"source file aliases are forbidden: {prior}, {relative}"
                    )
                identities[identity] = relative
                files.append(child)
    return tuple(sorted(files))


def _radon_block_type(
    node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
    parents: dict[ast.AST, ast.AST],
) -> str | None:
    ancestors: list[ast.AST] = []
    current = parents.get(node)
    while current is not None:
        if isinstance(current, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            ancestors.append(current)
        current = parents.get(current)
    if isinstance(node, ast.ClassDef):
        return "class" if not ancestors else None
    if not ancestors:
        return "function"
    if len(ancestors) == 1 and isinstance(ancestors[0], ast.ClassDef):
        return "method"
    return None


def _expected_cc_blocks(
    root: Path,
    source_files: tuple[Path, ...],
) -> set[tuple[str, str, str, int]]:
    expected: set[tuple[str, str, str, int]] = set()
    for path in source_files:
        source = read_text_file(path, max_bytes=20_000_000)
        try:
            tree = ast.parse(source, filename=path.as_posix())
        except SyntaxError as exc:
            raise MaintainabilityInputError(f"could not parse source file: {path}") from exc
        parents = {
            child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)
        }
        relative = path.relative_to(root).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            block_type = _radon_block_type(node, parents)
            if block_type is not None:
                expected.add((relative, block_type, node.name, node.lineno))
    return expected


def _hotspot_metrics(
    root: Path,
    source_files: tuple[Path, ...],
) -> tuple[HotspotMetric, tuple[Contributor, ...]]:
    hotspots: list[tuple[Path, int]] = []
    for path in source_files:
        lines = len(
            read_text_file(
                path,
                max_bytes=20_000_000,
                errors="replace",
            ).splitlines()
        )
        if lines >= 500:
            hotspots.append((path, lines))
    hotspots.sort(key=lambda item: (-item[1], item[0].as_posix()))
    contributors = tuple(
        Contributor(
            "hotspot",
            path.relative_to(root).as_posix(),
            None,
            f"{lines} lines",
        )
        for path, lines in hotspots[:MAX_CONTRIBUTORS]
    )
    return HotspotMetric(threshold_lines=500, count=len(hotspots)), contributors


def _current_metrics(
    root: Path,
    cc_path: Path,
    mi_path: Path,
    source_files: tuple[Path, ...],
) -> tuple[Metrics, tuple[Contributor, ...]]:
    cc, cc_contributors = _cc_metrics(root, cc_path, source_files)
    mi, mi_contributors = _mi_metrics(root, mi_path, source_files)
    hotspots, hotspot_contributors = _hotspot_metrics(root, source_files)
    return (
        Metrics(
            cyclomatic_complexity=cc,
            maintainability_index=mi,
            source_hotspots=hotspots,
        ),
        (*cc_contributors, *mi_contributors, *hotspot_contributors),
    )


def _family_violations(name: str, baseline: MetricFamily, current: MetricFamily) -> list[str]:
    violations = [
        f"{name} rank {rank} count increased: "
        f"{baseline.rank_counts.value(rank)} -> {current.rank_counts.value(rank)}"
        for rank in PROTECTED_RANKS
        if current.rank_counts.value(rank) > baseline.rank_counts.value(rank)
    ]
    if RANKS.index(current.worst_rank) > RANKS.index(baseline.worst_rank):
        violations.append(
            f"{name} worst rank worsened: {baseline.worst_rank} -> {current.worst_rank}"
        )
    if current.weighted_score > baseline.weighted_score:
        violations.append(
            f"{name} weighted score increased: "
            f"{baseline.weighted_score} -> {current.weighted_score}"
        )
    return violations


def _violations(baseline: Metrics, current: Metrics) -> tuple[str, ...]:
    violations = [
        *_family_violations(
            "cyclomatic_complexity",
            baseline.cyclomatic_complexity,
            current.cyclomatic_complexity,
        ),
        *_family_violations(
            "maintainability_index",
            baseline.maintainability_index,
            current.maintainability_index,
        ),
    ]
    if current.source_hotspots.count > baseline.source_hotspots.count:
        violations.append(
            "source_hotspots count increased: "
            f"{baseline.source_hotspots.count} -> {current.source_hotspots.count}"
        )
    return tuple(violations)


def _named_contributors(
    violations: tuple[str, ...],
    contributors: tuple[Contributor, ...],
) -> tuple[str, ...]:
    family_prefixes: tuple[tuple[Family, str], ...] = (
        ("cc", "cyclomatic"),
        ("mi", "maintainability"),
        ("hotspot", "source_hotspots"),
    )
    families = tuple(
        family
        for family, prefix in family_prefixes
        if any(violation.startswith(prefix) for violation in violations)
    )
    selected = sorted(
        (item for item in contributors if item.family in families),
        key=_contributor_key,
    )
    required = [next(item for item in selected if item.family == family) for family in families]
    remainder = [item for item in selected if item not in required]
    chosen = [*required, *remainder[: MAX_CONTRIBUTORS - len(required)]]
    chosen.sort(key=_contributor_key)
    return tuple(item.render() for item in chosen)


def _contributor_key(item: Contributor) -> tuple[str, int, str]:
    weight = WEIGHTS[item.rank] if item.rank is not None else 0
    return item.family, -weight, item.path


def _artifact_report(root: Path, artifact: EvidenceArtifact) -> tuple[Path, RatchetReport]:
    path = _checked_input(root, artifact.path, label="rebase evidence")
    content = read_text_file(path, max_bytes=JSON_MAX_BYTES)
    if hashlib.sha256(content.encode("utf-8")).hexdigest() != artifact.sha256:
        raise MaintainabilityInputError(f"rebase evidence hash mismatch: {artifact.path}")
    parsed = _parse_json(content, label=path)
    return path, RatchetReport.model_validate_json(json.dumps(parsed))


def _validate_rebase(
    root: Path,
    request_path: Path,
    *,
    baseline: Baseline,
    current: Metrics,
) -> tuple[RebaseValidation, tuple[Path, Path]]:
    request = RebaseRequest.model_validate_json(json.dumps(_json_value(request_path)))
    if request.current_revision != baseline.revision:
        raise MaintainabilityInputError("rebase current_revision does not match the baseline")
    if request.issue_url == baseline.evidence.issue_url:
        raise MaintainabilityInputError("baseline rebase requires a dedicated issue")
    before_path, before = _artifact_report(root, request.before_evidence)
    after_path, after = _artifact_report(root, request.after_evidence)
    if before_path.samefile(after_path):
        raise MaintainabilityInputError("before and after evidence must not alias")
    if before.current != baseline.metrics:
        raise MaintainabilityInputError("before evidence does not match the tracked baseline")
    if after.current != current:
        raise MaintainabilityInputError("after evidence does not match current metrics")
    worsening = _violations(before.current, after.current)
    if worsening:
        raise MaintainabilityInputError(
            "rebase evidence contains protected worsening: " + "; ".join(worsening)
        )
    return (
        RebaseValidation(
            status="passed",
            current_revision=request.current_revision,
            proposed_revision=request.proposed_revision,
            issue_url=request.issue_url,
            pull_request_url=request.pull_request_url,
            before_evidence=request.before_evidence.path,
            after_evidence=request.after_evidence.path,
        ),
        (before_path, after_path),
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _root_path(args.repo_root)
        cc_path = _checked_input(root, args.radon_cc, label="Radon CC input")
        mi_path = _checked_input(root, args.radon_mi, label="Radon MI input")
        if args.baseline != TRACKED_BASELINE.as_posix():
            raise MaintainabilityInputError("normal audit must use the tracked baseline")
        baseline_path = _checked_input(root, args.baseline, label="baseline")
        baseline = _baseline(baseline_path)
        source_files = _source_python_files(root)
        current, raw_contributors = _current_metrics(
            root,
            cc_path,
            mi_path,
            source_files,
        )
        violations = _violations(baseline.metrics, current)
        contributors = _named_contributors(violations, raw_contributors)
        rebase_validation = None
        protected_paths = [cc_path, mi_path, baseline_path, *source_files]
        if args.rebase_request is not None:
            request_path = _checked_input(
                root,
                args.rebase_request,
                label="rebase request",
            )
            rebase_validation, evidence_paths = _validate_rebase(
                root,
                request_path,
                baseline=baseline,
                current=current,
            )
            protected_paths.extend((request_path, *evidence_paths))
        report = RatchetReport(
            schema_version=REPORT_SCHEMA,
            baseline_revision=baseline.revision,
            status="regressed" if violations else "passed",
            baseline=baseline.metrics,
            current=current,
            violations=violations,
            contributors=contributors,
            rebase_validation=rebase_validation,
        )
        output_path = _checked_output(
            root,
            args.output,
            baseline_path=baseline_path,
            protected_paths=tuple(protected_paths),
        )
        write_json_file(
            output_path,
            report.model_dump(mode="json", by_alias=True),
            artifact="source maintainability ratchet report",
            root=root,
            append_newline=True,
        )
    except (MaintainabilityInputError, ScriptSafetyError, ValidationError) as exc:
        print(f"source maintainability ratchet failed: {exc}", file=sys.stderr)
        return 2

    print(f"Source maintainability ratchet: {report.status}")
    print(f"Wrote source maintainability ratchet report: {output_path}")
    if violations:
        for violation in violations:
            print(f"  {violation}", file=sys.stderr)
        for contributor in contributors:
            print(f"  contributor: {contributor}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
