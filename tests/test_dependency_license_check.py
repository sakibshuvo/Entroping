"""Direct dependency license policy guardrails."""

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "dependency_license_check.py"
POLICY = REPO_ROOT / "docs" / "meta" / "dependency-license-policy.json"


def run_dependency_license_check(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_dependency_license_check_passes_current_direct_dependencies() -> None:
    result = run_dependency_license_check()

    assert result.returncode == 0, result.stderr
    assert "Dependency license policy OK" in result.stdout
    assert "dependencies/default:pydantic" in result.stdout
    assert "optional-dependencies/proxy:mitmproxy" in result.stdout


def test_dependency_license_policy_covers_all_declared_dependency_groups() -> None:
    payload = json.loads(POLICY.read_text(encoding="utf-8"))
    groups = {entry["group"] for entry in payload["dependencies"]}

    assert {"dependencies/default", "optional-dependencies/ai", "dependency-groups/dev"} <= groups
    assert payload["allowed_license_families"] == ["Apache-2.0", "BSD", "MIT"]
    assert "reviewed_at" in payload


def test_dependency_license_check_rejects_unreviewed_direct_dependency(tmp_path: Path) -> None:
    (tmp_path / "docs" / "meta").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
dependencies = ["unknownpkg>=1"]

[project.optional-dependencies]
ai = ["knownai>=1"]
""",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "meta" / "dependency-license-policy.json").write_text(
        json.dumps(
            {
                "allowed_license_families": ["MIT"],
                "reviewed_at": "2026-05-31",
                "dependencies": [
                    {
                        "group": "optional-dependencies/ai",
                        "name": "knownai",
                        "license_family": "MIT",
                        "spdx": "MIT",
                        "notes": "fixture",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = run_dependency_license_check("--root", str(tmp_path))

    assert result.returncode == 1
    assert "unreviewed direct dependency" in result.stderr
    assert "dependencies/default:unknownpkg" in result.stderr
