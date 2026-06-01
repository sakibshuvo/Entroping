"""Release evidence ledger validation."""

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "release_evidence.py"


def run_release_evidence(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_release_evidence_json_reports_alpha_ci_and_stable_blockers() -> None:
    result = run_release_evidence("--format", "json", "--strict")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "entroping.release-evidence.v1"
    assert payload["stable_core_ready"] is False
    assert payload["release_count"] >= 2
    assert payload["latest_release"] == "v0.1.1-alpha"
    assert payload["latest_main_ci"]["conclusion"] == "success"
    assert payload["latest_main_ci"]["commit"] == "e667e438f6ebc95a9cf4d4c350b433e175ae0184"
    assert "package-index proof" in payload["stable_core_blockers"]
    assert "real downstream user feedback" in payload["stable_core_blockers"]
    assert payload["ledger_path"] == "docs/meta/release-evidence.json"


def test_release_evidence_markdown_is_maintainer_readable() -> None:
    result = run_release_evidence()

    assert result.returncode == 0, result.stderr
    assert "# Release Evidence" in result.stdout
    assert "v0.1.1-alpha" in result.stdout
    assert "Recorded main CI evidence" in result.stdout
    assert "Latest main CI" not in result.stdout
    assert "Stable-core ready: `false`" in result.stdout


def test_release_evidence_docs_explain_ci_evidence_is_recorded() -> None:
    docs = (REPO_ROOT / "docs" / "meta" / "RELEASE_EVIDENCE.md").read_text(
        encoding="utf-8"
    )

    assert "last reviewed `main` CI evidence" in docs
    assert "does not automatically prove the current `main` HEAD" in docs


def test_release_evidence_strict_rejects_malformed_ledger(tmp_path: Path) -> None:
    ledger_dir = tmp_path / "docs" / "meta"
    ledger_dir.mkdir(parents=True)
    (ledger_dir / "release-evidence.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.release-evidence.v1",
                "stable_core_ready": True,
                "stable_core_blockers": [],
                "releases": [
                    {
                        "tag": "v0.1.1-alpha",
                        "kind": "github-prerelease",
                        "published_at": "2026-05-31T11:22:04Z",
                        "commit": "short",
                        "url": "not-a-url",
                        "evidence": {},
                    }
                ],
                "latest_main_ci": {
                    "workflow": "CI",
                    "run_id": "not-an-int",
                    "conclusion": "pending",
                    "commit": "short",
                    "url": "not-a-url",
                },
            }
        ),
        encoding="utf-8",
    )

    result = run_release_evidence("--root", str(tmp_path), "--strict")

    assert result.returncode == 1
    assert "release evidence check failed" in result.stderr
    assert "stable_core_ready must remain false" in result.stderr
    assert "releases must contain at least two entries" in result.stderr
    assert "latest_main_ci.conclusion must be success" in result.stderr


def test_release_check_runs_release_evidence_validator() -> None:
    release_check = (REPO_ROOT / "scripts" / "release_check.sh").read_text(
        encoding="utf-8"
    )

    assert "scripts/release_evidence.py --strict" in release_check
