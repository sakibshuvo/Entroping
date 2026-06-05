"""Tests for deterministic QAnstitution policy gate coverage reports."""

import json
from pathlib import Path

import pytest

import entroping.core.gate_coverage_report as gate_coverage_report
from entroping.bridge.gate_coverage import compile_gate_coverage_report
from entroping.core.gate_coverage_report import (
    GateCoverageReportError,
    run_gate_coverage_report,
)
from entroping.core.safe_write import SafeWriteError
from entroping.models.hurl import HurlExchange, HurlMetadata, HurlTest
from entroping.models.qanstitution import GateRule, Qanstitution
from entroping.models.qanstitution_evidence import EffectiveGateEvidence, QanstitutionEvidence


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.lstrip(), encoding="utf-8")


def _write_policy(root: Path) -> None:
    _write_text(
        root / "qanstitution.yaml",
        """
project: checkout-api
gates:
  - id: all_status
    condition: "true"
    gate: status == 200
    enforcement: block
  - id: smoke_latency
    condition: tags contains 'smoke'
    gate: duration < 500
    enforcement: block
  - id: create_method
    condition: method == 'POST'
    gate: header "Location" exists
    enforcement: warn
  - id: orders_path
    condition: path startswith '/orders'
    gate: duration < 1500
    enforcement: block
  - id: billing_path
    condition: path contains 'billing'
    gate: status == 200
    enforcement: audit_only
""",
    )


def test_run_gate_coverage_report_maps_effective_gates_to_matching_hurl_tests(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path)
    _write_text(
        tmp_path / "tests" / "health.hurl",
        """
# entroping: tags=smoke
# entroping: operation_id=getHealth

GET http://api.example.test/health?token=secret
HTTP 200
""",
    )
    _write_text(
        tmp_path / "tests" / "orders.hurl",
        """
# entroping: tags=regression,payments
# entroping: operation_id=createOrder

POST http://api.example.test/orders?api_key=secret
HTTP 201

GET http://api.example.test/orders/123?session=secret
HTTP 200
""",
    )

    result = run_gate_coverage_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "gate-coverage.json"
    assert result.report.schema_version == "entroping.gate-coverage-report.v1"
    assert result.report.summary.total_gates == 5
    assert result.report.summary.matched_gates == 4
    assert result.report.summary.unmatched_gates == 1
    assert result.report.summary.total_tests == 2
    assert result.report.summary.total_test_matches == 5

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    gates = {gate["id"]: gate for gate in payload["gates"]}
    assert gates["all_status"]["matched"] is True
    assert [test["path"] for test in gates["all_status"]["tests"]] == [
        "tests/health.hurl",
        "tests/orders.hurl",
    ]
    assert gates["smoke_latency"]["tests"][0]["tags"] == ["smoke"]
    assert gates["smoke_latency"]["tests"][0]["operation_id"] == "getHealth"
    assert gates["create_method"]["tests"] == [
        {
            "path": "tests/orders.hurl",
            "tags": ["payments", "regression"],
            "operation_id": "createOrder",
            "exchanges": [{"method": "POST", "path": "/orders"}],
        }
    ]
    assert gates["orders_path"]["tests"][0]["exchanges"] == [
        {"method": "POST", "path": "/orders"},
        {"method": "GET", "path": "/orders/123"},
    ]
    assert gates["billing_path"]["matched"] is False
    assert gates["billing_path"]["tests"] == []
    serialized = json.dumps(payload, sort_keys=True)
    assert "api.example.test" not in serialized
    assert "token" not in serialized
    assert "api_key" not in serialized
    assert "session" not in serialized


def test_run_gate_coverage_report_records_empty_suites(tmp_path: Path) -> None:
    _write_policy(tmp_path)
    (tmp_path / "tests").mkdir()

    result = run_gate_coverage_report(project_root=tmp_path, output="md")

    assert result.report.summary.total_gates == 5
    assert result.report.summary.total_tests == 0
    assert result.report.summary.matched_gates == 0
    assert result.report.summary.unmatched_gates == 5
    markdown = result.output_path.read_text(encoding="utf-8")
    assert "Tests discovered: 0" in markdown
    assert "No matching Hurl tests." in markdown


def test_run_gate_coverage_report_treats_missing_tests_directory_as_empty_suite(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path)

    result = run_gate_coverage_report(project_root=tmp_path, output="json")

    assert result.report.summary.total_tests == 0
    assert all(not gate.matched for gate in result.report.gates)


def test_run_gate_coverage_report_wraps_malformed_hurl_metadata(tmp_path: Path) -> None:
    _write_policy(tmp_path)
    _write_text(
        tmp_path / "tests" / "broken.hurl",
        """
# entroping: tags=smoke
# entroping: tags=duplicate

GET http://api.example.test/health
HTTP 200
""",
    )

    with pytest.raises(GateCoverageReportError, match="duplicate metadata key 'tags'"):
        run_gate_coverage_report(project_root=tmp_path, output="json")


def test_compile_gate_coverage_report_keeps_external_provenance_absolute(
    tmp_path: Path,
) -> None:
    external_policy_path = tmp_path.parent / "central-qanstitution.yaml"
    rule = GateRule(
        id="external_latency",
        condition="true",
        gate="duration < 2000",
        enforcement="block",
    )
    evidence = QanstitutionEvidence(
        policy=Qanstitution(project="checkout-api", gates=[rule]),
        root_path=external_policy_path,
        import_paths=(),
        gates=(
            EffectiveGateEvidence(
                rule=rule,
                source_path=external_policy_path,
                group=None,
            ),
        ),
    )
    hurl_test = HurlTest(
        path=tmp_path / "tests" / "health.hurl",
        metadata=HurlMetadata(tags=frozenset({"smoke"})),
        exchanges=(
            HurlExchange(
                method="GET",
                url="https://api.example.test/health",
                path="/health",
            ),
        ),
    )

    report = compile_gate_coverage_report(evidence, (hurl_test,), root=tmp_path)

    assert report.config_path == external_policy_path.resolve().as_posix()
    assert report.gates[0].source_path == external_policy_path.resolve().as_posix()


def test_run_gate_coverage_report_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_policy(tmp_path)
    (tmp_path / "tests").mkdir()

    def fail_write(*args: object, **kwargs: object) -> None:
        raise SafeWriteError("blocked by symlink")

    monkeypatch.setattr(gate_coverage_report, "safe_write_text", fail_write)

    with pytest.raises(GateCoverageReportError, match="blocked by symlink"):
        run_gate_coverage_report(project_root=tmp_path, output="md")
