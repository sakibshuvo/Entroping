"""Safe local updates for non-secret QAnstitution configuration."""

import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yaml
from pydantic import ValidationError

from entroping.core.config_loader import QanstitutionLoadError, load_qanstitution
from entroping.models.qanstitution import AgentRole, Qanstitution


class ConfigUpdateError(ValueError):
    """Raised when a local configuration update cannot be safely applied."""


@dataclass(frozen=True)
class AgentModelUpdateResult:
    """Result of a non-secret agent routing update."""

    law: Qanstitution
    persona_template_path: Path | None


def update_agent_model(
    path: str | Path,
    *,
    agent: AgentRole,
    model: str,
) -> Qanstitution:
    """Update one agent model in ``qanstitution.yaml`` after schema validation."""

    return update_agent_model_with_persona_template(path, agent=agent, model=model).law


def update_agent_model_with_persona_template(
    path: str | Path,
    *,
    agent: AgentRole,
    model: str,
) -> AgentModelUpdateResult:
    """Update one agent model and create a missing local persona template."""

    config_path = _resolve_writable_config(Path(path))
    document = _read_yaml_mapping(config_path)
    _validate_effective_file(config_path)

    updated = _with_updated_agent_model(document, agent=agent, model=model)
    law = _validate_document(updated, config_path)
    persona_path = _resolve_persona_template_path(
        law.agents[agent].source,
        root=config_path.parent,
    )

    rendered = yaml.safe_dump(updated, sort_keys=False)
    temporary_path = _write_validated_temporary_update(config_path, rendered)
    persona_template_path: Path | None = None
    try:
        persona_template_path = _write_missing_persona_template(
            persona_path,
            role=agent,
            root=config_path.parent,
        )
        written_law = _replace_config(config_path, temporary_path)
        return AgentModelUpdateResult(
            law=written_law,
            persona_template_path=persona_template_path,
        )
    except Exception:
        if persona_template_path is not None and persona_template_path.exists():
            persona_template_path.unlink()
        raise
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _resolve_writable_config(path: Path) -> Path:
    expanded = path.expanduser()
    if expanded.is_symlink():
        msg = f"Refusing to update symlinked QAnstitution file: {expanded}"
        raise ConfigUpdateError(msg)

    resolved = expanded.resolve()
    if not resolved.is_file():
        msg = f"QAnstitution file not found: {resolved}"
        raise ConfigUpdateError(msg)
    return resolved


def _read_yaml_mapping(path: Path) -> dict[str, object]:
    try:
        loaded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        msg = f"Invalid YAML in {path}: {exc}"
        raise ConfigUpdateError(msg) from exc
    except OSError as exc:
        msg = f"Could not read QAnstitution file {path}: {exc}"
        raise ConfigUpdateError(msg) from exc

    if loaded is None:
        loaded = {}
    if not isinstance(loaded, Mapping):
        msg = f"QAnstitution file must contain a YAML mapping: {path}"
        raise ConfigUpdateError(msg)
    return _string_key_mapping(loaded, field="root", path=path)


def _with_updated_agent_model(
    document: Mapping[str, object],
    *,
    agent: AgentRole,
    model: str,
) -> dict[str, object]:
    updated = dict(document)
    agents_value = updated.get("agents")
    if agents_value is None:
        agents: dict[str, object] = {}
    else:
        agents = _string_key_mapping(agents_value, field="agents", path=Path("qanstitution.yaml"))

    existing = agents.get(agent)
    if existing is None:
        agent_config: dict[str, object] = {
            "source": f"agents/{agent}.md",
            "model": model,
            "temperature": 0.0,
        }
    else:
        agent_config = _string_key_mapping(
            existing,
            field=f"agents.{agent}",
            path=Path("qanstitution.yaml"),
        )
        agent_config["model"] = model

    agents[agent] = agent_config
    updated["agents"] = agents
    return updated


def _string_key_mapping(value: object, *, field: str, path: Path) -> dict[str, object]:
    if not isinstance(value, Mapping):
        msg = f"QAnstitution field {field} must be a YAML mapping in {path}"
        raise ConfigUpdateError(msg)

    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            msg = f"QAnstitution field {field} must use string keys in {path}"
            raise ConfigUpdateError(msg)
        result[key] = item
    return result


