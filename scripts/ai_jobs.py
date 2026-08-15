#!/usr/bin/env python3
"""Queue bounded OpenCode/DeepSeek worker jobs for later Codex review."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess  # nosec B404
import sys
import tempfile
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from datetime import timezone as datetime_timezone
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts import ai_job_fs  # noqa: E402
from scripts.ai_job_runtime_fs import QueueStateHandles, open_queue_state  # noqa: E402
from scripts.ai_job_worker_launch import (  # noqa: E402
    WorkerLaunchError,
    run_deepseek_worker,
    run_opencode_worker,
    validated_worker_artifact_dir,
)
from scripts.deepseek_worker_limits import MAX_TIMEOUT_SECONDS  # noqa: E402
from scripts.factory_control_plane_policy import (  # noqa: E402
    autonomy_tier_from_labels,
    protected_paths,
)

if TYPE_CHECKING:
    from scripts.bounded_process import BoundedProcessResult
    from scripts.factory_paid_dispatch_recovery import PaidDispatchRecovery
    from scripts.provider_capability_types import ProviderCapabilityRegistry

DEFAULT_JOB_ROOT = Path(".entroping") / "ai-jobs"
DEFAULT_ARTIFACT_ROOT = Path(".entroping") / "ai-reviews"
DEFAULT_FACTORY_COST_POLICY = Path(".entroping") / "factory-cost-policy.json"
DEFAULT_TIMEOUT_SECONDS = 300.0
STALE_RUNNING_GRACE_SECONDS = 60.0
SCHEMA_VERSION = "entroping.ai-job.v1"
CONTEXT_MANIFEST_COMMAND = "scripts/context_pack.sh --mode implementation --manifest"
TIER_A_MERGE_AUTHORITY = "Tier A autonomous after gates and green CI"
QUEUE_STATES = ("queued", "running", "completed", "failed")
SUCCESSFUL_WORKER_STATUSES = {"completed", "dry-run", "inconclusive", "patch-proposed"}
UTC_TZ = datetime_timezone.utc  # noqa: UP017 - factory scripts run under Python 3.9.
MAX_USAGE_VALUE = 9_223_372_036_854_775_807
TOKEN_USAGE_FIELDS = frozenset(
    {
        "cache_read_tokens",
        "cache_write_tokens",
        "completion_tokens",
        "input_tokens",
        "output_tokens",
        "prompt_cache_hit_tokens",
        "prompt_cache_miss_tokens",
        "prompt_tokens",
        "reasoning_tokens",
        "total_tokens",
    }
)
OPENCODE_USAGE_FIELDS = frozenset(
    {
        "cache_read_tokens",
        "cache_write_tokens",
        "cost_usd",
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
    }
)
OPENCODE_UNACCOUNTED_REASONS = frozenset(
    {
        "ambiguous_zero_cost",
        "conflicting_duplicate_usage",
        "dry_run",
        "error_event",
        "inconsistent_session",
        "invalid_receipt",
        "malformed_event",
        "malformed_usage",
        "missing_cost",
        "output_limit_exceeded",
        "process_failed",
        "secret_like_output",
        "text_limit_exceeded",
        "timed_out",
        "usage_absent",
    }
)

Mode = Literal["review", "patch"]
QueueState = Literal["queued", "running", "completed", "failed"]
WorkerEngine = Literal["opencode", "deepseek-api"]
AutonomyTier = Literal["tier_a", "tier_b", "tier_c"]


class AiJobError(ValueError):
    """Raised when an AI job queue input is invalid."""


class BoundedProcessError(RuntimeError):
    pass


def run_bounded_process(
    command: Sequence[str | Path],
    *,
    cwd: Path,
    timeout_seconds: float,
    max_output_bytes: int,
    env: Mapping[str, str] | None = None,
) -> BoundedProcessResult:
    from scripts.bounded_process import BoundedProcessError as ProcessError
    from scripts.bounded_process import run_bounded_process as run_process

    try:
        return run_process(
            command,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
            env=env,
        )
    except ProcessError as exc:
        raise BoundedProcessError(str(exc)) from exc


@cache
def _provider_registry() -> ProviderCapabilityRegistry:
    try:
        from scripts.provider_capability_registry import load_provider_registry
        from scripts.provider_capability_types import ProviderRegistryError
    except (ImportError, SyntaxError) as exc:
        raise AiJobError(
            "provider registry dependencies are unavailable; run with "
            "`uv run python scripts/ai_jobs.py ...`"
        ) from exc
    try:
        return load_provider_registry()
    except ProviderRegistryError as exc:
        raise AiJobError(f"provider capability registry is invalid ({exc})") from exc


def _queue_engines() -> tuple[WorkerEngine, ...]:
    from scripts.provider_capability_registry import supported_queue_engines

    return supported_queue_engines(_provider_registry())


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
            "Registered model profile from the canonical provider registry. "
            "Default: the registry's standard route, or its Tier A route for "
            "--autonomy-tier tier-a."
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
        "--work-purpose",
        choices=("experiment", "essential"),
        default="experiment",
        help="Budget purpose for quota/cash thresholds. Default: experiment.",
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
        "--allow-insecure-local-deepseek-base-url",
        action="store_true",
        help=argparse.SUPPRESS,
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
    run_next.add_argument(
        "--factory-cost-policy",
        type=Path,
        default=DEFAULT_FACTORY_COST_POLICY,
        help=("Local paid-dispatch policy. Default: .entroping/factory-cost-policy.json"),
    )
    run_next.add_argument(
        "--test-factory-provider-evidence",
        type=Path,
        help=argparse.SUPPRESS,
    )
    run_next.add_argument(
        "--test-factory-project-root",
        type=Path,
        help=argparse.SUPPRESS,
    )

    subparsers.add_parser("status", parents=[common], help="Summarize queue counts.")
    subparsers.add_parser(
        "collect",
        parents=[common],
        help="List completed jobs for Codex review.",
    )
    subparsers.add_parser(
        "audit-routing",
        parents=[common],
        help="Report invalid provider routes and Tier A cheap-routing drift.",
    )

    return parser.parse_args()


def _dispatch(args: argparse.Namespace) -> int:
    if args.command in ("submit", "run-next", "audit-routing"):
        _ = _provider_registry()
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
    if args.command == "audit-routing":
        payload = _audit_routing(job_root)
        _print_payload(payload, json_output=args.json)
        return 1 if payload["status"] == "violations" else 0

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
    source_revision = _current_revision(repo_root)
    file_sha256 = _selected_file_digests(repo_root, files)
    if not _valid_timeout_seconds(args.timeout_seconds):
        msg = "--timeout-seconds must be finite and at most 86400 seconds"
        raise AiJobError(msg)

    engine: WorkerEngine = args.engine
    autonomy_tier = _normalize_autonomy_tier(args.autonomy_tier)
    if autonomy_tier == "tier_a":
        _issue_number(args.issue, required=True)
        _enforce_tier_a_control_plane(files, repo_root=repo_root)
    profile = _default_profile(
        engine=engine,
        autonomy_tier=autonomy_tier,
        profile=args.profile,
    )
    model, resolved_profile = _resolve_model(
        engine=engine,
        profile=profile,
        model=args.model,
        autonomy_tier=autonomy_tier,
    )
    job_id = _new_job_id(mode=str(args.mode))
    worker_instruction = _worker_instruction(
        autonomy_tier=autonomy_tier,
        engine=engine,
        profile=resolved_profile,
        model=model,
        instruction=args.instruction,
    )
    job: dict[str, object] = {
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
        "source_revision": source_revision,
        "file_sha256": file_sha256,
        "timeout_seconds": args.timeout_seconds,
        "attempts": 0,
        "work_purpose": str(args.work_purpose),
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


def _resolve_model(
    *,
    engine: WorkerEngine,
    profile: str,
    model: str | None,
    autonomy_tier: AutonomyTier | None,
) -> tuple[str, str]:
    from scripts.provider_capability_registry import queue_profile_entries, resolve_queue_model
    from scripts.provider_capability_types import ProviderRegistryError

    if model is not None:
        model_id = model.strip()
        if not model_id:
            msg = "--model must not be empty"
            raise AiJobError(msg)
        try:
            route = resolve_queue_model(
                _provider_registry(),
                engine,
                model_id,
                autonomy_tier=autonomy_tier,
            )
        except ProviderRegistryError as exc:
            raise AiJobError(exc.detail) from exc
        return route.model.id, "custom"
    profiles = _model_profiles(engine)
    if profile not in profiles:
        known_for_engine = ", ".join(sorted(profiles))
        known_profiles = {
            known_profile
            for known_engine in _queue_engines()
            for known_profile, _model_id in queue_profile_entries(
                _provider_registry(),
                known_engine,
            )
        }
        if profile in known_profiles:
            msg = (
                f"model profile {profile!r} is not supported by engine {engine!r}; "
                f"expected one of: {known_for_engine}"
            )
            raise AiJobError(msg)
        known = ", ".join(sorted(known_profiles))
        msg = f"unknown model profile: {profile!r}; expected one of: {known}"
        raise AiJobError(msg)
    try:
        route = resolve_queue_model(
            _provider_registry(),
            engine,
            profiles[profile],
            autonomy_tier=autonomy_tier,
        )
    except ProviderRegistryError as exc:
        raise AiJobError(exc.detail) from exc
    return route.model.id, profile


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
    from scripts.provider_capability_registry import default_queue_route
    from scripts.provider_capability_types import ProviderRegistryError, QueueDefault

    if profile is not None:
        return profile
    selector: QueueDefault = "tier_a" if autonomy_tier == "tier_a" else "standard"
    try:
        return default_queue_route(_provider_registry(), engine, selector).queue.profile
    except ProviderRegistryError as exc:
        raise AiJobError(exc.detail) from exc


def _routing_metadata(
    *,
    autonomy_tier: AutonomyTier,
    engine: WorkerEngine,
    profile: str,
    model: str,
) -> dict[str, str | bool]:
    from scripts.provider_capability_registry import resolve_queue_model
    from scripts.provider_capability_types import ProviderRegistryError

    merge_authority = (
        TIER_A_MERGE_AUTHORITY if autonomy_tier == "tier_a" else "Codex/human required"
    )
    metadata: dict[str, str | bool] = {
        "context_manifest_command": CONTEXT_MANIFEST_COMMAND,
        "context_manifest_required": True,
        "merge_authority": merge_authority,
    }
    try:
        route = resolve_queue_model(
            _provider_registry(),
            engine,
            model,
            autonomy_tier=autonomy_tier,
        )
    except ProviderRegistryError as exc:
        raise AiJobError(exc.detail) from exc
    metadata.update(
        {
            "provider_lane": route.lane.id,
            "provider_host": route.lane.provider_host,
            "billing_path": route.billing_path,
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
    from scripts.provider_capability_registry import queue_profile_entries

    return dict(queue_profile_entries(_provider_registry(), engine))


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


def _current_revision(repo_root: Path) -> str:
    try:
        completed = subprocess.run(  # nosec B603
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        msg = f"current revision could not be resolved: {exc}"
        raise AiJobError(msg) from exc
    revision = completed.stdout.strip()
    if not revision:
        raise AiJobError("current revision could not be resolved")
    return revision


def _issue_number(value: object, *, required: bool) -> str | None:
    raw = str(value).strip() if value is not None else ""
    if not raw:
        if required:
            raise AiJobError("job must name a numeric GitHub issue")
        return None
    issue = raw.rstrip("/").rsplit("/", maxsplit=1)[-1]
    if not issue.isdigit():
        raise AiJobError("job must name a numeric GitHub issue")
    return issue


def _github_issue_snapshot(
    issue: str,
    *,
    required_autonomy_tier: AutonomyTier | None = None,
) -> dict[str, object]:
    try:
        completed = subprocess.run(  # nosec B603
            [
                "gh",
                "issue",
                "view",
                issue,
                "--repo",
                "sakibshuvo/Entroping",
                "--json",
                "state,labels",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        msg = f"GitHub issue revalidation failed for #{issue}: {exc}"
        raise AiJobError(msg) from exc
    if completed.returncode != 0:
        raise AiJobError(f"GitHub issue revalidation failed for #{issue}")
    try:
        snapshot = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        msg = f"GitHub issue revalidation returned malformed JSON for #{issue}"
        raise AiJobError(msg) from exc
    if not isinstance(snapshot, dict):
        raise AiJobError(f"GitHub issue revalidation returned invalid data for #{issue}")
    state = snapshot.get("state")
    ready = _labels_include_ready(snapshot.get("labels"))
    if state != "OPEN" or not ready:
        raise AiJobError(f"GitHub issue #{issue} must be OPEN with status:ready")
    snapshot_payload: dict[str, object] = {"state": state, "ready": ready}
    if required_autonomy_tier is not None:
        try:
            autonomy_tier = autonomy_tier_from_labels(snapshot.get("labels"))
        except ValueError as exc:
            raise AiJobError(f"GitHub issue #{issue} {exc}") from exc
        expected_tier = {
            "tier_a": "Tier A autonomous lane",
            "tier_b": "Tier B assisted lane",
            "tier_c": "Tier C restricted lane",
        }[required_autonomy_tier]
        if autonomy_tier != expected_tier:
            raise AiJobError(
                f"GitHub issue #{issue} autonomy label does not permit "
                f"{required_autonomy_tier.replace('_', '-')} dispatch"
            )
        snapshot_payload["autonomy_tier"] = required_autonomy_tier
    return snapshot_payload


def _labels_include_ready(value: object) -> bool:
    if not isinstance(value, list):
        return False
    return any(isinstance(label, dict) and label.get("name") == "status:ready" for label in value)


def _enforce_tier_a_control_plane(files: list[str], *, repo_root: Path) -> None:
    violations = protected_paths(files, repo_root=repo_root)
    if not violations:
        return
    details = ", ".join(f"{path} ({reason})" for path, reason in violations)
    raise AiJobError(
        "Tier A control-plane protection denied selected files: "
        f"{details}; route this work to Codex/human review"
    )


def _selected_file_digests(repo_root: Path, files: list[str]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for relative_path in files:
        path = repo_root / relative_path
        if _has_symlink_component(path) or not path.is_file():
            msg = f"selected file is missing or unsafe: {relative_path}"
            raise AiJobError(msg)
        digests[relative_path] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


def _job_structure_error(job: dict[str, object]) -> str | None:
    required_strings = ("job_id", "queue_status", "engine", "mode", "model")
    for field in required_strings:
        value = job.get(field)
        if not isinstance(value, str) or not value:
            return f"job field {field!r} must be a non-empty string"
    if job.get("schema_version") != SCHEMA_VERSION:
        return f"job schema_version must be {SCHEMA_VERSION!r}"
    if job.get("queue_status") not in QUEUE_STATES:
        return "job queue_status is not supported"
    if job.get("engine") not in ("opencode", "deepseek-api"):
        return "job engine is not supported"
    if job.get("mode") not in ("review", "patch"):
        return "job mode is not supported"
    files = job.get("files")
    if not isinstance(files, list) or not files:
        return "job files must be a non-empty list"
    if any(not isinstance(path, str) or not path for path in files):
        return "job files must contain non-empty strings"
    timeout = job.get("timeout_seconds")
    if not _valid_timeout_seconds(timeout):
        return "job timeout_seconds must be finite and at most 86400 seconds"
    attempts = job.get("attempts")
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
        return "job attempts must be a non-negative integer"
    autonomy_tier = job.get("autonomy_tier")
    if autonomy_tier is not None and autonomy_tier not in ("tier_a", "tier_b", "tier_c"):
        return "job autonomy_tier is not supported"
    work_purpose = job.get("work_purpose")
    if work_purpose is not None and work_purpose not in ("experiment", "essential"):
        return "job work_purpose is not supported"
    return None


def _run_next(
    args: argparse.Namespace,
    repo_root: Path,
    job_root: Path,
) -> tuple[dict[str, object], int]:
    try:
        with open_queue_state(job_root) as queue:
            return _run_next_pinned(args, repo_root, queue)
    except ai_job_fs.SafeStateError as exc:
        raise AiJobError(str(exc)) from exc


def _run_next_pinned(
    args: argparse.Namespace,
    repo_root: Path,
    queue: QueueStateHandles,
) -> tuple[dict[str, object], int]:
    recovered_running_jobs = _fail_recoverable_running_jobs(
        queue,
        args=args,
        repo_root=repo_root,
    )
    if recovered_running_jobs and not queue.names("queued"):
        return _running_recovery_result(recovered_running_jobs)
    routing_violations = _queued_routing_violations(queue)
    if routing_violations:
        return (
            {
                "status": "routing-violations-blocked",
                "job_root": str(queue.job_root),
                "violation_count": len(routing_violations),
                "violations": routing_violations,
            },
            1,
        )
    artifact_root = _resolve_root(
        repo_root,
        getattr(args, "artifact_root", DEFAULT_ARTIFACT_ROOT),
        "artifact root",
    )

    claimed_name = _claim_next_queued_job(queue)
    if claimed_name is None:
        if recovered_running_jobs:
            return _running_recovery_result(recovered_running_jobs)
        return {"status": "empty", "job_root": str(queue.job_root)}, 0
    running_path = queue.path("running", claimed_name)

    try:
        job = _decode_job_bytes(queue.read_bytes("running", claimed_name))
    except (
        AiJobError,
        ai_job_fs.SafeStateError,
        json.JSONDecodeError,
        OSError,
        UnicodeDecodeError,
    ) as exc:
        return _fail_corrupt_claimed_job(queue, claimed_name, exc)

    structure_error = _job_structure_error(job)
    if structure_error is not None:
        return _fail_corrupt_claimed_job(
            queue,
            claimed_name,
            AiJobError(structure_error),
        )
    dispatch_violation = _claimed_dispatch_violation(
        repo_root,
        running_path,
        job,
    )
    if dispatch_violation is not None:
        return _restore_dispatch_blocked_job(
            queue,
            claimed_name,
            dispatch_violation,
        )

    paid_violation = _prepare_paid_dispatch(args, repo_root, running_path, job)
    if paid_violation is not None:
        return _restore_dispatch_blocked_job(
            queue,
            claimed_name,
            paid_violation,
        )

    job["queue_status"] = "running"
    job["attempts"] = _int_value(job.get("attempts"), default=0) + 1
    job["started_at"] = _now()
    job["updated_at"] = _now()
    queue.write_json("running", claimed_name, job)

    if not bool(getattr(args, "worker_dry_run", False)) and not _paid_launch_authorized(
        args,
        repo_root,
        job,
    ):
        return _fail_running_job(
            queue,
            claimed_name,
            job,
            worker_status="paid-authorization-invalid",
        )

    worker_payload: dict[str, object]
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
    worker_usage: dict[str, object] | None
    usage_receipt: dict[str, object] | None = None
    if job.get("engine") == "opencode":
        usage_receipt, worker_usage = _opencode_usage_receipt_payload(
            worker_payload.get("usage_receipt"),
            expected_job_id=str(job["job_id"]),
            expected_model=str(job["model"]),
            artifact_dir=artifact_dir,
        )
        job["usage_receipt"] = usage_receipt
        if isinstance(job.get("dispatch_authorization_id"), str) and not isinstance(
            job.get("reservation_id"), str
        ):
            settlement_error = _settle_quota_dispatch(
                args,
                repo_root,
                job,
                worker_usage,
            )
            if (
                settlement_error is not None
                and artifact_validation_error is None
                and worker_status in SUCCESSFUL_WORKER_STATUSES
            ):
                worker_status = settlement_error
                job["worker_status"] = worker_status
    else:
        worker_usage = _usage_payload(worker_payload.get("usage"))
        usage_receipt = _deepseek_usage_receipt_payload(worker_payload.get("usage_receipt"))
        if usage_receipt is not None:
            job["usage_receipt"] = usage_receipt
        if isinstance(job.get("reservation_id"), str):
            settlement_error = _settle_paid_dispatch(
                args,
                repo_root,
                job,
                worker_payload,
                expected_run_id=(Path(artifact_dir).name if artifact_dir is not None else None),
            )
            if settlement_error is not None:
                worker_status = settlement_error
                job["worker_status"] = worker_status
    terminal_state: QueueState = (
        "completed" if worker_status in SUCCESSFUL_WORKER_STATUSES else "failed"
    )
    job["queue_status"] = terminal_state
    if worker_usage is not None:
        job["usage"] = worker_usage
    job["completed_at"] = _now()
    job["updated_at"] = _now()

    terminal_path = queue.path(terminal_state, claimed_name)
    queue.write_json(terminal_state, claimed_name, job)
    queue.unlink("running", claimed_name)

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
            **({"usage_receipt": usage_receipt} if usage_receipt is not None else {}),
        },
        0 if terminal_state == "completed" else 1,
    )


def _claim_next_queued_job(queue: QueueStateHandles) -> str | None:
    try:
        for name in queue.names("queued"):
            try:
                queue.move("queued", "running", name)
            except FileNotFoundError:
                continue
            except OSError as exc:
                msg = f"could not claim queued AI job {name}: {exc}"
                raise AiJobError(msg) from exc
            return name
        return None
    except ai_job_fs.SafeStateError as exc:
        raise AiJobError(str(exc)) from exc


def _claimed_dispatch_violation(
    repo_root: Path,
    running_path: Path,
    job: dict[str, object],
) -> dict[str, object] | None:
    routing_violation = _tier_a_routing_violation(job, running_path)
    if routing_violation is not None:
        return routing_violation
    if job.get("autonomy_tier") != "tier_a":
        return None

    source_revision = job.get("source_revision")
    expected_digests = job.get("file_sha256")
    if not isinstance(source_revision, str) or not isinstance(expected_digests, dict):
        return _dispatch_violation_payload(
            job,
            running_path,
            reason="legacy-revalidation-required",
        )
    try:
        current_revision = _current_revision(repo_root)
    except AiJobError:
        return _dispatch_violation_payload(
            job,
            running_path,
            reason="revision-revalidation-failed",
        )
    if source_revision != current_revision:
        return _dispatch_violation_payload(
            job,
            running_path,
            reason="stale-revision",
        )
    files = _string_list(job.get("files"))
    try:
        validated_files = _validate_files(
            repo_root,
            tuple(Path(path) for path in files),
        )
    except AiJobError:
        return _dispatch_violation_payload(
            job,
            running_path,
            reason="selected-files-unavailable",
        )
    if protected_paths(validated_files, repo_root=repo_root):
        return _dispatch_violation_payload(
            job,
            running_path,
            reason="protected-control-plane",
            suggested_action="route the issue to Codex/human review as Tier B or Tier C",
        )
    try:
        actual_digests = _selected_file_digests(repo_root, validated_files)
    except AiJobError:
        return _dispatch_violation_payload(
            job,
            running_path,
            reason="selected-files-unavailable",
        )
    if expected_digests != actual_digests:
        return _dispatch_violation_payload(
            job,
            running_path,
            reason="selected-files-changed",
        )
    try:
        issue = _issue_number(job.get("issue"), required=True)
        assert issue is not None
        _github_issue_snapshot(issue, required_autonomy_tier="tier_a")
    except AiJobError:
        return _dispatch_violation_payload(
            job,
            running_path,
            reason="issue-revalidation-failed",
        )
    return None


def _dispatch_violation_payload(
    job: dict[str, object],
    path: Path,
    *,
    reason: str,
    suggested_action: str | None = None,
    decision_code: str | None = None,
    decision_detail: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "job_id": job.get("job_id", path.stem),
        "job_path": str(path),
        "queue_status": "queued",
        "reason": reason,
        "suggested_action": suggested_action
        or (
            "use `uv run python scripts/ai_job_quarantine.py quarantine` and review "
            "the plan before --apply"
        ),
    }
    if decision_code is not None:
        payload["decision_code"] = decision_code
    if decision_detail is not None:
        payload["decision_detail"] = decision_detail
    return payload


def _prepare_paid_dispatch(
    args: argparse.Namespace,
    repo_root: Path,
    running_path: Path,
    job: dict[str, object],
) -> dict[str, object] | None:
    from scripts.factory_paid_dispatch_models import PaidDispatchError
    from scripts.factory_paid_dispatch_queue import (
        FactoryProviderEvidenceError,
        prepare_queue_paid_dispatch,
    )

    raw_policy = getattr(args, "factory_cost_policy", DEFAULT_FACTORY_COST_POLICY)
    policy_path = Path(raw_policy).expanduser()
    if not policy_path.is_absolute():
        policy_path = repo_root / policy_path
    try:
        worker_dry_run = bool(getattr(args, "worker_dry_run", False))
        test_evidence_path = getattr(args, "test_factory_provider_evidence", None)
        if test_evidence_path is not None and getattr(
            args,
            "test_factory_project_root",
            None,
        ) is None:
            raise PaidDispatchError(
                "test_root",
                "test provider evidence requires the loopback test project contract",
            )
        reservation = prepare_queue_paid_dispatch(
            _factory_budget_project_root(args, repo_root),
            job,
            registry=_provider_registry(),
            policy_path=policy_path,
            test_provider_evidence_path=test_evidence_path,
            occurred_at=datetime.now(UTC_TZ),
            worker_dry_run=worker_dry_run,
        )
    except (AiJobError, FactoryProviderEvidenceError, PaidDispatchError) as exc:
        code = (
            exc.code
            if isinstance(exc, (FactoryProviderEvidenceError, PaidDispatchError))
            else "path"
        )
        return _dispatch_violation_payload(
            job,
            running_path,
            reason="paid-cost-preflight-blocked",
            suggested_action=(
                "repair the local factory cost policy or provider evidence; "
                f"dispatch remained queued ({code})"
            ),
            decision_code=code,
            decision_detail=(
                exc.detail
                if isinstance(exc, (FactoryProviderEvidenceError, PaidDispatchError))
                else str(exc)
            ),
        )
    if reservation is not None:
        job.update(reservation.job_projection())
    return None


def _paid_launch_authorized(
    args: argparse.Namespace,
    repo_root: Path,
    job: dict[str, object],
) -> bool:
    from scripts.factory_paid_dispatch_queue import paid_launch_authorized

    return paid_launch_authorized(
        _factory_budget_project_root(args, repo_root),
        job,
        occurred_at=datetime.now(UTC_TZ),
    )


def _settle_quota_dispatch(
    args: argparse.Namespace,
    repo_root: Path,
    job: dict[str, object],
    usage: dict[str, object] | None,
) -> str | None:
    from scripts.factory_paid_dispatch_queue import settle_quota_dispatch

    return settle_quota_dispatch(
        _factory_budget_project_root(args, repo_root),
        job,
        usage,
        occurred_at=datetime.now(UTC_TZ),
    )


def _settle_paid_dispatch(
    args: argparse.Namespace,
    repo_root: Path,
    job: dict[str, object],
    worker_payload: dict[str, object],
    *,
    expected_run_id: str | None,
) -> str | None:
    from scripts.factory_paid_dispatch import PaidDispatchError, settle_paid_dispatch

    try:
        outcome = settle_paid_dispatch(
            _factory_budget_project_root(args, repo_root),
            job,
            worker_payload,
            expected_run_id=expected_run_id,
            occurred_at=datetime.now(UTC_TZ),
        )
    except PaidDispatchError:
        job["settlement_state"] = "unresolved"
        job["settlement_error"] = "paid cost settlement could not be recorded"
        return "paid-cost-settlement-failed"
    if outcome is None:
        job["settlement_state"] = "unresolved"
        return "paid-cost-settlement-missing"
    job["settlement_state"] = (
        "settled" if outcome.state in {"settled", "reconciled"} else "unresolved"
    )
    job["actual_microcents"] = outcome.actual_microcents
    if job["settlement_state"] == "unresolved":
        return "paid-cost-settlement-unresolved"
    return None


def _factory_budget_project_root(args: argparse.Namespace, repo_root: Path) -> Path:
    test_root = getattr(args, "test_factory_project_root", None)
    if test_root is None:
        return repo_root
    if not bool(getattr(args, "allow_insecure_local_deepseek_base_url", False)) or not str(
        getattr(args, "deepseek_api_key_env", "")
    ).startswith("ENTROPING_TEST_"):
        from scripts.factory_paid_dispatch import PaidDispatchError

        raise PaidDispatchError(
            "test_root",
            "test factory project root requires the loopback test provider contract",
        )
    return _resolve_root(repo_root, Path(test_root), "test factory project root")


def _restore_dispatch_blocked_job(
    queue: QueueStateHandles,
    claimed_name: str,
    violation: dict[str, object],
) -> tuple[dict[str, object], int]:
    queued_path = queue.path("queued", claimed_name)
    try:
        queue.move("running", "queued", claimed_name)
    except (ai_job_fs.SafeStateError, OSError) as exc:
        msg = f"could not restore dispatch-blocked AI job {claimed_name}: {exc}"
        raise AiJobError(msg) from exc
    violation["job_path"] = str(queued_path)
    return (
        {
            "status": "dispatch-preflight-blocked",
            "job_id": violation.get("job_id"),
            "job_path": str(queued_path),
            "violation": violation,
        },
        1,
    )


def _fail_recoverable_running_jobs(
    queue: QueueStateHandles,
    *,
    args: argparse.Namespace,
    repo_root: Path,
) -> list[tuple[dict[str, object], int]]:
    recovered: list[tuple[dict[str, object], int]] = []
    for name in queue.names("running"):
        try:
            job = _decode_job_bytes(queue.read_bytes("running", name))
        except (
            AiJobError,
            ai_job_fs.SafeStateError,
            json.JSONDecodeError,
            OSError,
            UnicodeDecodeError,
        ) as exc:
            recovered.append(_fail_corrupt_claimed_job(queue, name, exc))
            continue
        failure_status = _recoverable_running_job_status(job)
        if failure_status is None:
            continue
        paid_recovery = _recover_paid_running_job(args, repo_root, job)
        if paid_recovery == "error":
            job["settlement_state"] = "unknown"
            failure_status = "paid-cost-recovery-failed"
        elif paid_recovery is not None:
            job.update(paid_recovery.job_projection())
            if paid_recovery.queue_state == "completed":
                recovered.append(_complete_recovered_paid_job(queue, name, job))
                continue
            failure_status = "stale-paid-worker"
        recovered.append(_fail_running_job(queue, name, job, worker_status=failure_status))
    return recovered


def _recover_paid_running_job(
    args: argparse.Namespace,
    repo_root: Path,
    job: dict[str, object],
) -> PaidDispatchRecovery | Literal["error"] | None:
    from scripts.factory_paid_dispatch import PaidDispatchError, recover_paid_dispatch

    try:
        return recover_paid_dispatch(
            _factory_budget_project_root(args, repo_root),
            job,
            occurred_at=datetime.now(UTC_TZ),
        )
    except PaidDispatchError:
        return "error"


def _complete_recovered_paid_job(
    queue: QueueStateHandles,
    claimed_name: str,
    job: dict[str, object],
) -> tuple[dict[str, object], int]:
    completed_path = queue.path("completed", claimed_name)
    job["queue_status"] = "completed"
    job["worker_status"] = "paid-cost-already-settled"
    job["worker_returncode"] = _int_value(job.get("worker_returncode"), default=0)
    job["worker_process_returncode"] = _int_value(
        job.get("worker_process_returncode"),
        default=0,
    )
    job["completed_at"] = _now()
    job["updated_at"] = _now()
    queue.write_json("completed", claimed_name, job)
    queue.unlink("running", claimed_name)
    return (
        {
            "status": "completed",
            "job_id": job.get("job_id", Path(claimed_name).stem),
            "job_path": str(completed_path),
            "worker_status": job["worker_status"],
            "artifact_dir": job.get("artifact_dir"),
        },
        0,
    )


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
    raw_timeout = job.get("timeout_seconds")
    if not _valid_timeout_seconds(raw_timeout):
        return "invalid-running-job"
    timeout_seconds = float(cast("int | float", raw_timeout))
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
    queue: QueueStateHandles,
    claimed_name: str,
    job: dict[str, object],
    *,
    worker_status: str,
) -> tuple[dict[str, object], int]:
    failed_path = queue.path("failed", claimed_name)
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
    queue.write_json("failed", claimed_name, job)
    queue.unlink("running", claimed_name)
    return (
        {
            "status": "failed",
            "job_id": job.get("job_id", Path(claimed_name).stem),
            "job_path": str(failed_path),
            "worker_status": worker_status,
            "artifact_dir": job.get("artifact_dir"),
        },
        1,
    )


def _fail_corrupt_claimed_job(
    queue: QueueStateHandles,
    claimed_name: str,
    exc: Exception,
) -> tuple[dict[str, object], int]:
    failed_path = queue.path("failed", claimed_name)
    job: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "job_id": Path(claimed_name).stem,
        "queue_status": "failed",
        "worker_status": "corrupt-queued-job",
        "worker_returncode": 1,
        "worker_process_returncode": 1,
        "artifact_dir": None,
        "error": f"queued job artifact could not be read: {exc}",
        "completed_at": _now(),
        "updated_at": _now(),
    }
    queue.write_json("failed", claimed_name, job)
    queue.unlink("running", claimed_name)
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
    try:
        return validated_worker_artifact_dir(artifact_root, raw_value)
    except WorkerLaunchError as exc:
        raise AiJobError(str(exc)) from exc


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
    try:
        return run_opencode_worker(
            args,
            repo_root,
            job,
            artifact_root=artifact_root,
            timeout_seconds=job_timeout_seconds,
            scoped_files=_string_list(job.get("files")),
            run_process=run_bounded_process,
        )
    except BoundedProcessError:
        return {"status": "failed", "returncode": 1, "artifact_dir": None}, 1


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
    try:
        return run_deepseek_worker(
            args,
            repo_root,
            job,
            artifact_root=artifact_root,
            timeout_seconds=job_timeout_seconds,
            scoped_files=_string_list(job.get("files")),
            run_process=run_bounded_process,
        )
    except WorkerLaunchError as exc:
        raise AiJobError(str(exc)) from exc
    except BoundedProcessError:
        return {"status": "failed", "returncode": 1, "artifact_dir": None}, 1


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
        usage_receipt = _stored_usage_receipt_payload(job.get("usage_receipt"))
        if usage_receipt is not None:
            record["usage_receipt"] = usage_receipt
        completed_jobs.append(record)
    return {
        "status": "ok",
        "job_root": str(job_root),
        "summary": _completed_jobs_summary(completed_jobs),
        "completed_jobs": completed_jobs,
    }


def _audit_routing(job_root: Path) -> dict[str, object]:
    _ensure_queue_dirs(job_root)
    scanned_jobs = 0
    violations: list[dict[str, object]] = []
    for state in QUEUE_STATES:
        for path in sorted(_state_dir(job_root, state).glob("*.json")):
            job = _read_job(path)
            scanned_jobs += 1
            violation = _tier_a_routing_violation(job, path)
            if violation is not None:
                violations.append(violation)

    return {
        "status": "violations" if violations else "ok",
        "job_root": str(job_root),
        "scanned_jobs": scanned_jobs,
        "violation_count": len(violations),
        "violations": violations,
    }


def _queued_routing_violations(queue: QueueStateHandles) -> list[dict[str, object]]:
    violations: list[dict[str, object]] = []
    for name in queue.names("queued"):
        path = queue.path("queued", name)
        try:
            job = _decode_job_bytes(queue.read_bytes("queued", name))
        except ai_job_fs.SafeStateError:
            try:
                entry_still_exists = ai_job_fs.entry_exists(queue.directories["queued"], name)
            except ai_job_fs.SafeStateError:
                entry_still_exists = True
            if entry_still_exists:
                violations.append(_unsafe_queued_job_payload(path, reason="unsafe-job-path"))
            continue
        except (AiJobError, json.JSONDecodeError, OSError, UnicodeDecodeError):
            continue
        if _job_structure_error(job) is not None:
            continue
        violation = _tier_a_routing_violation(job, path)
        if violation is not None:
            violations.append(violation)
    return violations


def _unsafe_queued_job_payload(path: Path, *, reason: str) -> dict[str, object]:
    return {
        "job_id": path.stem,
        "job_path": str(path),
        "queue_status": "queued",
        "reason": reason,
        "suggested_action": (
            "use `uv run python scripts/ai_job_quarantine.py quarantine` and review "
            "the plan before --apply"
        ),
    }


def _tier_a_routing_violation(
    job: dict[str, object],
    path: Path,
) -> dict[str, object] | None:
    from scripts.provider_capability_registry import resolve_queue_model
    from scripts.provider_capability_types import ProviderRegistryError

    engine = _string_value(job.get("engine"), default="opencode")
    if engine not in ("opencode", "deepseek-api"):
        return _provider_route_violation_payload(
            job,
            path,
            "job uses an unsupported provider queue engine",
        )
    queue_engine = cast(WorkerEngine, engine)
    raw_autonomy_tier = job.get("autonomy_tier")
    if raw_autonomy_tier not in (None, "tier_a", "tier_b", "tier_c"):
        return _provider_route_violation_payload(
            job,
            path,
            "job autonomy_tier is not supported",
        )
    autonomy_tier: AutonomyTier | None = raw_autonomy_tier
    model = _string_value(job.get("model"), default="")
    try:
        route = resolve_queue_model(
            _provider_registry(),
            queue_engine,
            model,
            autonomy_tier=autonomy_tier,
        )
    except ProviderRegistryError as exc:
        return _provider_route_violation_payload(job, path, exc.detail)
    expected_metadata = {
        "provider_lane": route.lane.id,
        "provider_host": route.lane.provider_host,
        "billing_path": route.billing_path,
    }
    for field, expected in expected_metadata.items():
        actual = job.get(field)
        if actual is not None and actual != expected:
            return _provider_route_violation_payload(
                job,
                path,
                f"job {field} does not match the registered provider route",
            )
    if job.get("autonomy_tier") != "tier_a":
        return None

    profile = _string_value(job.get("profile"), default="")
    expected_profile, expected_model, suggested_action = _tier_a_expected_routing(engine)
    if expected_profile is None or expected_model is None:
        return _routing_violation_payload(
            job,
            path,
            expected_profile="known Tier A engine",
            expected_model="known Tier A model",
            suggested_action="inspect the job and requeue it with a supported Tier A worker engine",
        )
    if profile == expected_profile and model == expected_model:
        return None
    return _routing_violation_payload(
        job,
        path,
        expected_profile=expected_profile,
        expected_model=expected_model,
        suggested_action=suggested_action,
    )


def _provider_route_violation_payload(
    job: dict[str, object],
    path: Path,
    detail: str,
) -> dict[str, object]:
    return {
        "job_id": job.get("job_id", path.stem),
        "job_path": str(path),
        "queue_status": job.get("queue_status"),
        "reason": "provider-route-violation",
        "detail": detail,
        "issue": job.get("issue"),
        "engine": job.get("engine", "opencode"),
        "profile": job.get("profile"),
        "model": job.get("model"),
        "provider_lane": job.get("provider_lane"),
        "provider_host": job.get("provider_host"),
        "billing_path": job.get("billing_path"),
        "suggested_action": (
            "inspect the job and requeue it with a registered provider/model route"
        ),
    }


def _tier_a_expected_routing(engine: str) -> tuple[str | None, str | None, str]:
    from scripts.provider_capability_registry import default_queue_route

    if engine not in _queue_engines():
        return None, None, "inspect the job and requeue it with a supported Tier A worker engine"
    route = default_queue_route(_provider_registry(), engine, "tier_a")
    suggested_action = "requeue with --autonomy-tier tier-a and no --profile override"
    if engine != "opencode":
        suggested_action = (
            f"requeue with --engine {engine} --autonomy-tier tier-a and no --profile override"
        )
    return route.queue.profile, route.model.id, suggested_action


def _routing_violation_payload(
    job: dict[str, object],
    path: Path,
    *,
    expected_profile: str,
    expected_model: str,
    suggested_action: str,
) -> dict[str, object]:
    return {
        "job_id": job.get("job_id", path.stem),
        "job_path": str(path),
        "queue_status": job.get("queue_status"),
        "reason": "tier-a-routing-violation",
        "issue": job.get("issue"),
        "engine": job.get("engine", "opencode"),
        "profile": job.get("profile"),
        "model": job.get("model"),
        "provider_lane": job.get("provider_lane"),
        "provider_host": job.get("provider_host"),
        "billing_path": job.get("billing_path"),
        "expected_profile": expected_profile,
        "expected_model": expected_model,
        "suggested_action": suggested_action,
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
        if key in TOKEN_USAGE_FIELDS:
            if (
                isinstance(item, int)
                and not isinstance(item, bool)
                and 0 <= item <= MAX_USAGE_VALUE
            ):
                usage[key] = item
        elif key == "cost_usd" and (cost := _bounded_cost_value(item)) is not None:
            usage[key] = cost
    return usage or None


def _bounded_cost_value(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        cost = float(value)
    except (OverflowError, ValueError):
        return None
    if not math.isfinite(cost) or not 0 <= cost <= 1_000_000_000:
        return None
    return cost


def _opencode_usage_payload(value: object) -> dict[str, object] | None:
    usage = _usage_payload(value)
    if usage is None or frozenset(usage) != OPENCODE_USAGE_FIELDS:
        return None
    cost = usage["cost_usd"]
    if not isinstance(cost, float) or cost <= 0:
        return None
    return usage


def _opencode_usage_receipt_payload(
    value: object,
    *,
    expected_job_id: str,
    expected_model: str,
    artifact_dir: str | None,
) -> tuple[dict[str, object], dict[str, object] | None]:
    fallback = _invalid_opencode_usage_receipt(
        expected_job_id=expected_job_id,
        expected_model=expected_model,
        artifact_dir=artifact_dir,
    )
    if not isinstance(value, dict) or artifact_dir is None:
        return fallback, None
    status = value.get("accounting_status")
    reason = value.get("accounting_reason")
    run_id = value.get("run_id")
    session_fingerprint = value.get("session_fingerprint")
    unique_step_count = value.get("unique_step_count")
    if (
        value.get("schema_version") != "entroping.opencode-usage-receipt.v1"
        or value.get("job_id") != expected_job_id
        or value.get("requested_model") != expected_model
        or run_id != Path(artifact_dir).name
        or not _valid_receipt_identifier(run_id)
        or not isinstance(unique_step_count, int)
        or isinstance(unique_step_count, bool)
        or not 0 <= unique_step_count <= MAX_USAGE_VALUE
        or not _valid_session_fingerprint(session_fingerprint)
    ):
        return fallback, None
    if status == "accounted":
        usage = _opencode_usage_payload(value.get("usage"))
        if (
            reason != "complete"
            or session_fingerprint is None
            or unique_step_count <= 0
            or usage is None
        ):
            return fallback, None
    elif status == "unaccounted":
        if reason not in OPENCODE_UNACCOUNTED_REASONS or "usage" in value:
            return fallback, None
        usage = None
    else:
        return fallback, None
    return (
        {
            "accounting_reason": reason,
            "accounting_status": status,
            "job_id": expected_job_id,
            "requested_model": expected_model,
            "run_id": run_id,
            "schema_version": "entroping.opencode-usage-receipt.v1",
            "session_fingerprint": session_fingerprint,
            "unique_step_count": unique_step_count,
        },
        usage,
    )


def _invalid_opencode_usage_receipt(
    *,
    expected_job_id: str,
    expected_model: str,
    artifact_dir: str | None,
) -> dict[str, object]:
    return {
        "accounting_reason": "invalid_receipt",
        "accounting_status": "unaccounted",
        "job_id": expected_job_id,
        "requested_model": expected_model,
        "run_id": _safe_artifact_run_id(artifact_dir),
        "schema_version": "entroping.opencode-usage-receipt.v1",
        "session_fingerprint": None,
        "unique_step_count": 0,
    }


def _stored_usage_receipt_payload(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    status = value.get("accounting_status")
    reason = value.get("accounting_reason")
    schema_version = value.get("schema_version")
    if schema_version == "entroping.deepseek-usage-receipt.v1":
        if status not in {"accounted", "unaccounted"}:
            return None
        return {
            "accounting_status": status,
            "schema_version": schema_version,
        }
    if schema_version != "entroping.opencode-usage-receipt.v1":
        return None
    if status == "accounted":
        if reason != "complete":
            return None
    elif status == "unaccounted":
        if reason not in OPENCODE_UNACCOUNTED_REASONS:
            return None
    else:
        return None
    return {
        "accounting_reason": reason,
        "accounting_status": status,
        "schema_version": "entroping.opencode-usage-receipt.v1",
    }


def _deepseek_usage_receipt_payload(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return _stored_usage_receipt_payload(value)


def _valid_session_fingerprint(value: object) -> bool:
    if value is None:
        return True
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _valid_receipt_identifier(value: object) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 128
        and value[0].isalnum()
        and all(character.isalnum() or character in "._-" for character in value)
    )


def _safe_artifact_run_id(artifact_dir: str | None) -> str | None:
    if artifact_dir is None:
        return None
    run_id = Path(artifact_dir).name
    return run_id if _valid_receipt_identifier(run_id) else None


def _optional_string(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _ensure_queue_dirs(job_root: Path) -> None:
    try:
        ai_job_fs.ensure_job_root(job_root)
        for state in QUEUE_STATES:
            with ai_job_fs.open_state_directory(job_root, state):
                pass
    except ai_job_fs.SafeStateError as exc:
        raise AiJobError(str(exc)) from exc


def _state_dir(job_root: Path, state: str) -> Path:
    return job_root / state


def _read_job(path: Path) -> dict[str, object]:
    return _decode_job_bytes(path.read_bytes(), path=path)


def _decode_job_bytes(raw: bytes, *, path: Path | None = None) -> dict[str, object]:
    raw_payload: object = json.loads(raw.decode("utf-8"))
    if not isinstance(raw_payload, dict):
        msg = f"job file is not an object: {path}"
        raise AiJobError(msg)
    payload: dict[str, object] = {}
    for key, value in raw_payload.items():
        if not isinstance(key, str):
            msg = f"job file has a non-string key: {path}"
            raise AiJobError(msg)
        payload[key] = value
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
    if _valid_timeout_seconds(value):
        return float(cast("int | float", value))
    return default


def _valid_timeout_seconds(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and 0 < value <= MAX_TIMEOUT_SECONDS
    )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _string_value(value: object, *, default: str) -> str:
    if isinstance(value, str) and value:
        return value
    return default


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
    if "violations" in payload:
        violations = payload["violations"]
        if isinstance(violations, list):
            for violation in violations:
                if isinstance(violation, dict):
                    print(
                        f"{violation.get('job_id')}: {violation.get('model')} "
                        f"-> {violation.get('suggested_action')}"
                    )


if __name__ == "__main__":
    raise SystemExit(main())
