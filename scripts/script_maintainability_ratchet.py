#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Annotated, Final, Literal, Never, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.script_safety import (  # noqa: E402
    ScriptSafetyError,
    read_text_file,
    write_json_file,
)

TRACKED_BASELINE: Final = PurePosixPath(
    "docs/meta/script-maintainability-ratchet-baseline.json"
)
BASELINE_SCHEMA: Final = "entroping.script-maintainability-ratchet-baseline.v1"
REPORT_SCHEMA: Final = "entroping.script-maintainability-ratchet-report.v1"
RANKS: Final[tuple[Rank, ...]] = ("A", "B", "C", "D", "E", "F")
PROTECTED_RANKS: Final[tuple[Rank, ...]] = ("D", "E", "F")
WEIGHTS: Final[dict[Rank, int]] = {"A": 0, "B": 1, "C": 3, "D": 8, "E": 13, "F": 21}
HOTSPOT_LINES: Final = 500
MAX_CONTRIBUTORS: Final = 20
JSON_MAX_BYTES: Final = 10_000_000

Rank = Literal["A", "B", "C", "D", "E", "F"]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]


class MaintainabilityInputError(ValueError):
    pass


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class RankCounts(StrictModel):
    a: NonNegativeInt = Field(alias="A")
    b: NonNegativeInt = Field(alias="B")
    c: NonNegativeInt = Field(alias="C")
    d: NonNegativeInt = Field(alias="D")
    e: NonNegativeInt = Field(alias="E")
    f: NonNegativeInt = Field(alias="F")

    def value(self, rank: Rank) -> int:
        return {"A": self.a, "B": self.b, "C": self.c, "D": self.d, "E": self.e, "F": self.f}[rank]

    @property
    def weighted_score(self) -> int:
        return sum(self.value(rank) * WEIGHTS[rank] for rank in RANKS)

    @property
    def worst_rank(self) -> Rank:
        return next((rank for rank in reversed(RANKS) if self.value(rank)), "A")


class MetricFamily(StrictModel):
    rank_counts: RankCounts
    weighted_score: NonNegativeInt
    worst_rank: Rank

    @model_validator(mode="after")
    def validate_derived_values(self) -> Self:
        if self.weighted_score != self.rank_counts.weighted_score:
            raise MaintainabilityInputError("weighted_score does not match rank_counts")
        if self.worst_rank != self.rank_counts.worst_rank:
            raise MaintainabilityInputError("worst_rank does not match rank_counts")
        return self


class HotspotMetric(StrictModel):
    threshold_lines: PositiveInt
    count: NonNegativeInt
    files: dict[str, PositiveInt]

    @model_validator(mode="after")
    def validate_hotspots(self) -> Self:
        if self.threshold_lines != HOTSPOT_LINES:
            raise MaintainabilityInputError("script hotspot threshold must remain 500")
        if self.count != len(self.files):
            raise MaintainabilityInputError("script hotspot count must match recorded files")
        for raw_path, lines in self.files.items():
            relative = _relative_path(raw_path, label="script hotspot path")
            if relative.suffix != ".py" or relative.parts[0] != "scripts":
                raise MaintainabilityInputError(
                    f"script hotspot path is outside the allowed scope: {raw_path}"
                )
            if lines < HOTSPOT_LINES:
                raise MaintainabilityInputError(
                    f"script hotspot line count is below 500: {raw_path}"
                )
        return self


class Metrics(StrictModel):
    cyclomatic_complexity: MetricFamily
    script_hotspots: HotspotMetric


class Evidence(StrictModel):
    issue_url: Annotated[str, Field(strict=True, min_length=1)]
    cc_command: Annotated[str, Field(strict=True, min_length=1)]
    hotspot_definition: Annotated[str, Field(strict=True, min_length=1)]

    @model_validator(mode="after")
    def validate_issue_url(self) -> Self:
        if re.fullmatch(r"https://github\.com/[^/]+/[^/]+/issues/[1-9]\d*", self.issue_url) is None:
            raise MaintainabilityInputError("evidence issue_url must name a GitHub issue")
        return self


