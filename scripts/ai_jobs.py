#!/usr/bin/env python3
"""Queue bounded OpenCode/DeepSeek worker jobs for later Codex review."""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

DEFAULT_JOB_ROOT = Path(".entroping") / "ai-jobs"
DEFAULT_ARTIFACT_ROOT = Path(".entroping") / "ai-reviews"
DEFAULT_TIMEOUT_SECONDS = 300.0
SCHEMA_VERSION = "entroping.ai-job.v1"
QUEUE_STATES = ("queued", "running", "completed", "failed")
SUCCESSFUL_WORKER_STATUSES = {"completed", "dry-run", "inconclusive", "patch-proposed"}
MODEL_PROFILES = {
    "flash-free": "opencode/deepseek-v4-flash-free",
    "flash": "deepseek/deepseek-v4-flash",
    "pro": "deepseek/deepseek-v4-pro",
}

Mode = Literal["review", "patch"]
QueueState = Literal["queued", "running", "completed", "failed"]


class AiJobError(ValueError):
    """Raised when an AI job queue input is invalid."""


def main() -> int:
    try:
        args = _parse_args()
        return _dispatch(args)
    except AiJobError as exc:
        print(f"ai_jobs: {exc}", file=sys.stderr)
        return 2


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Queue and run bounded OpenCode/DeepSeek worker jobs.",
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--job-root",
        type=Path,
        default=DEFAULT_JOB_ROOT,
        help="Queue root. Default: .entroping/ai-jobs",
    )
    common.add_argument("--json", action="store_true", help="Print machine-readable output.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    submit = subparsers.add_parser(
        "submit",
        parents=[common],
        help="Create a queued worker job.",
    )
    submit.add_argument("--mode", choices=("review", "patch"), required=True)
    submit.add_argument(
        "--profile",
        default="pro",
        help="Model profile: flash-free, flash, or pro. Default: pro.",
    )
    submit.add_argument("--model", help="Explicit OpenCode model id; overrides --profile.")
    submit.add_argument(
        "--file",
        dest="files",
        action="append",
        default=[],
        help="Repo-local file in scope; repeatable.",
    )
    submit.add_argument("--issue", help="Optional GitHub issue number or URL.")
    submit.add_argument("--instruction", help="Task-specific bounded worker instruction.")
    submit.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Worker timeout passed to scripts/opencode_worker.py.",
    )

    run_next = subparsers.add_parser(
        "run-next",
        parents=[common],
        help="Run the oldest queued job.",
    )
    run_next.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_ARTIFACT_ROOT,
        help="Worker artifact root. Default: .entroping/ai-reviews",
    )
    run_next.add_argument("--opencode-bin", type=Path, help="OpenCode executable path.")
    run_next.add_argument(
        "--worker-dry-run",
        action="store_true",
        help="Write worker prompt/metadata without invoking OpenCode.",
    )

    subparsers.add_parser("status", parents=[common], help="Summarize queue counts.")
    subparsers.add_parser(
        "collect",
        parents=[common],
        help="List completed jobs for Codex review.",
    )

    return parser.parse_args()


def _dispatch(args: argparse.Namespace) -> int:
    repo_root = _repo_root()
    job_root = _resolve_root(repo_root, args.job_root)

    if args.command == "submit":
        payload = _submit_job(args, repo_root, job_root)
        _print_payload(payload, json_output=args.json)
        return 0
    if args.command == "run-next":
        payload, exit_code = _run_next(args, repo_root, job_root)
        _print_payload(payload, json_output=args.json)
        return exit_code
    if args.command == "status":
        payload = _status(job_root)
        _print_payload(payload, json_output=args.json)
        return 0
    if args.command == "collect":
        payload = _collect(job_root)
        _print_payload(payload, json_output=args.json)
        return 0

    msg = f"unknown command: {args.command}"
    raise AiJobError(msg)


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
        raise AiJobError(msg) from exc
    return Path(completed.stdout.strip()).resolve()


