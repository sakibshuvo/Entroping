from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from .deepseek_worker_limits import DEFAULT_MAX_REQUEST_BYTES, DEFAULT_MAX_TOKENS

MAX_WORKER_SUPERVISOR_OUTPUT_BYTES = 1_048_576
PROVIDER_EVIDENCE_HMAC_KEY_ENV = "ENTROPING_FACTORY_PROVIDER_EVIDENCE_HMAC_KEY_V1"
_BASE_WORKER_ENV_KEYS = ("LANG", "LC_ALL", "LC_CTYPE", "PATH", "TMPDIR")
_DEFAULT_PATH = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


class ProcessResult(Protocol):
    @property
    def returncode(self) -> int:
        raise NotImplementedError

    @property
    def stdout(self) -> str:
        raise NotImplementedError

    @property
    def timed_out(self) -> bool:
        raise NotImplementedError

    @property
    def output_limit_exceeded(self) -> bool:
        raise NotImplementedError


class ProcessRunner(Protocol):
    def __call__(
        self,
        command: Sequence[str | Path],
        *,
        cwd: Path,
        timeout_seconds: float,
        max_output_bytes: int,
        env: Mapping[str, str] | None = None,
    ) -> ProcessResult:
        raise NotImplementedError


class WorkerLaunchError(ValueError):
    pass


def run_opencode_worker(
    args: argparse.Namespace,
    repo_root: Path,
    job: Mapping[str, object],
    *,
    artifact_root: Path,
    timeout_seconds: float,
    scoped_files: Sequence[str],
    run_process: ProcessRunner,
) -> tuple[dict[str, object], int]:
    command = [
        sys.executable,
        str(repo_root / "scripts" / "opencode_worker.py"),
        "--mode",
        str(job["mode"]),
        "--model",
        str(job["model"]),
        "--artifact-root",
        str(artifact_root),
        "--timeout-seconds",
        str(timeout_seconds),
        "--job-id",
        str(job["job_id"]),
        "--json",
    ]
    for scoped_file in scoped_files:
        command.extend(["--file", scoped_file])
    if job.get("issue") is not None:
        command.extend(["--issue", str(job["issue"])])
    instruction = _effective_worker_instruction(job)
    if instruction is not None:
        command.extend(["--instruction", instruction])
    if args.opencode_bin is not None:
        command.extend(["--opencode-bin", str(args.opencode_bin)])
    if args.worker_dry_run:
        command.append("--dry-run")
    _extend_factory_metrics_args(command, args)
    return _run_command(
        command,
        repo_root=repo_root,
        timeout_seconds=timeout_seconds,
        environment=_worker_environment(opencode=True),
        run_process=run_process,
    )


def run_deepseek_worker(
    args: argparse.Namespace,
    repo_root: Path,
    job: Mapping[str, object],
    *,
    artifact_root: Path,
    timeout_seconds: float,
    scoped_files: Sequence[str],
    run_process: ProcessRunner,
) -> tuple[dict[str, object], int]:
    api_key_env = _validated_api_key_env(str(args.deepseek_api_key_env))
    command = [
        sys.executable,
        str(repo_root / "scripts" / "deepseek_worker.py"),
        "--mode",
        str(job["mode"]),
        "--model",
        str(job["model"]),
        "--artifact-root",
        str(artifact_root),
        "--timeout-seconds",
        str(timeout_seconds),
        "--job-id",
        str(job["job_id"]),
        "--base-url",
        str(args.deepseek_base_url),
        "--api-key-env",
        api_key_env,
        "--thinking",
        str(args.deepseek_thinking),
        "--max-request-bytes",
        str(DEFAULT_MAX_REQUEST_BYTES),
        "--max-tokens",
        str(DEFAULT_MAX_TOKENS),
        "--json",
    ]
    if getattr(args, "allow_insecure_local_deepseek_base_url", False):
        command.append("--allow-insecure-local-base-url")
    if args.deepseek_thinking == "enabled":
        command.extend(["--reasoning-effort", str(args.deepseek_reasoning_effort)])
    for scoped_file in scoped_files:
        command.extend(["--file", scoped_file])
    if job.get("issue") is not None:
        command.extend(["--issue", str(job["issue"])])
    instruction = _effective_worker_instruction(job)
    if instruction is not None:
        command.extend(["--instruction", instruction])
    if args.worker_dry_run:
        command.append("--dry-run")
    _extend_factory_metrics_args(command, args)
    return _run_command(
        command,
        repo_root=repo_root,
        timeout_seconds=timeout_seconds,
        environment=_worker_environment(api_key_env=api_key_env),
        run_process=run_process,
    )


