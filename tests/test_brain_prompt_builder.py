"""Architect prompt package tests."""

from pathlib import Path

import pytest

from entroping.brain.persona_loader import AgentPersona
from entroping.brain.prompt_builder import PromptBuildError, build_architect_prompt_package
from entroping.core.config_loader import load_qanstitution
from entroping.models.qanstitution import Qanstitution


def _law(tmp_path: Path) -> Qanstitution:
    config_path = tmp_path / "qanstitution.yaml"
    config_path.write_text(
        """
project: checkout-api
version: "4.1"
sources:
  spec: openapi.yaml
agents:
  builder:
    source: agents/builder.md
    model: openai/gpt-4.1-mini
gates:
  - id: global_latency
    condition: "true"
    gate: duration < 2000
    enforcement: block
""".lstrip(),
        encoding="utf-8",
    )
    return load_qanstitution(config_path)


def _persona(tmp_path: Path) -> AgentPersona:
    return AgentPersona(
        role="builder",
        source_path=tmp_path / "agents" / "builder.md",
        content="You build minimal Hurl tests.",
        model="openai/gpt-4.1-mini",
        temperature=0.0,
        max_tokens=None,
    )


def test_build_architect_prompt_package_includes_policy_and_context(tmp_path: Path) -> None:
    package = build_architect_prompt_package(
        law=_law(tmp_path),
        persona=_persona(tmp_path),
        intent="Generate checkout smoke coverage.",
        source_context={"docs/story.md": "Checkout must return 201."},
    )

    assert package.role == "builder"
    assert package.model == "openai/gpt-4.1-mini"
    assert package.messages[0].role == "system"
    assert "You build minimal Hurl tests." in package.messages[0].content
    assert "global_latency" in package.messages[0].content
    assert package.messages[1].role == "user"
    assert "Generate checkout smoke coverage." in package.messages[1].content
    assert "docs/story.md" in package.messages[1].content


@pytest.mark.parametrize(
    ("intent", "message"),
    [
        ("", "intent must not be empty"),
        ("Use sk-proj-live-secret", "must not contain secret-like values"),
        ("Generate\x00coverage", "must not contain control characters"),
    ],
)
def test_build_architect_prompt_package_rejects_unsafe_intent(
    tmp_path: Path,
    intent: str,
    message: str,
) -> None:
    with pytest.raises(PromptBuildError, match=message):
        build_architect_prompt_package(
            law=_law(tmp_path),
            persona=_persona(tmp_path),
            intent=intent,
            source_context={},
        )


def test_build_architect_prompt_package_rejects_unsafe_context_path(tmp_path: Path) -> None:
    with pytest.raises(PromptBuildError, match="context path must stay under project"):
        build_architect_prompt_package(
            law=_law(tmp_path),
            persona=_persona(tmp_path),
            intent="Generate coverage.",
            source_context={"../secret.md": "secret"},
        )


def test_build_architect_prompt_package_rejects_secret_like_context(tmp_path: Path) -> None:
    with pytest.raises(PromptBuildError, match="must not contain secret-like values"):
        build_architect_prompt_package(
            law=_law(tmp_path),
            persona=_persona(tmp_path),
            intent="Generate coverage.",
            source_context={"docs/story.md": "Authorization: Bearer live-secret"},
        )


def test_build_architect_prompt_package_rejects_secret_like_persona_content(
    tmp_path: Path,
) -> None:
    persona = AgentPersona(
        role="builder",
        source_path=tmp_path / "agents" / "builder.md",
        content="Use sk-proj-live-secret.",
        model="openai/gpt-4.1-mini",
        temperature=0.0,
        max_tokens=None,
    )

    with pytest.raises(PromptBuildError, match="persona must not contain secret-like values"):
        build_architect_prompt_package(
            law=_law(tmp_path),
            persona=persona,
            intent="Generate coverage.",
            source_context={},
        )


def test_build_architect_prompt_package_rejects_secret_like_policy_summary(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "qanstitution.yaml"
    config_path.write_text(
        """
project: checkout-api
sources:
  spec: sk-proj-live-secret
agents:
  builder:
    source: agents/builder.md
    model: openai/gpt-4.1-mini
gates: []
""".lstrip(),
        encoding="utf-8",
    )
    law = load_qanstitution(config_path)

    with pytest.raises(PromptBuildError, match="QAnstitution summary must not contain"):
        build_architect_prompt_package(
            law=law,
            persona=_persona(tmp_path),
            intent="Generate coverage.",
            source_context={},
        )
