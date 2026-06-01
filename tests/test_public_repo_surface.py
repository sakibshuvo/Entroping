"""Guardrails for keeping the public clone surface clean."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _tracked_files() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return set(result.stdout.splitlines())


def test_public_clone_does_not_track_obsidian_machine_state_or_root_vault_index() -> None:
    tracked = _tracked_files()

    assert "00_INDEX.md" not in tracked
    assert "docs/meta/VAULT_INDEX.md" in tracked
    assert not any(path.startswith(".obsidian/") for path in tracked)


def test_public_surface_policy_classifies_context_without_data_loss() -> None:
    tracked = _tracked_files()
    policy = (REPO_ROOT / "docs" / "meta" / "PUBLIC_REPO_SURFACE.md").read_text(
        encoding="utf-8"
    )
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    vault_index = (REPO_ROOT / "docs" / "meta" / "VAULT_INDEX.md").read_text(
        encoding="utf-8"
    )

    for durable_file in (
        ".context/plan.md",
        ".context/changelog.md",
        ".context/lessons-learned.md",
    ):
        assert durable_file in tracked
        assert durable_file in policy

    assert "Obsidian machine state" in policy
    assert "docs/meta/VAULT_INDEX.md" in readme
    assert ".obsidian/" not in readme
    assert "Entroping Index" in vault_index


def test_curated_obsidian_canvas_and_base_are_repo_relative() -> None:
    tracked = _tracked_files()
    base = (REPO_ROOT / "docs" / "meta" / "ENTROPING_DOCS.base").read_text(
        encoding="utf-8"
    )
    canvas = (REPO_ROOT / "docs" / "meta" / "ENTROPING_PRODUCT_MAP.canvas").read_text(
        encoding="utf-8"
    )
    vault_index = (REPO_ROOT / "docs" / "meta" / "VAULT_INDEX.md").read_text(
        encoding="utf-8"
    )
    policy = (REPO_ROOT / "docs" / "meta" / "PUBLIC_REPO_SURFACE.md").read_text(
        encoding="utf-8"
    )

    assert "docs/meta/ENTROPING_DOCS.base" in tracked
    assert "docs/meta/ENTROPING_PRODUCT_MAP.canvas" in tracked
    assert 'file.name == "VAULT_INDEX"' in base
    assert '"file": "docs/meta/VAULT_INDEX.md"' in canvas
    assert "00_INDEX.md" not in base
    assert "00_INDEX.md" not in canvas
    assert "ENTROPING_DOCS.base" in vault_index
    assert "ENTROPING_PRODUCT_MAP.canvas" in vault_index
    assert "`docs/meta/*.canvas` and `docs/meta/*.base`" in policy
