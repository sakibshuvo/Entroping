"""Aha readiness scorecard tests."""

import json
from pathlib import Path
from subprocess import CompletedProcess, run

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "aha_readiness.py"


def run_aha_readiness(
    *args: str,
    root: Path = REPO_ROOT,
) -> CompletedProcess[str]:
    return run(
        ["python", str(SCRIPT), "--root", str(root), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_aha_readiness_strict_rejects_not_ready_state(tmp_path: Path) -> None:
    root = _build_aha_root(tmp_path, include_failure_fixture=False)
    result = run_aha_readiness("--format", "json", "--strict", root=root)
    payload = _json_payload(result.stdout)

    assert result.returncode == 1
    assert payload["status"] == "blocked"
    assert payload["local_blockers"]
    assert payload["external_blockers"]
    assert "aha readiness check failed" in result.stderr


def test_aha_readiness_separates_local_and_external_blockers(tmp_path: Path) -> None:
    root = _build_aha_root(tmp_path, include_failure_fixture=True, install_deferred=True)
    result = run_aha_readiness("--format", "json", root=root)
    payload = _json_payload(result.stdout)

    assert result.returncode == 0
    assert payload["status"] == "blocked"
    assert payload["local_blockers"] == []
    assert payload["external_blockers"]
    assert not payload["aha_ready"]


def test_aha_readiness_returns_ready_payload_when_all_checks_pass(tmp_path: Path) -> None:
    root = _build_aha_root(tmp_path, include_failure_fixture=True, install_deferred=False)
    result = run_aha_readiness("--format", "json", root=root)
    payload = _json_payload(result.stdout)

    assert result.returncode == 0
    assert payload["status"] == "ready"
    assert payload["aha_ready"] is True
    assert payload["ready_checks"] == payload["total_checks"]
    assert payload["local_blockers"] == []
    assert payload["external_blockers"] == []


def test_aha_readiness_allows_unrelated_init_demo_deferral(tmp_path: Path) -> None:
    root = _build_aha_root(tmp_path, include_failure_fixture=True, install_deferred=False)
    decision_path = root / "docs" / "meta" / "ZERO_CONFIG_DEMO_ENTRYPOINT.md"
    decision_path.write_text(
        decision_path.read_text(encoding="utf-8")
        + "\n| `entroping init --demo` | Deferred | future setup command |\n",
        encoding="utf-8",
    )

    result = run_aha_readiness("--format", "json", root=root)
    payload = _json_payload(result.stdout)

    assert result.returncode == 0
    assert payload["status"] == "ready"
    assert payload["aha_ready"] is True
    assert payload["external_blockers"] == []


def test_aha_readiness_partial_check_is_reflected_without_strict(tmp_path: Path) -> None:
    root = _build_aha_root(
        tmp_path,
        include_failure_fixture=True,
        omit_demo_matrix_marker=True,
        install_deferred=False,
    )
    result = run_aha_readiness("--format", "json", root=root)
    payload = _json_payload(result.stdout)

    assert result.returncode == 0
    assert payload["status"] == "partial"
    checks = payload["checks"]
    assert isinstance(checks, dict)
    demo_matrix = checks.get("demo_generation_and_run_matrix")
    assert isinstance(demo_matrix, dict)
    assert demo_matrix["status"] == "partial"


def _build_aha_root(
    tmp_path: Path,
    *,
    include_failure_fixture: bool,
    install_deferred: bool = True,
    include_install: bool = True,
    omit_demo_matrix_marker: bool = False,
) -> Path:
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "examples" / "aha-broken-endpoint").mkdir(parents=True, exist_ok=True)
    (root / "examples" / "ai-regression-demo").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "meta").mkdir(parents=True, exist_ok=True)

    (root / "scripts" / "demo.sh").write_text(
        "#!/usr/bin/env bash\nscripts/live_demo_smoke.sh\n",
        encoding="utf-8",
    )
    (root / "scripts" / "ai_regression_demo.sh").write_text(
        "#!/usr/bin/env bash\nprintf 'request_id_header blocked\n'\n",
        encoding="utf-8",
    )

    demo_matrix = "scripts/demo.sh\nscripts/ai_regression_demo.sh\n"
    if not omit_demo_matrix_marker:
        demo_matrix += "uv run python scripts/launch_readiness.py --strict\n"
    (root / "scripts" / "demo_matrix.sh").write_text(demo_matrix, encoding="utf-8")

    if include_failure_fixture:
        (root / "examples" / "aha-broken-endpoint" / "README.md").write_text(
            "Aha broken-endpoint fixture\nentroping run --env local --tag aha-endpoint\n"
            "no_missing_product_endpoint\n",
            encoding="utf-8",
        )

    (root / "examples" / "ai-regression-demo" / "README.md").write_text(
        "request_id_header walkthrough\nX-Request-Id\nscripts/ai_regression_demo.sh\n",
        encoding="utf-8",
    )

    if include_install:
        decision = (
            "Current: entroping demo --project <path> is deferred until package "
            "prerequisites are ready.\n"
            if install_deferred
            else "Current: entroping demo --project <path> is ready and configured.\n"
        )
        (root / "docs" / "meta" / "ZERO_CONFIG_DEMO_ENTRYPOINT.md").write_text(
            decision,
            encoding="utf-8",
        )

    return root


def _json_payload(output: str) -> dict[str, object]:
    payload = json.loads(output)
    assert isinstance(payload, dict)
    return payload
