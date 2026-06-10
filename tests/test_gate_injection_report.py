"""Tests for deterministic QAnstitution gate-injection explanations."""

import json
from datetime import date
from pathlib import Path

import pytest

import entroping.core.gate_injection_report as gate_injection_report
from entroping.bridge.gate_injection_explain import compile_gate_injection_report
from entroping.core.gate_injection_report import (
    GateInjectionReportError,
    run_gate_injection_report,
)
from entroping.core.safe_write import SafeWriteError
from entroping.models.hurl import HurlExchange, HurlMetadata, HurlTest
from entroping.models.qanstitution import GateRule, Qanstitution
from entroping.models.qanstitution_evidence import EffectiveGateEvidence, QanstitutionEvidence


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.lstrip(), encoding="utf-8")


def _write_hurl(path: Path, *, tags: str = "smoke", url_path: str = "/api/health") -> None:
    _write_text(
        path,
        f"""
# entroping: tags={tags}
# entroping: operation_id=getHealth

GET http://api.example.test{url_path}
HTTP 200
""",
    )


def test_run_gate_injection_report_explains_matching_imported_and_local_gates(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "rules" / "security.yaml",
        """
project: imported-security
gates:
  - id: security_header
    condition: path startswith '/api'
    gate: header "X-Request-Id" exists
    enforcement: warn
    final: true
""",
    )
    _write_text(
        tmp_path / "qanstitution.yaml",
        """
project: checkout-api
imports:
  - ./rules/security.yaml
gates:
  - id: smoke_latency
    condition: tags contains 'smoke'
    gate: duration < 500
    enforcement: block
  - id: billing_latency
    condition: tags contains 'billing'
    gate: duration < 2000
    enforcement: block
""",
    )
    source = tmp_path / "tests" / "health.hurl"
    _write_hurl(source)

    result = run_gate_injection_report(
        project_root=tmp_path,
        targets=(Path("tests/health.hurl"),),
        output="json",
    )

    assert result.output_path == tmp_path / "reports" / "gate-injection.json"
    assert result.report.schema_version == "entroping.gate-injection-report.v1"
    assert result.report.summary.total_targets == 1
    assert result.report.summary.total_would_inject == 2
    assert result.report.summary.total_known_failures == 0
    target = result.report.targets[0]
    assert target.path == "tests/health.hurl"
    assert target.operation_id == "getHealth"
    assert target.tags == ("smoke",)
    assert [
        (gate.id, gate.source_path, gate.enforcement, gate.final, gate.status)
        for gate in target.gates
    ] == [
        ("security_header", "rules/security.yaml", "warn", True, "would_inject"),
        ("smoke_latency", "qanstitution.yaml", "block", False, "would_inject"),
    ]
    assert "# entroping-gate:" not in source.read_text(encoding="utf-8")
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["targets"][0]["gates"][0]["condition"] == "path startswith '/api'"


def test_run_gate_injection_report_keeps_non_matching_targets_empty(tmp_path: Path) -> None:
    _write_text(
        tmp_path / "qanstitution.yaml",
        """
project: checkout-api
gates:
  - id: billing_latency
    condition: tags contains 'billing'
    gate: duration < 2000
    enforcement: block
""",
    )
    _write_hurl(tmp_path / "tests" / "health.hurl", tags="smoke")

    result = run_gate_injection_report(
        project_root=tmp_path,
        targets=(Path("tests/health.hurl"),),
        output="md",
    )

    assert result.report.summary.total_would_inject == 0
    assert result.report.targets[0].gates == ()
    markdown = result.output_path.read_text(encoding="utf-8")
    assert "No matching gates" in markdown


def test_run_gate_injection_report_marks_active_known_failures(tmp_path: Path) -> None:
    _write_text(
        tmp_path / "qanstitution.yaml",
        """
project: checkout-api
gates:
  - id: latency
    condition: "true"
    gate: duration < 2000
    enforcement: block
ignore_failures:
  - test: tests/other.hurl
    rule_id: latency
    issue_id: GH-122
    expires: "2999-01-01"
    reason: Different target exception.
  - test: tests/health.hurl
    rule_id: latency
    issue_id: GH-123
    expires: "2999-01-01"
    reason: Temporary latency exception.
""",
    )
    _write_hurl(tmp_path / "tests" / "health.hurl")

    result = run_gate_injection_report(
        project_root=tmp_path,
        targets=(Path("tests/health.hurl"),),
        output="md",
    )

    assert result.report.summary.total_would_inject == 0
    assert result.report.summary.total_known_failures == 1
    gate = result.report.targets[0].gates[0]
    assert gate.status == "known_failure"
    assert gate.issue_id == "GH-123"
    assert gate.expires == "2999-01-01"
    assert gate.reason == "Temporary latency exception."
    markdown = result.output_path.read_text(encoding="utf-8")
    assert "GH-123 until 2999-01-01: Temporary latency exception." in markdown


