"""Guardrails for Studio mutation workflow design-before-code."""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_studio_mutation_design_covers_required_safety_boundaries() -> None:
    design = (
        _REPO_ROOT / "docs" / "technical" / "STUDIO_MUTATION_WORKFLOW_DESIGN.md"
    ).read_text(encoding="utf-8")

    required_sections = [
        "## Decision",
        "## User Flows",
        "## Safety Boundaries",
        "## Review And Confirmation Model",
        "## Redaction And Secret Handling",
        "## Test Strategy",
        "## v0.3 Non-Goals",
        "## Future Acceptance Gate",
    ]
    for section in required_sections:
        assert section in design

    required_terms = [
        "No Studio mutation implementation is planned for v0.3.",
        "read-only Studio remains the only shipped Studio behavior",
        "Mutation commands must produce reviewable file diffs before writing",
        "two-step confirmation",
        "rollback",
        (
            "Never render raw secrets, raw captured traffic, provider output, "
            "or unredacted Hurl output"
        ),
        "Use existing CLI/core writers instead of Textual widgets writing files directly",
        "scripts/regression.sh --security",
        "unit tests, adapter tests, CLI tests, and end-to-end smoke",
        "separate issue and accepted design amendment",
    ]
    for term in required_terms:
        assert term in design


def test_studio_mutation_design_is_linked_from_studio_docs() -> None:
    required_links = {
        "README.md": "STUDIO_MUTATION_WORKFLOW_DESIGN.md",
        "docs/meta/VAULT_INDEX.md": (
            "[[docs/technical/STUDIO_MUTATION_WORKFLOW_DESIGN|"
            "STUDIO_MUTATION_WORKFLOW_DESIGN]]"
        ),
        "mkdocs.yml": (
            "Studio Mutation Workflow Design: "
            "technical/STUDIO_MUTATION_WORKFLOW_DESIGN.md"
        ),
        "docs/index.md": "technical/STUDIO_MUTATION_WORKFLOW_DESIGN.md",
        "docs/user/USER_GUIDE.md": "STUDIO_MUTATION_WORKFLOW_DESIGN.md",
        "docs/technical/TDS.md": "STUDIO_MUTATION_WORKFLOW_DESIGN.md",
        "decisions/ADR-0010-studio-cli-report-first-boundary.md": (
            "STUDIO_MUTATION_WORKFLOW_DESIGN.md"
        ),
    }

    for relative_path, expected in required_links.items():
        content = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert expected in content


def test_studio_scope_decision_remains_no_mutation_for_v03() -> None:
    readme = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
    user_guide = (_REPO_ROOT / "docs" / "user" / "USER_GUIDE.md").read_text(
        encoding="utf-8"
    )
    roadmap = (_REPO_ROOT / "ROADMAP.md").read_text(encoding="utf-8")

    assert "optional local inspector is read-only" in readme
    assert "No Studio mutation implementation is planned for v0.3" in roadmap
    assert (
        "Studio should not rerun suites, edit tests, or change config in the alpha"
        in user_guide
    )
    assert "entroping studio --edit" not in readme
    assert "Future Studio work should add rerun/action workflows" not in user_guide
