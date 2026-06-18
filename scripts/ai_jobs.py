#!/usr/bin/env python3
"""Queue bounded OpenCode/DeepSeek worker jobs for later Codex review."""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404
import sys
import tempfile
import uuid
from datetime import datetime, timedelta
from datetime import timezone as datetime_timezone
from pathlib import Path
from typing import Literal

DEFAULT_JOB_ROOT = Path(".entroping") / "ai-jobs"
DEFAULT_ARTIFACT_ROOT = Path(".entroping") / "ai-reviews"
DEFAULT_TIMEOUT_SECONDS = 300.0
STALE_RUNNING_GRACE_SECONDS = 60.0
SCHEMA_VERSION = "entroping.ai-job.v1"
CONTEXT_MANIFEST_COMMAND = "scripts/context_pack.sh --mode implementation --manifest"
TIER_A_MERGE_AUTHORITY = (
    "Tier A autonomous after gates and green CI"
)
QUEUE_STATES = ("queued", "running", "completed", "failed")
SUCCESSFUL_WORKER_STATUSES = {"completed", "dry-run", "inconclusive", "patch-proposed"}
MODEL_PROFILES = {
    "flash-free": "opencode/deepseek-v4-flash-free",
    "flash": "deepseek/deepseek-v4-flash",
    "pro": "deepseek/deepseek-v4-pro",
}
DEEPSEEK_API_MODEL_PROFILES = {
    "flash": "deepseek-v4-flash",
    "pro": "deepseek-v4-pro",
}
UTC_TZ = datetime_timezone.utc  # noqa: UP017 - factory scripts run under Python 3.9.

