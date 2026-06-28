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


def _check(payload: dict[str, object], key: str) -> dict[str, object]:
    checks = payload["checks"]
    assert isinstance(checks, dict)
    typed_checks = cast(dict[str, object], checks)
    check = typed_checks[key]
    assert isinstance(check, dict)
    return cast(dict[str, object], check)