class Baseline(StrictModel):
    schema_version: Literal["entroping.script-maintainability-ratchet-baseline.v1"]
    revision: PositiveInt
    owner: Annotated[str, Field(strict=True, min_length=1)]
    reviewed_on: Annotated[str, Field(strict=True, pattern=r"^\d{4}-\d{2}-\d{2}$")]
    evidence: Evidence
    weights: RankCounts
    metrics: Metrics

    @model_validator(mode="after")
    def validate_weights(self) -> Self:
        if any(self.weights.value(rank) != WEIGHTS[rank] for rank in RANKS):
            raise MaintainabilityInputError("baseline weights do not match protected policy")
        return self


@dataclass(frozen=True, slots=True)
class Contributor:
    family: Literal["cc", "hotspot"]
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
            "Compare Python script maintainability with an immutable tracked baseline."
        )
    )
    parser.add_argument("--repo-root", default=".", help="Repository root.")
    parser.add_argument("--radon-cc", required=True, help="Radon CC JSON from `scripts`.")
    parser.add_argument("--baseline", required=True, help="Tracked immutable baseline JSON.")
    parser.add_argument("--output", required=True, help="Ignored deterministic report JSON.")
    return parser.parse_args(argv)


def _relative_path(raw: str, *, label: str) -> PurePosixPath:
    if not raw or "\\" in raw:
        raise MaintainabilityInputError(f"{label} must be a canonical relative POSIX path")
    path = PurePosixPath(raw)
    if path.is_absolute() or path.as_posix() != raw:
        raise MaintainabilityInputError(f"{label} must be a canonical relative POSIX path")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise MaintainabilityInputError(f"{label} contains a forbidden path alias")
    return path


def _root_path(raw: str) -> Path:
    candidate = Path(raw).expanduser()
    if candidate.is_symlink():
        raise MaintainabilityInputError("repository root must not be a symlink")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_dir():
        raise MaintainabilityInputError("repository root must be a directory")
    return resolved


def _checked_input(root: Path, raw: str, *, label: str) -> Path:
    relative = _relative_path(raw, label=label)
    current = root
    for part in relative.parts:
        current /= part
        metadata = current.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise MaintainabilityInputError(f"{label} must not traverse a symlink")
    if not stat.S_ISREG(current.stat().st_mode):
        raise MaintainabilityInputError(f"{label} must be a regular file")
    return current


def _checked_output(root: Path, raw: str, *, inputs: tuple[Path, ...]) -> Path:
    relative = _relative_path(raw, label="output")
    output = root.joinpath(*relative.parts)
    if relative == TRACKED_BASELINE:
        raise MaintainabilityInputError("normal audit cannot overwrite the tracked baseline")
    if not relative.parts or relative.parts[0] != "reports":
        raise MaintainabilityInputError("output must be under reports")
    if output.exists() and any(output.samefile(path) for path in inputs):
        raise MaintainabilityInputError("output must not alias an input")
    return output


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise MaintainabilityInputError("duplicate JSON key is forbidden")
        result[key] = value
    return result


def _reject_non_finite(raw: str) -> Never:
    raise MaintainabilityInputError(f"non-finite JSON number is forbidden: {raw}")


def _json_value(path: Path) -> object:
    content = read_text_file(path, max_bytes=JSON_MAX_BYTES)
    try:
        return json.loads(
            content,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_non_finite,
        )
    except json.JSONDecodeError as exc:
        raise MaintainabilityInputError(f"invalid JSON in {path}: {exc.msg}") from exc


def _script_files(root: Path) -> tuple[Path, ...]:
    script_root = root / "scripts"
    if not script_root.is_dir() or script_root.is_symlink():
        raise MaintainabilityInputError("scripts must be a regular directory")
    files: list[Path] = []
    for path in sorted(script_root.rglob("*")):
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise MaintainabilityInputError(f"script tree symlinks are forbidden: {path}")
        if stat.S_ISREG(metadata.st_mode) and path.suffix == ".py":
            files.append(path)
    return tuple(files)


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


