"""Preflight checks for unresolved Hurl template variables."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from entroping.core.gate_injector import HurlExecutionCopy
from entroping.hurl_source import HurlSourceTooLargeError, read_hurl_source_text

_HURL_TEMPLATE_RE = re.compile(r"\{\{\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_SECTION_RE = re.compile(r"^\s*\[(?P<name>[A-Za-z][A-Za-z0-9_-]*)\]\s*$")
_CAPTURE_RE = re.compile(r"^\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:")
_OPTION_VARIABLE_RE = re.compile(r"^\s*variable:\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=")
_HURL_BUILT_INS = frozenset({"newDate", "newUuid"})


class HurlVariablePreflightError(ValueError):
    """Raised when Hurl files reference variables that are unavailable."""


@dataclass(frozen=True)
class MissingHurlVariable:
    """One unresolved Hurl variable reference found before execution."""

    path: Path
    name: str


def preflight_hurl_variables(
    execution_copies: Sequence[HurlExecutionCopy],
    *,
    variables: Mapping[str, str],
    project_root: Path,
) -> None:
    """Fail before subprocess execution when selected Hurl files need variables."""

    missing = find_missing_hurl_variables(
        execution_copies,
        variables=variables,
        project_root=project_root,
    )
    if missing:
        raise HurlVariablePreflightError(_format_missing_variables(missing, project_root))


def find_missing_hurl_variables(
    execution_copies: Sequence[HurlExecutionCopy],
    *,
    variables: Mapping[str, str],
    project_root: Path,
) -> tuple[MissingHurlVariable, ...]:
    """Return unresolved Hurl template variables without raising."""

    missing: list[MissingHurlVariable] = []
    available_variables = set(variables)
    for execution_copy in execution_copies:
        content = _read_execution_content(execution_copy.execution_path)
        local_variables = _local_hurl_variables(content)
        referenced = _referenced_hurl_variables(content)
        unresolved = referenced - available_variables - local_variables - _HURL_BUILT_INS
        for name in sorted(unresolved):
            missing.append(MissingHurlVariable(path=execution_copy.source_path, name=name))

    return tuple(
        sorted(missing, key=lambda item: (_display_path(item.path, project_root), item.name))
    )


def _read_execution_content(path: Path) -> str:
    try:
        return read_hurl_source_text(path, label="execution Hurl copy")
    except HurlSourceTooLargeError as exc:
        raise HurlVariablePreflightError(str(exc)) from exc
    except UnicodeDecodeError as exc:
        msg = f"{path}: execution Hurl copy is not valid UTF-8"
        raise HurlVariablePreflightError(msg) from exc
    except OSError as exc:
        msg = f"Could not read execution Hurl copy {path}: {exc}"
        raise HurlVariablePreflightError(msg) from exc


def _referenced_hurl_variables(content: str) -> set[str]:
    references: set[str] = set()
    for line in content.splitlines():
        if _is_hurl_comment(line):
            continue
        references.update(match.group("name") for match in _HURL_TEMPLATE_RE.finditer(line))
    return references


def _local_hurl_variables(content: str) -> set[str]:
    variables: set[str] = set()
    section: str | None = None
    for line in content.splitlines():
        stripped = line.strip()
        section_match = _SECTION_RE.fullmatch(stripped)
        if section_match is not None:
            section = section_match.group("name").lower()
            continue
        if not stripped:
            section = None
            continue
        if _is_hurl_comment(line):
            continue
        if section == "captures":
            capture_match = _CAPTURE_RE.match(line)
            if capture_match is not None:
                variables.add(capture_match.group("name"))
            continue
        if section == "options":
            variable_match = _OPTION_VARIABLE_RE.match(line)
            if variable_match is not None:
                variables.add(variable_match.group("name"))
    return variables


def _format_missing_variables(
    missing: Sequence[MissingHurlVariable],
    project_root: Path,
) -> str:
    by_path: dict[str, set[str]] = {}
    for item in missing:
        display_path = _display_path(item.path, project_root)
        by_path.setdefault(display_path, set()).add(item.name)

    names = sorted({item.name for item in missing})
    locations = "; ".join(
        f"{path}: {', '.join(sorted(path_names))}"
        for path, path_names in sorted(by_path.items())
    )
    return (
        "Unresolved Hurl variables before execution: "
        f"{', '.join(names)}. "
        "Define missing variables in envs/<name>.env, shell HURL_VARIABLE_<name>, "
        "or local Hurl [Options]/[Captures] entries. "
        f"Occurrences: {locations}"
    )


def _display_path(path: Path, project_root: Path) -> str:
    root = project_root.expanduser().resolve()
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved.as_posix()


def _is_hurl_comment(line: str) -> bool:
    return line.lstrip().startswith("#")
