"""Generated Hurl quality score report tests."""

import json
from pathlib import Path
from typing import NoReturn

import pytest

import entroping.core.test_quality_report as test_quality_report
import entroping.hurl_source as hurl_source
from entroping.bridge.test_quality import (
    TEST_QUALITY_REPORT_SCHEMA_VERSION,
    compile_test_quality_report,
    render_test_quality_markdown,
)
from entroping.bridge.test_quality import (
    TestQualitySummary as QualitySummaryModel,
)
from entroping.core.hurl_discovery import discover_hurl_tests
from entroping.core.safe_write import SafeWriteError
from entroping.core.test_quality_report import (
    TestQualityReportError as QualityReportError,
)
from entroping.core.test_quality_report import (
    run_test_quality_report,
)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.lstrip(), encoding="utf-8")


def test_compile_test_quality_report_scores_generated_hurl_findings(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "tests" / "generated" / "weak_checkout.hurl",
        """
        # entroping: source=architect
        # entroping: tags=generated

        GET {{base_url}}/users/123
        HTTP 200
        [Asserts]
        jsonpath "$.items[0].id" == "usr_123"
        """,
    )
    _write_text(
        tmp_path / "tests" / "generated" / "strong_auth.hurl",
        """
        # entroping: source=openapi
        # entroping: tags=generated,security,negative
        # entroping: operation_id=createCheckout
        # entroping: negative_category=invalid-auth
        # entroping: severity=high

        POST {{base_url}}/checkout
        HTTP 401
        [Asserts]
        jsonpath "$.error.code" exists
        jsonpath "$.error.message" isString
        [Options]
        retry: 2
        """,
    )
    _write_text(
        tmp_path / "tests" / "manual" / "health.hurl",
        """
        GET {{base_url}}/health
        HTTP 200
        """,
    )

    hurl_tests = tuple(discover_hurl_tests((tmp_path / "tests",)))
    report = compile_test_quality_report(
        hurl_tests,
        project="checkout-api",
        root=tmp_path,
    )

    assert report.schema_version == TEST_QUALITY_REPORT_SCHEMA_VERSION
    assert report.summary.total_tests == 3
    assert report.summary.generated_tests == 2
    assert report.summary.manual_tests == 1
    assert report.summary.score < 100
    assert report.summary.status == "warn"
    weak = next(item for item in report.tests if item.path == "tests/generated/weak_checkout.hurl")
    strong = next(item for item in report.tests if item.path == "tests/generated/strong_auth.hurl")
    assert weak.score < strong.score
    assert strong.negative_category == "invalid-auth"
    assert strong.security is None
    assert {finding.category for finding in weak.findings} == {
        "assertion-strength",
        "brittle-selector",
        "shallow-schema-check",
        "overfitted-example",
        "policy-alignment",
    }
    assert all(finding.path == "tests/generated/weak_checkout.hurl" for finding in weak.findings)
    assert not any(finding.category == "missing-negative-path" for finding in report.findings)
    assert not any(finding.category == "weak-auth-coverage" for finding in report.findings)


def test_compile_test_quality_report_reports_missing_generated_negative_and_auth_coverage(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "tests" / "generated" / "happy.hurl",
        """
        # entroping: source=openapi
        # entroping: tags=generated,smoke
        # entroping: operation_id=listTickets

        GET {{base_url}}/tickets
        HTTP 200
        [Asserts]
        jsonpath "$.items" exists
        """,
    )

    report = compile_test_quality_report(
        tuple(discover_hurl_tests((tmp_path / "tests",))),
        project="support-api",
        root=tmp_path,
    )

    categories = {finding.category for finding in report.findings}
    assert "missing-negative-path" in categories
    assert "weak-auth-coverage" in categories
    assert report.summary.status == "warn"