Mode = Literal["review", "patch"]
QueueState = Literal["queued", "running", "completed", "failed"]
WorkerEngine = Literal["opencode", "deepseek-api"]
AutonomyTier = Literal["tier_a", "tier_b", "tier_c"]


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
        "--engine",
        choices=("opencode", "deepseek-api"),
        default="opencode",
        help="Worker engine. Default: opencode.",
    )
    submit.add_argument(
        "--profile",
        help=(
            "Model profile: flash-free, flash, or pro. Default: pro, or "
            "flash-free for --autonomy-tier tier-a on OpenCode."
        ),
    )
    submit.add_argument("--model", help="Explicit OpenCode model id; overrides --profile.")
    submit.add_argument(
        "--autonomy-tier",
        choices=("tier-a", "tier-b", "tier-c"),
        help=(
            "Declared worker autonomy tier. tier-a defaults to cheap worker "
            "routing and a context-manifest-first worker instruction."
        ),
    )
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
        "--deepseek-base-url",
        default="https://api.deepseek.com",
        help="Direct DeepSeek OpenAI-compatible base URL.",
    )
    run_next.add_argument(
        "--deepseek-api-key-env",
        default="DEEPSEEK_API_KEY",
        help="Env var containing the direct DeepSeek API key.",
    )
    run_next.add_argument(
        "--deepseek-thinking",
        choices=("enabled", "disabled"),
        default="disabled",
        help=(
            "Direct DeepSeek thinking mode toggle. Default: disabled; use enabled "
            "only for deliberate deep-review jobs."
        ),
    )
    run_next.add_argument(
        "--deepseek-reasoning-effort",
        choices=("high", "max"),
        default="high",
        help="Direct DeepSeek reasoning effort.",
    )
    run_next.add_argument(
        "--worker-dry-run",
        action="store_true",
        help="Write worker prompt/metadata without invoking OpenCode.",
    )
    run_next.add_argument(
        "--record-factory-metrics",
        action="store_true",
        help="Pass opt-in factory metrics recording to the worker harness.",
    )
    run_next.add_argument(
        "--factory-role",
        help="Factory role tag passed through to the worker metrics recorder.",
    )
    run_next.add_argument(
        "--factory-metrics-ledger",
        type=Path,
        help="Factory metrics ledger path under .entroping/factory-metrics/.",
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
    job_root = _resolve_root(repo_root, args.job_root, "job root")

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


def _resolve_root(repo_root: Path, raw_root: Path, purpose: str = "root") -> Path:
    root = raw_root.expanduser()
    relative_root = not root.is_absolute()
    if relative_root:
        root = repo_root / root
    if _has_symlink_component(root):
        msg = f"{purpose} must not use symlink components"
        raise AiJobError(msg)
    resolved = root.resolve()
    if relative_root:
        try:
            resolved.relative_to(repo_root)
        except ValueError as exc:
            msg = f"{purpose} must stay inside repository"
            raise AiJobError(msg) from exc
    elif not (
        _path_is_relative_to(resolved, repo_root)
        or _path_is_relative_to(resolved, _system_temp_root())
    ):
        msg = f"{purpose} must stay inside repository or system temp directory"
        raise AiJobError(msg)
    return resolved


def _path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _system_temp_root() -> Path:
    return Path(tempfile.gettempdir()).resolve()


def _submit_job(args: argparse.Namespace, repo_root: Path, job_root: Path) -> dict[str, object]:
    files = _validate_files(repo_root, tuple(Path(path) for path in args.files))
    if args.timeout_seconds <= 0:
        msg = "--timeout-seconds must be greater than zero"
        raise AiJobError(msg)

    engine: WorkerEngine = args.engine
    autonomy_tier = _normalize_autonomy_tier(args.autonomy_tier)
    profile = _default_profile(
        engine=engine,
        autonomy_tier=autonomy_tier,
        profile=args.profile,
    )
    model, resolved_profile = _resolve_model(engine=engine, profile=profile, model=args.model)
    job_id = _new_job_id(mode=str(args.mode))
    worker_instruction = _worker_instruction(
        autonomy_tier=autonomy_tier,
        engine=engine,
        profile=resolved_profile,
        model=model,
        instruction=args.instruction,
    )
    job = {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "queue_status": "queued",
        "engine": engine,
        "mode": str(args.mode),
        "profile": resolved_profile,
        "model": model,
        "issue": args.issue,
        "instruction": args.instruction,
        "files": files,
        "timeout_seconds": args.timeout_seconds,
        "attempts": 0,
        "created_at": _now(),
        "updated_at": _now(),
    }
    if autonomy_tier is not None:
        job["autonomy_tier"] = autonomy_tier
        job.update(
            _routing_metadata(
                autonomy_tier=autonomy_tier,
                engine=engine,
                profile=resolved_profile,
                model=model,
            )
        )
    if worker_instruction is not None:
        job["worker_instruction"] = worker_instruction

    queued_dir = _state_dir(job_root, "queued")
    queued_dir.mkdir(parents=True, exist_ok=True)
    job_path = queued_dir / f"{job_id}.json"
    _write_job(job_path, job)
    return {"status": "queued", "job_id": job_id, "job_path": str(job_path)}


def _resolve_model(*, engine: WorkerEngine, profile: str, model: str | None) -> tuple[str, str]:
    if model is not None:
        model_id = model.strip()
        if not model_id:
            msg = "--model must not be empty"
            raise AiJobError(msg)
        return model_id, "custom"
    profiles = _model_profiles(engine)
    if profile not in profiles:
        known_for_engine = ", ".join(sorted(profiles))
        known_profiles = set(MODEL_PROFILES) | set(DEEPSEEK_API_MODEL_PROFILES)
        if profile in known_profiles:
            msg = (
                f"model profile {profile!r} is not supported by engine {engine!r}; "
                f"expected one of: {known_for_engine}"
            )
            raise AiJobError(msg)
        known = ", ".join(sorted(known_profiles))
        msg = f"unknown model profile: {profile!r}; expected one of: {known}"
        raise AiJobError(msg)
    return profiles[profile], profile


def _normalize_autonomy_tier(raw_tier: str | None) -> AutonomyTier | None:
    if raw_tier is None:
        return None
    known_tiers: dict[str, AutonomyTier] = {
        "tier-a": "tier_a",
        "tier-b": "tier_b",
        "tier-c": "tier_c",
    }
    normalized = known_tiers.get(raw_tier)
    if normalized is None:
        msg = f"unknown autonomy tier: {raw_tier!r}"
        raise AiJobError(msg)
    return normalized


def _default_profile(
    *,
    engine: WorkerEngine,
    autonomy_tier: AutonomyTier | None,
    profile: str | None,
) -> str:
    if profile is not None:
        return profile
    if autonomy_tier == "tier_a" and engine == "opencode":
        return "flash-free"
    if autonomy_tier == "tier_a" and engine == "deepseek-api":
        return "flash"
    return "pro"


def _routing_metadata(
    *,
    autonomy_tier: AutonomyTier,
    engine: WorkerEngine,
    profile: str,
    model: str,
) -> dict[str, str | bool]:
    merge_authority = (
        TIER_A_MERGE_AUTHORITY if autonomy_tier == "tier_a" else "Codex/human required"
    )
    metadata: dict[str, str | bool] = {
        "context_manifest_command": CONTEXT_MANIFEST_COMMAND,
        "context_manifest_required": True,
        "merge_authority": merge_authority,
    }
    if engine == "deepseek-api":
        metadata.update(
            {
                "provider_lane": "deepseek-api/direct",
                "provider_host": "repo-local DeepSeek worker",
                "billing_path": "paid direct DeepSeek API",
            }
        )
        return metadata

    metadata.update(
        {
            "provider_lane": "opencode/native-deepseek",
            "provider_host": "OpenCode",
            "billing_path": (
                "OpenCode free-model lane"
                if profile == "flash-free" or "flash-free" in model
                else "OpenCode configured provider"
            ),
        }
    )
    return metadata


def _worker_instruction(
    *,
    autonomy_tier: AutonomyTier | None,
    engine: WorkerEngine,
    profile: str,
    model: str,
    instruction: str | None,
) -> str | None:
    if autonomy_tier != "tier_a":
        return instruction

    metadata = _routing_metadata(
        autonomy_tier=autonomy_tier,
        engine=engine,
        profile=profile,
        model=model,
    )
    lines = [
        "Tier A cheap-worker context contract:",
        f"- Provider lane: {metadata['provider_lane']}",
        f"- Provider host: {metadata['provider_host']}",
        f"- Billing path: {metadata['billing_path']}",
        f"- Model id: {model}",
        f"- Start with `{CONTEXT_MANIFEST_COMMAND}`.",
        (
            "- Use the manifest inventory first, then request only the needed "
            "files/snippets before loading full file content."
        ),
        (
            "- Stop and escalate if the issue crosses into Tier B or Tier C, "
            "security-sensitive work, runtime behavior, provider boundaries, "
            "release behavior, secrets handling, raw traffic, or audit evidence."
        ),
        (
            "- Product boundary: entroping run remains deterministic, "
            "Hurl-backed, QAnstitution-governed, and provider-free."
        ),
        f"- Merge authority: {TIER_A_MERGE_AUTHORITY}.",
    ]
    if instruction is not None and instruction.strip():
        lines.extend(["", "Task-specific instruction:", instruction.strip()])
    return "\n".join(lines)


def _model_profiles(engine: WorkerEngine) -> dict[str, str]:
    if engine == "opencode":
        return MODEL_PROFILES
    return DEEPSEEK_API_MODEL_PROFILES


def _validate_files(repo_root: Path, raw_files: tuple[Path, ...]) -> list[str]:
    if not raw_files:
        msg = "at least one --file is required"
        raise AiJobError(msg)

    validated: list[str] = []
    for raw_file in raw_files:
        path = raw_file.expanduser()
        if not path.is_absolute():
            path = repo_root / path
        if _has_symlink_component(path):
            msg = f"input path must be a regular non-symlink file: {raw_file}"
            raise AiJobError(msg)
        resolved = path.resolve()
        if not resolved.exists():
            msg = f"input file does not exist: {raw_file}"
            raise AiJobError(msg)
        if not resolved.is_file():
            msg = f"input path must be a regular non-symlink file: {raw_file}"
            raise AiJobError(msg)
        try:
            relative = resolved.relative_to(repo_root)
        except ValueError as exc:
            msg = f"input file must be inside repository: {raw_file}"
            raise AiJobError(msg) from exc
        validated.append(relative.as_posix())
    return list(dict.fromkeys(validated))


def _has_symlink_component(path: Path) -> bool:
    return any(candidate.is_symlink() for candidate in (path, *path.parents))


def _run_next(
    args: argparse.Namespace,
    repo_root: Path,
    job_root: Path,
) -> tuple[dict[str, object], int]:
    _ensure_queue_dirs(job_root)
    recovered_running_jobs = _fail_recoverable_running_jobs(job_root)
    if recovered_running_jobs and not any(_state_dir(job_root, "queued").glob("*.json")):
        return _running_recovery_result(recovered_running_jobs)
    artifact_root = _resolve_root(
        repo_root,
        getattr(args, "artifact_root", DEFAULT_ARTIFACT_ROOT),
        "artifact root",
    )

    running_path = _claim_next_queued_job(job_root)
    if running_path is None:
        if recovered_running_jobs:
            return _running_recovery_result(recovered_running_jobs)
        return {"status": "empty", "job_root": str(job_root)}, 0

    try:
        job = _read_job(running_path)
    except (AiJobError, json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        return _fail_corrupt_claimed_job(job_root, running_path, exc)

    job["queue_status"] = "running"
    job["attempts"] = _int_value(job.get("attempts"), default=0) + 1
    job["started_at"] = _now()
    job["updated_at"] = _now()
    _write_job(running_path, job)

    try:
        worker_payload, worker_process_returncode = _run_worker(args, repo_root, job)
    except (AiJobError, OSError, subprocess.SubprocessError) as exc:
        worker_payload = {
            "status": "failed",
            "returncode": 1,
            "artifact_dir": None,
            "error": f"worker supervisor failed: {exc}",
        }
        worker_process_returncode = 1
    artifact_validation_error: str | None = None
    try:
        artifact_dir = _validated_worker_artifact_dir(
            artifact_root,
            worker_payload.get("artifact_dir"),
        )
    except AiJobError as exc:
        artifact_validation_error = str(exc)
        artifact_dir = None
    worker_status = (
        "invalid-worker-artifact-dir"
        if artifact_validation_error is not None
        else str(worker_payload.get("status", "failed"))
    )
    terminal_state: QueueState = (
        "completed" if worker_status in SUCCESSFUL_WORKER_STATUSES else "failed"
    )
    job["queue_status"] = terminal_state
    job["worker_status"] = worker_status
    job["worker_returncode"] = (
        1
        if artifact_validation_error is not None
        else _int_value(worker_payload.get("returncode"), default=1)
    )
    job["worker_process_returncode"] = (
        1 if artifact_validation_error is not None else worker_process_returncode
    )
    job["artifact_dir"] = artifact_dir
    if artifact_validation_error is not None:
        job["error"] = artifact_validation_error
    worker_usage = _usage_payload(worker_payload.get("usage"))
    if worker_usage is not None:
        job["usage"] = worker_usage
    job["completed_at"] = _now()
    job["updated_at"] = _now()

    terminal_path = _state_dir(job_root, terminal_state) / running_path.name
    _write_job(terminal_path, job)
    running_path.unlink(missing_ok=True)

    return (
        {
            "status": terminal_state,
            "job_id": job["job_id"],
            "job_path": str(terminal_path),
            "worker_status": worker_status,
            "artifact_dir": artifact_dir,
            **(
                {"running_jobs_failed_before_claim": len(recovered_running_jobs)}
                if recovered_running_jobs
                else {}
            ),
            **({"usage": worker_usage} if worker_usage is not None else {}),
        },
        0 if terminal_state == "completed" else 1,
    )


def _claim_next_queued_job(job_root: Path) -> Path | None:
    running_dir = _state_dir(job_root, "running")
    for queued_path in sorted(_state_dir(job_root, "queued").glob("*.json")):
        running_path = running_dir / queued_path.name
        try:
            queued_path.rename(running_path)
        except FileNotFoundError:
            continue
        except OSError as exc:
            msg = f"could not claim queued AI job {queued_path.name}: {exc}"
            raise AiJobError(msg) from exc
        return running_path
    return None


def _fail_recoverable_running_jobs(job_root: Path) -> list[tuple[dict[str, object], int]]:
    recovered: list[tuple[dict[str, object], int]] = []
    for running_path in sorted(_state_dir(job_root, "running").glob("*.json")):
        try:
            job = _read_job(running_path)
        except (AiJobError, json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            recovered.append(_fail_corrupt_claimed_job(job_root, running_path, exc))
            continue
        failure_status = _recoverable_running_job_status(job)
        if failure_status is None:
            continue
        recovered.append(
            _fail_running_job(job_root, running_path, job, worker_status=failure_status)
        )
    return recovered


def _running_recovery_result(
    recovered: list[tuple[dict[str, object], int]],
) -> tuple[dict[str, object], int]:
    payload, exit_code = recovered[0]
    payload = {
        **payload,
        "running_jobs_failed_before_claim": len(recovered),
    }
    return payload, exit_code


def _recoverable_running_job_status(job: dict[str, object]) -> str | None:
    started_at = _parse_job_timestamp(job.get("started_at")) or _parse_job_timestamp(
        job.get("updated_at")
    )
    if started_at is None:
        return "invalid-running-job"
    timeout_seconds = _float_value(job.get("timeout_seconds"), default=DEFAULT_TIMEOUT_SECONDS)
    stale_after = started_at + timedelta(seconds=timeout_seconds + STALE_RUNNING_GRACE_SECONDS)
    if datetime.now(UTC_TZ) > stale_after:
        return "stale-running-job"
    return None


def _parse_job_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC_TZ)
    return parsed.astimezone(UTC_TZ)


def _fail_running_job(
    job_root: Path,
    running_path: Path,
    job: dict[str, object],
    *,
    worker_status: str,
) -> tuple[dict[str, object], int]:
    failed_path = _state_dir(job_root, "failed") / running_path.name
    job["queue_status"] = "failed"
    job["worker_status"] = worker_status
    job["worker_returncode"] = _int_value(job.get("worker_returncode"), default=1)
    job["worker_process_returncode"] = _int_value(
        job.get("worker_process_returncode"),
        default=1,
    )
    job["artifact_dir"] = job.get("artifact_dir")
    job["completed_at"] = _now()
    job["updated_at"] = _now()
    _write_job(failed_path, job)
    running_path.unlink(missing_ok=True)
    return (
        {
            "status": "failed",
            "job_id": job.get("job_id", running_path.stem),
            "job_path": str(failed_path),
            "worker_status": worker_status,
            "artifact_dir": job.get("artifact_dir"),
        },
        1,
    )


def _fail_corrupt_claimed_job(
    job_root: Path,
    running_path: Path,
    exc: Exception,
) -> tuple[dict[str, object], int]:
    failed_path = _state_dir(job_root, "failed") / running_path.name
    job = {
        "schema_version": SCHEMA_VERSION,
        "job_id": running_path.stem,
        "queue_status": "failed",
        "worker_status": "corrupt-queued-job",
        "worker_returncode": 1,
        "worker_process_returncode": 1,
        "artifact_dir": None,
        "error": f"queued job artifact could not be read: {exc}",
        "completed_at": _now(),
        "updated_at": _now(),
    }
    _write_job(failed_path, job)
    running_path.unlink(missing_ok=True)
    return (
        {
            "status": "failed",
            "job_id": job["job_id"],
            "job_path": str(failed_path),
            "worker_status": job["worker_status"],
            "artifact_dir": None,
        },
        1,
    )


def _validated_worker_artifact_dir(artifact_root: Path, raw_value: object) -> str | None:
    artifact_dir = _optional_string(raw_value)
    if artifact_dir is None:
        return None
    path = Path(artifact_dir).expanduser()
    if not path.is_absolute():
        path = artifact_root / path
    if _has_symlink_component(path):
        msg = "worker artifact_dir must not use symlink components"
        raise AiJobError(msg)
    resolved = path.resolve()
    try:
        resolved.relative_to(artifact_root)
    except ValueError as exc:
        msg = "worker artifact_dir must stay under artifact root"
        raise AiJobError(msg) from exc
    return str(resolved)


def _run_worker(
    args: argparse.Namespace,
    repo_root: Path,
    job: dict[str, object],
) -> tuple[dict[str, object], int]:
    engine = str(job.get("engine", "opencode"))
    if engine == "deepseek-api":
        return _run_deepseek_worker(args, repo_root, job)
    if engine != "opencode":
        return {"status": "failed", "returncode": 1, "artifact_dir": None}, 1

    artifact_root = _resolve_root(repo_root, args.artifact_root, "artifact root")
    job_timeout_seconds = _float_value(
        job.get("timeout_seconds"),
        default=DEFAULT_TIMEOUT_SECONDS,
    )
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
        str(job_timeout_seconds),
        "--json",
    ]
    for scoped_file in _string_list(job.get("files")):
        command.extend(["--file", scoped_file])
    if job.get("issue") is not None:
        command.extend(["--issue", str(job["issue"])])
    worker_instruction = _effective_worker_instruction(job)
    if worker_instruction is not None:
        command.extend(["--instruction", worker_instruction])
    if args.opencode_bin is not None:
        command.extend(["--opencode-bin", str(args.opencode_bin)])
    if args.worker_dry_run:
        command.append("--dry-run")
    _extend_factory_metrics_args(command, args)

    timeout_seconds = job_timeout_seconds + 30.0
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


def _run_deepseek_worker(
    args: argparse.Namespace,
    repo_root: Path,
    job: dict[str, object],
) -> tuple[dict[str, object], int]:
    artifact_root = _resolve_root(repo_root, args.artifact_root, "artifact root")
    job_timeout_seconds = _float_value(
        job.get("timeout_seconds"),
        default=DEFAULT_TIMEOUT_SECONDS,
    )
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
        str(job_timeout_seconds),
        "--base-url",
        str(args.deepseek_base_url),
        "--api-key-env",
        str(args.deepseek_api_key_env),
        "--thinking",
        str(args.deepseek_thinking),
        "--json",
    ]
    if args.deepseek_thinking == "enabled":
        command.extend(["--reasoning-effort", str(args.deepseek_reasoning_effort)])
    for scoped_file in _string_list(job.get("files")):
        command.extend(["--file", scoped_file])
    if job.get("issue") is not None:
        command.extend(["--issue", str(job["issue"])])
    worker_instruction = _effective_worker_instruction(job)
    if worker_instruction is not None:
        command.extend(["--instruction", worker_instruction])
    if args.worker_dry_run:
        command.append("--dry-run")
    _extend_factory_metrics_args(command, args)

    timeout_seconds = job_timeout_seconds + 30.0
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


