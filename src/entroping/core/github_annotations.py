"""GitHub Actions annotation rendering from Entroping report artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, Literal, Protocol, cast

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from entroping.bridge.story_traceability import (
    StoryTraceabilityReport,
    compile_story_traceability,
)
from entroping.core.bounded_read import BoundedReadError, read_text_bounded
from entroping.core.drift_report import DRIFT_REPORT_SCHEMA_VERSION
from entroping.core.evidence_common import LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES
from entroping.core.hurl_discovery import discover_hurl_tests
from entroping.core.hurl_runner import redact_hurl_output

AnnotationLevel = Literal["error", "warning", "notice"]
_MAX_GITHUB_ANNOTATION_ARTIFACT_BYTES: Final = LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES


class _XmlElement(Protocol):
    text: str | None

    def get(self, key: str) -> str | None: ...

    def findall(self, path: str) -> Sequence[_XmlElement]: ...


class GitHubAnnotationError(ValueError):
    """Raised when report artifacts cannot be converted into annotations."""


@dataclass(frozen=True, slots=True)
class GitHubAnnotation:
    """One GitHub Actions workflow-command annotation."""

    level: AnnotationLevel
    title: str
    message: str
    file: str | None = None
    line: int = 1


def collect_github_annotations(
    *,
    junit_path: Path,
    drift_path: Path,
    include_traceability: bool,
) -> tuple[GitHubAnnotation, ...]:
    """Collect annotations from available local report artifacts."""

    annotations = [
        *annotations_from_junit_report(junit_path),
        *annotations_from_drift_report(drift_path),
    ]
    if include_traceability:
        hurl_tests = discover_hurl_tests() if Path("tests").exists() else []
        annotations.extend(
            annotations_from_traceability_report(compile_story_traceability(hurl_tests))
        )
    return tuple(annotations)


def annotations_from_junit_report(path: Path) -> tuple[GitHubAnnotation, ...]:
    """Return GitHub annotations for JUnit failures and errors."""

    if not path.exists():
        return ()

    try:
        root = cast(_XmlElement, ElementTree.parse(path).getroot())
    except DefusedXmlException as exc:
        msg = f"Could not parse JUnit report {path}: unsafe XML construct: {exc}"
        raise GitHubAnnotationError(msg) from exc
    except ElementTree.ParseError as exc:
        msg = f"Could not parse JUnit report {path}: {exc}"
        raise GitHubAnnotationError(msg) from exc
    except OSError as exc:
        msg = f"Could not read JUnit report {path}: {exc}"
        raise GitHubAnnotationError(msg) from exc
    annotations: list[GitHubAnnotation] = []
    for testcase in root.findall(".//testcase"):
        for element_name, title in (
            ("failure", "Entroping Hurl failure"),
            ("error", "Entroping JUnit error"),
        ):
            for element in testcase.findall(element_name):
                message = _annotation_message(
                    element.text or element.get("message") or testcase.get("name") or title
                )
                annotations.append(
                    GitHubAnnotation(
                        level="error",
                        title=title,
                        message=message,
                        file=_junit_test_path(testcase, message),
                        line=1,
                    )
                )
    return tuple(annotations)


def annotations_from_drift_report(path: Path) -> tuple[GitHubAnnotation, ...]:
    """Return GitHub annotations for drift findings."""

    if not path.exists():
        return ()

    data = _load_json_object(path, artifact="drift report")
    _validate_drift_report_schema(data, path)
    raw_findings = data.get("findings", [])
    if not isinstance(raw_findings, list):
        msg = f"Drift report {path} must contain a findings list"
        raise GitHubAnnotationError(msg)

    annotations: list[GitHubAnnotation] = []
    for raw_finding in raw_findings:
        if not isinstance(raw_finding, dict):
            continue
        kind = _string_field(raw_finding.get("kind"), fallback="unknown")
        message = _annotation_message(_string_field(raw_finding.get("message"), fallback=kind))
        annotations.append(
            GitHubAnnotation(
                level=_drift_level(raw_finding.get("severity")),
                title=f"Entroping drift: {kind}",
                message=message,
                file=_finding_file(raw_finding.get("path")),
                line=1,
            )
        )
    return tuple(annotations)


def annotations_from_traceability_report(
    report: StoryTraceabilityReport,
) -> tuple[GitHubAnnotation, ...]:
    """Return GitHub annotations for traceability findings."""

    annotations: list[GitHubAnnotation] = []
    for finding in report.findings:
        annotations.append(
            GitHubAnnotation(
                level=_traceability_level(finding.kind),
                title=f"Entroping traceability: {finding.kind}",
                message=_annotation_message(finding.message),
                file=_safe_traceability_file(finding.test_path),
                line=1,
            )
        )
    return tuple(annotations)


def render_github_annotation(annotation: GitHubAnnotation) -> str:
    """Render a GitHub Actions workflow command for one annotation."""

    properties = []
    if annotation.file is not None:
        safe_file = _safe_file(annotation.file)
        if safe_file is not None:
            properties.append(f"file={_escape_property(safe_file)}")
            properties.append(f"line={annotation.line}")
    properties.append(f"title={_escape_property(annotation.title)}")
    return (
        f"::{annotation.level} {','.join(properties)}::"
        f"{_escape_data(_annotation_message(annotation.message))}"
    )


def main(argv: list[str] | None = None) -> int:
    """Emit GitHub Actions annotations from local Entroping report artifacts."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", type=Path, default=Path("reports") / "junit.xml")
    parser.add_argument("--drift", type=Path, default=Path("reports") / "drift.json")
    parser.add_argument(
        "--traceability",
        action="store_true",
        help="Compile local Hurl metadata and annotate traceability findings.",
    )
    parser.add_argument("--max-annotations", type=int, default=50)
    args = parser.parse_args(argv)

    try:
        annotations = collect_github_annotations(
            junit_path=args.junit,
            drift_path=args.drift,
            include_traceability=args.traceability,
        )
    except GitHubAnnotationError as exc:
        print(f"error: {_annotation_message(str(exc))}", file=sys.stderr)
        return 1
    max_annotations = max(0, args.max_annotations)
    for annotation in annotations[:max_annotations]:
        print(render_github_annotation(annotation))
    if len(annotations) > max_annotations:
        omitted = len(annotations) - max_annotations
        print(
            render_github_annotation(
                GitHubAnnotation(
                    level="notice",
                    title="Entroping annotations truncated",
                    message=f"{omitted} annotation(s) omitted by --max-annotations.",
                )
            )
        )
    return 0


