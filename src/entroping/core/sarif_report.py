"""SARIF report generation from Entroping local finding artifacts."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

from entroping.core.github_annotations import (
    AnnotationLevel,
    GitHubAnnotation,
    collect_github_annotations,
)
from entroping.core.hurl_runner import redact_hurl_output
from entroping.core.safe_write import SafeWriteError, safe_write_text
from entroping.models.sarif import (
    SarifArtifactLocation,
    SarifDriver,
    SarifLocation,
    SarifMessage,
    SarifPhysicalLocation,
    SarifRegion,
    SarifReport,
    SarifReportPayload,
    SarifResult,
    SarifResultLevel,
    SarifRule,
    SarifRun,
    SarifTool,
)

_RULE_ID_PREFIX = "entroping"
_SLUG_PATTERN = re.compile(r"[^a-z0-9_.]+")
_COLLAPSED_SEPARATORS = re.compile(r"[-.]{2,}")


class SarifReportError(ValueError):
    """Raised when a SARIF report cannot be built or written."""


@dataclass(frozen=True, slots=True)
class SarifReportResult:
    """Result of writing a SARIF report artifact."""

    output_path: Path
    report: SarifReport


def run_sarif_report(
    *,
    project_root: Path,
    output_path: Path,
    junit_path: Path,
    drift_path: Path,
    include_traceability: bool,
) -> SarifReportResult:
    """Collect local Entroping findings and write a SARIF report."""

    annotations = collect_github_annotations(
        junit_path=_rooted_path(junit_path, project_root),
        drift_path=_rooted_path(drift_path, project_root),
        include_traceability=include_traceability,
    )
    report = build_sarif_report(annotations, project_root=project_root)
    written = write_sarif_report(
        report,
        _rooted_path(output_path, project_root),
        root=project_root,
    )
    return SarifReportResult(output_path=written, report=report)


def build_sarif_report(
    annotations: Sequence[GitHubAnnotation],
    *,
    project_root: Path,
) -> SarifReport:
    """Build a SARIF report from sanitized Entroping annotations."""

    root = project_root.expanduser().resolve()
    rules_by_id: dict[str, SarifRule] = {}
    results: list[SarifResult] = []

    for annotation in annotations:
        title = _clean_text(annotation.title)
        rule_id = _rule_id_from_title(title)
        if rule_id not in rules_by_id:
            rules_by_id[rule_id] = SarifRule(
                id=rule_id,
                name=title,
                shortDescription=SarifMessage(text=title),
            )
        results.append(
            SarifResult(
                ruleId=rule_id,
                level=_sarif_level(annotation.level),
                message=SarifMessage(text=_clean_text(annotation.message, root=root)),
                locations=_sarif_locations(annotation, root),
            )
        )

    return SarifReport(
        runs=[
            SarifRun(
                tool=SarifTool(
                    driver=SarifDriver(rules=list(rules_by_id.values()))
                ),
                results=results,
            )
        ]
    )


def sarif_report_to_dict(report: SarifReport) -> SarifReportPayload:
    """Return a JSON-ready SARIF payload."""

    return cast(
        SarifReportPayload,
        report.model_dump(by_alias=True, exclude_none=True),
    )


def write_sarif_report(
    report: SarifReport,
    path: Path,
    *,
    root: Path | None = None,
) -> Path:
    """Write a SARIF report through the standard safe artifact writer."""

    try:
        return safe_write_text(
            path,
            json.dumps(sarif_report_to_dict(report), indent=2, sort_keys=True) + "\n",
            artifact="SARIF report",
            root=root,
        )
    except SafeWriteError as exc:
        raise SarifReportError(str(exc)) from exc


def _rooted_path(path: Path, project_root: Path) -> Path:
    expanded = path.expanduser()
    if expanded.is_absolute():
        return expanded
    return project_root / expanded


def _clean_text(value: str, *, root: Path | None = None) -> str:
    redacted = redact_hurl_output(value)
    if root is None:
        return redacted
    root_text = root.as_posix()
    return redacted.replace(f"{root_text}/", "")


def _sarif_level(level: AnnotationLevel) -> SarifResultLevel:
    if level == "error":
        return "error"
    if level == "warning":
        return "warning"
    return "note"


def _rule_id_from_title(title: str) -> str:
    normalized = title.strip()
    if normalized.startswith("Entroping drift: "):
        return f"{_RULE_ID_PREFIX}.drift.{_slug(normalized.removeprefix('Entroping drift: '))}"
    if normalized.startswith("Entroping traceability: "):
        return (
            f"{_RULE_ID_PREFIX}.traceability."
            f"{_slug(normalized.removeprefix('Entroping traceability: '))}"
        )
    if normalized == "Entroping Hurl failure":
        return f"{_RULE_ID_PREFIX}.hurl.failure"
    if normalized == "Entroping JUnit error":
        return f"{_RULE_ID_PREFIX}.junit.error"
    if normalized.startswith("Entroping "):
        return f"{_RULE_ID_PREFIX}.{_slug(normalized.removeprefix('Entroping ')).replace('-', '.')}"
    return f"{_RULE_ID_PREFIX}.{_slug(normalized)}"


def _slug(value: str) -> str:
    lowered = value.lower().replace("[redacted]", "redacted")
    normalized = _SLUG_PATTERN.sub("-", lowered).strip("-._")
    normalized = _COLLAPSED_SEPARATORS.sub(lambda match: match.group(0)[0], normalized)
    return normalized or "finding"


def _sarif_locations(annotation: GitHubAnnotation, root: Path) -> list[SarifLocation] | None:
    if annotation.file is None:
        return None

    uri = _safe_artifact_uri(annotation.file, root)
    if uri is None:
        return None

    region = SarifRegion(startLine=annotation.line) if annotation.line > 0 else None
    return [
        SarifLocation(
            physicalLocation=SarifPhysicalLocation(
                artifactLocation=SarifArtifactLocation(uri=uri),
                region=region,
            )
        )
    ]


def _safe_artifact_uri(raw_file: str, root: Path) -> str | None:
    redacted = _clean_text(raw_file).replace("\\", "/").strip()
    if not redacted:
        return None
    if "://" in redacted:
        return None

    local_path = Path(redacted)
    if local_path.is_absolute():
        try:
            return local_path.expanduser().resolve(strict=False).relative_to(root).as_posix()
        except ValueError:
            return None

    candidate = PurePosixPath(redacted)
    if candidate.is_absolute() or candidate.name in {"", "."}:
        return None
    if candidate.parts and candidate.parts[0].endswith(":"):
        return None
    if any(part in {"", ".", ".."} for part in candidate.parts):
        return None
    return candidate.as_posix()