def validated_worker_artifact_dir(
    artifact_root: Path,
    raw_value: object,
) -> str | None:
    if not isinstance(raw_value, str) or not raw_value:
        return None
    path = Path(raw_value).expanduser()
    if not path.is_absolute():
        path = artifact_root / path
    if any(candidate.is_symlink() for candidate in (path, *path.parents)):
        raise WorkerLaunchError("worker artifact_dir must not use symlink components")
    resolved = path.resolve()
    try:
        resolved.relative_to(artifact_root)
    except ValueError as exc:
        raise WorkerLaunchError("worker artifact_dir must stay under artifact root") from exc
    if not resolved.is_dir():
        raise WorkerLaunchError("worker artifact_dir must be an existing directory")
    return str(resolved)


def _run_command(
    command: list[str],
    *,
    repo_root: Path,
    timeout_seconds: float,
    environment: Mapping[str, str],
    run_process: ProcessRunner,
) -> tuple[dict[str, object], int]:
    completed = run_process(
        command,
        cwd=repo_root,
        timeout_seconds=timeout_seconds + 30.0,
        max_output_bytes=MAX_WORKER_SUPERVISOR_OUTPUT_BYTES,
        env=environment,
    )
    if completed.timed_out:
        return {"status": "timed-out", "returncode": 124, "artifact_dir": None}, 124
    if completed.output_limit_exceeded:
        return {"status": "failed", "returncode": 1, "artifact_dir": None}, 1
    return _parse_worker_payload(completed.stdout, completed.returncode), completed.returncode


def _worker_environment(
    *,
    api_key_env: str | None = None,
    opencode: bool = False,
) -> Mapping[str, str]:
    environment = {key: os.environ[key] for key in _BASE_WORKER_ENV_KEYS if key in os.environ}
    environment.setdefault("PATH", _DEFAULT_PATH)
    if opencode and "DEEPSEEK_API_KEY" in os.environ:
        environment["DEEPSEEK_API_KEY"] = os.environ["DEEPSEEK_API_KEY"]
    if api_key_env is not None and api_key_env in os.environ:
        environment[api_key_env] = os.environ[api_key_env]
    environment.pop(PROVIDER_EVIDENCE_HMAC_KEY_ENV, None)
    return environment


def _validated_api_key_env(raw_name: str) -> str:
    name = raw_name.strip()
    if not name or not name.replace("_", "A").isalnum() or name[0].isdigit():
        raise WorkerLaunchError("DeepSeek API key environment name is invalid")
    if name == PROVIDER_EVIDENCE_HMAC_KEY_ENV:
        raise WorkerLaunchError("provider evidence authentication key cannot be a worker API key")
    return name


def _parse_worker_payload(stdout: str, returncode: int) -> dict[str, object]:
    try:
        raw_payload: object = json.loads(stdout)
    except json.JSONDecodeError:
        return {"status": "failed", "returncode": returncode, "artifact_dir": None}
    if not isinstance(raw_payload, dict):
        return {"status": "failed", "returncode": returncode, "artifact_dir": None}
    return {key: value for key, value in raw_payload.items() if isinstance(key, str)}


def _effective_worker_instruction(job: Mapping[str, object]) -> str | None:
    for key in ("worker_instruction", "instruction"):
        value = job.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _extend_factory_metrics_args(command: list[str], args: argparse.Namespace) -> None:
    if not getattr(args, "record_factory_metrics", False):
        return
    command.append("--record-factory-metrics")
    factory_role = getattr(args, "factory_role", None)
    if factory_role is not None:
        command.extend(["--factory-role", str(factory_role)])
    factory_metrics_ledger = getattr(args, "factory_metrics_ledger", None)
    if factory_metrics_ledger is not None:
        command.extend(["--factory-metrics-ledger", str(factory_metrics_ledger)])
