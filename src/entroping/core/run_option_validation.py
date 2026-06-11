"""Validation helpers for run command option combinations."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass

from entroping.core.hurl_discovery import normalize_operation_id_filters, normalize_tag_filters
from entroping.core.tag_expression import TagExpressionSyntaxError, compile_tag_expression


class RunOptionValidationError(ValueError):
    """Raised when run command options are unsupported together."""

    def __init__(self, message: str, *, param_hint: str) -> None:
        super().__init__(message)
        self.param_hint = param_hint


@dataclass(frozen=True, slots=True)
class RunSelectorOptions:
    """Normalized ad hoc selector filters for run workflows."""

    tag_filters: tuple[str, ...]
    operation_filters: tuple[str, ...]


def prepare_ad_hoc_run_selectors(
    *,
    tag: Sequence[str] | None,
    tag_expression: str | None,
    operation_id: Collection[str] | None,
    changed_from: str | None,
) -> RunSelectorOptions:
    """Validate and normalize ad hoc run selectors before workflow execution."""

    if tag and tag_expression is not None:
        raise RunOptionValidationError(
            "--tag cannot be combined with --tag-expression",
            param_hint="--tag-expression",
        )
    if operation_id and tag:
        raise RunOptionValidationError(
            "--operation-id cannot be combined with --tag",
            param_hint="--operation-id",
        )
    if operation_id and tag_expression is not None:
        raise RunOptionValidationError(
            "--operation-id cannot be combined with --tag-expression",
            param_hint="--operation-id",
        )
    if operation_id and changed_from is not None:
        raise RunOptionValidationError(
            "--operation-id cannot be combined with --changed-from",
            param_hint="--operation-id",
        )
    try:
        tag_filters = tuple(normalize_tag_filters(tag))
    except ValueError as exc:
        raise RunOptionValidationError(str(exc), param_hint="--tag") from exc
    try:
        operation_filters = tuple(sorted(normalize_operation_id_filters(operation_id)))
    except ValueError as exc:
        raise RunOptionValidationError(str(exc), param_hint="--operation-id") from exc
    if tag_expression is not None:
        try:
            compile_tag_expression(tag_expression)
        except TagExpressionSyntaxError as exc:
            raise RunOptionValidationError(
                f"Invalid tag expression: {exc}",
                param_hint="--tag-expression",
            ) from exc
    return RunSelectorOptions(tag_filters=tag_filters, operation_filters=operation_filters)


def normalize_run_report_formats(report: Sequence[str] | None) -> tuple[str, ...]:
    """Normalize repeated report format options while preserving first-seen order."""

    if not report:
        return ()

    normalized: list[str] = []
    for raw_format in report:
        report_format = raw_format.strip().lower()
        if report_format not in {"drift", "html", "json", "junit"}:
            msg = (
                f"Unsupported report format {raw_format!r}; "
                "supported formats: drift, html, json, junit"
            )
            raise RunOptionValidationError(msg, param_hint="--report")
        if report_format not in normalized:
            normalized.append(report_format)
    return tuple(normalized)


def validate_rerun_failure_options(
    *,
    tag: Sequence[str] | None,
    tag_expression: str | None,
    operation_id: Collection[str] | None,
    changed_from: str | None,
) -> None:
    """Reject selector combinations that make rerun-failures ambiguous."""

    conflicts: list[str] = []
    if tag:
        conflicts.append("--tag")
    if tag_expression is not None:
        conflicts.append("--tag-expression")
    if operation_id:
        conflicts.append("--operation-id")
    if changed_from is not None:
        conflicts.append("--changed-from")
    if conflicts:
        joined = ", ".join(conflicts)
        raise RunOptionValidationError(
            f"--rerun-failures cannot be combined with {joined}",
            param_hint="--rerun-failures",
        )


def validate_run_suite_options(
    *,
    env: str | None,
    tag: Sequence[str] | None,
    tag_expression: str | None,
    operation_id: Collection[str] | None,
    report: Sequence[str] | None,
    parallel: bool,
    fail_fast: bool,
    drift_check: bool,
    changed_from: str | None,
    rerun_failures: bool,
) -> None:
    """Reject ad hoc run options that are owned by suite manifests."""

    conflicts: list[str] = []
    if env is not None:
        conflicts.append("--env")
    if tag:
        conflicts.append("--tag")
    if tag_expression is not None:
        conflicts.append("--tag-expression")
    if operation_id:
        conflicts.append("--operation-id")
    if report:
        conflicts.append("--report")
    if parallel:
        conflicts.append("--parallel")
    if fail_fast:
        conflicts.append("--fail-fast")
    if drift_check:
        conflicts.append("--drift-check")
    if changed_from is not None:
        conflicts.append("--changed-from")
    if rerun_failures:
        conflicts.append("--rerun-failures")
    if conflicts:
        joined = ", ".join(conflicts)
        raise RunOptionValidationError(
            f"{joined} cannot be combined with --suite",
            param_hint="--suite",
        )
