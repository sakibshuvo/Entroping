"""Safe QAnstitution config writer tests."""

from pathlib import Path

import pytest
import yaml

from entroping.core.config_writer import (
    ConfigUpdateError,
    update_agent_model_with_persona_template,
)


def test_update_agent_model_creates_default_persona_for_missing_role(tmp_path: Path) -> None:
    config_path = tmp_path / "qanstitution.yaml"
    config_path.write_text("project: checkout-api\ngates: []\n", encoding="utf-8")

    result = update_agent_model_with_persona_template(
        config_path,
        agent="builder",
        model="openai/gpt-4.1-mini",
    )

    persona_path = tmp_path / "agents" / "builder.md"
    assert result.persona_template_path == persona_path.resolve()
    assert persona_path.is_file()
    assert "Builder" in persona_path.read_text(encoding="utf-8")
    assert "sk-" not in persona_path.read_text(encoding="utf-8")
    document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert document["agents"]["builder"]["source"] == "agents/builder.md"
    assert document["agents"]["builder"]["model"] == "openai/gpt-4.1-mini"


def test_update_agent_model_creates_missing_existing_source_persona(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "qanstitution.yaml"
    config_path.write_text(
        """
project: checkout-api
agents:
  auditor:
    source: personas/auditor.md
    model: old/auditor
    temperature: 0.4
    max_tokens: 4096
gates: []
""".lstrip(),
        encoding="utf-8",
    )

    result = update_agent_model_with_persona_template(
        config_path,
        agent="auditor",
        model="anthropic/claude-audit",
    )

    persona_path = tmp_path / "personas" / "auditor.md"
    assert result.persona_template_path == persona_path.resolve()
    assert persona_path.is_file()
    document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert document["agents"]["auditor"] == {
        "source": "personas/auditor.md",
        "model": "anthropic/claude-audit",
        "temperature": 0.4,
        "max_tokens": 4096,
    }


def test_update_agent_model_does_not_overwrite_existing_persona(tmp_path: Path) -> None:
    config_path = tmp_path / "qanstitution.yaml"
    persona_path = tmp_path / "agents" / "breaker.md"
    persona_path.parent.mkdir()
    persona_path.write_text("Existing persona\n", encoding="utf-8")
    config_path.write_text(
        """
project: checkout-api
agents:
  breaker:
    source: agents/breaker.md
    model: old/breaker
gates: []
""".lstrip(),
        encoding="utf-8",
    )

    result = update_agent_model_with_persona_template(
        config_path,
        agent="breaker",
        model="deepseek/deepseek-r1",
    )

    assert result.persona_template_path is None
    assert persona_path.read_text(encoding="utf-8") == "Existing persona\n"


def test_update_agent_model_rejects_unsafe_persona_source_without_config_write(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "qanstitution.yaml"
    original = """
project: checkout-api
agents:
  builder:
    source: ../builder.md
    model: old/builder
gates: []
""".lstrip()
    config_path.write_text(original, encoding="utf-8")

    with pytest.raises(ConfigUpdateError, match="Agent persona source must stay under"):
        update_agent_model_with_persona_template(
            config_path,
            agent="builder",
            model="openai/gpt-4.1-mini",
        )

    assert config_path.read_text(encoding="utf-8") == original
    assert not (tmp_path.parent / "builder.md").exists()


def test_update_agent_model_rejects_control_character_persona_source_without_write(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "qanstitution.yaml"
    original = """
project: checkout-api
agents:
  builder:
    source: "agents/bad\\nsource.md"
    model: old/builder
gates: []
""".lstrip()
    config_path.write_text(original, encoding="utf-8")

    with pytest.raises(ConfigUpdateError, match="Agent persona source must not contain"):
        update_agent_model_with_persona_template(
            config_path,
            agent="builder",
            model="openai/gpt-4.1-mini",
        )

    assert config_path.read_text(encoding="utf-8") == original
    assert not (tmp_path / "agents").exists()


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("https://example.com/builder.md", "must be a local Markdown path"),
        ("/tmp/builder.md", "must be relative"),
        ("agents/builder.txt", "must be a Markdown file"),
    ],
)
def test_update_agent_model_rejects_invalid_persona_sources_without_config_write(
    tmp_path: Path,
    source: str,
    message: str,
) -> None:
    config_path = tmp_path / "qanstitution.yaml"
    original = f"""
project: checkout-api
agents:
  builder:
    source: "{source}"
    model: old/builder
gates: []
""".lstrip()
    config_path.write_text(original, encoding="utf-8")

    with pytest.raises(ConfigUpdateError, match=message):
        update_agent_model_with_persona_template(
            config_path,
            agent="builder",
            model="openai/gpt-4.1-mini",
        )

    assert config_path.read_text(encoding="utf-8") == original


def test_update_agent_model_rejects_symlinked_persona_parent_without_config_write(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "qanstitution.yaml"
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (tmp_path / "agents").symlink_to(outside_dir)
    original = "project: checkout-api\ngates: []\n"
    config_path.write_text(original, encoding="utf-8")

    with pytest.raises(ConfigUpdateError, match="Agent persona source must not use symlinks"):
        update_agent_model_with_persona_template(
            config_path,
            agent="builder",
            model="openai/gpt-4.1-mini",
        )

    assert config_path.read_text(encoding="utf-8") == original
    assert not (outside_dir / "builder.md").exists()