def _validate_document(document: Mapping[str, object], path: Path) -> Qanstitution:
    try:
        return Qanstitution.model_validate(document)
    except ValidationError as exc:
        msg = f"Invalid QAnstitution config in {path}: {exc}"
        raise ConfigUpdateError(msg) from exc


def _validate_effective_file(path: Path) -> Qanstitution:
    try:
        return load_qanstitution(path)
    except QanstitutionLoadError as exc:
        raise ConfigUpdateError(str(exc)) from exc


def _write_validated_temporary_update(path: Path, content: str) -> Path:
    temporary_path = _write_temporary_file(path, content)
    try:
        _validate_effective_file(temporary_path)
        return temporary_path
    except Exception:
        if temporary_path.exists():
            temporary_path.unlink()
        raise


def _replace_config(path: Path, temporary_path: Path) -> Qanstitution:
    try:
        temporary_path.replace(path)
    except OSError as exc:
        msg = f"Could not update QAnstitution file {path}: {exc}"
        raise ConfigUpdateError(msg) from exc
    return _validate_effective_file(path)


def _write_temporary_file(path: Path, content: str) -> Path:
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            return temporary_path
    except OSError as exc:
        msg = f"Could not write temporary QAnstitution file for {path}: {exc}"
        raise ConfigUpdateError(msg) from exc


def _resolve_persona_template_path(source: str, *, root: Path) -> Path:
    if _has_path_control(source):
        msg = "Agent persona source must not contain control characters"
        raise ConfigUpdateError(msg)

    parsed = urlparse(source)
    if parsed.scheme:
        msg = f"Agent persona source must be a local Markdown path: {source}"
        raise ConfigUpdateError(msg)

    raw_path = Path(source)
    if raw_path.is_absolute():
        msg = f"Agent persona source must be relative: {source}"
        raise ConfigUpdateError(msg)
    if raw_path.suffix.lower() != ".md":
        msg = f"Agent persona source must be a Markdown file: {source}"
        raise ConfigUpdateError(msg)

    candidate = root / raw_path
    try:
        relative_parts = candidate.relative_to(root).parts
    except ValueError as exc:
        msg = f"Agent persona source must stay under {root}: {source}"
        raise ConfigUpdateError(msg) from exc
    if ".." in relative_parts:
        msg = f"Agent persona source must stay under {root}: {source}"
        raise ConfigUpdateError(msg)

    _reject_symlink_persona_path(candidate, root=root)
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        msg = f"Agent persona source must stay under {root}: {source}"
        raise ConfigUpdateError(msg)
    return resolved


def _reject_symlink_persona_path(candidate: Path, *, root: Path) -> None:
    current = root
    for part in candidate.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            msg = f"Agent persona source must not use symlinks: {current}"
            raise ConfigUpdateError(msg)


def _write_missing_persona_template(
    path: Path,
    *,
    role: AgentRole,
    root: Path,
) -> Path | None:
    if path.is_symlink():
        msg = f"Agent persona source must not use symlinks: {path}"
        raise ConfigUpdateError(msg)
    if path.exists():
        if not path.is_file():
            msg = f"Agent persona source must be a file: {path}"
            raise ConfigUpdateError(msg)
        return None

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _reject_symlink_persona_path(path, root=root)
    except OSError as exc:
        msg = f"Could not inspect agent persona template path {path}: {exc}"
        raise ConfigUpdateError(msg) from exc

    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(_persona_template(role))
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        if path.is_symlink():
            msg = f"Agent persona source must not use symlinks: {path}"
            raise ConfigUpdateError(msg) from exc
        if not path.is_file():
            msg = f"Agent persona source must be a file: {path}"
            raise ConfigUpdateError(msg) from exc
        return None
    except OSError as exc:
        msg = f"Could not create agent persona template {path}: {exc}"
        raise ConfigUpdateError(msg) from exc
    return path


def _persona_template(role: AgentRole) -> str:
    title = role.title()
    return (
        f"# Entroping {title} Persona\n\n"
        "You are an Entroping Architect agent. Generate minimal, reviewable Hurl "
        "tests that follow the QAnstitution and avoid secrets.\n"
    )


def _has_path_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)
