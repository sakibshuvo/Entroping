"""Run option validation tests."""

import pytest

from entroping.core.run_option_validation import (
    RunOptionValidationError,
    normalize_run_report_formats,
    prepare_ad_hoc_run_selectors,
    validate_rerun_failure_options,
    validate_run_suite_options,
)


def test_prepare_ad_hoc_run_selectors_normalizes_tags_and_operation_ids() -> None:
    selectors = prepare_ad_hoc_run_selectors(
        tag=[" smoke ", "critical", "smoke"],
        tag_expression=None,
        operation_id=None,
        changed_from=None,
    )
    operation_selectors = prepare_ad_hoc_run_selectors(
        tag=None,
        tag_expression=None,
        operation_id=["createRefund", "createCheckout", "createRefund"],
        changed_from=None,
    )

    assert set(selectors.tag_filters) == {"smoke", "critical"}
    assert selectors.operation_filters == ()
    assert operation_selectors.tag_filters == ()
    assert operation_selectors.operation_filters == ("createCheckout", "createRefund")


@pytest.mark.parametrize(
    ("kwargs", "message", "param_hint"),
    [
        (
            {"tag": ["smoke"], "tag_expression": "smoke", "operation_id": None},
            "--tag cannot be combined with --tag-expression",
            "--tag-expression",
        ),
        (
            {"tag": ["smoke"], "tag_expression": None, "operation_id": ["getHealth"]},
            "--operation-id cannot be combined with --tag",
            "--operation-id",
        ),
        (
            {"tag": None, "tag_expression": "smoke", "operation_id": ["getHealth"]},
            "--operation-id cannot be combined with --tag-expression",
            "--operation-id",
        ),
        (
            {"tag": None, "tag_expression": None, "operation_id": ["getHealth"]},
            "--operation-id cannot be combined with --changed-from",
            "--operation-id",
        ),
    ],
)
def test_prepare_ad_hoc_run_selectors_reports_param_hint(
    kwargs: dict[str, list[str] | str | None],
    message: str,
    param_hint: str,
) -> None:
    with pytest.raises(RunOptionValidationError) as exc_info:
        prepare_ad_hoc_run_selectors(
            tag=kwargs["tag"] if isinstance(kwargs["tag"], list) else None,
            tag_expression=(
                kwargs["tag_expression"] if isinstance(kwargs["tag_expression"], str) else None
            ),
            operation_id=(
                kwargs["operation_id"] if isinstance(kwargs["operation_id"], list) else None
            ),
            changed_from="main" if "changed-from" in message else None,
        )

    assert str(exc_info.value) == message
    assert exc_info.value.param_hint == param_hint


def test_prepare_ad_hoc_run_selectors_wraps_normalization_and_expression_errors() -> None:
    with pytest.raises(RunOptionValidationError) as tag_exc:
        prepare_ad_hoc_run_selectors(
            tag=[""],
            tag_expression=None,
            operation_id=None,
            changed_from=None,
        )
    with pytest.raises(RunOptionValidationError) as expression_exc:
        prepare_ad_hoc_run_selectors(
            tag=None,
            tag_expression="smoke and",
            operation_id=None,
            changed_from=None,
        )

    assert tag_exc.value.param_hint == "--tag"
    assert expression_exc.value.param_hint == "--tag-expression"
    assert "Invalid tag expression" in str(expression_exc.value)


def test_normalize_run_report_formats_deduplicates_and_rejects_unknown() -> None:
    assert normalize_run_report_formats([" JSON ", "junit", "json"]) == ("json", "junit")

    with pytest.raises(RunOptionValidationError) as exc_info:
        normalize_run_report_formats(["xml"])

    assert exc_info.value.param_hint == "--report"
    assert "Unsupported report format 'xml'" in str(exc_info.value)


def test_validate_rerun_failure_options_reports_combined_conflicts() -> None:
    with pytest.raises(RunOptionValidationError) as exc_info:
        validate_rerun_failure_options(
            tag=["smoke"],
            tag_expression="critical",
            operation_id=["getHealth"],
            changed_from="main",
        )

    assert str(exc_info.value) == (
        "--rerun-failures cannot be combined with "
        "--tag, --tag-expression, --operation-id, --changed-from"
    )
    assert exc_info.value.param_hint == "--rerun-failures"


def test_validate_run_suite_options_reports_combined_conflicts() -> None:
    with pytest.raises(RunOptionValidationError) as exc_info:
        validate_run_suite_options(
            env="local",
            tag=["smoke"],
            tag_expression="critical",
            operation_id=["getHealth"],
            report=["json"],
            parallel=True,
            fail_fast=True,
            drift_check=True,
            changed_from="main",
            rerun_failures=True,
        )

    assert str(exc_info.value) == (
        "--env, --tag, --tag-expression, --operation-id, --report, --parallel, "
        "--fail-fast, --drift-check, --changed-from, --rerun-failures "
        "cannot be combined with --suite"
    )
    assert exc_info.value.param_hint == "--suite"


def test_validate_run_suite_options_accepts_default_cli_values() -> None:
    validate_run_suite_options(
        env=None,
        tag=None,
        tag_expression=None,
        operation_id=None,
        report=None,
        parallel=False,
        fail_fast=False,
        drift_check=False,
        changed_from=None,
        rerun_failures=False,
    )


def test_validate_helpers_do_not_need_project_paths() -> None:
    selectors = prepare_ad_hoc_run_selectors(
        tag=None,
        tag_expression=None,
        operation_id=None,
        changed_from=None,
    )

    assert selectors.tag_filters == ()
    assert selectors.operation_filters == ()
