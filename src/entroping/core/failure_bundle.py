"""Sanitized failure bundle generation for local bug handoff."""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

from entroping.core.bounded_read import BoundedReadError, read_text_bounded
from entroping.core.evidence_common import LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES
from entroping.core.hurl_runner import redact_hurl_output
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.report_rendering import render_bug_report
from entroping.core.report_serialization import (
    RUN_REPORT_SCHEMA_VERSION,
    load_run_report,
    run_report_to_dict,
)
from entroping.core.safe_write import SafeWriteError, safe_write_text
from entroping.hurl_source import HurlSourceTooLargeError, read_hurl_source_text
from entroping.models.hurl import (
    HurlMetadataSyntaxError,
    HurlTest,
    parse_hurl_exchanges,
    parse_hurl_metadata,
)
from entroping.models.report import RunReport, RunTestReport

FAILURE_BUNDLE_SCHEMA_VERSION: Final = "entroping.failure-bundle.v1"
HURL_METADATA_SCHEMA_VERSION: Final = "entroping.hurl-metadata.v1"
_MAX_FAILURE_BUNDLE_ARTIFACT_BYTES: Final = LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES

_DEFAULT_OUTPUT_DIR = Path("reports") / "failure-bundle"
_OPTIONAL_TEXT_ARTIFACTS: Final = (
    (Path("reports") / "junit.xml", "junit", "junit.xml"),
    (Path("reports") / "run-latest.html", "html", "run-latest.html"),
    (Path("reports") / "effective-policy.md", "effective_policy", "effective-policy.md"),
    (Path("reports") / "effective-policy.json", "effective_policy", "effective-policy.json"),
    (Path("reports") / "redaction-review.md", "redaction_review", "redaction-review.md"),
    (Path("reports") / "redaction-review.html", "redaction_review", "redaction-review.html"),
)


class FailureBundleError(ValueError):
    """Raised when a sanitized failure bundle cannot be generated."""


@dataclass(frozen=True, slots=True)
class FailureBundleArtifact:
    """One artifact included in a failure bundle manifest."""

    kind: str
    path: str
    source_path: str
    schema_version: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class FailureBundleResult:
    """Result of a successful failure bundle workflow."""

    output_dir: Path
    manifest_path: Path
    artifacts: tuple[FailureBundleArtifact, ...]


