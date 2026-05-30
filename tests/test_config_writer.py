"""Safe QAnstitution config writer tests."""

from pathlib import Path

import pytest
import yaml

from entroping.core import config_writer
from entroping.core.config_writer import (
    ConfigUpdateError,
    update_agent_model,
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


def test_update_agent_model_wrapper_returns_updated_law(tmp_path: Path) -> None:
    config_path = tmp_path / "qanstitution.yaml"
    config_path.write_text("project: checkout-api\ngates: []\n", encoding="utf-8")

    law = update_agent_model(
        config_path,
        agent="auditor",
        model="anthropic/claude-audit",
    )

    assert law.agents["auditor"].model == "anthropic/claude-audit"


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


def test_update_agent_model_rejects_missing_or_symlinked_config(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"
    with pytest.raises(ConfigUpdateError, match="QAnstitution file not found"):
        update_agent_model_with_persona_template(
            missing,
            agent="builder",
            model="openai/gpt-4.1-mini",
        )

    real_config = tmp_path / "real.yaml"
    real_config.write_text("project: checkout-api\ngates: []\n", encoding="utf-8")
    symlink = tmp_path / "qanstitution.yaml"
    symlink.symlink_to(real_config)
    with pytest.raises(ConfigUpdateError, match="symlinked QAnstitution file"):
        update_agent_model_with_persona_template(
            symlink,
            agent="builder",
            model="openai/gpt-4.1-mini",
        )


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


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("project: [", "Invalid YAML"),
        ("[]", "must contain a YAML mapping"),
        ("1: checkout-api", "must use string keys"),
        ("", "Invalid QAnstitution config"),
        ("project: checkout-api\nagents: []\ngates: []\n", "Invalid QAnstitution config"),
        (
            "project: checkout-api\nagents:\n  builder: []\ngates: []\n",
            "Invalid QAnstitution config",
        ),
    ],
)
def test_update_agent_model_rejects_invalid_yaml_documents(
    tmp_path: Path,
    body: str,
    message: str,
) -> None:
    config_path = tmp_path / "qanstitution.yaml"
    config_path.write_text(body, encoding="utf-8")

    with pytest.raises(ConfigUpdateError, match=message):
        update_agent_model_with_persona_template(
            config_path,
            agent="builder",
            model="openai/gpt-4.1-mini",
        )


def test_update_agent_model_rejects_invalid_effective_config_before_write(tmp_path: Path) -> None:
    config_path = tmp_path / "qanstitution.yaml"
    original = """
project: checkout-api
imports:
  - https://example.com/security.yaml
gates: []
""".lstrip()
    config_path.write_text(original, encoding="utf-8")

    with pytest.raises(ConfigUpdateError, match="Remote QAnstitution imports"):
        update_agent_model_with_persona_template(
            config_path,
            agent="builder",
            model="openai/gpt-4.1-mini",
        )

    assert config_path.read_text(encoding="utf-8") == original


def test_update_agent_model_rejects_invalid_model_without_write(tmp_path: Path) -> None:
    config_path = tmp_path / "qanstitution.yaml"
    original = "project: checkout-api\ngates: []\n"
    config_path.write_text(original, encoding="utf-8")

    with pytest.raises(ConfigUpdateError, match="model identifier must not be empty"):
        update_agent_model_with_persona_template(
            config_path,
            agent="builder",
            model=" ",
        )

    assert config_path.read_text(encoding="utf-8") == original


