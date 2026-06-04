"""Tests for effective QAnstitution policy evidence reports."""

import json
from pathlib import Path

import pytest

import entroping.core.effective_policy_report as effective_policy_report
from entroping.bridge.effective_policy import (
    compile_effective_policy_report,
    render_effective_policy_markdown,
)
from entroping.core.config_loader import load_qanstitution_evidence
from entroping.core.effective_policy_report import (
    EffectivePolicyReportError,
    run_effective_policy_report,
)
from entroping.core.safe_write import SafeWriteError


def _write_yaml(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.lstrip(), encoding="utf-8")


def _write_imported_policy(root: Path) -> None:
    _write_yaml(
        root / "rules" / "security.yaml",
        """
project: imported-security
gates:
  - id: security_header
    description: Imported request ID requirement
    condition: path startswith '/api'
    gate: header "X-Request-Id" exists
    enforcement: warn
    final: true
  - id: smoke_latency
    condition: tags contains 'smoke'
    gate: duration < 700
    enforcement: warn
""",
    )
    _write_yaml(
        root / "qanstitution.yaml",
        """
project: checkout-api
imports:
  - ./rules/security.yaml
gates:
  - id: smoke_latency
    description: Local smoke latency override
    condition: tags contains 'smoke'
    gate: duration < 500
    enforcement: block
""",
    )


def test_compile_effective_policy_report_renders_gate_provenance(tmp_path: Path) -> None:
    _write_imported_policy(tmp_path)

    evidence = load_qanstitution_evidence(tmp_path / "qanstitution.yaml")
    report = compile_effective_policy_report(evidence, root=tmp_path)

    assert report.schema_version == "entroping.effective-policy-report.v1"
    assert report.project == "checkout-api"
    assert report.config_path == "qanstitution.yaml"
    assert report.imports == ("rules/security.yaml",)
    assert [(gate.id, gate.source_path, gate.final) for gate in report.gates] == [
        ("security_header", "rules/security.yaml", True),
        ("smoke_latency", "qanstitution.yaml", False),
    ]
    assert report.gates[1].description == "Local smoke latency override"


def test_compile_effective_policy_report_includes_gate_group_provenance(
    tmp_path: Path,
) -> None:
    _write_yaml(
        tmp_path / "qanstitution.yaml",
        """
project: checkout-api
gate_groups:
  api_baseline:
    gates:
      - id: no_server_errors
        condition: "true"
        gate: status < 500
        enforcement: block
gates:
  - group: api_baseline
""",
    )

    evidence = load_qanstitution_evidence(tmp_path / "qanstitution.yaml")
    report = compile_effective_policy_report(evidence, root=tmp_path)
    markdown = render_effective_policy_markdown(report)

    assert [(gate.id, gate.source_path, gate.group) for gate in report.gates] == [
        ("no_server_errors", "qanstitution.yaml", "api_baseline")
    ]
    assert (
        "| ID | Source | Group | Enforcement | Final | Condition | Assertion | Description |"
        in markdown
    )
    assert "api_baseline" in markdown


def test_render_effective_policy_markdown_escapes_table_cells(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "qanstitution.yaml",
        """
project: checkout-api
gates:
  - id: table_gate
    description: "contains | pipe"
    condition: "true"
    gate: header "X-Request-Id" exists
    enforcement: warn
""",
    )

    evidence = load_qanstitution_evidence(tmp_path / "qanstitution.yaml")
    markdown = render_effective_policy_markdown(
        compile_effective_policy_report(evidence, root=tmp_path)
    )

    assert "# Entroping Effective Policy" in markdown
    assert "contains \\| pipe" in markdown
    assert "header \"X-Request-Id\" exists" in markdown
    assert "qanstitution.yaml" in markdown


def test_compile_effective_policy_report_uses_absolute_paths_outside_root(
    tmp_path: Path,
) -> None:
    _write_yaml(
        tmp_path / "policy" / "qanstitution.yaml",
        """
project: checkout-api
gates:
  - id: global_latency
    condition: "true"
    gate: duration < 2000
    enforcement: block
""",
    )

    evidence = load_qanstitution_evidence(tmp_path / "policy" / "qanstitution.yaml")
    report = compile_effective_policy_report(evidence, root=tmp_path / "other-root")

    assert report.config_path == (tmp_path / "policy" / "qanstitution.yaml").resolve().as_posix()
    assert report.gates[0].source_path == (
        tmp_path / "policy" / "qanstitution.yaml"
    ).resolve().as_posix()


def test_run_effective_policy_report_writes_json_and_markdown(tmp_path: Path) -> None:
    _write_imported_policy(tmp_path)

    markdown_result = run_effective_policy_report(project_root=tmp_path, output="md")
    json_result = run_effective_policy_report(project_root=tmp_path, output="json")

    assert markdown_result.output_path == tmp_path / "reports" / "effective-policy.md"
    assert json_result.output_path == tmp_path / "reports" / "effective-policy.json"
    assert "smoke_latency" in markdown_result.output_path.read_text(encoding="utf-8")
    payload = json.loads(json_result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.effective-policy-report.v1"
    assert payload["gates"][0]["source_path"] == "rules/security.yaml"


def test_run_effective_policy_report_wraps_load_errors(tmp_path: Path) -> None:
    _write_yaml(tmp_path / "qanstitution.yaml", "project: [")

    with pytest.raises(EffectivePolicyReportError, match="Invalid YAML"):
        run_effective_policy_report(project_root=tmp_path, output="md")


def test_run_effective_policy_report_wraps_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_imported_policy(tmp_path)

    def fail_write(*args: object, **kwargs: object) -> Path:
        raise SafeWriteError("disk unavailable")

    monkeypatch.setattr(effective_policy_report, "safe_write_text", fail_write)

    with pytest.raises(EffectivePolicyReportError, match="disk unavailable"):
        run_effective_policy_report(project_root=tmp_path, output="md")
