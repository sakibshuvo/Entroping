"""Bounded, configuration-free GitHub CLI transport and strict JSON parsing."""

from __future__ import annotations

import hashlib
import os
import pwd
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from scripts.bounded_process import BoundedProcessError, BoundedProcessResult, run_bounded_process
from scripts.factory_issue_selector_json import JsonBoundaryError, decode_json
from scripts.factory_issue_selector_models import JsonObject, JsonValue
from scripts.factory_orchestration_tools import trusted_executable

_MAX_OUTPUT: Final = 5_000_000
_TIMEOUT: Final = 20.0
_REPO_PATH: Final = "repos/sakibshuvo/Entroping"


class GitHubTransportError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code

    def __str__(self) -> str:
        return self.code


def trusted_gh_contract() -> tuple[Path, Mapping[str, str]]:
    try:
        executable = trusted_executable("gh")
        home = Path(pwd.getpwuid(os.geteuid()).pw_dir).resolve(strict=True)
    except (KeyError, OSError):
        raise GitHubTransportError("tool-unavailable") from None
    return executable, {
        "HOME": str(home),
        "PATH": "/usr/bin:/bin:/opt/homebrew/bin:/usr/local/bin",
        "LC_ALL": "C",
        "LANG": "C",
        "GH_PAGER": "cat",
        "GH_FORCE_TTY": "0",
        "NO_COLOR": "1",
    }


def run_gh_json(
    executable: Path,
    environment: Mapping[str, str],
    args: tuple[str, ...],
    *,
    cwd: Path,
) -> JsonValue:
    result = run_gh(executable, environment, args, cwd=cwd)
    try:
        return decode_json(result.stdout)
    except JsonBoundaryError:
        raise GitHubTransportError("github-response-invalid") from None


def run_gh_text(
    executable: Path,
    environment: Mapping[str, str],
    args: tuple[str, ...],
    *,
    cwd: Path,
) -> str:
    return run_gh(executable, environment, args, cwd=cwd).stdout


def run_gh(
    executable: Path,
    environment: Mapping[str, str],
    args: tuple[str, ...],
    *,
    cwd: Path,
) -> BoundedProcessResult:
    try:
        result = run_bounded_process(
            [executable, *args],
            cwd=cwd,
            timeout_seconds=_TIMEOUT,
            max_output_bytes=_MAX_OUTPUT,
            env=environment,
        )
    except BoundedProcessError:
        raise GitHubTransportError("github-command-failed") from None
    if result.timed_out or result.cancelled:
        raise GitHubTransportError("github-command-timeout")
    if result.output_limit_exceeded:
        raise GitHubTransportError("github-output-exceeded")
    if result.returncode != 0:
        raise GitHubTransportError("github-command-failed")
    return result


def require_object(value: JsonValue) -> JsonObject:
    if not isinstance(value, dict):
        raise GitHubTransportError("github-response-invalid")
    return value


def body_digest(body: object) -> str:
    if not isinstance(body, str) or len(body.encode()) > 65_536:
        raise GitHubTransportError("github-response-invalid")
    return hashlib.sha256(body.encode()).hexdigest()


def validate_argument(value: str, *, max_bytes: int, allow_newlines: bool = False) -> str:
    if not isinstance(value, str) or len(value.encode()) > max_bytes:
        raise GitHubTransportError("github-request-invalid")
    for character in value:
        if ord(character) < 32 and character not in ({"\n", "\t"} if allow_newlines else set()):
            raise GitHubTransportError("github-request-invalid")
    return value


def string_field(payload: JsonObject, key: str, *, max_bytes: int = 4096) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value or len(value.encode()) > max_bytes:
        raise GitHubTransportError("github-response-invalid")
    return value


def int_field(payload: JsonObject, key: str, *, minimum: int = 1) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise GitHubTransportError("github-response-invalid")
    return value


def bool_field(payload: JsonObject, key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise GitHubTransportError("github-response-invalid")
    return value


def list_field(payload: JsonObject, key: str) -> list[JsonValue]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise GitHubTransportError("github-response-invalid")
    return value