def test_update_agent_model_wraps_config_read_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "qanstitution.yaml"
    config_path.write_text("project: checkout-api\ngates: []\n", encoding="utf-8")
    original_read_text = Path.read_text

    def fail_read_text(
        self: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if self == config_path.resolve():
            raise OSError("disk unavailable")
        return original_read_text(self, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    with pytest.raises(ConfigUpdateError, match="Could not read QAnstitution file"):
        update_agent_model_with_persona_template(
            config_path,
            agent="builder",
            model="openai/gpt-4.1-mini",
        )


def test_update_agent_model_rejects_existing_persona_directory_without_config_write(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "qanstitution.yaml"
    persona_path = tmp_path / "agents" / "builder.md"
    persona_path.mkdir(parents=True)
    original = "project: checkout-api\ngates: []\n"
    config_path.write_text(original, encoding="utf-8")

    with pytest.raises(ConfigUpdateError, match="Agent persona source must be a file"):
        update_agent_model_with_persona_template(
            config_path,
            agent="builder",
            model="openai/gpt-4.1-mini",
        )

    assert config_path.read_text(encoding="utf-8") == original


def test_update_agent_model_wraps_temporary_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "qanstitution.yaml"
    config_path.write_text("project: checkout-api\ngates: []\n", encoding="utf-8")

    def fail_named_temporary_file(*args: object, **kwargs: object) -> object:
        raise OSError("disk full")

    monkeypatch.setattr(
        "entroping.core.config_writer.tempfile.NamedTemporaryFile",
        fail_named_temporary_file,
    )

    with pytest.raises(ConfigUpdateError, match="Could not write temporary QAnstitution file"):
        update_agent_model_with_persona_template(
            config_path,
            agent="builder",
            model="openai/gpt-4.1-mini",
        )


def test_update_agent_model_cleans_persona_template_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "qanstitution.yaml"
    config_path.write_text("project: checkout-api\ngates: []\n", encoding="utf-8")
    original_replace = Path.replace

    def fail_replace(self: Path, target: str | Path) -> Path:
        if Path(target) == config_path:
            raise OSError("locked")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(ConfigUpdateError, match="Could not update QAnstitution file"):
        update_agent_model_with_persona_template(
            config_path,
            agent="builder",
            model="openai/gpt-4.1-mini",
        )

    assert not (tmp_path / "agents" / "builder.md").exists()


def test_config_writer_mapping_helper_rejects_invalid_internal_mappings() -> None:
    with pytest.raises(ConfigUpdateError, match="field agents must be a YAML mapping"):
        config_writer._string_key_mapping([], field="agents", path=Path("qanstitution.yaml"))

    with pytest.raises(ConfigUpdateError, match="field agents must use string keys"):
        config_writer._string_key_mapping(
            {1: "builder"},
            field="agents",
            path=Path("qanstitution.yaml"),
        )


def test_update_agent_model_cleans_invalid_temporary_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "qanstitution.yaml"
    config_path.write_text("project: checkout-api\ngates: []\n", encoding="utf-8")
    original_validate = config_writer._validate_effective_file

    def fail_temporary_validation(path: Path) -> object:
        if path.name.startswith(".qanstitution.yaml."):
            raise ConfigUpdateError("temporary config invalid")
        return original_validate(path)

    monkeypatch.setattr(config_writer, "_validate_effective_file", fail_temporary_validation)

    with pytest.raises(ConfigUpdateError, match="temporary config invalid"):
        update_agent_model_with_persona_template(
            config_path,
            agent="builder",
            model="openai/gpt-4.1-mini",
        )

    assert not list(tmp_path.glob(".qanstitution.yaml.*.tmp"))


def test_persona_template_path_rejects_resolved_paths_outside_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outside_dir = tmp_path.parent / f"{tmp_path.name}-outside"
    outside_dir.mkdir()
    (tmp_path / "agents").symlink_to(outside_dir, target_is_directory=True)
    monkeypatch.setattr(config_writer, "_reject_symlink_persona_path", lambda path, *, root: None)

    with pytest.raises(ConfigUpdateError, match="must stay under"):
        config_writer._resolve_persona_template_path("agents/builder.md", root=tmp_path)


def test_persona_template_path_wraps_relative_to_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = tmp_path / "agents" / "builder.md"
    original_relative_to = Path.relative_to

    def fail_relative_to(self: Path, *other: str | Path) -> Path:
        if self == candidate:
            raise ValueError("different roots")
        return original_relative_to(self, *other)

    monkeypatch.setattr(Path, "relative_to", fail_relative_to)

    with pytest.raises(ConfigUpdateError, match="must stay under"):
        config_writer._resolve_persona_template_path("agents/builder.md", root=tmp_path)


def test_persona_template_writer_rejects_symlinked_final_path(tmp_path: Path) -> None:
    outside_file = tmp_path / "outside.md"
    outside_file.write_text("outside\n", encoding="utf-8")
    persona_path = tmp_path / "agents" / "builder.md"
    persona_path.parent.mkdir()
    persona_path.symlink_to(outside_file)

    with pytest.raises(ConfigUpdateError, match="must not use symlinks"):
        config_writer._write_missing_persona_template(
            persona_path,
            role="builder",
            root=tmp_path,
        )


def test_persona_template_writer_wraps_parent_inspection_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persona_path = tmp_path / "agents" / "builder.md"
    original_mkdir = Path.mkdir

    def fail_mkdir(self: Path, parents: bool = False, exist_ok: bool = False) -> None:
        _ = (parents, exist_ok)
        if self == persona_path.parent:
            raise OSError("permission denied")
        original_mkdir(self, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)

    with pytest.raises(ConfigUpdateError, match="Could not inspect agent persona template path"):
        config_writer._write_missing_persona_template(
            persona_path,
            role="builder",
            root=tmp_path,
        )


@pytest.mark.parametrize(
    ("path_state", "message"),
    [
        ("file", None),
        ("directory", "Agent persona source must be a file"),
        ("symlink", "Agent persona source must not use symlinks"),
        ("oserror", "Could not create agent persona template"),
    ],
)
def test_persona_template_writer_handles_create_races(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    path_state: str,
    message: str | None,
) -> None:
    persona_path = tmp_path / "agents" / "builder.md"
    persona_path.parent.mkdir()
    original_open = Path.open

    def fake_open(
        self: Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> object:
        if self != persona_path or mode != "x":
            return original_open(
                self,
                mode=mode,
                buffering=buffering,
                encoding=encoding,
                errors=errors,
                newline=newline,
            )
        if path_state == "file":
            original_open(self, mode="w", encoding="utf-8").close()
            raise FileExistsError("raced")
        if path_state == "directory":
            self.mkdir()
            raise FileExistsError("raced")
        if path_state == "symlink":
            outside_file = tmp_path / "outside.md"
            outside_file.write_text("outside\n", encoding="utf-8")
            self.symlink_to(outside_file)
            raise FileExistsError("raced")
        raise OSError("disk full")

    monkeypatch.setattr(Path, "open", fake_open)

    if message is None:
        assert (
            config_writer._write_missing_persona_template(
                persona_path,
                role="builder",
                root=tmp_path,
            )
            is None
        )
    else:
        with pytest.raises(ConfigUpdateError, match=message):
            config_writer._write_missing_persona_template(
                persona_path,
                role="builder",
                root=tmp_path,
            )
