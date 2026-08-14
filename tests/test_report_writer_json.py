"""JSON serialization and round-trip tests for deterministic run reports."""

import json
from pathlib import Path

import pytest

import entroping.core.report_writer as report_writer
from entroping.core.report_gate_results import _to_gate_result
from entroping.core.report_serialization import (
    _require_gate_results,
    _serialized_gate_results,
)


def test_load_run_report_round_trips_retry_evidence_and_ignores_malformed_entries(
    tmp_path: Path,
) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "local",
                "generated_at": "2026-06-03T00:00:00+00:00",
                "summary": {"total": 3, "passed": 1, "failed": 2, "exit_code": 1},
                "tests": [
                    {
                        "path": "tests/eventual.hurl",
                        "execution_path": ".entroping/run/eventual.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 50,
                        "timeout_ms": 2500,
                        "rule_ids": [],
                        "stdout": "",
                        "stderr": "",
                        "retry": {
                            "retry_count": 1,
                            "unstable": True,
                            "attempts": [
                                "not-a-dict",
                                {
                                    "attempt": 1,
                                    "status": "failed",
                                    "exit_code": 42,
                                    "duration_ms": 20,
                                    "stdout_truncated": False,
                                    "stderr_truncated": True,
                                },
                                {
                                    "attempt": 2,
                                    "status": "invalid",
                                    "exit_code": 0,
                                    "duration_ms": 30,
                                    "stdout_truncated": False,
                                    "stderr_truncated": False,
                                },
                            ],
                        },
                    },
                    {
                        "path": "tests/no-retry.hurl",
                        "execution_path": ".entroping/run/no-retry.hurl",
                        "status": "failed",
                        "exit_code": 1,
                        "duration_ms": 10,
                        "rule_ids": [],
                        "stdout": "",
                        "stderr": "",
                        "retry": "not-a-dict",
                    },
                    {
                        "path": "tests/bad-retry-attempts.hurl",
                        "execution_path": ".entroping/run/bad-retry-attempts.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 1,
                        "rule_ids": [],
                        "stdout": "",
                        "stderr": "",
                        "retry": {
                            "retry_count": 4,
                            "unstable": True,
                            "attempts": "not-a-list",
                        },
                    },
                ],
            },
        )
        + "\n",
        encoding="utf-8",
    )

    report = report_writer.load_run_report(latest)

    assert report.tests[0].timeout_ms == 2500
    assert report.tests[1].timeout_ms == 0
    assert report.tests[0].retry.retry_count == 1
    assert report.tests[0].retry.unstable
    assert [
        (
            attempt.attempt,
            attempt.status,
            attempt.exit_code,
            attempt.duration_ms,
            attempt.stdout_truncated,
            attempt.stderr_truncated,
        )
        for attempt in report.tests[0].retry.attempts
    ] == [(1, "failed", 42, 20, False, True)]
    assert report.tests[1].retry.retry_count == 0
    assert not report.tests[1].retry.unstable
    assert report.tests[2].retry.retry_count == 4
    assert report.tests[2].retry.unstable
    assert report.tests[2].retry.attempts == ()