def test_compile_test_quality_report_requires_negative_category_metadata(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "tests" / "generated" / "bare_negative.hurl",
        """
        # entroping: source=openapi
        # entroping: tags=generated,negative,security
        # entroping: operation_id=getProfile

        GET {{base_url}}/profile
        HTTP 401
        [Asserts]
        jsonpath "$.error.code" exists
        jsonpath "$.error.message" isString
        """,
    )

    report = compile_test_quality_report(
        tuple(discover_hurl_tests((tmp_path / "tests",))),
        project="profile-api",
        root=tmp_path,
    )

    categories = {finding.category for finding in report.findings}
    assert "missing-negative-path" in categories
    assert "weak-auth-coverage" not in categories


def test_render_test_quality_markdown_omits_raw_hurl_values(tmp_path: Path) -> None:
    _write_text(
        tmp_path / "tests" / "generated" / "secret.hurl",
        """
        # entroping: source=architect
        # entroping: tags=generated

        GET {{base_url}}/tokens/secret-123
        HTTP 200
        [Asserts]
        jsonpath "$.token" == "live-secret-token"
        """,
    )

    report = compile_test_quality_report(
        tuple(discover_hurl_tests((tmp_path / "tests",))),
        project="token-api",
        root=tmp_path,
    )
    markdown = render_test_quality_markdown(report)
    payload = json.loads(report.model_dump_json())

    assert "# Entroping Generated-Test Quality Score" in markdown
    assert "tests/generated/secret.hurl" in markdown
    assert "live-secret-token" not in markdown
    assert "secret-123" not in markdown
    assert "live-secret-token" not in json.dumps(payload)
    assert "secret-123" not in json.dumps(payload)


def test_compile_test_quality_report_rejects_oversized_generated_hurl_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "tests" / "generated" / "oversized.hurl"
    _write_text(
        source,
        """
        # entroping: source=architect
        # entroping: tags=generated

        GET {{base_url}}/tokens
        HTTP 200
        [Asserts]
        jsonpath "$.token" exists
        """,
    )
    hurl_tests = tuple(discover_hurl_tests((tmp_path / "tests",)))
    source.write_bytes(source.read_bytes() + (b"x" * 64))
    monkeypatch.setattr(hurl_source, "HURL_SOURCE_MAX_BYTES", 32)

    with pytest.raises(hurl_source.HurlSourceTooLargeError, match=r"Hurl source .* exceeds 32"):
        compile_test_quality_report(
            hurl_tests,
            project="token-api",
            root=tmp_path,
        )


def test_compile_test_quality_report_treats_generated_tag_as_generated(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "tests" / "manual_tagged.hurl",
        """
        # entroping: tags=generated,negative,security
        # entroping: operation_id=getTagged

        GET {{base_url}}/tagged
        HTTP 401
        [Asserts]
        jsonpath "$.error" exists
        jsonpath "$.error" isString
        """,
    )

    report = compile_test_quality_report(
        tuple(discover_hurl_tests((tmp_path / "tests",))),
        project="tagged-api",
        root=tmp_path,
    )

    assert report.summary.generated_tests == 1
    assert report.tests[0].path == "tests/manual_tagged.hurl"