def _effective_worker_instruction(job: dict[str, object]) -> str | None:
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


def _status(job_root: Path) -> dict[str, object]:
    _ensure_queue_dirs(job_root)
    counts = {
        state: len(list(_state_dir(job_root, state).glob("*.json"))) for state in QUEUE_STATES
    }
    return {"status": "ok", "job_root": str(job_root), "counts": counts}


def _collect(job_root: Path) -> dict[str, object]:
    _ensure_queue_dirs(job_root)
    completed_jobs: list[dict[str, object]] = []
    for path in sorted(_state_dir(job_root, "completed").glob("*.json")):
        job = _read_job(path)
        record = {
            "job_id": job.get("job_id"),
            "engine": job.get("engine", "opencode"),
            "profile": job.get("profile"),
            "mode": job.get("mode"),
            "model": job.get("model"),
            "issue": job.get("issue"),
            "worker_status": job.get("worker_status"),
            "artifact_dir": job.get("artifact_dir"),
        }
        if isinstance(job.get("artifact_dir"), str):
            record["metadata_path"] = str(Path(str(job["artifact_dir"])) / "metadata.json")
        usage = _usage_payload(job.get("usage"))
        if usage is not None:
            record["usage"] = usage
        completed_jobs.append(record)
    return {
        "status": "ok",
        "job_root": str(job_root),
        "summary": _completed_jobs_summary(completed_jobs),
        "completed_jobs": completed_jobs,
    }


