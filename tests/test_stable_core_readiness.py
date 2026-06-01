"""Stable-core readiness evidence checks."""

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "stable_core_readiness.py"


def run_stable_core_readiness(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_stable_core_readiness_json_reports_alpha_blockers() -> None:
    result = run_stable_core_readiness("--format", "json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "entroping.stable-core-readiness.v1"
    assert payload["stable_core_ready"] is False
    assert "repeated release evidence" in payload["blockers"]
    assert payload["evidence"]["release_evidence_ledger"]["status"] == "present"
    assert payload["evidence"]["release_check"]["status"] == "present"
    assert payload["evidence"]["security_threat_model"]["status"] == "present"
    assert set(payload["blocker_issue_map"]) == set(payload["blockers"])
    assert payload["blocker_issue_map"]["repeated release evidence"] == [
        {
            "number": 307,
            "title": "stable-core: repeat alpha release evidence cycle",
            "url": "https://github.com/sakibshuvo/Entroping/issues/307",
            "status": "ready",
        }
    ]
    assert [
        issue["number"]
        for issue in payload["blocker_issue_map"]["package-index proof"]
    ] == [303, 304, 305]
    assert [
        issue["number"]
        for issue in payload["blocker_issue_map"]["real downstream user feedback"]
    ] == [306, 318]
    assert payload["blocker_issue_map"]["real downstream user feedback"][1]["status"] == "done"
    assert [
        issue["number"]
        for issue in payload["blocker_issue_map"]["stable-core compatibility decision"]
    ] == [308]


def test_stable_core_readiness_markdown_links_blocker_issues() -> None:
    result = run_stable_core_readiness()

    assert result.returncode == 0, result.stderr
    assert "## Blocker Issue Map" in result.stdout
    assert (
        "- repeated release evidence: "
        "[#307](https://github.com/sakibshuvo/Entroping/issues/307)"
        in result.stdout
    )
    assert (
        "- package-index proof: "
        "[#303](https://github.com/sakibshuvo/Entroping/issues/303), "
        "[#304](https://github.com/sakibshuvo/Entroping/issues/304), "
        "[#305](https://github.com/sakibshuvo/Entroping/issues/305)"
        in result.stdout
    )
    assert (
        "- real downstream user feedback: "
        "[#306](https://github.com/sakibshuvo/Entroping/issues/306), "
        "[#318](https://github.com/sakibshuvo/Entroping/issues/318)"
        in result.stdout
    )


def test_stable_core_readiness_strict_rejects_missing_evidence(tmp_path: Path) -> None:
    result = run_stable_core_readiness("--root", str(tmp_path), "--strict")

    assert result.returncode == 1
    assert "stable-core evidence check failed" in result.stderr
    assert "README.md" in result.stderr


def test_release_check_runs_stable_core_evidence_check() -> None:
    release_script = (REPO_ROOT / "scripts" / "release_check.sh").read_text(encoding="utf-8")

    assert "scripts/stable_core_readiness.py --strict" in release_script
