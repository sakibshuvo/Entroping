"""Tests for effective QAnstitution policy diff reports."""

import json
from pathlib import Path
from typing import cast

import pytest

from entroping.bridge.effective_policy import (
    EffectivePolicyGateReport,
    EffectivePolicyReport,
)
from entroping.bridge.effective_policy_diff import (
    EFFECTIVE_POLICY_DIFF_SCHEMA_VERSION,
    EffectivePolicyDiffError,
    build_effective_policy_diff_report,
    effective_policy_diff_report_to_dict,
    render_effective_policy_diff_markdown,
)
from entroping.models.qanstitution import Enforcement


def _report(
    *,
    imports: tuple[str, ...] = (),
    gates: tuple[EffectivePolicyGateReport, ...],
) -> EffectivePolicyReport:
    return EffectivePolicyReport(
        project="checkout-api",
        config_path="qanstitution.yaml",
        imports=imports,
        gates=gates,
    )


def _gate(
    gate_id: str,
    *,
    source_path: str = "qanstitution.yaml",
    condition: str = "true",
    assertion: str = "duration < 2000",
    enforcement: Enforcement = "block",
    final: bool = False,
    group: str | None = None,
    description: str | None = None,
) -> EffectivePolicyGateReport:
    return EffectivePolicyGateReport(
        id=gate_id,
        source_path=source_path,
        condition=condition,
        gate=assertion,
        enforcement=enforcement,
        final=final,
        group=group,
        description=description,
    )


def test_effective_policy_diff_reports_added_removed_and_changed_evidence() -> None:
    base = _report(
        imports=("rules/base.yaml", "rules/removed.yaml"),
        gates=(
            _gate("latency", final=False, description="old latency"),
            _gate("removed_gate", source_path="rules/removed.yaml"),
            _gate("source_shift", source_path="rules/base.yaml"),
        ),
    )
    current = _report(
        imports=("rules/base.yaml", "rules/current.yaml"),
        gates=(
            _gate("latency", final=True, description="new latency"),
            _gate("new_gate", source_path="rules/current.yaml", enforcement="warn"),
            _gate("source_shift", source_path="qanstitution.yaml"),
        ),
    )

    report = build_effective_policy_diff_report(
        base=base,
        current=current,
        base_path=Path("reports/base-policy.json"),
        current_path=Path("reports/effective-policy.json"),
    )
    payload = effective_policy_diff_report_to_dict(report)

    assert payload["schema_version"] == EFFECTIVE_POLICY_DIFF_SCHEMA_VERSION
    assert payload["status"] == "changed"
    assert payload["summary"] == {
        "added_imports": 1,
        "removed_imports": 1,
        "added_gates": 1,
        "removed_gates": 1,
        "changed_gates": 2,
    }
    assert payload["added_imports"] == [{"path": "rules/current.yaml"}]
    assert payload["removed_imports"] == [{"path": "rules/removed.yaml"}]
    added_gates = cast(list[dict[str, object]], payload["added_gates"])
    removed_gates = cast(list[dict[str, object]], payload["removed_gates"])
    assert added_gates[0]["id"] == "new_gate"
    assert removed_gates[0]["id"] == "removed_gate"
    assert payload["changed_gates"] == [
        {
            "id": "latency",
            "changed_fields": ["description", "final"],
            "base": {
                "id": "latency",
                "source_path": "qanstitution.yaml",
                "condition": "true",
                "gate": "duration < 2000",
                "enforcement": "block",
                "final": False,
                "group": None,
                "description": "old latency",
            },
            "current": {
                "id": "latency",
                "source_path": "qanstitution.yaml",
                "condition": "true",
                "gate": "duration < 2000",
                "enforcement": "block",
                "final": True,
                "group": None,
                "description": "new latency",
            },
        },
        {
            "id": "source_shift",
            "changed_fields": ["source_path"],
            "base": {
                "id": "source_shift",
                "source_path": "rules/base.yaml",
                "condition": "true",
                "gate": "duration < 2000",
                "enforcement": "block",
                "final": False,
                "group": None,
                "description": None,
            },
            "current": {
                "id": "source_shift",
                "source_path": "qanstitution.yaml",
                "condition": "true",
                "gate": "duration < 2000",
                "enforcement": "block",
                "final": False,
                "group": None,
                "description": None,
            },
        },
    ]

    markdown = render_effective_policy_diff_markdown(report)
    assert "# Entroping Effective Policy Diff" in markdown
    assert "| Added imports | 1 |" in markdown
    assert "`rules/current.yaml`" in markdown
    assert "| latency | description, final |" in markdown
    assert "| source_shift | source_path |" in markdown


def test_effective_policy_diff_reports_no_change() -> None:
    base = _report(imports=("rules/base.yaml",), gates=(_gate("latency"),))
    current = _report(imports=("rules/base.yaml",), gates=(_gate("latency"),))

    report = build_effective_policy_diff_report(
        base=base,
        current=current,
        base_path=Path("base.json"),
        current_path=Path("current.json"),
    )

    assert effective_policy_diff_report_to_dict(report)["status"] == "unchanged"
    assert "No effective policy differences found." in render_effective_policy_diff_markdown(
        report
    )


def test_effective_policy_diff_markdown_marks_empty_sections_for_gate_only_change() -> None:
    base = _report(gates=(_gate("latency"),))
    current = _report(gates=(_gate("latency", assertion="duration < 1000"),))

    report = build_effective_policy_diff_report(
        base=base,
        current=current,
        base_path=Path("base.json"),
        current_path=Path("current.json"),
    )

    markdown = render_effective_policy_diff_markdown(report)

    assert "## Added Imports\n\nNone." in markdown
    assert "## Removed Imports\n\nNone." in markdown
    assert "## Added Gates\n\nNone." in markdown
    assert "## Removed Gates\n\nNone." in markdown
    assert "| latency | gate |" in markdown


def test_effective_policy_diff_markdown_marks_empty_changed_gates_for_import_only_change() -> None:
    base = _report(imports=("rules/old.yaml",), gates=(_gate("latency"),))
    current = _report(imports=("rules/new.yaml",), gates=(_gate("latency"),))

    report = build_effective_policy_diff_report(
        base=base,
        current=current,
        base_path=Path("base.json"),
        current_path=Path("current.json"),
    )

    markdown = render_effective_policy_diff_markdown(report)

    assert "`rules/new.yaml`" in markdown
    assert "`rules/old.yaml`" in markdown
    assert "## Added Gates\n\nNone." in markdown
    assert "## Removed Gates\n\nNone." in markdown
    assert "## Changed Gates\n\nNone." in markdown


def test_effective_policy_diff_rejects_duplicate_gate_ids() -> None:
    base = _report(gates=(_gate("latency"), _gate("latency")))
    current = _report(gates=(_gate("latency"),))

    with pytest.raises(EffectivePolicyDiffError, match="duplicate gate id"):
        build_effective_policy_diff_report(
            base=base,
            current=current,
            base_path=Path("base.json"),
            current_path=Path("current.json"),
        )


def test_effective_policy_diff_json_is_value_safe() -> None:
    base = _report(gates=(_gate("latency"),))
    current = _report(gates=(_gate("latency", assertion="duration < 1000"),))

    payload = effective_policy_diff_report_to_dict(
        build_effective_policy_diff_report(
            base=base,
            current=current,
            base_path=Path("base.json"),
            current_path=Path("current.json"),
        )
    )

    assert "secret" not in json.dumps(payload).lower()