def _completed_jobs_summary(completed_jobs: list[dict[str, object]]) -> dict[str, object]:
    usage_records = [
        usage for job in completed_jobs if (usage := _usage_payload(job.get("usage"))) is not None
    ]
    return {
        "total_completed": len(completed_jobs),
        "by_engine": _count_field(completed_jobs, "engine"),
        "by_profile": _count_field(completed_jobs, "profile"),
        "by_mode": _count_field(completed_jobs, "mode"),
        "by_worker_status": _count_field(completed_jobs, "worker_status"),
        "by_model": _count_field(completed_jobs, "model"),
        "usage": {
            "known_jobs": len(usage_records),
            "unknown_jobs": len(completed_jobs) - len(usage_records),
            "totals": _usage_totals(usage_records),
        },
    }


def _count_field(records: list[dict[str, object]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        raw_value = record.get(field)
        value = raw_value if isinstance(raw_value, str) and raw_value else "unknown"
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _usage_totals(usage_records: list[dict[str, object]]) -> dict[str, int | float]:
    totals: dict[str, int | float] = {}
    for usage in usage_records:
        for key, value in usage.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            totals[key] = totals.get(key, 0) + value
    return dict(sorted(totals.items()))


def _usage_payload(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    usage: dict[str, object] = {}
    for key, item in value.items():
        if (
            isinstance(key, str)
            and not isinstance(item, bool)
            and isinstance(item, (int, float))
        ):
            usage[key] = item
    return usage or None


def _optional_string(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


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
    payload = json.dumps(job, indent=2, sort_keys=True) + "\n"
    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary_path.write_text(payload, encoding="utf-8")
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _new_job_id(*, mode: str) -> str:
    timestamp = datetime.now(UTC_TZ).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid.uuid4().hex[:8]
    return f"{timestamp}-{mode}-{suffix}"


def _now() -> str:
    return datetime.now(UTC_TZ).isoformat()


def _int_value(value: object, *, default: int) -> int:
    if isinstance(value, int):
        return value
    return default


def _float_value(value: object, *, default: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
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