def _load_json_object(path: Path, *, artifact: str) -> dict[str, object]:
    try:
        raw_json = read_text_bounded(
            path,
            max_bytes=_MAX_GITHUB_ANNOTATION_ARTIFACT_BYTES,
            label=artifact,
        )
        data = json.loads(raw_json)
    except BoundedReadError as exc:
        raise GitHubAnnotationError(str(exc)) from exc
    except json.JSONDecodeError as exc:
        msg = f"Could not parse {artifact} {path}: {exc}"
        raise GitHubAnnotationError(msg) from exc
    if not isinstance(data, dict):
        msg = f"{artifact.capitalize()} {path} must be a JSON object"
        raise GitHubAnnotationError(msg)
    return data


def _validate_drift_report_schema(data: dict[str, object], path: Path) -> None:
    schema_version = data.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version.strip():
        msg = (
            f"drift report schema_version in {path} must declare schema_version "
            f"{DRIFT_REPORT_SCHEMA_VERSION}"
        )
        raise GitHubAnnotationError(msg)
    if schema_version != DRIFT_REPORT_SCHEMA_VERSION:
        msg = (
            f"Unsupported drift report schema_version in {path}; expected "
            f"{DRIFT_REPORT_SCHEMA_VERSION}"
        )
        raise GitHubAnnotationError(msg)


def _junit_test_path(testcase: _XmlElement, message: str) -> str | None:
    for line in message.splitlines():
        if line.startswith("path: "):
            return _safe_file(line.removeprefix("path: "))

    name = testcase.get("name")
    if not name:
        return None
    classname = testcase.get("classname") or ""
    if not classname or classname == ".":
        return _safe_file(name)
    return _safe_file(str(Path(classname) / name))


def _finding_file(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    stripped = value.strip()
    if stripped == "*" or stripped.startswith("dependency:"):
        return None
    return _safe_file(stripped)


def _safe_file(value: str) -> str | None:
    normalized = " ".join(value.replace("\\", "/").split())
    if not normalized or "://" in normalized:
        return None

    candidate = PurePosixPath(normalized)
    if candidate.is_absolute() or candidate.name in {"", "."}:
        return None
    if candidate.parts and candidate.parts[0].endswith(":"):
        return None
    if any(part in {"", ".", ".."} for part in candidate.parts):
        return None
    return candidate.as_posix()


def _safe_traceability_file(path: Path | None) -> str | None:
    if path is None:
        return None
    if not path.is_absolute():
        return _safe_file(str(path))

    try:
        relative_path = path.expanduser().resolve(strict=False).relative_to(
            Path.cwd().resolve(strict=False)
        )
    except ValueError:
        return None
    return _safe_file(relative_path.as_posix())


def _string_field(value: object, *, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return " ".join(value.split())
    return fallback


def _drift_level(value: object) -> AnnotationLevel:
    if value == "error":
        return "error"
    if value == "warning":
        return "warning"
    return "notice"


def _traceability_level(kind: str) -> AnnotationLevel:
    if kind == "missing_story_id":
        return "error"
    return "warning"


def _annotation_message(value: str) -> str:
    return redact_hurl_output(value)


def _escape_property(value: str) -> str:
    return _escape_data(value).replace(":", "%3A").replace(",", "%2C")


def _escape_data(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
