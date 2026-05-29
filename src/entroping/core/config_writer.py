"""Safe local updates for non-secret QAnstitution configuration."""

import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

import yaml
from pydantic import ValidationError

from entroping.core.config_loader import QanstitutionLoadError, load_qanstitution
from entroping.models.qanstitution import AgentRole, Qanstitution


class ConfigUpdateError(ValueError):
    """Raised when a local configuration update cannot be safely applied."""


def update_agent_model(
    path: str | Path,
    *,
    agent: AgentRole,
    model: str,
) -> Qanstitution:
    """Update one agent model in ``qanstitution.yaml`` after schema validation."""

    config_path = _resolve_writable_config(Path(path))
    document = _read_yaml_mapping(config_path)
    _validate_effective_file(config_path)

    updated = _with_updated_agent_model(document, agent=agent, model=model)
    _validate_document(updated, config_path)

    rendered = yaml.safe_dump(updated, sort_keys=False)
    return _write_validated_update(config_path, rendered)


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


def _write_validated_update(path: Path, content: str) -> Qanstitution:
    temporary_path = _write_temporary_file(path, content)
    try:
        law = _validate_effective_file(temporary_path)
        temporary_path.replace(path)
        return law
    except OSError as exc:
        msg = f"Could not update QAnstitution file {path}: {exc}"
        raise ConfigUpdateError(msg) from exc
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


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
