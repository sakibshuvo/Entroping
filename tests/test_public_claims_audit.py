"""Guardrails for public product claims."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "public_claims_audit.py"


def run_public_claims_audit(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_public_claims_audit_passes_current_public_surface() -> None:
    result = run_public_claims_audit()

    assert result.returncode == 0, result.stderr
    assert "Public claims audit OK" in result.stdout
    assert "README.md" in result.stdout


def test_public_claims_audit_rejects_unsupported_production_claim(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Demo\n\nEntroping is production-ready and guaranteed secure.\n",
        encoding="utf-8",
    )

    result = run_public_claims_audit("--root", str(tmp_path))

    assert result.returncode == 1
    assert "unsupported public claim" in result.stderr
    assert "production-ready" in result.stderr
    assert "guaranteed secure" in result.stderr


def test_public_claims_audit_rejects_contract_version_as_product_stability(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text(
        "# Demo\n\n**Version:** 4.1 Stable\n",
        encoding="utf-8",
    )

    result = run_public_claims_audit("--root", str(tmp_path))

    assert result.returncode == 1
    assert "unsupported public claim" in result.stderr
    assert "4.1 stable" in result.stderr


def test_public_claims_audit_skips_generated_context_tool_outputs(tmp_path: Path) -> None:
    generated_paths = [
        "llm-wiki-out/README.md",
        "understand-anything-out/repo/README.md",
        ".understand-anything/knowledge.md",
        "agent-context-out/probe.md",
    ]
    for path in generated_paths:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("External tool says production-ready.\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Demo\n\nNo launch claim here.\n", encoding="utf-8")

    result = run_public_claims_audit("--root", str(tmp_path))

    assert result.returncode == 0, result.stderr
    assert "Public claims audit OK" in result.stdout


def test_public_claims_audit_is_part_of_documentation_governance() -> None:
    doc_governance = (REPO_ROOT / "scripts" / "doc_governance_check.sh").read_text(
        encoding="utf-8"
    )

    assert "scripts/public_claims_audit.py" in doc_governance
