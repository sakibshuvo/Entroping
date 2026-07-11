"""Guardrails for the first-hour QAnstitution onboarding path."""

import re
from pathlib import Path

import yaml
from _public_docs import public_doc_sources

from entroping.cli.main import MINIMAL_QANSTITUTION
from entroping.core.config_loader import load_qanstitution

REPO_ROOT = Path(__file__).resolve().parents[1]
FIRST_HOUR_GATE_IDS = ["no_server_errors", "global_latency", "request_id_header"]
_POLICY_MARKER_RE = re.compile(
    r"<!-- first-hour-policy:start -->\n```yaml\n(?P<body>.*?)\n```\n"
    r"<!-- first-hour-policy:end -->",
    re.DOTALL,
)


def _load_policy_from_text(tmp_path: Path, name: str, content: str) -> list[str]:
    policy_path = tmp_path / name
    policy_path.write_text(content, encoding="utf-8")
    law = load_qanstitution(policy_path)
    return [gate.id for gate in law.gates]


def test_first_hour_policy_doc_is_schema_valid_and_matches_starter_policy(
    tmp_path: Path,
) -> None:
    guide = (REPO_ROOT / "docs" / "user" / "QANSTITUTION_FIRST_HOUR.md").read_text(
        encoding="utf-8"
    )
    match = _POLICY_MARKER_RE.search(guide)

    assert match is not None
    guide_policy = match.group("body")
    assert _load_policy_from_text(tmp_path, "guide-qanstitution.yaml", guide_policy) == (
        FIRST_HOUR_GATE_IDS
    )
    assert _load_policy_from_text(
        tmp_path,
        "minimal-qanstitution.yaml",
        MINIMAL_QANSTITUTION,
    ) == FIRST_HOUR_GATE_IDS
    assert _load_policy_from_text(
        tmp_path,
        "checkout-qanstitution.yaml",
        (REPO_ROOT / "examples" / "checkout-api" / "qanstitution.yaml").read_text(
            encoding="utf-8"
        ),
    ) == FIRST_HOUR_GATE_IDS

    guide_data = yaml.safe_load(guide_policy)
    minimal_data = yaml.safe_load(MINIMAL_QANSTITUTION)
    assert guide_data["gates"] == minimal_data["gates"]


def test_first_hour_policy_doc_is_visible_from_public_onboarding_surfaces() -> None:
    required_link = "docs/user/QANSTITUTION_FIRST_HOUR.md"
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    user_guide = (REPO_ROOT / "docs" / "user" / "USER_GUIDE.md").read_text(
        encoding="utf-8"
    )
    reference = (
        REPO_ROOT / "docs" / "technical" / "QANSTITUTION_REFERENCE.md"
    ).read_text(encoding="utf-8")
    docs_index = (REPO_ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    vault_index = (REPO_ROOT / "docs/meta/VAULT_INDEX.md").read_text(encoding="utf-8")

    assert required_link in readme
    assert "QANSTITUTION_FIRST_HOUR.md" in user_guide
    assert "QANSTITUTION_FIRST_HOUR.md" in reference
    assert 'New QAnstitution files should use `version: "4.1"`.' in user_guide
    assert "old or future version" in user_guide
    assert "user/QANSTITUTION_FIRST_HOUR.md" in docs_index
    assert required_link in public_doc_sources()
    assert "[[docs/user/QANSTITUTION_FIRST_HOUR|QANSTITUTION_FIRST_HOUR]]" in vault_index
