"""Release evidence ledger validation."""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "release_evidence.py"
LEDGER_SCHEMA = "entroping.release-evidence.v1"
DOWNSTREAM_SCHEMA = "entroping.downstream-smoke.v1"
COMMIT_A = "a" * 40
COMMIT_B = "b" * 40
COMMIT_C = "c" * 40
COMMIT_D = "d" * 40


def run_release_evidence(
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


def write_release_evidence_ledger(
    root: Path,
    *,
    ci_run_id: int = 111,
    ci_commit: str = COMMIT_A,
    pages_run_id: int = 222,
    pages_commit: str = COMMIT_B,
) -> Path:
    ledger_dir = root / "docs" / "meta"
    ledger_dir.mkdir(parents=True)
    ledger_path = ledger_dir / "release-evidence.json"
    ledger_path.write_text(
        json.dumps(
            {
                "schema_version": LEDGER_SCHEMA,
                "stable_core_ready": False,
                "stable_core_blockers": [
                    "package-index proof",
                    "real downstream user feedback",
                    "stable-core compatibility decision",
                ],
                "releases": [
                    {
                        "tag": "v0.1.1-alpha",
                        "kind": "github-prerelease",
                        "published_at": "2026-05-31T11:22:04Z",
                        "commit": COMMIT_A,
                        "url": "https://github.com/sakibshuvo/Entroping/releases/tag/v0.1.1-alpha",
                        "evidence": {"release_gate": "scripts/release_check.sh"},
                    },
                    {
                        "tag": "v0.1.0-alpha",
                        "kind": "github-prerelease",
                        "published_at": "2026-05-30T08:54:33Z",
                        "commit": COMMIT_B,
                        "url": "https://github.com/sakibshuvo/Entroping/releases/tag/v0.1.0-alpha",
                        "evidence": {"release_gate": "scripts/release_check.sh"},
                    },
                ],
                "release_candidates": [
                    {
                        "name": "v0.1.2-alpha-rc.1",
                        "kind": "local-release-candidate",
                        "recorded_at": "2026-06-01T11:25:51Z",
                        "commit": COMMIT_A,
                        "release_gate": "scripts/release_check.sh --require-live-demo",
                        "release_gate_result": "pass",
                        "ci_run_id": ci_run_id,
                        "pages_run_id": pages_run_id,
                        "release_notes": (
                            "Release-candidate notes preserve the alpha boundary: "
                            "this is not stable-core, not package-index proof, "
                            "and not real downstream user feedback."
                        ),
                        "stable_boundary": (
                            "alpha release-candidate evidence only; not package-index "
                            "proof and not stable-core proof"
                        ),
                    }
                ],
                "latest_main_ci": {
                    "workflow": "CI",
                    "run_id": ci_run_id,
                    "created_at": "2026-06-01T05:08:06Z",
                    "event": "push",
                    "conclusion": "success",
                    "commit": ci_commit,
                    "url": f"https://github.com/sakibshuvo/Entroping/actions/runs/{ci_run_id}",
                },
                "latest_pages_ci": {
                    "workflow": "Pages",
                    "run_id": pages_run_id,
                    "created_at": "2026-06-01T05:08:06Z",
                    "event": "push",
                    "conclusion": "success",
                    "commit": pages_commit,
                    "url": f"https://github.com/sakibshuvo/Entroping/actions/runs/{pages_run_id}",
                },
                "downstream_smoke": {
                    "status": "local-pass",
                    "schema_version": DOWNSTREAM_SCHEMA,
                    "recorded_at": "2026-06-01T05:02:00Z",
                    "command": "uv run python scripts/downstream_smoke.py --format json",
                    "stable_boundary": (
                        "maintainer-controlled local smoke evidence only; "
                        "not real downstream user feedback"
                    ),
                },
                "package_index": {
                    "status": "not-published",
                    "blocked_by": "TestPyPI proof has not run yet",
                    "runbook": "docs/meta/PYPI_RELEASE_RUNBOOK.md",
                },
            }
        ),
        encoding="utf-8",
    )
    return ledger_path


def write_freshness_fixture(
    path: Path,
    *,
    ci_run_id: int = 111,
    ci_commit: str = COMMIT_A,
    pages_run_id: int = 222,
    pages_commit: str = COMMIT_B,
) -> Path:
    path.write_text(
        json.dumps(
            {
                "latest_main_ci": {
                    "workflow": "CI",
                    "run_id": ci_run_id,
                    "created_at": "2026-06-01T06:00:00Z",
                    "event": "push",
                    "conclusion": "success",
                    "commit": ci_commit,
                    "url": f"https://github.com/sakibshuvo/Entroping/actions/runs/{ci_run_id}",
                },
                "latest_pages_ci": {
                    "workflow": "Pages",
                    "run_id": pages_run_id,
                    "created_at": "2026-06-01T06:00:00Z",
                    "event": "push",
                    "conclusion": "success",
                    "commit": pages_commit,
                    "url": f"https://github.com/sakibshuvo/Entroping/actions/runs/{pages_run_id}",
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_release_evidence_json_reports_alpha_ci_and_stable_blockers() -> None:
    result = run_release_evidence("--format", "json", "--strict")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "entroping.release-evidence.v1"
    assert payload["stable_core_ready"] is False
    assert payload["release_count"] >= 2
    assert payload["release_candidate_count"] >= 1
    assert payload["latest_release"] == "v0.1.1-alpha"
    assert payload["latest_main_ci"]["conclusion"] == "success"
    assert payload["latest_main_ci"]["commit"] == "1e8125489a8b3fe7a8d4a2112c80b172c17cf693"
    assert payload["latest_main_ci"]["run_id"] == 26751047871
    assert payload["latest_pages_ci"]["conclusion"] == "success"
    assert payload["latest_pages_ci"]["workflow"] == "Pages"
    assert payload["latest_pages_ci"]["commit"] == "1e8125489a8b3fe7a8d4a2112c80b172c17cf693"
    assert payload["latest_pages_ci"]["run_id"] == 26751047840
    assert payload["release_candidates"][0]["name"] == "v0.1.2-alpha-rc.1"
    assert payload["release_candidates"][0]["release_gate_result"] == "pass"
    assert payload["downstream_smoke"]["status"] == "local-pass"
    assert payload["downstream_smoke"]["schema_version"] == "entroping.downstream-smoke.v1"
    assert payload["downstream_smoke"]["stable_boundary"].startswith(
        "maintainer-controlled local smoke"
    )
    assert payload["freshness"]["status"] == "not_checked"
    assert "repeated release evidence" not in payload["stable_core_blockers"]
    assert "package-index proof" in payload["stable_core_blockers"]
    assert "real downstream user feedback" in payload["stable_core_blockers"]
    assert payload["ledger_path"] == "docs/meta/release-evidence.json"


def test_release_evidence_blockers_match_stable_core_readiness() -> None:
    release_result = run_release_evidence("--format", "json", "--strict")
    readiness_result = subprocess.run(
        ["python", str(REPO_ROOT / "scripts" / "stable_core_readiness.py"), "--format", "json"],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert release_result.returncode == 0, release_result.stderr
    assert readiness_result.returncode == 0, readiness_result.stderr
    release_payload = json.loads(release_result.stdout)
    readiness_payload = json.loads(readiness_result.stdout)
    assert release_payload["stable_core_blockers"] == readiness_payload["blockers"]


def test_release_evidence_markdown_is_maintainer_readable() -> None:
    result = run_release_evidence()

    assert result.returncode == 0, result.stderr
    assert "# Release Evidence" in result.stdout
    assert "v0.1.1-alpha" in result.stdout
    assert "Recorded main CI evidence" in result.stdout
    assert "Recorded Pages evidence" in result.stdout
    assert "Release candidates" in result.stdout
    assert "v0.1.2-alpha-rc.1" in result.stdout
    assert "Downstream smoke evidence" in result.stdout
    assert "Latest main CI" not in result.stdout
    assert "Stable-core ready: `false`" in result.stdout


def test_release_evidence_docs_explain_ci_evidence_is_recorded() -> None:
    docs = (REPO_ROOT / "docs" / "meta" / "RELEASE_EVIDENCE.md").read_text(
        encoding="utf-8"
    )

    assert "last reviewed `main` CI evidence" in docs
    assert "last reviewed Pages deployment evidence" in docs
    assert "local alpha release-candidate rehearsal evidence" in docs
    assert "maintainer-controlled local smoke evidence" in docs
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
                "release_candidates": [
                    {
                        "name": "",
                        "kind": "wrong",
                        "recorded_at": "not-a-date",
                        "commit": "short",
                        "release_gate": "pytest",
                        "release_gate_result": "failed",
                        "ci_run_id": "not-an-int",
                        "pages_run_id": 0,
                        "release_notes": "stable",
                        "stable_boundary": "stable",
                    }
                ],
                "latest_main_ci": {
                    "workflow": "CI",
                    "run_id": "not-an-int",
                    "conclusion": "pending",
                    "commit": "short",
                    "url": "not-a-url",
                },
                "latest_pages_ci": {
                    "workflow": "Wrong",
                    "run_id": 0,
                    "conclusion": "pending",
                    "event": "workflow_dispatch",
                    "created_at": "not-a-date",
                    "commit": "short",
                    "url": "not-a-url",
                },
                "downstream_smoke": {
                    "status": "real-user-feedback",
                    "schema_version": "wrong",
                    "command": "python smoke.py",
                    "recorded_at": "not-a-date",
                    "stable_boundary": "stable",
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
    assert "release_candidates[0].kind must be local-release-candidate" in result.stderr
    assert (
        "release_candidates[0].release_gate must be scripts/release_check.sh"
        " --require-live-demo"
        in result.stderr
    )
    assert (
        "release_candidates[0].release_notes must preserve alpha/stable-core boundaries"
        in result.stderr
    )
    assert "latest_main_ci.conclusion must be success" in result.stderr
    assert "latest_pages_ci.workflow must be Pages" in result.stderr
    assert "downstream_smoke.schema_version must be entroping.downstream-smoke.v1" in result.stderr
    assert (
        "downstream_smoke.stable_boundary must say it is not real downstream user feedback"
        in result.stderr
    )


def test_release_evidence_freshness_accepts_current_fixture(tmp_path: Path) -> None:
    write_release_evidence_ledger(tmp_path)
    fixture = write_freshness_fixture(tmp_path / "freshness.json")

    result = run_release_evidence(
        "--root",
        str(tmp_path),
        "--format",
        "json",
        "--strict",
        "--check-freshness",
        "--freshness-input",
        str(fixture),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    assert payload["freshness"]["status"] == "current"
    assert payload["freshness"]["source"] == str(fixture)
    assert payload["freshness"]["failures"] == []


def test_release_evidence_freshness_rejects_stale_fixture(tmp_path: Path) -> None:
    write_release_evidence_ledger(tmp_path)
    fixture = write_freshness_fixture(
        tmp_path / "freshness.json",
        ci_run_id=333,
        ci_commit=COMMIT_C,
        pages_run_id=444,
        pages_commit=COMMIT_D,
    )

    result = run_release_evidence(
        "--root",
        str(tmp_path),
        "--format",
        "json",
        "--strict",
        "--check-freshness",
        "--freshness-input",
        str(fixture),
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "fail"
    assert payload["freshness"]["status"] == "stale"
    assert "release evidence freshness check failed" in result.stderr
    assert "latest_main_ci.run_id is 111 but latest successful main run is 333" in result.stderr
    assert (
        f"latest_main_ci.commit is {COMMIT_A} but latest successful main run is {COMMIT_C}"
        in result.stderr
    )
    assert "latest_pages_ci.run_id is 222 but latest successful main run is 444" in result.stderr
    assert (
        f"latest_pages_ci.commit is {COMMIT_B} but latest successful main run is {COMMIT_D}"
        in result.stderr
    )


def test_release_evidence_freshness_reports_missing_gh_as_unavailable(tmp_path: Path) -> None:
    write_release_evidence_ledger(tmp_path)
    env = os.environ.copy()
    env["PATH"] = str(tmp_path / "missing-bin")

    result = run_release_evidence(
        "--root",
        str(tmp_path),
        "--format",
        "json",
        "--strict",
        "--check-freshness",
        env=env,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    assert payload["freshness"]["status"] == "unavailable"
    assert "gh executable unavailable" in payload["freshness"]["message"]


def test_release_evidence_freshness_reports_gh_errors_as_unavailable(tmp_path: Path) -> None:
    write_release_evidence_ledger(tmp_path)
    fake_gh = tmp_path / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "sys.stderr.write('not authenticated\\n')\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"

    result = run_release_evidence(
        "--root",
        str(tmp_path),
        "--format",
        "json",
        "--check-freshness",
        env=env,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["freshness"]["status"] == "unavailable"
    assert "not authenticated" in payload["freshness"]["message"]


def test_release_evidence_freshness_reads_latest_runs_from_gh(tmp_path: Path) -> None:
    write_release_evidence_ledger(tmp_path)
    fake_gh = tmp_path / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import sys\n"
        "workflow = sys.argv[sys.argv.index('--workflow') + 1]\n"
        "run_id = 111 if workflow == 'CI' else 222\n"
        "commit = 'a' * 40 if workflow == 'CI' else 'b' * 40\n"
        "print(json.dumps([{\n"
        "    'databaseId': run_id,\n"
        "    'workflowName': workflow,\n"
        "    'headSha': commit,\n"
        "    'conclusion': 'success',\n"
        "    'event': 'push',\n"
        "    'createdAt': '2026-06-01T06:00:00Z',\n"
        "    'url': f'https://github.com/sakibshuvo/Entroping/actions/runs/{run_id}',\n"
        "}]))\n",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"

    result = run_release_evidence(
        "--root",
        str(tmp_path),
        "--format",
        "json",
        "--strict",
        "--check-freshness",
        env=env,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["freshness"]["status"] == "current"
    assert payload["freshness"]["source"] == "gh run list --repo sakibshuvo/Entroping"
    assert payload["freshness"]["latest"]["latest_main_ci"]["run_id"] == 111
    assert payload["freshness"]["latest"]["latest_pages_ci"]["run_id"] == 222


def test_release_check_runs_release_evidence_validator() -> None:
    release_check = (REPO_ROOT / "scripts" / "release_check.sh").read_text(
        encoding="utf-8"
    )

    assert "scripts/release_evidence.py --strict" in release_check
