from __future__ import annotations

import json
import os
import subprocess  # nosec B404
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from entroping.core.safe_write import SafeWriteError, safe_report_output_path, safe_write_text


class ScriptSafetyError(ValueError):
    pass

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_OUTPUT_BYTES = 262_144
DEFAULT_MAX_TEXT_BYTES = 5_000_000
DEFAULT_MAX_JSON_BYTES = 5_000_000
TRUNCATED_MESSAGE = "[truncated output]"


def run_subprocess(
    command: Sequence[str | Path],
    *,
    cwd: Path | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    env: Mapping[str, str] | None = None,
    inherit_env: bool = True,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    check: bool = False,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    args = _coerce_command(command)
    if timeout <= 0:
        raise ScriptSafetyError("timeout must be positive")
    if max_output_bytes <= 0:
        raise ScriptSafetyError("max_output_bytes must be positive")

    combined_env = os.environ.copy() if inherit_env else {}
    if env is not None:
        combined_env.update(env)

    try:
        completed = subprocess.run(  # nosec B603
            args,
            check=False,
            cwd=None if cwd is None else str(cwd),
            env=combined_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            input=input_text,
        )
    except subprocess.TimeoutExpired as exc:
        msg = f"command timed out after {exc.timeout:g} seconds: {args[0]}"
        raise ScriptSafetyError(msg) from exc
    except UnicodeDecodeError as exc:
        msg = f"command output was not valid UTF-8: {args[0]}"
        raise ScriptSafetyError(msg) from exc
    except OSError as exc:
        msg = f"command execution failed: {exc}"
        raise ScriptSafetyError(msg) from exc

    stdout = _bounded_output(completed.stdout, limit=max_output_bytes)
    stderr = _bounded_output(completed.stderr, limit=max_output_bytes)
    result = subprocess.CompletedProcess(
        args=completed.args,
        returncode=completed.returncode,
        stdout=stdout,
        stderr=stderr,
    )

    if check and completed.returncode != 0:
        msg = (
            f"command failed with exit code {completed.returncode}: "
            f"{args[0]}"
        )
        raise ScriptSafetyError(msg)
    return result


def read_text_file(
    path: Path,
    *,
    max_bytes: int = DEFAULT_MAX_TEXT_BYTES,
    errors: str = "strict",
) -> str:
    if max_bytes <= 0:
        raise ScriptSafetyError("max_bytes must be positive")

    try:
        with path.open("rb") as handle:
            payload = handle.read(max_bytes + 1)
    except OSError as exc:
        raise ScriptSafetyError(f"could not read text file: {path}: {exc}") from exc

    if len(payload) > max_bytes:
        raise ScriptSafetyError(f"text file exceeds safe read limit: {path}")

    try:
        return payload.decode("utf-8", errors=errors)
    except (LookupError, UnicodeDecodeError) as exc:
        raise ScriptSafetyError(f"text file is not valid UTF-8: {path}") from exc


def read_json_file(path: Path, *, max_bytes: int = DEFAULT_MAX_JSON_BYTES) -> Any:
    content = read_text_file(path, max_bytes=max_bytes)
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ScriptSafetyError(f"invalid JSON in {path}: {exc.msg}") from exc


def write_text_file(
    path: Path,
    content: str,
    *,
    artifact: str,
    root: Path | None = None,
) -> Path:
    try:
        safe_path = _safe_output_path(path=path, root=root, artifact=artifact)
        return safe_write_text(safe_path, content, artifact=artifact, root=root)
    except SafeWriteError as exc:
        msg = f"could not write {artifact} {path}: {exc}"
        raise ScriptSafetyError(msg) from exc


def write_json_file(
    path: Path,
    payload: Any,
    *,
    artifact: str,
    root: Path | None = None,
    indent: int = 2,
    sort_keys: bool = True,
    append_newline: bool = False,
) -> Path:
    try:
        content = json.dumps(payload, indent=indent, sort_keys=sort_keys)
    except (TypeError, ValueError) as exc:
        raise ScriptSafetyError(f"could not serialize {artifact} JSON") from exc
    if append_newline:
        content += "\n"
    return write_text_file(path, content, artifact=artifact, root=root)


def _safe_output_path(
    path: Path,
    *,
    artifact: str,
    root: Path | None,
) -> Path:
    if root is None:
        return path.expanduser()
    return safe_report_output_path(
        path=path,
        root=root,
        artifact=artifact,
        forbidden_components=(".entroping",),
        forbid_components_anywhere=True,
    )


def _coerce_command(command: Sequence[str | Path]) -> list[str]:
    if len(command) == 0:
        raise ScriptSafetyError("command must contain at least one argument")
    args: list[str] = []
    for part in command:
        if isinstance(part, Path):
            args.append(str(part))
        elif isinstance(part, str):
            args.append(part)
        else:
            raise ScriptSafetyError(f"command argument must be str or Path: {part!r}")
    return args


def _bounded_output(value: str, *, limit: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    truncated_suffix = TRUNCATED_MESSAGE
    encoded_suffix = truncated_suffix.encode("utf-8")
    if len(encoded_suffix) >= limit:
        return encoded_suffix[:limit].decode("utf-8", errors="ignore")
    head = encoded[: limit - len(encoded_suffix)].decode("utf-8", errors="ignore")
    return f"{head}{truncated_suffix}"
