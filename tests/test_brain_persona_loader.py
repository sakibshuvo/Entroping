"""Brain persona loader tests."""

import os
from pathlib import Path

import pytest

import entroping.brain.persona_loader as persona_loader
from entroping.brain.persona_loader import PersonaLoadError, load_agent_persona
from entroping.core.config_loader import load_qanstitution


def _write_config(tmp_path: Path, source: str) -> Path:
    config_path = tmp_path / "qanstitution.yaml"
    config_path.write_text(
        f"""
project: checkout-api
agents:
  builder:
    source: {source}
    model: openai/gpt-4.1-mini
gates: []
""".lstrip(),
        encoding="utf-8",
    )
    return config_path


def test_load_agent_persona_reads_root_bounded_markdown(tmp_path: Path) -> None:
    persona_path = tmp_path / "agents" / "builder.md"
    persona_path.parent.mkdir()
    persona_path.write_text("You are the Builder.\n", encoding="utf-8")
    config_path = _write_config(tmp_path, "agents/builder.md")
    law = load_qanstitution(config_path)

    persona = load_agent_persona(law, "builder", config_path=config_path)

    assert persona.role == "builder"
    assert persona.model == "openai/gpt-4.1-mini"
    assert persona.source_path == persona_path.resolve()
    assert persona.content == "You are the Builder.\n"


def test_load_agent_persona_rejects_missing_role(tmp_path: Path) -> None:
    config_path = tmp_path / "qanstitution.yaml"
    config_path.write_text("project: checkout-api\ngates: []\n", encoding="utf-8")
    law = load_qanstitution(config_path)

    with pytest.raises(PersonaLoadError, match="No agent config found for role builder"):
        load_agent_persona(law, "builder", config_path=config_path)


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("https://example.com/builder.md", "must be a local Markdown path"),
        ("../builder.md", "must stay under"),
        ("/tmp/builder.md", "must be relative"),
        ("agents/builder.txt", "must be a Markdown file"),
    ],
)
def test_load_agent_persona_rejects_unsafe_source_path(
    tmp_path: Path,
    source: str,
    message: str,
) -> None:
    config_path = _write_config(tmp_path, source)
    law = load_qanstitution(config_path)

    with pytest.raises(PersonaLoadError, match=message):
        load_agent_persona(law, "builder", config_path=config_path)


def test_load_agent_persona_rejects_symlinked_persona(tmp_path: Path) -> None:
    real_path = tmp_path / "builder.md"
    real_path.write_text("hidden\n", encoding="utf-8")
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "builder.md").symlink_to(real_path)
    config_path = _write_config(tmp_path, "agents/builder.md")
    law = load_qanstitution(config_path)

    with pytest.raises(PersonaLoadError, match="must not use symlinks"):
        load_agent_persona(law, "builder", config_path=config_path)


def test_load_agent_persona_rejects_secret_like_content(tmp_path: Path) -> None:
    persona_path = tmp_path / "agents" / "builder.md"
    persona_path.parent.mkdir()
    persona_path.write_text("Use sk-proj-live-secret\n", encoding="utf-8")
    config_path = _write_config(tmp_path, "agents/builder.md")
    law = load_qanstitution(config_path)

    with pytest.raises(PersonaLoadError, match="must not contain secret-like values"):
        load_agent_persona(law, "builder", config_path=config_path)


def test_load_agent_persona_rejects_missing_file(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, "agents/missing.md")
    law = load_qanstitution(config_path)

    with pytest.raises(PersonaLoadError, match="Agent persona file not found"):
        load_agent_persona(law, "builder", config_path=config_path)


def test_read_persona_rejects_inspection_and_read_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persona_path = tmp_path / "agents" / "builder.md"
    persona_path.parent.mkdir()
    persona_path.write_text("You are the Builder.\n", encoding="utf-8")
    original_stat = Path.stat

    def fail_stat(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if self == persona_path:
            raise OSError("stat failed")
        return original_stat(self, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", fail_stat)
    with pytest.raises(PersonaLoadError, match="Could not inspect agent persona"):
        persona_loader._read_persona(persona_path)

    monkeypatch.setattr(Path, "stat", original_stat)
    original_read_text = Path.read_text

    def fail_read_text(
        self: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if self == persona_path:
            raise OSError("read failed")
        return original_read_text(self, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", fail_read_text)
    with pytest.raises(PersonaLoadError, match="Could not read agent persona"):
        persona_loader._read_persona(persona_path)


def test_read_persona_rejects_invalid_content_shapes(tmp_path: Path) -> None:
    persona_path = tmp_path / "agents" / "builder.md"
    persona_path.parent.mkdir()

    persona_path.write_text("x" * 128_001, encoding="utf-8")
    with pytest.raises(PersonaLoadError, match="too large"):
        persona_loader._read_persona(persona_path)

    persona_path.write_bytes(b"\xff")
    with pytest.raises(PersonaLoadError, match="UTF-8"):
        persona_loader._read_persona(persona_path)

    persona_path.write_text("  \n\t", encoding="utf-8")
    with pytest.raises(PersonaLoadError, match="must not be empty"):
        persona_loader._read_persona(persona_path)

    persona_path.write_text("Builder\u0007persona\n", encoding="utf-8")
    with pytest.raises(PersonaLoadError, match="must not contain control characters"):
        persona_loader._read_persona(persona_path)
