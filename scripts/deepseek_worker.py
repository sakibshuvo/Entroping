#!/usr/bin/env python3
"""Run bounded direct DeepSeek API workers and capture local artifacts."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess  # nosec B404
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone as datetime_timezone
from pathlib import Path
from typing import Literal, cast
from urllib import error, request
from urllib.parse import urlparse

from ai_worker_file_safety import (
    secret_like_content_reason,
    sensitive_selected_path_reason,
)

DEFAULT_MODEL = "deepseek-v4-pro"
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_API_KEY_ENV = "DEEPSEEK_API_KEY"
DEFAULT_ARTIFACT_ROOT = Path(".entroping") / "ai-reviews"
DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_MAX_TOKENS = 4096
DEFAULT_MAX_FILE_BYTES = 64_000
UTC_TZ = datetime_timezone.utc  # noqa: UP017 - factory scripts run under Python 3.9.
Mode = Literal["review", "patch"]
Status = Literal["completed", "dry-run", "failed", "inconclusive", "patch-proposed", "timed-out"]
ThinkingMode = Literal["enabled", "disabled"]
ReasoningEffort = Literal["high", "max"]


@dataclass(frozen=True)
class DirectWorkerConfig:
    """Validated direct DeepSeek worker configuration."""

    mode: Mode
    model: str
    repo_root: Path
    files: tuple[Path, ...]
    artifact_root: Path
    base_url: str
    api_key_env: str
    timeout_seconds: float
    max_tokens: int
    max_file_bytes: int
    thinking: ThinkingMode
    reasoning_effort: ReasoningEffort
    issue: str | None
    instruction: str | None
    dry_run: bool
    json_output: bool
    record_factory_metrics: bool
    factory_role: str | None
    factory_metrics_ledger: Path | None


@dataclass(frozen=True)
class DirectWorkerResult:
    """Direct DeepSeek worker execution result."""

    status: Status
    artifact_dir: Path
    returncode: int
    stdout: str
    stderr: str
    response_payload: dict[str, object] | None
    usage: dict[str, object] | None


@dataclass(frozen=True)
class PreparedContextFile:
    """Validated file content allowed to leave the local machine."""

    relative_path: str
    content: str


class DirectWorkerInputError(ValueError):
    """Raised when direct worker inputs are unsafe or incomplete."""


def main() -> int:
    try:
        config = _parse_args()
        result = run_worker(config)
    except DirectWorkerInputError as exc:
        print(f"deepseek_worker: {exc}", file=sys.stderr)
        return 2

    payload = {
        "status": result.status,
        "artifact_dir": str(result.artifact_dir),
        "returncode": result.returncode,
    }
    if result.usage is not None:
        payload["usage"] = result.usage
    if config.json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"DeepSeek worker status: {result.status}")
        print(f"Artifact directory: {result.artifact_dir}")

    if result.status == "timed-out":
        return 124
    if result.status == "failed":
        return 1
    return 0


def run_worker(config: DirectWorkerConfig) -> DirectWorkerResult:
    """Run a direct DeepSeek request and write local artifacts."""

    started_at = time.monotonic()
    context_files = _prepare_context_files(config)
    api_key = "" if config.dry_run else _read_api_key(config.api_key_env)
    artifact_dir = _new_artifact_dir(config.artifact_root, config.mode)
    artifact_dir.mkdir(parents=True, exist_ok=False)

    prompt = _build_prompt(config, context_files)
    (artifact_dir / "prompt.md").write_text(prompt, encoding="utf-8")

    endpoint = _chat_endpoint(config.base_url)
    request_body = _request_body(config, prompt)
    (artifact_dir / "request.json").write_text(
        json.dumps(_sanitized_request_body(request_body), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if config.dry_run:
        result = DirectWorkerResult(
            status="dry-run",
            artifact_dir=artifact_dir,
            returncode=0,
            stdout="",
            stderr="",
            response_payload=None,
            usage=None,
        )
        _write_metadata(config, result, endpoint)
        _record_factory_metrics(
            config,
            result,
            duration_seconds=time.monotonic() - started_at,
        )
        return result

    result = _call_deepseek(config, endpoint, api_key, request_body, artifact_dir)
    _write_execution_artifacts(config, result, endpoint)
    _record_factory_metrics(
        config,
        result,
        duration_seconds=time.monotonic() - started_at,
    )
    return result


def _parse_args() -> DirectWorkerConfig:
    parser = argparse.ArgumentParser(
        description="Run a bounded direct DeepSeek review or patch proposal.",
    )
    parser.add_argument("--mode", choices=("review", "patch"), required=True)
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"DeepSeek model id. Default: {DEFAULT_MODEL}.",
    )
    parser.add_argument(
        "--file",
        dest="files",
        action="append",
        default=[],
        help="Repo-local file to include in the worker scope; repeatable.",
    )
    parser.add_argument("--issue", help="Optional GitHub issue number or URL.")
    parser.add_argument(
        "--instruction",
        help="Optional task-specific instruction appended to the bounded prompt.",
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_ARTIFACT_ROOT,
        help="Directory for local worker artifacts. Default: .entroping/ai-reviews",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="DeepSeek OpenAI-compatible base URL. Default: https://api.deepseek.com",
    )
    parser.add_argument(
        "--api-key-env",
        default=DEFAULT_API_KEY_ENV,
        help="Environment variable containing the DeepSeek API key.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="HTTP request timeout in seconds.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help="Maximum completion tokens for the worker response.",
    )
    parser.add_argument(
        "--max-file-bytes",
        type=int,
        default=DEFAULT_MAX_FILE_BYTES,
        help=(
            "Maximum bytes per selected file to include in the prompt. "
            f"Default: {DEFAULT_MAX_FILE_BYTES}."
        ),
    )
    parser.add_argument(
        "--thinking",
        choices=("enabled", "disabled"),
        default="disabled",
        help=(
            "DeepSeek thinking mode toggle. Default: disabled to avoid hidden "
            "reasoning-token burn for short worker reviews."
        ),
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=("high", "max"),
        default="high",
        help="DeepSeek thinking effort when thinking is enabled. Default: high.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write prompt/request metadata without invoking DeepSeek.",
    )
    parser.add_argument(
        "--record-factory-metrics",
        action="store_true",
        help="Append an ignored local software-factory metrics event.",
    )
    parser.add_argument(
        "--factory-role",
        help=(
            "Factory role tag for metrics. Defaults to code_review_agent for "
            "review mode and dev_agent for patch mode."
        ),
    )
    parser.add_argument(
        "--factory-metrics-ledger",
        type=Path,
        help="Metrics ledger path under .entroping/factory-metrics/.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary.")
    args = parser.parse_args()

    repo_root = _repo_root()
    files = _validate_files(repo_root, tuple(Path(path) for path in args.files))
    if not files:
        msg = "at least one --file is required"
        raise DirectWorkerInputError(msg)
    if args.timeout_seconds <= 0:
        msg = "--timeout-seconds must be greater than zero"
        raise DirectWorkerInputError(msg)
    if args.max_tokens <= 0:
        msg = "--max-tokens must be greater than zero"
        raise DirectWorkerInputError(msg)
    if args.max_file_bytes <= 0:
        msg = "--max-file-bytes must be greater than zero"
        raise DirectWorkerInputError(msg)

    api_key_env = _validate_env_name(str(args.api_key_env))
    base_url = _validate_base_url(str(args.base_url))
    artifact_root = args.artifact_root
    if not artifact_root.is_absolute():
        artifact_root = repo_root / artifact_root

    mode: Mode = args.mode
    thinking: ThinkingMode = args.thinking
    reasoning_effort: ReasoningEffort = args.reasoning_effort
    return DirectWorkerConfig(
        mode=mode,
        model=str(args.model),
        repo_root=repo_root,
        files=files,
        artifact_root=artifact_root.expanduser().resolve(),
        base_url=base_url,
        api_key_env=api_key_env,
        timeout_seconds=float(args.timeout_seconds),
        max_tokens=int(args.max_tokens),
        max_file_bytes=int(args.max_file_bytes),
        thinking=thinking,
        reasoning_effort=reasoning_effort,
        issue=args.issue,
        instruction=args.instruction,
        dry_run=bool(args.dry_run),
        json_output=bool(args.json),
        record_factory_metrics=bool(args.record_factory_metrics),
        factory_role=args.factory_role,
        factory_metrics_ledger=args.factory_metrics_ledger,
    )


def _repo_root() -> Path:
    try:
        completed = subprocess.run(  # nosec B603
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        msg = "run this from inside the Entroping git repository"
        raise DirectWorkerInputError(msg) from exc
    return Path(completed.stdout.strip()).resolve()


def _validate_files(repo_root: Path, raw_files: tuple[Path, ...]) -> tuple[Path, ...]:
    validated: list[Path] = []
    for raw_file in raw_files:
        path = raw_file.expanduser()
        if not path.is_absolute():
            path = repo_root / path
        resolved = path.resolve()
        if not resolved.exists():
            msg = f"input file does not exist: {raw_file}"
            raise DirectWorkerInputError(msg)
        if not resolved.is_file() or resolved.is_symlink():
            msg = f"input path must be a regular non-symlink file: {raw_file}"
            raise DirectWorkerInputError(msg)
        try:
            resolved.relative_to(repo_root)
        except ValueError as exc:
            msg = f"input file must be inside repository: {raw_file}"
            raise DirectWorkerInputError(msg) from exc
        validated.append(resolved)
    return tuple(dict.fromkeys(validated))


def _validate_env_name(raw_name: str) -> str:
    name = raw_name.strip()
    if not name or not name.replace("_", "A").isalnum() or name[0].isdigit():
        msg = "--api-key-env must be an environment variable name"
        raise DirectWorkerInputError(msg)
    return name


def _validate_base_url(raw_url: str) -> str:
    url = raw_url.strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        msg = "--base-url must be an http or https URL"
        raise DirectWorkerInputError(msg)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        msg = "--base-url must not include credentials, query, or fragment"
        raise DirectWorkerInputError(msg)
    return url


def _read_api_key(env_name: str) -> str:
    api_key = os.environ.get(env_name, "").strip()
    if not api_key:
        msg = f"missing DeepSeek API key env var: {env_name}"
        raise DirectWorkerInputError(msg)
    return api_key


def _prepare_context_files(config: DirectWorkerConfig) -> tuple[PreparedContextFile, ...]:
    prepared_files: list[PreparedContextFile] = []
    for path in config.files:
        relative_path = path.relative_to(config.repo_root).as_posix()
        _reject_sensitive_path(relative_path)
        try:
            size = path.stat().st_size
        except OSError as exc:
            msg = f"could not stat selected file: {relative_path}"
            raise DirectWorkerInputError(msg) from exc
        if size > config.max_file_bytes:
            msg = (
                "refusing to send selected file to DeepSeek: "
                f"{relative_path} is {size} bytes and exceeds --max-file-bytes "
                f"({config.max_file_bytes})"
            )
            raise DirectWorkerInputError(msg)
        try:
            raw_content = path.read_bytes()
        except OSError as exc:
            msg = f"could not read selected file: {relative_path}"
            raise DirectWorkerInputError(msg) from exc
        if b"\x00" in raw_content:
            msg = (
                "refusing to send selected file to DeepSeek: "
                f"{relative_path} contains binary content"
            )
            raise DirectWorkerInputError(msg)
        try:
            content = raw_content.decode("utf-8")
        except UnicodeDecodeError as exc:
            msg = (
                "refusing to send selected file to DeepSeek: "
                f"{relative_path} must be UTF-8 text"
            )
            raise DirectWorkerInputError(msg) from exc
        _reject_secret_like_content(relative_path, content)
        prepared_files.append(
            PreparedContextFile(relative_path=relative_path, content=content)
        )
    return tuple(prepared_files)


def _reject_sensitive_path(relative_path: str) -> None:
    reason = sensitive_selected_path_reason(relative_path)
    if reason is not None:
        msg = (
            "refusing to send selected file to DeepSeek: "
            f"{relative_path} {reason}"
        )
        raise DirectWorkerInputError(msg)


def _reject_secret_like_content(relative_path: str, content: str) -> None:
    reason = secret_like_content_reason(content)
    if reason is not None:
        msg = (
            "refusing to send selected file to DeepSeek: "
            f"{relative_path} contains secret-like content ({reason})"
        )
        raise DirectWorkerInputError(msg)


def _build_prompt(
    config: DirectWorkerConfig,
    context_files: tuple[PreparedContextFile, ...],
) -> str:
    template = _template_path(config.repo_root, config.mode).read_text(encoding="utf-8")
    relative_files = [path.relative_to(config.repo_root).as_posix() for path in config.files]
    absolute_files = [str(path) for path in config.files]
    lines = [
        template.rstrip(),
        "",
        "## Worker Scope",
        "",
        f"- Repository: {config.repo_root}",
        f"- Mode: {config.mode}",
        f"- Issue: {config.issue or 'not provided'}",
        "- Context pack command: scripts/context_pack.sh --mode review",
        "",
        "## Allowed Files",
        "",
    ]
    lines.extend(f"- {path}" for path in relative_files)
    lines.extend(["", "## Absolute File Paths", ""])
    lines.extend(f"- {path}" for path in absolute_files)
    lines.extend(
        [
            "",
            "## Bounded File Contents",
            "",
            (
                "The following UTF-8 text files passed local size, binary, path, "
                "and secret-like-content checks before this prompt was built."
            ),
            "",
        ]
    )
    for context_file in context_files:
        fence = _markdown_fence(context_file.content)
        lines.extend(
            [
                f"### File: {context_file.relative_path}",
                "",
                f"{fence}text",
                context_file.content.rstrip("\n"),
                fence,
                "",
            ]
        )
    if config.instruction is not None:
        lines.extend(["", "## Task Instruction", "", config.instruction.strip()])
    return "\n".join(lines).rstrip() + "\n"


def _markdown_fence(content: str) -> str:
    longest_run = 0
    for match in re.finditer(r"`+", content):
        longest_run = max(longest_run, len(match.group(0)))
    return "`" * max(3, longest_run + 1)


def _template_path(repo_root: Path, mode: Mode) -> Path:
    path = repo_root / "prompts" / "deepseek" / f"{mode}.md"
    if not path.is_file():
        msg = f"missing prompt template: {path}"
        raise DirectWorkerInputError(msg)
    return path


def _chat_endpoint(base_url: str) -> str:
    return f"{base_url}/chat/completions"


def _request_body(config: DirectWorkerConfig, prompt: str) -> dict[str, object]:
    body: dict[str, object] = {
        "model": config.model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a bounded Entroping worker. Return only the requested "
                    "review or patch artifact. Codex validates all outputs."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "max_tokens": config.max_tokens,
        "thinking": {"type": config.thinking},
    }
    if config.thinking == "enabled":
        body["reasoning_effort"] = config.reasoning_effort
    return body


def _sanitized_request_body(body: dict[str, object]) -> dict[str, object]:
    return dict(body)


def _call_deepseek(
    config: DirectWorkerConfig,
    endpoint: str,
    api_key: str,
    request_body: dict[str, object],
    artifact_dir: Path,
) -> DirectWorkerResult:
    encoded_body = json.dumps(request_body).encode("utf-8")
    http_request = request.Request(
        endpoint,
        data=encoded_body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with request.urlopen(  # nosec B310
            http_request,
            timeout=config.timeout_seconds,
        ) as response:
            response_text = response.read().decode("utf-8", errors="replace")
    except TimeoutError:
        return DirectWorkerResult(
            status="timed-out",
            artifact_dir=artifact_dir,
            returncode=124,
            stdout="",
            stderr=f"DeepSeek worker timed out after {config.timeout_seconds} seconds.",
            response_payload=None,
            usage=None,
        )
    except error.HTTPError as exc:
        response_text = exc.read().decode("utf-8", errors="replace")
        stderr = f"DeepSeek API returned HTTP {exc.code}."
        if response_text:
            stderr = f"{stderr}\n{response_text}"
        return DirectWorkerResult(
            status="failed",
            artifact_dir=artifact_dir,
            returncode=1,
            stdout="",
            stderr=stderr,
            response_payload=_json_object_or_none(response_text),
            usage=None,
        )
    except error.URLError as exc:
        return DirectWorkerResult(
            status="failed",
            artifact_dir=artifact_dir,
            returncode=1,
            stdout="",
            stderr=f"DeepSeek API request failed: {exc.reason}",
            response_payload=None,
            usage=None,
        )

    payload = _json_object_or_none(response_text)
    if payload is None:
        return DirectWorkerResult(
            status="failed",
            artifact_dir=artifact_dir,
            returncode=1,
            stdout="",
            stderr="DeepSeek API returned non-object JSON.",
            response_payload=None,
            usage=None,
        )

    content = _assistant_content(payload)
    usage = _usage_object(payload)
    status = _classify_status(config.mode, content)
    return DirectWorkerResult(
        status=status,
        artifact_dir=artifact_dir,
        returncode=0,
        stdout=content,
        stderr="",
        response_payload=payload,
        usage=usage,
    )


def _json_object_or_none(text: str) -> dict[str, object] | None:
    if not text.strip():
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return cast(dict[str, object], payload)


def _assistant_content(payload: dict[str, object]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return ""
    message = first_choice.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if not isinstance(content, str):
        return ""
    return content


def _usage_object(payload: dict[str, object]) -> dict[str, object] | None:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None
    safe_usage: dict[str, object] = {}
    for key, value in usage.items():
        if isinstance(key, str) and isinstance(value, (int, float, str)):
            safe_usage[key] = value
    return safe_usage


def _new_artifact_dir(artifact_root: Path, mode: Mode) -> Path:
    timestamp = datetime.now(UTC_TZ).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid.uuid4().hex[:8]
    return artifact_root / f"{timestamp}-deepseek-{mode}-{suffix}"


def _classify_status(mode: Mode, output: str) -> Status:
    if mode == "patch":
        if _extract_unified_diff(output) is not None:
            return "patch-proposed"
        return "inconclusive"
    if output.strip():
        return "completed"
    return "inconclusive"


def _looks_like_unified_diff(output: str) -> bool:
    return (
        "diff --git " in output
        and "\n--- " in output
        and "\n+++ " in output
        and "\n@@" in output
    )


def _extract_unified_diff(output: str) -> str | None:
    lines = output.splitlines()
    start_index: int | None = None
    for index, line in enumerate(lines):
        if line.startswith("diff --git "):
            start_index = index
            break
    if start_index is None:
        return None

    diff_lines: list[str] = []
    for line in lines[start_index:]:
        if line.strip() == "```" and diff_lines:
            break
        diff_lines.append(line)

    diff = "\n".join(diff_lines).rstrip() + "\n"
    if not _looks_like_unified_diff(diff):
        return None
    return diff


def _write_execution_artifacts(
    config: DirectWorkerConfig,
    result: DirectWorkerResult,
    endpoint: str,
) -> None:
    (result.artifact_dir / "stdout.txt").write_text(result.stdout, encoding="utf-8")
    (result.artifact_dir / "stderr.txt").write_text(result.stderr, encoding="utf-8")
    if result.response_payload is not None:
        (result.artifact_dir / "response.json").write_text(
            json.dumps(result.response_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if config.mode == "patch":
        proposal = _extract_unified_diff(result.stdout)
        if proposal is not None:
            (result.artifact_dir / "proposal.diff").write_text(proposal, encoding="utf-8")
    _write_metadata(config, result, endpoint)


def _write_metadata(
    config: DirectWorkerConfig,
    result: DirectWorkerResult,
    endpoint: str,
) -> None:
    metadata = {
        "schema_version": "entroping.deepseek-worker.v1",
        "status": result.status,
        "mode": config.mode,
        "model": config.model,
        "issue": config.issue,
        "files": [path.relative_to(config.repo_root).as_posix() for path in config.files],
        "artifact_dir": str(result.artifact_dir),
        "returncode": result.returncode,
        "timeout_seconds": config.timeout_seconds,
        "max_tokens": config.max_tokens,
        "max_file_bytes": config.max_file_bytes,
        "context_policy": "bounded-file-content-v1",
        "base_url": config.base_url,
        "endpoint": endpoint,
        "api_key_env": config.api_key_env,
        "thinking": config.thinking,
        "reasoning_effort": config.reasoning_effort,
        "usage": result.usage,
        "created_at": datetime.now(UTC_TZ).isoformat(),
        "dry_run": config.dry_run,
    }
    (result.artifact_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _record_factory_metrics(
    config: DirectWorkerConfig,
    result: DirectWorkerResult,
    *,
    duration_seconds: float,
) -> None:
    if not config.record_factory_metrics:
        return

    context_bytes = _selected_files_bytes(config.files)
    estimated_tokens = _usage_total_tokens(result.usage)
    if estimated_tokens is None:
        estimated_tokens = max(1, (context_bytes + 3) // 4)

    command = [
        sys.executable,
        str(config.repo_root / "scripts" / "factory_metrics.py"),
        "--repo-root",
        str(config.repo_root),
        "append",
        "--event-type",
        "worker_job",
        "--role",
        config.factory_role or _default_factory_role(config.mode),
        "--agent",
        "DeepSeek",
        "--tool",
        "scripts/deepseek_worker.py",
        "--provider",
        "deepseek",
        "--model",
        config.model,
        "--worktree",
        str(config.repo_root),
        "--context-bytes",
        str(context_bytes),
        "--estimated-tokens",
        str(estimated_tokens),
        "--candidate-files",
        str(len(config.files)),
        "--files-read",
        str(len(config.files)),
        "--duration-seconds",
        f"{duration_seconds:.6f}",
        "--outcome",
        _factory_outcome(result.status),
        "--decision",
        _factory_decision(result.status),
        "--note",
        _factory_note(config, result),
        "--json",
    ]
    if config.issue is not None:
        command.extend(["--issue", config.issue])
    if config.factory_metrics_ledger is not None:
        command.extend(["--ledger", str(config.factory_metrics_ledger)])

    completed = subprocess.run(  # nosec B603
        command,
        cwd=config.repo_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        warning = (completed.stderr or completed.stdout).strip()
        print(f"deepseek_worker: factory metrics warning: {warning}", file=sys.stderr)


def _selected_files_bytes(files: tuple[Path, ...]) -> int:
    total = 0
    for path in files:
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return total


def _usage_total_tokens(usage: dict[str, object] | None) -> int | None:
    if usage is None:
        return None

    total = _numeric_usage_value(usage.get("total_tokens"))
    if total is not None:
        return total

    prompt_tokens = _numeric_usage_value(usage.get("prompt_tokens"))
    completion_tokens = _numeric_usage_value(usage.get("completion_tokens"))
    if prompt_tokens is not None and completion_tokens is not None:
        return prompt_tokens + completion_tokens
    return None


def _numeric_usage_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value >= 0:
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _default_factory_role(mode: Mode) -> str:
    if mode == "patch":
        return "dev_agent"
    return "code_review_agent"


def _factory_outcome(status: Status) -> str:
    if status in {"completed", "dry-run", "patch-proposed"}:
        return "success"
    if status == "timed-out":
        return "blocked"
    if status == "failed":
        return "failure"
    return "inconclusive"


def _factory_decision(status: Status) -> str:
    if status == "dry-run":
        return "not_applicable"
    return "needs_review"


def _factory_note(config: DirectWorkerConfig, result: DirectWorkerResult) -> str:
    parts = [f"mode={config.mode}", f"status={result.status}"]
    ignored_root = (config.repo_root / ".entroping").resolve()
    try:
        relative_artifact_dir = result.artifact_dir.resolve().relative_to(ignored_root)
    except ValueError:
        return ";".join(parts)
    parts.append(f"artifact_dir=.entroping/{relative_artifact_dir.as_posix()}")
    return ";".join(parts)


if __name__ == "__main__":
    raise SystemExit(main())
