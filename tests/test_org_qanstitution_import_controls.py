"""Guardrails for organization QAnstitution import-control decisions."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ADR_PATH = REPO_ROOT / "decisions" / "ADR-0011-organization-qanstitution-import-controls.md"


def test_org_qanstitution_import_controls_adr_covers_required_boundaries() -> None:
    adr = ADR_PATH.read_text(encoding="utf-8")

    required_sections = [
        "## Decision",
        "## Import Provenance",
        "## Override Rules",
        "## Final Gate Behavior",
        "## Offline And Local-First Behavior",
        "## Audit And Report Evidence",
        "## Non-Goals",
        "## Consequences",
    ]
    for section in required_sections:
        assert section in adr

    required_terms = [
        "Organization QAnstitution imports are not a separate runtime authority.",
        "source URI",
        "resolved path",
        "content digest",
        "import chain",
        "local repos may add stricter gates",
        "must not weaken imported `final: true` gates",
        "remote imports remain disabled in deterministic `entroping run`",
        "offline validation must use committed or reviewed local files",
        "effective-policy report",
    ]
    for term in required_terms:
        assert term in adr


def test_org_qanstitution_import_controls_are_linked_from_policy_docs() -> None:
    required_links = {
        "00_INDEX.md": "[[decisions/ADR-0011-organization-qanstitution-import-controls|ADR-0011]]",
        "docs/technical/QANSTITUTION_REFERENCE.md": (
            "ADR-0011-organization-qanstitution-import-controls.md"
        ),
        "docs/technical/TDS.md": "ADR-0011-organization-qanstitution-import-controls.md",
        "docs/meta/PROJECT_PROGRESS.md": "Organization QAnstitution import controls",
        ".context/plan.md": "Issue #202 defines organization QAnstitution import controls",
    }

    for relative_path, expected in required_links.items():
        content = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert expected in content
