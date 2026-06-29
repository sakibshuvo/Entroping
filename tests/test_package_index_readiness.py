import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "package_index_readiness.py"


def run_package_index_readiness(
    *args: str,
    root: Path = REPO_ROOT,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def copy_readiness_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for relative in (
        ".github/workflows/publish-python-package.yml",
        "docs/meta/PYPI_RELEASE_RUNBOOK.md",
        "docs/meta/release-evidence.json",
        "pyproject.toml",
    ):
        source = REPO_ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = shutil.copyfile(source, target)
    return root


def test_package_index_readiness_reports_repo_guardrails_without_overclaiming() -> None:
    result = run_package_index_readiness("--format", "json", "--strict")

    assert result.returncode == 0, result.stderr
    payload = _json_payload(result.stdout)
    assert payload["schema_version"] == "entroping.package-index-readiness.v1"
    assert payload["repo_guardrails_ready"] is True
    assert payload["package_index_ready"] is False
    assert _string_list(payload, "repo_failures") == []
    assert any(
        "TestPyPI Trusted Publisher" in requirement
        for requirement in _string_list(payload, "external_requirements")
    )
    assert _check(payload, "publish_workflow")["status"] == "pass"
    assert _check(payload, "release_evidence_boundary")["status"] == "pass"
    assert _check(payload, "runbook_preflight")["status"] == "pass"


def test_package_index_readiness_distinguishes_publish_evidence_gaps(tmp_path: Path) -> None:
    root = copy_readiness_fixture(tmp_path)
    result = run_package_index_readiness("--format", "json", "--strict", root=root)

    assert result.returncode == 0, result.stderr
    payload = _json_payload(result.stdout)
    detail = str(_check(payload, "release_evidence_boundary")["detail"])

    assert "TestPyPI" in detail
    assert "PyPI" in detail
    assert _check(payload, "release_evidence_boundary")["status"] == "pass"
    assert payload["package_index_ready"] is False


def test_package_index_readiness_distinguishes_testpypi_and_pypi_publish_stages(
    tmp_path: Path,
) -> None:
    root = copy_readiness_fixture(tmp_path)
    release_evidence = root / "docs" / "meta" / "release-evidence.json"
    ledger = json.loads(release_evidence.read_text(encoding="utf-8"))
    ledger["package_index"]["status"] = "testpypi-published"
    ledger["package_index"]["blocked_by"] = "PyPI publish proof has not run yet"
    (root / "docs" / "meta" / "release-evidence.json").write_text(
        json.dumps(ledger, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    result = run_package_index_readiness("--format", "json", "--strict", root=root)
    assert result.returncode == 0, result.stderr
    payload = _json_payload(result.stdout)

    detail = str(_check(payload, "release_evidence_boundary")["detail"])
    assert "PyPI publish/install evidence" in detail
    assert "TestPyPI" not in detail
    assert payload["package_index_ready"] is False


def test_package_index_readiness_ignores_downstream_smoke_status_when_scoping_publish_readiness(
    tmp_path: Path,
) -> None:
    root = copy_readiness_fixture(tmp_path)
    release_evidence = root / "docs" / "meta" / "release-evidence.json"
    ledger = json.loads(release_evidence.read_text(encoding="utf-8"))
    ledger["package_index"]["status"] = "published"
    ledger["downstream_smoke"]["status"] = "missing"
    (root / "docs" / "meta" / "release-evidence.json").write_text(
        json.dumps(ledger, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    result = run_package_index_readiness("--format", "json", "--strict", root=root)
    assert result.returncode == 0, result.stderr
    payload = _json_payload(result.stdout)

    assert payload["package_index_ready"] is True
    detail = str(_check(payload, "release_evidence_boundary")["detail"]).lower()
    assert "downstream" not in detail


def test_package_index_readiness_rejects_token_based_publish_workflow(
    tmp_path: Path,
) -> None:
    root = copy_readiness_fixture(tmp_path)
    workflow = root / ".github" / "workflows" / "publish-python-package.yml"
    _ = workflow.write_text(
        workflow.read_text(encoding="utf-8")
        + "\n# unsafe example\n# password: ${{ secrets.PYPI_API_TOKEN }}\n",
        encoding="utf-8",
    )

    result = run_package_index_readiness("--format", "json", "--strict", root=root)

    assert result.returncode == 1
    payload = _json_payload(result.stdout)
    assert payload["repo_guardrails_ready"] is False
    assert any(
        "long-lived package-index secret" in item
        for item in _string_list(payload, "repo_failures")
    )


def test_package_index_readiness_rejects_missing_publish_oidc(
    tmp_path: Path,
) -> None:
    root = copy_readiness_fixture(tmp_path)
    workflow = root / ".github" / "workflows" / "publish-python-package.yml"
    _ = workflow.write_text(
        workflow.read_text(encoding="utf-8").replace("id-token: write", "id-token: read"),
        encoding="utf-8",
    )

    result = run_package_index_readiness("--format", "json", "--strict", root=root)

    assert result.returncode == 1
    payload = _json_payload(result.stdout)
    assert payload["repo_guardrails_ready"] is False
    assert any("id-token: write" in item for item in _string_list(payload, "repo_failures"))


def test_package_index_readiness_checker_has_no_pyright_suppression() -> None:
    source = (REPO_ROOT / "scripts" / "package_index_readiness_checks.py").read_text(
        encoding="utf-8"
    )

    assert "pyright: ignore" not in source


def _json_payload(text: str) -> dict[str, object]:
    payload = cast(object, json.loads(text))
    assert isinstance(payload, dict)
    return cast(dict[str, object], payload)


def _string_list(payload: dict[str, object], key: str) -> list[str]:
    value = payload[key]
    assert isinstance(value, list)
    items = cast(list[object], value)
    strings: list[str] = []
    for item in items:
        assert isinstance(item, str)
        strings.append(item)
    return strings


def test_strict_fails_nonstrict_passes_on_same_failure_mode(
    tmp_path: Path,
) -> None:
    root = copy_readiness_fixture(tmp_path)
    (root / "docs" / "meta" / "release-evidence.json").unlink()

    strict = run_package_index_readiness("--format", "json", "--strict", root=root)
    nonstrict = run_package_index_readiness("--format", "json", root=root)

    assert strict.returncode == 1, f"strict expected exit 1, got {strict.returncode}"
    assert nonstrict.returncode == 0, f"non-strict expected exit 0, got {nonstrict.returncode}"
    strict_payload = _json_payload(strict.stdout)
    nonstrict_payload = _json_payload(nonstrict.stdout)
    assert strict_payload["repo_guardrails_ready"] is False
    assert nonstrict_payload["repo_guardrails_ready"] is False


def test_missing_release_evidence_json_reported_as_failure(
    tmp_path: Path,
) -> None:
    root = copy_readiness_fixture(tmp_path)
    (root / "docs" / "meta" / "release-evidence.json").unlink()

    result = run_package_index_readiness("--format", "json", "--strict", root=root)

    assert result.returncode == 1
    payload = _json_payload(result.stdout)
    assert payload["repo_guardrails_ready"] is False
    boundary = _check(payload, "release_evidence_boundary")
    assert boundary["status"] == "fail"
    assert any("must exist" in f for f in _string_list(payload, "repo_failures"))


def test_corrupt_release_evidence_json_must_not_crash(
    tmp_path: Path,
) -> None:
    root = copy_readiness_fixture(tmp_path)
    (root / "docs" / "meta" / "release-evidence.json").write_text(
        "{not valid json!!!", encoding="utf-8"
    )

    result = run_package_index_readiness("--format", "json", "--strict", root=root)

    assert result.returncode == 1
    payload = _json_payload(result.stdout)
    assert payload["repo_guardrails_ready"] is False
    boundary = _check(payload, "release_evidence_boundary")
    assert boundary["status"] == "fail"
    assert "JSON" in str(boundary["detail"]) or any(
        "JSON" in f for f in _string_list(payload, "repo_failures")
    )


def test_release_evidence_wrong_package_index_status_fails(
    tmp_path: Path,
) -> None:
    root = copy_readiness_fixture(tmp_path)
    ledger = root / "docs" / "meta" / "release-evidence.json"
    content = ledger.read_text(encoding="utf-8").replace(
        '"status": "not-published"', '"status": "published-alpha"'
    )
    _ = ledger.write_text(content, encoding="utf-8")

    result = run_package_index_readiness("--format", "json", "--strict", root=root)

    assert result.returncode == 1
    payload = _json_payload(result.stdout)
    assert payload["repo_guardrails_ready"] is False
    assert any(
        "not-published" in f for f in _string_list(payload, "repo_failures")
    )


def test_missing_runbook_preflight_markers_rejected(
    tmp_path: Path,
) -> None:
    root = copy_readiness_fixture(tmp_path)
    (root / "docs" / "meta" / "PYPI_RELEASE_RUNBOOK.md").write_text(
        "# Bare-minimum runbook\n\nNothing useful here.\n", encoding="utf-8"
    )

    result = run_package_index_readiness("--format", "json", "--strict", root=root)

    assert result.returncode == 1
    payload = _json_payload(result.stdout)
    assert payload["repo_guardrails_ready"] is False
    runbook = _check(payload, "runbook_preflight")
    assert runbook["status"] == "fail"
    assert any(
        "runbook must mention" in f for f in _string_list(payload, "repo_failures")
    )


def test_missing_pyproject_version_guard_not_crash(
    tmp_path: Path,
) -> None:
    root = copy_readiness_fixture(tmp_path)
    (root / "pyproject.toml").unlink()

    result = run_package_index_readiness("--format", "json", "--strict", root=root)

    assert result.returncode == 1
    payload = _json_payload(result.stdout)
    assert payload["repo_guardrails_ready"] is False
    version_check = _check(payload, "pyproject_version_guard")
    assert version_check["status"] == "fail"
    assert any("must exist" in f for f in _string_list(payload, "repo_failures"))


def test_pyproject_version_not_0_1_1_reports_pass(
    tmp_path: Path,
) -> None:
    root = copy_readiness_fixture(tmp_path)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "entroping"\nversion = "0.2.0a1"\n', encoding="utf-8"
    )
    result = run_package_index_readiness("--format", "json", root=root)
    assert result.returncode == 0
    payload = _json_payload(result.stdout)
    version_check = _check(payload, "pyproject_version_guard")
    assert version_check["status"] == "pass"


def test_error_messages_never_expose_local_paths(
    tmp_path: Path,
) -> None:
    root = copy_readiness_fixture(tmp_path)
    (root / "docs" / "meta" / "release-evidence.json").unlink()

    result = run_package_index_readiness("--format", "json", "--strict", root=root)
    payload = _json_payload(result.stdout)

    output = json.dumps(payload)
    assert "/Users/" not in output, "output must not contain /Users/ paths"
    assert str(Path.home()) not in output, f"output must not contain home dir {Path.home()}"


def _check(payload: dict[str, object], key: str) -> dict[str, object]:
    checks = payload["checks"]
    assert isinstance(checks, dict)
    typed_checks = cast(dict[str, object], checks)
    check = typed_checks[key]
    assert isinstance(check, dict)
    return cast(dict[str, object], check)
