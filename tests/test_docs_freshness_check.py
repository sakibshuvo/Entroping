"""Guardrails for Markdown freshness and context hygiene."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "docs_freshness_check.py"
DOC_GOVERNANCE_SCRIPT = REPO_ROOT / "scripts" / "doc_governance_check.sh"


def run_docs_freshness_check(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_docs_freshness_check_passes_current_repo() -> None:
    result = run_docs_freshness_check()

    assert result.returncode == 0, result.stderr
    assert "Markdown freshness OK" in result.stdout


def test_docs_freshness_check_rejects_context_corruption_patterns(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Demo\n"
        "Use the old checkout at /Users/sakibshuvo/Documents/Entroping for work.\n"
        "`entroping chaos` runs the suite.\n"
        "Entroping is stable-core ready and guaranteed secure.\n"
        "<<<<<<< HEAD\n",
        encoding="utf-8",
    )

    result = run_docs_freshness_check("--root", str(tmp_path))

    assert result.returncode == 1
    assert "stale active-repo path reference" in result.stderr
    assert "deprecated command literal" in result.stderr
    assert "unsupported readiness/security claim" in result.stderr
    assert "merge conflict marker" in result.stderr


def test_docs_freshness_check_allows_explicit_stale_path_warning(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Demo\n"
        "Stale path: /Users/sakibshuvo/Documents/Entroping\n",
        encoding="utf-8",
    )

    result = run_docs_freshness_check("--root", str(tmp_path))

    assert result.returncode == 0, result.stderr


def test_docs_freshness_check_rejects_broken_local_markdown_links(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Demo\n"
        "[Missing](docs/missing.md)\n",
        encoding="utf-8",
    )

    result = run_docs_freshness_check("--root", str(tmp_path))

    assert result.returncode == 1
    assert "broken local Markdown link" in result.stderr
    assert "docs/missing.md" in result.stderr


def test_docs_freshness_check_rejects_invalid_utf8(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_bytes(b"# Demo\n\xff\n")

    result = run_docs_freshness_check("--root", str(tmp_path))

    assert result.returncode == 1
    assert "invalid UTF-8" in result.stderr


def test_docs_freshness_check_rejects_nul_bytes_and_placeholders(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_bytes(b"# Demo\nTODO: later\ncontains \0 byte\n")

    result = run_docs_freshness_check("--root", str(tmp_path))

    assert result.returncode == 1
    assert "contains NUL byte" in result.stderr
    assert "placeholder marker TODO/FIXME/TBD" in result.stderr


def test_docs_freshness_check_is_part_of_documentation_governance() -> None:
    doc_governance = DOC_GOVERNANCE_SCRIPT.read_text(encoding="utf-8")

    assert "scripts/docs_freshness_check.py" in doc_governance
