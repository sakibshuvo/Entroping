"""Local environment-file loading for deterministic Hurl runs."""

import os
import re
from collections.abc import Mapping
from pathlib import Path

_ENV_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_VARIABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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


def _read_env_file(path: Path) -> dict[str, str]:
    if path.is_symlink():
        msg = f"Refusing to load symlinked environment file: {path}"
        raise EnvironmentLoadError(msg)

    resolved = path.expanduser().resolve()
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
        if _VARIABLE_NAME_RE.fullmatch(key) is None:
            msg = f"{resolved}: line {line_number}: Invalid environment variable name {key!r}"
            raise EnvironmentLoadError(msg)
        if key in variables:
            msg = f"{resolved}: line {line_number}: duplicate environment variable {key!r}"
            raise EnvironmentLoadError(msg)
        if "\n" in value or "\r" in value:
            msg = f"{resolved}: line {line_number}: environment values must be single-line"
            raise EnvironmentLoadError(msg)
        variables[key] = value

    return variables
