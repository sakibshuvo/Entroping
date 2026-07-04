import json
import os
from pathlib import Path

from entroping.core.aha_artifact_index import build_aha_artifact_index


def test_aha_artifact_index_reports_present_schema_and_missing_guidance(
    tmp_path: Path,
) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "run-latest.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "private-demo",
            }
        ),
        encoding="utf-8",
    )

    index = build_aha_artifact_index(project_root=tmp_path)
    by_key = {item.key: item for item in index.items}

    assert by_key["run-json"].state == "present"
    assert by_key["run-json"].schema_version == "entroping.run-report.v1"
    assert by_key["run-json"].path == Path("reports/run-latest.json")
    assert by_key["runtime-card-json"].state == "missing"
    assert by_key["runtime-card-json"].hints == (
        "Run entroping report runtime-card --output json after a local run.",
    )
    assert "private-demo" not in repr(index)


def test_aha_artifact_index_marks_symlinked_artifact_unsafe(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    target = tmp_path / "target.json"
    target.write_text('{"schema_version":"entroping.run-report.v1"}\n', encoding="utf-8")
    os.symlink(target, reports_dir / "run-latest.json")

    index = build_aha_artifact_index(project_root=tmp_path)
    by_key = {item.key: item for item in index.items}

    assert by_key["run-json"].state == "unsafe"
    assert by_key["run-json"].schema_version is None