def _expected_blocks(root: Path, files: tuple[Path, ...]) -> set[tuple[str, str, str, int]]:
    expected: set[tuple[str, str, str, int]] = set()
    for path in files:
        source = read_text_file(path, max_bytes=20_000_000)
        try:
            tree = ast.parse(source, filename=path.as_posix())
        except SyntaxError as exc:
            raise MaintainabilityInputError(f"could not parse script: {path}") from exc
        parents = {
            child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)
        }
        relative = path.relative_to(root).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                block_type = _radon_block_type(node, parents)
                if block_type is not None:
                    expected.add((relative, block_type, node.name, node.lineno))
    return expected


def _rank(raw: object) -> Rank:
    if not isinstance(raw, str) or raw not in RANKS:
        raise MaintainabilityInputError("Radon CC rank must be one of A, B, C, D, E, F")
    return raw


def _positive_int(raw: object, *, label: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        raise MaintainabilityInputError(f"{label} must be a positive integer")
    return raw


def _complexity_metrics(
    root: Path,
    radon_path: Path,
    files: tuple[Path, ...],
) -> tuple[MetricFamily, tuple[Contributor, ...]]:
    payload = _json_value(radon_path)
    if not isinstance(payload, dict):
        raise MaintainabilityInputError("Radon CC JSON must be an object")
    counts: dict[Rank, int] = dict.fromkeys(RANKS, 0)
    observed: set[tuple[str, str, str, int]] = set()
    contributors: list[Contributor] = []
    for raw_path in sorted(payload):
        relative = _relative_path(raw_path, label="Radon script key")
        if relative.suffix != ".py" or relative.parts[0] != "scripts":
            raise MaintainabilityInputError(
                f"Radon script key is outside the allowed scope: {raw_path}"
            )
        _checked_input(root, raw_path, label="Radon script")
        entries = payload[raw_path]
        if not isinstance(entries, list):
            raise MaintainabilityInputError(f"Radon CC entries must be an array: {raw_path}")
        for entry in entries:
            if not isinstance(entry, dict):
                raise MaintainabilityInputError(f"Radon CC entry must be an object: {raw_path}")
            block_type = entry.get("type")
            name = entry.get("name")
            if block_type not in {"class", "function", "method"}:
                raise MaintainabilityInputError("Radon CC type must name a code block")
            if not isinstance(name, str) or not name:
                raise MaintainabilityInputError("Radon CC name must be non-empty")
            rank = _rank(entry.get("rank"))
            line = _positive_int(entry.get("lineno"), label="Radon CC lineno")
            complexity = _positive_int(entry.get("complexity"), label="Radon CC complexity")
            key = (relative.as_posix(), block_type, name, line)
            if key in observed:
                raise MaintainabilityInputError(f"duplicate Radon CC block: {raw_path}:{line}")
            observed.add(key)
            counts[rank] += 1
            contributors.append(
                Contributor("cc", f"{raw_path}:{line} {name}", rank, str(complexity))
            )
    if observed != _expected_blocks(root, files):
        raise MaintainabilityInputError(
            "Radon CC evidence must exactly match script code blocks"
        )
    rank_counts = RankCounts.model_validate(counts)
    family = MetricFamily(
        rank_counts=rank_counts,
        weighted_score=rank_counts.weighted_score,
        worst_rank=rank_counts.worst_rank,
    )
    return family, tuple(contributors)


def _hotspot_metrics(
    root: Path,
    files: tuple[Path, ...],
) -> tuple[HotspotMetric, tuple[Contributor, ...]]:
    hotspots: dict[str, int] = {}
    contributors: list[Contributor] = []
    for path in files:
        lines = len(read_text_file(path, max_bytes=20_000_000, errors="replace").splitlines())
        if lines >= HOTSPOT_LINES:
            relative = path.relative_to(root).as_posix()
            hotspots[relative] = lines
            contributors.append(Contributor("hotspot", relative, None, f"{lines} lines"))
    contributors.sort(key=lambda item: (-int(item.detail.split()[0]), item.path))
    return (
        HotspotMetric(
            threshold_lines=HOTSPOT_LINES,
            count=len(hotspots),
            files=dict(sorted(hotspots.items())),
        ),
        tuple(contributors),
    )


def _violations(baseline: Metrics, current: Metrics) -> tuple[str, ...]:
    before = baseline.cyclomatic_complexity
    after = current.cyclomatic_complexity
    violations = [
        f"cyclomatic_complexity rank {rank} count increased: "
        f"{before.rank_counts.value(rank)} -> {after.rank_counts.value(rank)}"
        for rank in PROTECTED_RANKS
        if after.rank_counts.value(rank) > before.rank_counts.value(rank)
    ]
    if RANKS.index(after.worst_rank) > RANKS.index(before.worst_rank):
        violations.append(
            f"cyclomatic_complexity worst rank worsened: {before.worst_rank} -> {after.worst_rank}"
        )
    if after.weighted_score > before.weighted_score:
        violations.append(
            "cyclomatic_complexity weighted score increased: "
            f"{before.weighted_score} -> {after.weighted_score}"
        )
    if current.script_hotspots.count > baseline.script_hotspots.count:
        violations.append(
            "script_hotspots count increased: "
            f"{baseline.script_hotspots.count} -> {current.script_hotspots.count}"
        )
    for path, lines in current.script_hotspots.files.items():
        accepted = baseline.script_hotspots.files.get(path)
        if accepted is None:
            violations.append(f"script_hotspots new file: {path} untracked -> {lines} lines")
        elif lines > accepted:
            violations.append(f"script_hotspots file grew: {path} {accepted} -> {lines} lines")
    return tuple(violations)


def _named_contributors(
    violations: tuple[str, ...],
    contributors: tuple[Contributor, ...],
) -> tuple[str, ...]:
    families = {
        "cc" if violation.startswith("cyclomatic") else "hotspot"
        for violation in violations
    }
    selected = [item for item in contributors if item.family in families]
    selected.sort(
        key=lambda item: (
            item.family,
            -(WEIGHTS[item.rank] if item.rank is not None else 0),
            item.path,
        )
    )
    return tuple(item.render() for item in selected[:MAX_CONTRIBUTORS])


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _root_path(args.repo_root)
        if _relative_path(args.baseline, label="baseline") != TRACKED_BASELINE:
            raise MaintainabilityInputError("normal audit requires the tracked baseline")
        radon_path = _checked_input(root, args.radon_cc, label="Radon CC report")
        baseline_path = _checked_input(root, args.baseline, label="tracked baseline")
        output_path = _checked_output(root, args.output, inputs=(radon_path, baseline_path))
        baseline = Baseline.model_validate(_json_value(baseline_path))
        files = _script_files(root)
        complexity, complexity_contributors = _complexity_metrics(
            root, radon_path, files
        )
        hotspots, hotspot_contributors = _hotspot_metrics(root, files)
        current = Metrics(
            cyclomatic_complexity=complexity,
            script_hotspots=hotspots,
        )
        violations = _violations(baseline.metrics, current)
        contributors = _named_contributors(
            violations,
            (*complexity_contributors, *hotspot_contributors),
        )
        report = {
            "schema_version": REPORT_SCHEMA,
            "baseline_revision": baseline.revision,
            "status": "regressed" if violations else "passed",
            "baseline": baseline.metrics.model_dump(mode="json", by_alias=True),
            "current": current.model_dump(mode="json", by_alias=True),
            "violations": list(violations),
            "contributors": list(contributors),
        }
        write_json_file(
            output_path,
            report,
            artifact="script maintainability report",
            root=root,
            append_newline=True,
        )
    except (MaintainabilityInputError, ScriptSafetyError, ValidationError, OSError) as exc:
        print(f"script maintainability input error: {exc}", file=sys.stderr)
        return 2

    if violations:
        print("Script maintainability ratchet failed:", file=sys.stderr)
        for violation in violations:
            print(f"  {violation}", file=sys.stderr)
        for contributor in contributors:
            print(f"  contributor: {contributor}", file=sys.stderr)
        return 1
    print(
        "Script maintainability ratchet passed: "
        f"weighted score {current.cyclomatic_complexity.weighted_score}, "
        f"worst rank {current.cyclomatic_complexity.worst_rank}, "
        f"hotspots {current.script_hotspots.count}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