@pytest.mark.parametrize(
    ("raw_gate_results", "message"),
    [
        ({"rule_id": "latency"}, "must be a JSON array"),
        ([None], "must be a JSON object"),
        (
            [{"rule_id": "", "enforcement": "block", "result": "passed", "exit_code": 0}],
            "is invalid",
        ),
    ],
)
def test_gate_result_deserialization_rejects_invalid_shapes(
    raw_gate_results: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _require_gate_results(
            raw_gate_results,
            path=Path("run-latest.json"),
            test_index=0,
        )


def test_gate_result_deserialization_skips_invalid_serialized_items() -> None:
    assert (
        _serialized_gate_results(
            [
                None,
                {"rule_id": "", "enforcement": "block", "result": "passed", "exit_code": 0},
            ],
        )
        == ()
    )


def test_gate_result_conversion_rejects_invalid_mapping_without_assertions() -> None:
    with pytest.raises(ValueError, match="invalid serialized gate result"):
        _to_gate_result(
            {
                "rule_id": 7,
                "enforcement": "block",
                "result": "passed",
                "exit_code": 0,
            },
        )


def test_load_run_report_ignores_bool_optional_integer_fields(tmp_path: Path) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "local",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "summary": {
                    "total": 1,
                    "passed": 1,
                    "failed": 0,
                    "exit_code": 0,
                    "selected": True,
                    "executed": False,
                    "not_scheduled": True,
                },
                "tests": [
                    {
                        "path": "tests/health.hurl",
                        "execution_path": ".entroping/run/health.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 1,
                        "timeout_ms": True,
                        "rule_ids": [],
                        "stdout": "",
                        "stderr": "",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = report_writer.load_run_report(latest)

    assert report.summary.selected is None
    assert report.summary.executed is None
    assert report.summary.not_scheduled == 0
    assert report.tests[0].timeout_ms == 0


def test_load_run_report_round_trips_response_fingerprint(tmp_path: Path) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "local",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "summary": {"total": 1, "passed": 1, "failed": 0, "exit_code": 0},
                "tests": [
                    {
                        "path": "tests/checkout.hurl",
                        "execution_path": ".entroping/run/checkout.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 42,
                        "rule_ids": ["global_latency"],
                        "stdout": "",
                        "stderr": "",
                        "response": {
                            "status_code": 201,
                            "headers": {"content-type": "application/json"},
                            "body_shape": ["$:object", "$.id:string"],
                        },
                    },
                ],
            },
        )
        + "\n",
        encoding="utf-8",
    )

    report = report_writer.load_run_report(latest)

    response = report.tests[0].response
    assert response is not None
    assert response.status_code == 201
    assert {header.name: header.value for header in response.headers} == {
        "content-type": "application/json",
    }
    assert response.body_shape == ("$:object", "$.id:string")


def test_load_run_report_ignores_malformed_optional_response_fields(tmp_path: Path) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "local",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "summary": {"total": 1, "passed": 1, "failed": 0, "exit_code": 0},
                "tests": [
                    {
                        "path": "tests/checkout.hurl",
                        "execution_path": ".entroping/run/checkout.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 42,
                        "rule_ids": ["global_latency"],
                        "stdout": "",
                        "stderr": "",
                        "response": {
                            "status_code": "201",
                            "headers": {
                                "content-type": 123,
                                "date": "volatile",
                                7: "ignored",
                            },
                            "body_shape": "not-a-list",
                        },
                    },
                    {
                        "path": "tests/bad-shape.hurl",
                        "execution_path": ".entroping/run/bad-shape.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 10,
                        "rule_ids": [],
                        "stdout": "",
                        "stderr": "",
                        "response": {
                            "headers": "not-a-dict",
                            "body_shape": "not-a-list",
                        },
                    },
                ],
            },
        )
        + "\n",
        encoding="utf-8",
    )

    report = report_writer.load_run_report(latest)

    assert report.tests[0].response is None
    assert report.tests[1].response is None


def test_load_run_report_round_trips_valid_known_failures_and_ignores_malformed_entries(
    tmp_path: Path,
) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "local",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "summary": {"total": 1, "passed": 1, "failed": 0, "exit_code": 0},
                "tests": [
                    {
                        "path": "tests/health.hurl",
                        "execution_path": ".entroping/run/health.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 42,
                        "rule_ids": [],
                        "stdout": "",
                        "stderr": "",
                        "known_failures": [
                            "not-a-dict",
                            {
                                "test": 123,
                                "rule_id": "latency",
                                "issue_id": "GH-001",
                                "expires": "2026-06-30",
                                "reason": "wrong type",
                            },
                            {
                                "test": "",
                                "rule_id": "latency",
                                "issue_id": "GH-002",
                                "expires": "2026-06-30",
                                "reason": "empty test",
                            },
                            {
                                "test": "tests/bad\n.hurl",
                                "rule_id": "latency",
                                "issue_id": "GH-003",
                                "expires": "2026-06-30",
                                "reason": "control character",
                            },
                            {
                                "test": " tests/health.hurl ",
                                "rule_id": " latency ",
                                "issue_id": " GH-123 ",
                                "expires": " 2026-06-30 ",
                                "reason": " Temporary upstream latency regression. ",
                            },
                        ],
                    },
                    {
                        "path": "tests/checkout.hurl",
                        "execution_path": ".entroping/run/checkout.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 10,
                        "rule_ids": [],
                        "stdout": "",
                        "stderr": "",
                        "known_failures": "not-a-list",
                    },
                ],
            },
        )
        + "\n",
        encoding="utf-8",
    )

    report = report_writer.load_run_report(latest)

    assert [
        (
            known_failure.test,
            known_failure.rule_id,
            known_failure.issue_id,
            known_failure.expires,
            known_failure.reason,
        )
        for known_failure in report.tests[0].known_failures
    ] == [
        (
            "tests/health.hurl",
            "latency",
            "GH-123",
            "2026-06-30",
            "Temporary upstream latency regression.",
        )
    ]
    assert report.tests[1].known_failures == ()