def test_run_gate_injection_report_rejects_expired_known_failures(tmp_path: Path) -> None:
    _write_text(
        tmp_path / "qanstitution.yaml",
        """
project: checkout-api
gates:
  - id: latency
    condition: "true"
    gate: duration < 2000
    enforcement: block
ignore_failures:
  - test: tests/health.hurl
    rule_id: latency
    issue_id: GH-123
    expires: "2000-01-01"
    reason: Expired exception.
""",
    )
    _write_hurl(tmp_path / "tests" / "health.hurl")

    with pytest.raises(GateInjectionReportError, match="Known failure exception expired"):
        run_gate_injection_report(
            project_root=tmp_path,
            targets=(Path("tests/health.hurl"),),
            output="json",
        )


def test_run_gate_injection_report_rejects_malformed_known_failure_expiry(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "qanstitution.yaml",
        """
project: checkout-api
gates:
  - id: latency
    condition: "true"
    gate: duration < 2000
    enforcement: block
ignore_failures:
  - test: tests/health.hurl
    rule_id: latency
    issue_id: GH-123
    expires: tomorrow
    reason: Malformed expiry.
""",
    )
    _write_hurl(tmp_path / "tests" / "health.hurl")

    with pytest.raises(
        GateInjectionReportError,
        match="expires must use YYYY-MM-DD",
    ):
        run_gate_injection_report(
            project_root=tmp_path,
            targets=(Path("tests/health.hurl"),),
            output="json",
        )


def test_compile_gate_injection_report_keeps_external_provenance_absolute(
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

    report = compile_gate_injection_report(
        evidence,
        (hurl_test,),
        root=tmp_path,
        today=date(2026, 6, 5),
    )

    assert report.config_path == external_policy_path.resolve().as_posix()
    assert report.targets[0].gates[0].source_path == external_policy_path.resolve().as_posix()


def test_run_gate_injection_report_rejects_unsafe_targets(tmp_path: Path) -> None:
    _write_text(tmp_path / "qanstitution.yaml", "project: checkout-api\ngates: []\n")
    _write_hurl(tmp_path / "tests" / "health.hurl")

    with pytest.raises(GateInjectionReportError, match="At least one --target"):
        run_gate_injection_report(
            project_root=tmp_path,
            targets=(),
            output="json",
        )

    with pytest.raises(GateInjectionReportError, match="Target must stay inside project"):
        run_gate_injection_report(
            project_root=tmp_path,
            targets=(Path("../health.hurl"),),
            output="json",
        )

    with pytest.raises(GateInjectionReportError, match="Target must stay inside project"):
        run_gate_injection_report(
            project_root=tmp_path,
            targets=(tmp_path.parent / "outside.hurl",),
            output="json",
        )

    _write_text(tmp_path / "tests" / "health.txt", "GET http://api.example.test/health\n")
    with pytest.raises(GateInjectionReportError, match="Expected a .hurl target"):
        run_gate_injection_report(
            project_root=tmp_path,
            targets=(Path("tests/health.txt"),),
            output="json",
        )

    with pytest.raises(GateInjectionReportError, match="Hurl target not found"):
        run_gate_injection_report(
            project_root=tmp_path,
            targets=(Path("tests/missing.hurl"),),
            output="json",
        )


def test_run_gate_injection_report_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_text(tmp_path / "qanstitution.yaml", "project: checkout-api\ngates: []\n")
    _write_hurl(tmp_path / "tests" / "health.hurl")

    def fail_safe_write(
        path: Path,
        content: str,
        *,
        artifact: str,
        root: Path | None = None,
    ) -> Path:
        _ = path, content, artifact, root
        raise SafeWriteError("temporary write failed")

    monkeypatch.setattr(gate_injection_report, "safe_write_text", fail_safe_write)

    with pytest.raises(GateInjectionReportError, match="temporary write failed"):
        run_gate_injection_report(
            project_root=tmp_path,
            targets=(Path("tests/health.hurl"),),
            output="json",
        )