def _resolve_root(repo_root: Path, raw_root: Path) -> Path:
    root = raw_root.expanduser()
    if not root.is_absolute():
        root = repo_root / root
    return root.resolve()


def _submit_job(args: argparse.Namespace, repo_root: Path, job_root: Path) -> dict[str, object]:
    files = _validate_files(repo_root, tuple(Path(path) for path in args.files))
    if args.timeout_seconds <= 0:
        msg = "--timeout-seconds must be greater than zero"
        raise AiJobError(msg)

    model, profile = _resolve_model(profile=str(args.profile), model=args.model)
    job_id = _new_job_id(mode=str(args.mode))
    job = {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "queue_status": "queued",
        "mode": str(args.mode),
        "profile": profile,
        "model": model,
        "issue": args.issue,
        "instruction": args.instruction,
        "files": files,
        "timeout_seconds": args.timeout_seconds,
        "attempts": 0,
        "created_at": _now(),
        "updated_at": _now(),
    }

    queued_dir = _state_dir(job_root, "queued")
    queued_dir.mkdir(parents=True, exist_ok=True)
    job_path = queued_dir / f"{job_id}.json"
    job_path.write_text(json.dumps(job, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"status": "queued", "job_id": job_id, "job_path": str(job_path)}


def _resolve_model(*, profile: str, model: str | None) -> tuple[str, str]:
    if model is not None:
        model_id = model.strip()
        if not model_id:
            msg = "--model must not be empty"
            raise AiJobError(msg)
        return model_id, "custom"
    if profile not in MODEL_PROFILES:
        known = ", ".join(sorted(MODEL_PROFILES))
        msg = f"unknown model profile: {profile!r}; expected one of: {known}"
        raise AiJobError(msg)
    return MODEL_PROFILES[profile], profile


def _validate_files(repo_root: Path, raw_files: tuple[Path, ...]) -> list[str]:
    if not raw_files:
        msg = "at least one --file is required"
        raise AiJobError(msg)

    validated: list[str] = []
    for raw_file in raw_files:
        path = raw_file.expanduser()
        if not path.is_absolute():
            path = repo_root / path
        resolved = path.resolve()
        if not resolved.exists():
            msg = f"input file does not exist: {raw_file}"
            raise AiJobError(msg)
        if not resolved.is_file() or resolved.is_symlink():
            msg = f"input path must be a regular non-symlink file: {raw_file}"
            raise AiJobError(msg)
        try:
            relative = resolved.relative_to(repo_root)
        except ValueError as exc:
            msg = f"input file must be inside repository: {raw_file}"
            raise AiJobError(msg) from exc
        validated.append(relative.as_posix())
    return list(dict.fromkeys(validated))


def _run_next(
    args: argparse.Namespace,
    repo_root: Path,
    job_root: Path,
) -> tuple[dict[str, object], int]:
    _ensure_queue_dirs(job_root)
    queued_jobs = sorted(_state_dir(job_root, "queued").glob("*.json"))
    if not queued_jobs:
        return {"status": "empty", "job_root": str(job_root)}, 0

    queued_path = queued_jobs[0]
    job = _read_job(queued_path)
    running_path = _state_dir(job_root, "running") / queued_path.name
    job["queue_status"] = "running"
    job["attempts"] = int(job.get("attempts", 0)) + 1
    job["started_at"] = _now()
    job["updated_at"] = _now()
    _write_job(running_path, job)
    queued_path.unlink()

    worker_payload, worker_process_returncode = _run_worker(args, repo_root, job)
    worker_status = str(worker_payload.get("status", "failed"))
    terminal_state: QueueState = (
        "completed" if worker_status in SUCCESSFUL_WORKER_STATUSES else "failed"
    )
    job["queue_status"] = terminal_state
    job["worker_status"] = worker_status
    job["worker_returncode"] = _int_value(worker_payload.get("returncode"), default=1)
    job["worker_process_returncode"] = worker_process_returncode
    job["artifact_dir"] = worker_payload.get("artifact_dir")
    job["completed_at"] = _now()
    job["updated_at"] = _now()

    terminal_path = _state_dir(job_root, terminal_state) / running_path.name
    _write_job(terminal_path, job)
    running_path.unlink()

    return (
        {
            "status": terminal_state,
            "job_id": job["job_id"],
            "job_path": str(terminal_path),
            "worker_status": worker_status,
            "artifact_dir": worker_payload.get("artifact_dir"),
        },
        0 if terminal_state == "completed" else 1,
    )


def _run_worker(
    args: argparse.Namespace,
    repo_root: Path,
    job: dict[str, object],
) -> tuple[dict[str, object], int]:
    artifact_root = _resolve_root(repo_root, args.artifact_root)
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
        str(job["timeout_seconds"]),
        "--json",
    ]
    for scoped_file in _string_list(job.get("files")):
        command.extend(["--file", scoped_file])
    if job.get("issue") is not None:
        command.extend(["--issue", str(job["issue"])])
    if job.get("instruction") is not None:
        command.extend(["--instruction", str(job["instruction"])])
    if args.opencode_bin is not None:
        command.extend(["--opencode-bin", str(args.opencode_bin)])
    if args.worker_dry_run:
        command.append("--dry-run")

    timeout_seconds = float(job["timeout_seconds"]) + 30.0
    try:
        completed = subprocess.run(  # nosec B603
            command,
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return {"status": "timed-out", "returncode": 124, "artifact_dir": None}, 124

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {
            "status": "failed",
            "returncode": completed.returncode,
            "artifact_dir": None,
        }
    if not isinstance(payload, dict):
        payload = {
            "status": "failed",
            "returncode": completed.returncode,
            "artifact_dir": None,
        }
    return payload, completed.returncode


def _status(job_root: Path) -> dict[str, object]:
    _ensure_queue_dirs(job_root)
    counts = {
        state: len(list(_state_dir(job_root, state).glob("*.json"))) for state in QUEUE_STATES
    }
    return {"status": "ok", "job_root": str(job_root), "counts": counts}


def _collect(job_root: Path) -> dict[str, object]:
    _ensure_queue_dirs(job_root)
    completed_jobs = []
    for path in sorted(_state_dir(job_root, "completed").glob("*.json")):
        job = _read_job(path)
        completed_jobs.append(
            {
                "job_id": job.get("job_id"),
                "mode": job.get("mode"),
                "model": job.get("model"),
                "issue": job.get("issue"),
                "worker_status": job.get("worker_status"),
                "artifact_dir": job.get("artifact_dir"),
            }
        )
    return {"status": "ok", "job_root": str(job_root), "completed_jobs": completed_jobs}


def _ensure_queue_dirs(job_root: Path) -> None:
    for state in QUEUE_STATES:
        _state_dir(job_root, state).mkdir(parents=True, exist_ok=True)


def _state_dir(job_root: Path, state: str) -> Path:
    return job_root / state


def _read_job(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"job file is not an object: {path}"
        raise AiJobError(msg)
    return payload


def _write_job(path: Path, job: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(job, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _new_job_id(*, mode: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid.uuid4().hex[:8]
    return f"{timestamp}-{mode}-{suffix}"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _int_value(value: object, *, default: int) -> int:
    if isinstance(value, int):
        return value
    return default


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _print_payload(payload: dict[str, object], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    status = payload.get("status", "ok")
    print(f"AI jobs status: {status}")
    if "job_path" in payload:
        print(f"Job path: {payload['job_path']}")
    if "counts" in payload:
        counts = payload["counts"]
        if isinstance(counts, dict):
            for state in QUEUE_STATES:
                print(f"{state}: {counts.get(state, 0)}")
    if "completed_jobs" in payload:
        completed_jobs = payload["completed_jobs"]
        if isinstance(completed_jobs, list):
            for job in completed_jobs:
                if isinstance(job, dict):
                    print(f"{job.get('job_id')}: {job.get('artifact_dir')}")


if __name__ == "__main__":
    raise SystemExit(main())