def test_load_run_report_round_trips_auth_evidence_and_preserves_compat_normalization(
    tmp_path: Path,
) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "local",
                "generated_at": "2026-06-12T00:00:00+00:00",
                "summary": {"total": 5, "passed": 5, "failed": 0, "exit_code": 0},
                "tests": [
                    {
                        "path": "tests/normalized-auth.hurl",
                        "execution_path": ".entroping/run/normalized-auth.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 42,
                        "rule_ids": [],
                        "stdout": "",
                        "stderr": "",
                        "auth": {
                            "flow": " oauth2-client-credentials ",
                            "requires": [" access_token ", "csrf_token"],
                            "produces": [" session_cookie "],
                        },
                    },
                    {
                        "path": "tests/arbitrary-flow-auth.hurl",
                        "execution_path": ".entroping/run/arbitrary-flow-auth.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 10,
                        "rule_ids": [],
                        "stdout": "",
                        "stderr": "",
                        "auth": {
                            "flow": "oauth2 live-secret",
                            "requires": ["session_token"],
                            "produces": ["oauth2_token"],
                        },
                    },
                    {
                        "path": "tests/null-flow-auth.hurl",
                        "execution_path": ".entroping/run/null-flow-auth.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 10,
                        "rule_ids": [],
                        "stdout": "",
                        "stderr": "",
                        "auth": {
                            "flow": None,
                            "requires": ["session_token"],
                            "produces": [],
                        },
                    },
                    {
                        "path": "tests/empty-normalized-auth.hurl",
                        "execution_path": ".entroping/run/empty-normalized-auth.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 10,
                        "rule_ids": [],
                        "stdout": "",
                        "stderr": "",
                        "auth": {
                            "flow": "oauth2 live-secret",
                            "requires": ["1bad"],
                            "produces": [""],
                        },
                    },
                    {
                        "path": "tests/filtered-vars-auth.hurl",
                        "execution_path": ".entroping/run/filtered-vars-auth.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 10,
                        "rule_ids": [],
                        "stdout": "",
                        "stderr": "",
                        "auth": {
                            "flow": None,
                            "requires": ["  ", "session_token", "1bad"],
                            "produces": ["-invalid"],
                        },
                    },
                ],
            },
        )
        + "\n",
        encoding="utf-8",
    )

    report = report_writer.load_run_report(latest)

    assert report.tests[0].auth is not None
    assert report.tests[0].auth.flow == "oauth2-client-credentials"
    assert report.tests[0].auth.requires == ("access_token", "csrf_token")
    assert report.tests[0].auth.produces == ("session_cookie",)
    assert report.tests[1].auth is not None
    assert report.tests[1].auth.flow is None
    assert report.tests[1].auth.requires == ("session_token",)
    assert report.tests[1].auth.produces == ("oauth2_token",)
    assert report.tests[2].auth is not None
    assert report.tests[2].auth.flow is None
    assert report.tests[2].auth.requires == ("session_token",)
    assert report.tests[2].auth.produces == ()
    assert report.tests[3].auth is None
    assert report.tests[4].auth is not None
    assert report.tests[4].auth.flow is None
    assert report.tests[4].auth.requires == ("session_token",)
    assert report.tests[4].auth.produces == ()