def create_failure_bundle(
    *,
    project_root: Path,
    output_dir: Path | None = None,
    latest_run_path: Path | None = None,
) -> FailureBundleResult:
    """Create a sanitized local failure bundle from the latest failed run."""

    root = project_root.expanduser().resolve()
    latest_path = _resolve_required_artifact(
        root,
        latest_run_path or Path(".entroping") / "latest-run.json",
        artifact="latest run",
        missing_message="No latest run found. Run entroping run before report failure-bundle.",
        allow_local_state=True,
    )

    try:
        report = load_run_report(latest_path)
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        msg = f"Could not load latest run report {latest_path}: {exc}"
        raise FailureBundleError(msg) from exc

    sanitized_report = _sanitize_run_report(report)
    failed_tests = _failed_test_metadata(sanitized_report, root=root)
    if not failed_tests:
        msg = "Latest Entroping run has no failures to bundle."
        raise FailureBundleError(msg)

    bundle_dir = _prepare_bundle_dir(root, output_dir or _DEFAULT_OUTPUT_DIR)
    artifacts: list[FailureBundleArtifact] = []

    artifacts.append(
        _write_bundle_text(
            root=root,
            bundle_dir=bundle_dir,
            relative_path=Path("run-latest.json"),
            content=json.dumps(run_report_to_dict(sanitized_report), indent=2, sort_keys=True)
            + "\n",
            kind="run_json",
            source_path=_display_path(latest_path, root),
            schema_version=RUN_REPORT_SCHEMA_VERSION,
        )
    )
    artifacts.append(
        _write_bundle_text(
            root=root,
            bundle_dir=bundle_dir,
            relative_path=Path("bug.md"),
            content=render_bug_report(sanitized_report),
            kind="bug_markdown",
            source_path="generated",
            schema_version="entroping.bug-report.md",
        )
    )
    artifacts.append(
        _write_bundle_text(
            root=root,
            bundle_dir=bundle_dir,
            relative_path=Path("hurl-metadata.json"),
            content=json.dumps(
                {
                    "schema_version": HURL_METADATA_SCHEMA_VERSION,
                    "tests": failed_tests,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            kind="hurl_metadata",
            source_path="generated",
            schema_version=HURL_METADATA_SCHEMA_VERSION,
        )
    )

    for artifact_path, kind, bundle_name in _OPTIONAL_TEXT_ARTIFACTS:
        source_path = _resolve_optional_artifact(root, artifact_path, artifact=kind)
        if source_path is None:
            continue
        try:
            content = redact_hurl_output(
                read_text_bounded(
                    source_path,
                    max_bytes=_MAX_FAILURE_BUNDLE_ARTIFACT_BYTES,
                    label=f"{kind} artifact",
                )
            )
        except BoundedReadError as exc:
            raise FailureBundleError(str(exc)) from exc
        artifacts.append(
            _write_bundle_text(
                root=root,
                bundle_dir=bundle_dir,
                relative_path=Path(bundle_name),
                content=content,
                kind=kind,
                source_path=_display_path(source_path, root),
                schema_version=_schema_version_for_optional_artifact(bundle_name),
            )
        )

    manifest = {
        "schema_version": FAILURE_BUNDLE_SCHEMA_VERSION,
        "project": sanitized_report.project,
        "environment": sanitized_report.environment,
        "generated_at": sanitized_report.generated_at,
        "summary": {
            "total": sanitized_report.summary.total,
            "passed": sanitized_report.summary.passed,
            "failed": sanitized_report.summary.failed,
            "exit_code": sanitized_report.summary.exit_code,
        },
        "failed_tests": failed_tests,
        "artifacts": [
            {
                "kind": artifact.kind,
                "path": artifact.path,
                "source_path": artifact.source_path,
                "schema_version": artifact.schema_version,
                "size_bytes": artifact.size_bytes,
                "sha256": artifact.sha256,
            }
            for artifact in sorted(artifacts, key=lambda item: item.path)
        ],
    }
    manifest_artifact = _write_bundle_text(
        root=root,
        bundle_dir=bundle_dir,
        relative_path=Path("manifest.json"),
        content=json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        kind="manifest",
        source_path="generated",
        schema_version=FAILURE_BUNDLE_SCHEMA_VERSION,
    )
    return FailureBundleResult(
        output_dir=bundle_dir,
        manifest_path=bundle_dir / manifest_artifact.path,
        artifacts=tuple(artifacts),
    )


def _sanitize_run_report(report: RunReport) -> RunReport:
    return replace(
        report,
        tests=tuple(
            replace(
                test,
                stdout=redact_hurl_output(test.stdout),
                stderr=redact_hurl_output(test.stderr),
            )
            for test in report.tests
        ),
    )


def _failed_test_metadata(report: RunReport, *, root: Path) -> list[dict[str, object]]:
    metadata: list[dict[str, object]] = []
    for test in report.tests:
        if test.status == "passed" and test.exit_code == 0:
            continue
        metadata.append(_hurl_metadata_for_failed_test(test, root=root))
    return metadata


def _hurl_metadata_for_failed_test(test: RunTestReport, *, root: Path) -> dict[str, object]:
    source_path = _resolve_failed_test_path(root, test.path)
    discovered = _discover_single_hurl_test(source_path)
    return {
        "path": _display_path(source_path, root),
        "status": test.status,
        "rule_ids": list(test.rule_ids),
        "tags": sorted(discovered.tags) if discovered is not None else [],
        "metadata": (
            _redacted_hurl_metadata(discovered.metadata.meta)
            if discovered is not None
            else {}
        ),
        "exchanges": (
            [
                {"method": exchange.method, "path": exchange.path}
                for exchange in discovered.exchanges
            ]
            if discovered is not None
            else []
        ),
    }


def _discover_single_hurl_test(path: Path) -> HurlTest | None:
    if not path.exists():
        return None
    if path.suffix != ".hurl":
        msg = f"Expected a .hurl file, got: {path}"
        raise FailureBundleError(msg)
    try:
        content = read_hurl_source_text(path)
        return HurlTest(
            path=path.resolve(),
            metadata=parse_hurl_metadata(content, source=path),
            exchanges=parse_hurl_exchanges(content),
        )
    except (
        HurlMetadataSyntaxError,
        HurlSourceTooLargeError,
        OSError,
        UnicodeDecodeError,
    ) as exc:
        raise FailureBundleError(str(exc)) from exc


def _redacted_hurl_metadata(metadata: Mapping[str, str]) -> dict[str, str]:
    return {
        key: redact_hurl_output(value)
        for key, value in sorted(metadata.items())
    }


def _resolve_failed_test_path(root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        msg = f"failed Hurl test path must stay inside the project: {raw_path}"
        raise FailureBundleError(msg) from exc
    _reject_symlink_path(resolved, root=root, artifact="failed Hurl test")
    if resolved.exists() and not resolved.is_file():
        msg = f"failed Hurl test path is not a file: {_display_path(resolved, root)}"
        raise FailureBundleError(msg)
    return resolved


def _prepare_bundle_dir(root: Path, raw_output_dir: Path) -> Path:
    output_dir = raw_output_dir.expanduser()
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    _reject_symlink_path(output_dir, root=root, artifact="failure bundle output")
    resolved = output_dir.resolve(strict=False)
    try:
        relative_parts = resolved.relative_to(root).parts
    except ValueError as exc:
        msg = f"failure bundle output path must stay inside the project: {raw_output_dir}"
        raise FailureBundleError(msg) from exc
    if relative_parts and relative_parts[0] in {".entroping", "envs"}:
        msg = "failure bundle output must not be written into .entroping or envs"
        raise FailureBundleError(msg)
    if resolved.exists() and not resolved.is_dir():
        msg = f"failure bundle output path is not a directory: {_display_path(resolved, root)}"
        raise FailureBundleError(msg)
    try:
        resolved.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        msg = f"Could not create failure bundle directory {resolved}: {exc}"
        raise FailureBundleError(msg) from exc
    return resolved


def _resolve_required_artifact(
    root: Path,
    raw_path: Path,
    *,
    artifact: str,
    missing_message: str,
    allow_local_state: bool,
) -> Path:
    path = _resolve_artifact_path(
        root,
        raw_path,
        artifact=artifact,
        allow_local_state=allow_local_state,
    )
    if not path.exists():
        raise FailureBundleError(missing_message)
    if not path.is_file():
        msg = f"{artifact} artifact is not a file: {_display_path(path, root)}"
        raise FailureBundleError(msg)
    return path


def _resolve_optional_artifact(root: Path, raw_path: Path, *, artifact: str) -> Path | None:
    path = _resolve_artifact_path(root, raw_path, artifact=artifact, allow_local_state=False)
    if not path.exists():
        return None
    if not path.is_file():
        msg = f"unsafe artifact is not a file: {_display_path(path, root)}"
        raise FailureBundleError(msg)
    return path


def _resolve_artifact_path(
    root: Path,
    raw_path: Path,
    *,
    artifact: str,
    allow_local_state: bool,
) -> Path:
    path = raw_path.expanduser()
    if not path.is_absolute():
        path = root / path
    _reject_symlink_path(path, root=root, artifact=artifact)
    resolved = path.resolve(strict=False)
    try:
        relative_parts = resolved.relative_to(root).parts
    except ValueError as exc:
        msg = f"unsafe artifact path must stay inside the project: {raw_path}"
        raise FailureBundleError(msg) from exc
    if relative_parts and relative_parts[0] in {"envs"}:
        msg = f"unsafe artifact path refuses local env files: {raw_path}"
        raise FailureBundleError(msg)
    if (
        relative_parts
        and relative_parts[0] == ".entroping"
        and not allow_local_state
    ):
        msg = f"unsafe artifact path refuses local state files: {raw_path}"
        raise FailureBundleError(msg)
    return resolved


def _reject_symlink_path(path: Path, *, root: Path, artifact: str) -> None:
    try:
        symlink_path = first_symlink_path_component(path, root=root)
    except ValueError as exc:
        msg = f"unsafe artifact path must stay inside the project: {path}"
        raise FailureBundleError(msg) from exc
    if symlink_path is not None:
        msg = f"unsafe artifact path uses symlinked component for {artifact}: {symlink_path}"
        raise FailureBundleError(msg)


def _write_bundle_text(
    *,
    root: Path,
    bundle_dir: Path,
    relative_path: Path,
    content: str,
    kind: str,
    source_path: str,
    schema_version: str,
) -> FailureBundleArtifact:
    if relative_path.is_absolute() or ".." in relative_path.parts:
        msg = f"failure bundle artifact path must be relative and local: {relative_path}"
        raise FailureBundleError(msg)
    destination = bundle_dir / relative_path
    try:
        safe_write_text(
            destination,
            content,
            artifact=f"failure bundle {kind}",
            root=root,
        )
    except SafeWriteError as exc:
        raise FailureBundleError(str(exc)) from exc
    data = destination.read_bytes()
    return FailureBundleArtifact(
        kind=kind,
        path=relative_path.as_posix(),
        source_path=source_path,
        schema_version=schema_version,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


def _schema_version_for_optional_artifact(bundle_name: str) -> str:
    if bundle_name == "junit.xml":
        return "junit.xml"
    if bundle_name == "run-latest.html":
        return "entroping.run-report.html"
    if bundle_name.startswith("effective-policy."):
        return "entroping.effective-policy-report.v1"
    if bundle_name.startswith("redaction-review."):
        return "entroping.redaction-review.v1"
    return "text"


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(root).as_posix()
    except ValueError:
        return str(path)
