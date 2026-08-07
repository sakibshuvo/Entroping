"""CLI compatibility tests for provider-scorecard commands."""
# ruff: noqa: E402

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from support.provider_scorecard import (  # pyright: ignore[reportImplicitRelativeImport]
    case,
    document,
    report,
    run,
    validate,
    write_scorecard,
)


def test_authenticated_cli_validate_and_report_are_deterministic_and_value_free(
    tmp_path: Path,
) -> None:
    # Given: three distinct authenticated, eligible samples.
    path = write_scorecard(tmp_path, document(case(1), case(2), case(3)))

    # When: validate and report are invoked twice through the public command.
    validation = validate(tmp_path, path)
    first = report(tmp_path, path)
    second = report(tmp_path, path)

    # Then: validation succeeds and deterministic output contains no raw receipt values.
    assert validation.returncode == 0
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    assert "reservation-" not in first.stdout
    assert json.loads(first.stdout)["scorecards"][0]["manual_promotion_eligible"] is True


def test_markdown_is_stable_value_free_and_exposes_tier_and_lane(tmp_path: Path) -> None:
    path = write_scorecard(tmp_path, document(case(1)))
    first = report(tmp_path, path, output_format="md")
    second = report(tmp_path, path, output_format="md")
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    assert "| tier_c | security-runtime |" in first.stdout
    assert "reservation-" not in first.stdout
    assert "diff_sha256" not in first.stdout


def test_report_output_path_writes_only_under_factory_metrics(tmp_path: Path) -> None:
    path = write_scorecard(tmp_path, document(case(1)))
    written = report(tmp_path, path, output=".entroping/factory-metrics/report.json")
    refused = report(tmp_path, path, output="outside.json")
    target = tmp_path / ".entroping" / "factory-metrics" / "report.json"
    assert written.returncode == 0
    assert target.is_file()
    assert refused.returncode == 2


def test_legacy_factory_metrics_commands_remain_available(tmp_path: Path) -> None:
    # Given: an empty legacy ledger in its permitted local location.
    ledger = tmp_path / ".entroping" / "factory-metrics" / "events.jsonl"
    ledger.parent.mkdir(parents=True)
    _ = ledger.write_text("", encoding="utf-8")

    # When: a legacy read-only command is invoked through the shared parser.
    result = run(tmp_path, "validate", "--ledger", str(ledger.relative_to(tmp_path)), "--json")

    # Then: the legacy schema contract stays intact.
    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "valid"