@pytest.mark.parametrize(
    ("auth_payload", "error_fragment"),
    [
        ({}, "must include flow"),
        ("not-a-dict", "must be a JSON object"),
        ([], "must be a JSON object"),
        (None, "must be a JSON object"),
        (
            {"flow": 1, "requires": ["session_token"], "produces": []},
            "flow has invalid type",
        ),
        (
            {"flow": None, "requires": "session_token", "produces": []},
            "must be an array of strings",
        ),
        (
            {"flow": None, "requires": ["session_token"], "produces": "session_token"},
            "must be an array of strings",
        ),
        (
            {"flow": None, "requires": [1], "produces": ["session_token"]},
            "must be an array of strings",
        ),
        (
            {"flow": None, "requires": ["session_token"], "produces": [1]},
            "must be an array of strings",
        ),
        (
            {"requires": ["session_token"], "produces": ["session_token"]},
            "must include flow",
        ),
        (
            {"flow": None, "requires": ["session_token"]},
            "must include produces",
        ),
        (
            {
                "requires": ["session_token"],
                "produces": ["session_token"],
                "flow": None,
                "private": "no",
            },
            "contains unknown fields",
        ),
    ],
)

def test_load_run_report_rejects_invalid_auth_shape(
    tmp_path: Path,
    auth_payload: object,
    error_fragment: str,
) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()

    latest.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "local",
                "generated_at": "2026-06-12T00:00:00+00:00",
                "summary": {"total": 1, "passed": 1, "failed": 0, "exit_code": 0},
                "tests": [
                    {
                        "path": "tests/auth.hurl",
                        "execution_path": ".entroping/run/auth.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 42,
                        "rule_ids": [],
                        "stdout": "",
                        "stderr": "",
                        "auth": auth_payload,
                    },
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc_info:
        report_writer.load_run_report(latest)
    assert "field tests[0].auth" in str(exc_info.value)
    assert error_fragment in str(exc_info.value)
    assert "session_secret" not in str(exc_info.value)


def test_load_run_report_rejects_non_object_gate_result_entry(
    tmp_path: Path,
) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "local",
                "generated_at": "2026-06-12T00:00:00+00:00",
                "summary": {"total": 1, "passed": 1, "failed": 0, "exit_code": 0},
                "tests": [
                    {
                        "path": "tests/gate-results.hurl",
                        "execution_path": ".entroping/run/gate-results.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 42,
                        "rule_ids": [],
                        "stdout": "",
                        "stderr": "",
                        "gate_results": [None],
                    },
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc_info:
        report_writer.load_run_report(latest)
    assert "field tests[0].gate_results[0] must be a JSON object" in str(exc_info.value)


def test_load_run_report_trims_valid_operation_ids_and_ignores_malformed_values(
    tmp_path: Path,
) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    tests = [
        {
            "path": "tests/not-string.hurl",
            "execution_path": ".entroping/run/not-string.hurl",
            "status": "passed",
            "exit_code": 0,
            "duration_ms": 1,
            "rule_ids": [],
            "stdout": "",
            "stderr": "",
            "operation_id": 123,
        },
        {
            "path": "tests/control.hurl",
            "execution_path": ".entroping/run/control.hurl",
            "status": "passed",
            "exit_code": 0,
            "duration_ms": 1,
            "rule_ids": [],
            "stdout": "",
            "stderr": "",
            "operation_id": "create\nCheckout",
        },
        {
            "path": "tests/valid.hurl",
            "execution_path": ".entroping/run/valid.hurl",
            "status": "passed",
            "exit_code": 0,
            "duration_ms": 1,
            "rule_ids": [],
            "stdout": "",
            "stderr": "",
            "operation_id": " createCheckout ",
        },
    ]
    latest.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "local",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "summary": {"total": 3, "passed": 3, "failed": 0, "exit_code": 0},
                "tests": tests,
            },
        ),
        encoding="utf-8",
    )

    report = report_writer.load_run_report(latest)

    assert [test.operation_id for test in report.tests] == [None, None, "createCheckout"]
