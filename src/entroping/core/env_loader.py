"""Local environment-file loading for deterministic Hurl runs."""

import os
import re
from collections.abc import Mapping
from pathlib import Path

from entroping.core.path_safety import first_symlink_path_component
from entroping.models.hurl import HURL_VARIABLE_NAME_RE

_ENV_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class EnvironmentLoadError(ValueError):
    """Raised when an Entroping environment file cannot be loaded safely."""


def load_environment_variables(
    env_name: str,
    *,
    root: Path = Path("."),
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Load ``envs/<name>.env`` and apply process overrides for matching keys."""

    normalized_name = env_name.strip()
    if _ENV_NAME_RE.fullmatch(normalized_name) is None:
        msg = (
            "Environment name must contain only letters, numbers, underscore, dot, "
            f"or hyphen: {env_name!r}"
        )
        raise EnvironmentLoadError(msg)

    env_path = root / "envs" / f"{normalized_name}.env"
    variables = _read_env_file(env_path)
    process_environ = os.environ if environ is None else environ
    for key in tuple(variables):
        if key in process_environ:
            variables[key] = process_environ[key]
    return variables


def load_process_hurl_variables(
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Load explicit ``HURL_VARIABLE_<name>`` process variables for Hurl."""

    process_environ = os.environ if environ is None else environ
    variables: dict[str, str] = {}
    for env_key, value in process_environ.items():
        if not env_key.startswith("HURL_VARIABLE_"):
            continue
        variable_name = env_key.removeprefix("HURL_VARIABLE_")
        if HURL_VARIABLE_NAME_RE.fullmatch(variable_name) is None:
            msg = f"Invalid Hurl environment variable name {env_key!r}"
            raise EnvironmentLoadError(msg)
        variables[variable_name] = value
    return variables


def _read_env_file(path: Path) -> dict[str, str]:
    expanded = path.expanduser()
    _reject_symlink_path_components(expanded)
    resolved = expanded.resolve()
    if not resolved.is_file():
        msg = f"Environment file not found: {resolved}"
        raise EnvironmentLoadError(msg)

    variables: dict[str, str] = {}
    try:
        lines = resolved.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        msg = f"Environment file is not valid UTF-8: {resolved}"
        raise EnvironmentLoadError(msg) from exc
    except OSError as exc:
        msg = f"Could not read environment file {resolved}: {exc}"
        raise EnvironmentLoadError(msg) from exc

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            msg = f"{resolved}: line {line_number}: expected KEY=value"
            raise EnvironmentLoadError(msg)

        key, value = (part.strip() for part in line.split("=", maxsplit=1))
        if HURL_VARIABLE_NAME_RE.fullmatch(key) is None:
            msg = f"{resolved}: line {line_number}: Invalid environment variable name {key!r}"
            raise EnvironmentLoadError(msg)
        if key in variables:
            msg = f"{resolved}: line {line_number}: duplicate environment variable {key!r}"
            raise EnvironmentLoadError(msg)
        variables[key] = value

    return variables


def _reject_symlink_path_components(path: Path) -> None:
    symlink_component = first_symlink_path_component(path)
    if symlink_component is not None:
        msg = (
            "Refusing to load symlinked environment path component: "
            f"{symlink_component}"
        )
        raise EnvironmentLoadError(msg)
