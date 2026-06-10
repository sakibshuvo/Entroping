"""Guardrails for the cross-platform install and smoke matrix."""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_ci_defines_cross_platform_install_smoke_matrix() -> None:
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )

    job = workflow["jobs"]["install-smoke"]
    matrix = job["strategy"]["matrix"]["include"]
    os_entries = {entry["os"]: entry for entry in matrix}

    assert job["needs"] == "checks"
    assert set(os_entries) == {"ubuntu-latest", "macos-latest", "windows-latest"}
    assert os_entries["ubuntu-latest"]["hurl_mode"] == "pinned-archive"
    assert os_entries["macos-latest"]["hurl_mode"] == "homebrew"
    assert os_entries["windows-latest"]["hurl_mode"] == "doctor-only"

    run_blocks = "\n".join(str(step.get("run", "")) for step in job["steps"])
    verify_steps = [
        step for step in job["steps"] if step.get("name") == "Verify Hurl formatters are available"
    ]
    assert "uv tool install . --force" in run_blocks
    assert "uv tool dir --bin" in run_blocks
    assert "entroping --version" in run_blocks
    assert "entroping init --minimal" in run_blocks
    assert "entroping doctor" in run_blocks
    assert "brew install hurl" in run_blocks
    assert "HURL_SHA256" in run_blocks
    assert verify_steps == [
        {
            "name": "Verify Hurl formatters are available",
            "if": "matrix.hurl_mode != 'doctor-only'",
            "run": "command -v hurl\ncommand -v hurlfmt\nhurlfmt --version\n",
        }
    ]


def test_install_smoke_matrix_doc_matches_ci_and_support_claims() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "INSTALL_SMOKE_MATRIX.md").read_text(
        encoding="utf-8"
    )
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    index = (REPO_ROOT / "docs/meta/VAULT_INDEX.md").read_text(encoding="utf-8")
    release_checklist = (
        REPO_ROOT / "docs" / "meta" / "RELEASE_CHECKLIST.md"
    ).read_text(encoding="utf-8")
    test_strategy = (REPO_ROOT / "docs" / "meta" / "TEST_STRATEGY.md").read_text(
        encoding="utf-8"
    )

    required_terms = [
        "ubuntu-latest",
        "macos-latest",
        "windows-latest",
        "pinned Hurl archive",
        "Homebrew Hurl",
        "doctor-only",
        "Windows Hurl-backed `entroping run` is not claimed for alpha",
        "uv tool install . --force",
        "entroping init --minimal",
        "entroping doctor",
        "hurlfmt",
        "Architect generated-Hurl validation",
        "optional-extras-smoke",
    ]
    for term in required_terms:
        assert term in doc

    assert "INSTALL_SMOKE_MATRIX.md" in readme
    assert "[[docs/meta/INSTALL_SMOKE_MATRIX|INSTALL_SMOKE_MATRIX]]" in index
    assert "install-smoke" in release_checklist
    assert "install-smoke" in test_strategy