def test_compile_test_quality_report_displays_outside_root_paths_without_values(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside-quality.hurl"
    _write_text(
        outside,
        """
        # entroping: source=architect
        # entroping: tags=generated,negative,security
        # entroping: operation_id=getOutside

        GET {{base_url}}/outside
        HTTP 401
        [Asserts]
        jsonpath "$.error" exists
        jsonpath "$.error" isString
        """,
    )
    try:
        report = compile_test_quality_report(
            tuple(discover_hurl_tests((outside,))),
            project="outside-api",
            root=tmp_path,
        )
    finally:
        outside.unlink(missing_ok=True)

    assert report.tests[0].path == f"<outside-project>/{outside.name}"
    assert tmp_path.parent.as_posix() not in report.model_dump_json()


def test_render_test_quality_markdown_escapes_backtick_paths(tmp_path: Path) -> None:
    _write_text(
        tmp_path / "tests" / "generated" / "we`ird.hurl",
        """
        # entroping: source=architect
        # entroping: tags=generated

        GET {{base_url}}/profile
        HTTP 200
        [Asserts]
        jsonpath "$.id" == "usr_123"
        """,
    )

    report = compile_test_quality_report(
        tuple(discover_hurl_tests((tmp_path / "tests",))),
        project="profile-api",
        root=tmp_path,
    )
    markdown = render_test_quality_markdown(report)

    assert "## tests/generated/we\\`ird.hurl" in markdown
    assert "## `tests/generated/we`ird.hurl`" not in markdown


def test_compile_test_quality_report_skips_outside_root_manual_tests(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside-manual.hurl"
    _write_text(
        outside,
        """
        GET {{base_url}}/outside
        HTTP 200
        """,
    )
    try:
        report = compile_test_quality_report(
            tuple(discover_hurl_tests((outside,))),
            project="outside-api",
            root=tmp_path,
        )
    finally:
        outside.unlink(missing_ok=True)

    assert report.summary.generated_tests == 0
    assert report.tests == ()


def test_run_test_quality_report_writes_json_and_markdown(tmp_path: Path) -> None:
    _write_text(
        tmp_path / "tests" / "generated" / "auth.hurl",
        """
        # entroping: source=openapi
        # entroping: tags=generated,negative,security
        # entroping: operation_id=getProfile
        # entroping: negative_category=invalid-auth

        GET {{base_url}}/profile
        HTTP 401
        [Asserts]
        jsonpath "$.error" exists
        jsonpath "$.error" isString
        """,
    )

    json_result = run_test_quality_report(project_root=tmp_path, output="json")
    md_result = run_test_quality_report(project_root=tmp_path, output="md")

    assert json_result.output_path == tmp_path / "reports" / "test-quality.json"
    assert md_result.output_path == tmp_path / "reports" / "test-quality.md"
    assert json.loads(json_result.output_path.read_text(encoding="utf-8"))[
        "schema_version"
    ] == TEST_QUALITY_REPORT_SCHEMA_VERSION
    assert "# Entroping Generated-Test Quality Score" in md_result.output_path.read_text(
        encoding="utf-8"
    )


def test_compile_test_quality_report_status_is_missing_without_generated_tests(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "tests" / "manual" / "health.hurl",
        """
        GET {{base_url}}/health
        HTTP 200
        """,
    )

    report = compile_test_quality_report(
        tuple(discover_hurl_tests((tmp_path / "tests",))),
        project="checkout-api",
        root=tmp_path,
    )

    assert report.summary.generated_tests == 0
    assert report.summary.score == 0
    assert report.summary.status == "missing"
    assert {finding.category for finding in report.findings} == {"missing-generated-tests"}
    assert "|  |  |  |  | 0 | 0 |" in render_test_quality_markdown(report)


def test_compile_test_quality_report_rejects_negative_counts() -> None:
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        QualitySummaryModel(
            total_tests=-1,
            generated_tests=0,
            manual_tests=0,
            score=0,
            status="missing",
            findings=0,
        )


def test_run_test_quality_report_wraps_discovery_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "tests").mkdir()

    def fail_discovery(*args: object, **kwargs: object) -> NoReturn:
        _ = args, kwargs
        raise ValueError("bad hurl metadata")

    monkeypatch.setattr(test_quality_report, "discover_hurl_tests", fail_discovery)

    with pytest.raises(QualityReportError, match="bad hurl metadata"):
        run_test_quality_report(project_root=tmp_path, output="json")


def test_run_test_quality_report_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_write(*args: object, **kwargs: object) -> NoReturn:
        _ = args, kwargs
        raise SafeWriteError("write refused")

    monkeypatch.setattr(test_quality_report, "safe_write_text", fail_write)

    with pytest.raises(QualityReportError, match="write refused"):
        run_test_quality_report(project_root=tmp_path, output="json")
