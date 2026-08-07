#!/usr/bin/env python3
"""Run bounded OpenCode workers and capture review or patch artifacts."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess  # nosec B404
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone as datetime_timezone
from pathlib import Path
from typing import Literal

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.ai_worker_file_safety import (  # noqa: E402
    secret_like_content_reason,
    sensitive_selected_path_reason,
)
from scripts.bounded_process import BoundedProcessError, run_bounded_process  # noqa: E402
from scripts.opencode_event_stream import (  # noqa: E402
    OpenCodeEventStream,
    OpenCodeStreamSummary,
    OpenCodeUsageReceipt,
    ReceiptReason,
    build_usage_receipt,
)
from scripts.opencode_unattended_preflight import (  # noqa: E402
    preflight_unattended_profile,
    verify_execution_binding,
)
from scripts.opencode_unattended_profile import (  # noqa: E402
    UnattendedAttestation,
    UnattendedProfileError,
    build_unattended_profile,
)
from scripts.provider_capability_registry import (  # noqa: E402
    load_provider_registry,
    resolve_queue_model,
)
from scripts.provider_capability_types import ProviderRegistryError  # noqa: E402
from scripts.worker_output import (  # noqa: E402
    atomic_write_text,
    bounded_persisted_text,
)

DEFAULT_MODEL = "deepseek/deepseek-v4-pro"
DEFAULT_ARTIFACT_ROOT = Path(".entroping") / "ai-reviews"
DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_MAX_FILE_BYTES = 64_000
DEFAULT_MAX_OUTPUT_BYTES = 262_144
CAPABILITY_CONTEXT_VERSION = "entroping.opencode-host-capability-context.v1"
UTC_TZ = datetime_timezone.utc  # noqa: UP017 - factory scripts run under Python 3.9.
Mode = Literal["review", "patch"]
Status = Literal["completed", "dry-run", "failed", "inconclusive", "patch-proposed", "timed-out"]


@dataclass(frozen=True)
class PreparedSelectedFile:
    """Selected file content that passed preflight safety checks."""

    source_path: Path
    relative_path: str
    content: str
    size_bytes: int


@dataclass(frozen=True)
class WorkerConfig:
    """Validated OpenCode worker configuration."""

    mode: Mode
    model: str
    repo_root: Path
    files: tuple[PreparedSelectedFile, ...]
    artifact_root: Path
    opencode_bin: Path
    timeout_seconds: float
    max_file_bytes: int
    max_output_bytes: int
    issue: str | None
    job_id: str | None
    instruction: str | None
    dry_run: bool
    json_output: bool
    record_factory_metrics: bool
    factory_role: str | None
    factory_metrics_ledger: Path | None


@dataclass(frozen=True)
class WorkerResult:
    """OpenCode worker execution result."""

    status: Status
    artifact_dir: Path
    returncode: int
    stdout: str
    stderr: str
    usage_receipt: OpenCodeUsageReceipt


def main() -> int:
    try:
        config = _parse_args()
        result = run_worker(config)
    except WorkerInputError as exc:
        print(f"opencode_worker: {exc}", file=sys.stderr)
        return 2

    payload: dict[str, object] = {
        "status": result.status,
        "artifact_dir": str(result.artifact_dir),
        "returncode": result.returncode,
        "usage_receipt": result.usage_receipt.to_payload(),
    }
    if result.usage_receipt.usage is not None:
        payload["usage"] = result.usage_receipt.usage.to_payload()
    if config.json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"OpenCode worker status: {result.status}")
        print(f"Artifact directory: {result.artifact_dir}")

    if result.status == "timed-out":
        return 124
    if result.status == "failed":
        return 1
    return 0


class WorkerInputError(ValueError):
    """Raised when worker inputs are unsafe or incomplete."""


def run_worker(config: WorkerConfig) -> WorkerResult:
    """Run OpenCode in a bounded subprocess and write local artifacts."""

    started_at = time.monotonic()
    artifact_dir = _new_artifact_dir(config.artifact_root, config.mode)
    artifact_dir.mkdir(parents=True, exist_ok=False)

    snapshot_paths = _write_selected_file_snapshots(config, artifact_dir)
    prompt = _build_prompt(config, snapshot_paths)
    if config.dry_run:
        command = _opencode_command(config, prompt, snapshot_paths)
        receipt = build_usage_receipt(
            None,
            job_id=config.job_id,
            requested_model=config.model,
            run_id=artifact_dir.name,
            override_reason="dry_run",
        )
        result = WorkerResult(
            status="dry-run",
            artifact_dir=artifact_dir,
            returncode=0,
            stdout="",
            stderr="",
            usage_receipt=receipt,
        )
        _write_usage_receipt(result)
        _write_metadata(config, result, command, None)
        _record_factory_metrics(
            config,
            result,
            duration_seconds=time.monotonic() - started_at,
        )
        return result

    with tempfile.TemporaryDirectory(prefix="entroping-opencode-unattended-") as root:
        isolated_root = Path(root).resolve()
        if _path_is_relative_to(isolated_root, config.repo_root):
            raise WorkerInputError("OpenCode isolated root must stay outside repository")
        try:
            profile = build_unattended_profile(
                mode=config.mode,
                model=config.model,
                executable=config.opencode_bin,
                isolated_root=isolated_root,
                snapshot_paths=snapshot_paths,
                inherited_environment=os.environ,
            )
            attestation = preflight_unattended_profile(profile)
            verify_execution_binding(attestation)
        except UnattendedProfileError as exc:
            raise WorkerInputError(str(exc)) from exc
        command = profile.command(prompt)
        return _run_attested_worker(
            config,
            artifact_dir,
            command,
            attestation,
            started_at=started_at,
        )


def _run_attested_worker(
    config: WorkerConfig,
    artifact_dir: Path,
    command: list[str],
    attestation: UnattendedAttestation,
    *,
    started_at: float,
) -> WorkerResult:
    event_stream = OpenCodeEventStream(max_text_bytes=config.max_output_bytes)
    try:
        verify_execution_binding(attestation)
        completed = run_bounded_process(
            command,
            cwd=attestation.profile.worker_directory,
            env=attestation.profile.environment,
            timeout_seconds=config.timeout_seconds,
            max_output_bytes=config.max_output_bytes,
            stdout_consumer=event_stream.feed,
            capture_stdout=False,
        )
    except BoundedProcessError as exc:
        raise WorkerInputError("OpenCode bounded subprocess failed") from exc
    stream_summary = event_stream.finish()
    if completed.timed_out:
        receipt = _usage_receipt(config, artifact_dir, stream_summary, "timed_out")
        result = WorkerResult(
            status="timed-out",
            artifact_dir=artifact_dir,
            returncode=124,
            stdout=stream_summary.output_text,
            stderr=f"OpenCode worker timed out after {config.timeout_seconds} seconds.",
            usage_receipt=receipt,
        )
    elif completed.output_limit_exceeded:
        receipt = _usage_receipt(
            config,
            artifact_dir,
            stream_summary,
            "output_limit_exceeded",
        )
        result = WorkerResult(
            status="failed",
            artifact_dir=artifact_dir,
            returncode=completed.returncode,
            stdout=stream_summary.output_text,
            stderr=(
                f"OpenCode worker exceeded the {config.max_output_bytes}-byte output limit."
            ),
            usage_receipt=receipt,
        )
    else:
        receipt_reason: ReceiptReason | None = (
            "process_failed" if completed.returncode != 0 else None
        )
        result = WorkerResult(
            status=_classify_stream_status(
                config.mode,
                completed.returncode,
                stream_summary,
            ),
            artifact_dir=artifact_dir,
            returncode=completed.returncode,
            stdout=stream_summary.output_text,
            stderr=_sanitized_child_stderr(completed.stderr),
            usage_receipt=_usage_receipt(
                config,
                artifact_dir,
                stream_summary,
                receipt_reason,
            ),
        )
    result = _withhold_secret_like_worker_output(result)
    _write_execution_artifacts(config, result, command, attestation)
    _record_factory_metrics(
        config,
        result,
        duration_seconds=time.monotonic() - started_at,
    )
    return result


def _parse_args() -> WorkerConfig:
    parser = argparse.ArgumentParser(
        description=(
            "Run a bounded OpenCode/DeepSeek review or patch proposal and save artifacts."
        )
    )
    parser.add_argument("--mode", choices=("review", "patch"), required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenCode model id.")
    parser.add_argument(
        "--file",
        dest="files",
        action="append",
        default=[],
        help="Repo-local file to include in the worker scope; repeatable.",
    )
    parser.add_argument("--issue", help="Optional GitHub issue number or URL.")
    parser.add_argument(
        "--job-id",
        help="Optional sanitized queue job id for usage receipt correlation.",
    )
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
        "--opencode-bin",
        type=Path,
        default=None,
        help="OpenCode executable path. Default: first opencode on PATH.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Subprocess timeout in seconds.",
    )
    parser.add_argument(
        "--max-file-bytes",
        type=int,
        default=DEFAULT_MAX_FILE_BYTES,
        help=(
            "Maximum bytes per selected file to preflight. "
            f"Default: {DEFAULT_MAX_FILE_BYTES}."
        ),
    )
    parser.add_argument(
        "--max-output-bytes",
        type=int,
        default=DEFAULT_MAX_OUTPUT_BYTES,
        help=f"Maximum captured bytes per worker stream. Default: {DEFAULT_MAX_OUTPUT_BYTES}.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write prompt and metadata without invoking OpenCode.",
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
    if args.timeout_seconds <= 0:
        msg = "--timeout-seconds must be greater than zero"
        raise WorkerInputError(msg)
    if args.max_file_bytes <= 0:
        msg = "--max-file-bytes must be greater than zero"
        raise WorkerInputError(msg)
    if args.max_output_bytes <= 0:
        msg = "--max-output-bytes must be greater than zero"
        raise WorkerInputError(msg)
    if args.job_id is not None and re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", args.job_id
    ) is None:
        msg = "--job-id must be a safe 1-128 character identifier"
        raise WorkerInputError(msg)
    max_file_bytes = int(args.max_file_bytes)
    files = _validate_files(
        repo_root,
        tuple(Path(path) for path in args.files),
        max_file_bytes=max_file_bytes,
    )
    if not files:
        msg = "at least one --file is required"
        raise WorkerInputError(msg)

    try:
        resolve_queue_model(load_provider_registry(), "opencode", args.model)
    except ProviderRegistryError as exc:
        raise WorkerInputError(
            f"--model must name an active registered OpenCode queue model ({exc})"
        ) from exc

    opencode_bin = _resolve_opencode_bin(args.opencode_bin, required=not args.dry_run)
    mode: Mode = args.mode
    return WorkerConfig(
        mode=mode,
        model=args.model,
        repo_root=repo_root,
        files=files,
        artifact_root=_resolve_artifact_root(repo_root, args.artifact_root),
        opencode_bin=opencode_bin,
        timeout_seconds=args.timeout_seconds,
        max_file_bytes=max_file_bytes,
        max_output_bytes=int(args.max_output_bytes),
        issue=args.issue,
        job_id=args.job_id,
        instruction=args.instruction,
        dry_run=args.dry_run,
        json_output=args.json,
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
        raise WorkerInputError(msg) from exc
    return Path(completed.stdout.strip()).resolve()


def _resolve_artifact_root(repo_root: Path, raw_root: Path) -> Path:
    artifact_root = raw_root.expanduser()
    relative_root = not artifact_root.is_absolute()
    if relative_root:
        artifact_root = repo_root / artifact_root
    if _has_symlink_component(artifact_root):
        msg = "artifact root must not use symlink components"
        raise WorkerInputError(msg)
    resolved = artifact_root.resolve()
    if relative_root:
        try:
            resolved.relative_to(repo_root)
        except ValueError as exc:
            msg = "artifact root must stay inside repository"
            raise WorkerInputError(msg) from exc
    elif not (
        _path_is_relative_to(resolved, repo_root)
        or _path_is_relative_to(resolved, _system_temp_root())
    ):
        msg = "artifact root must stay inside repository or system temp directory"
        raise WorkerInputError(msg)
    return resolved


def _path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _system_temp_root() -> Path:
    return Path(tempfile.gettempdir()).resolve()


def _has_symlink_component(path: Path) -> bool:
    return any(candidate.is_symlink() for candidate in (path, *path.parents))


def _validate_files(
    repo_root: Path,
    raw_files: tuple[Path, ...],
    *,
    max_file_bytes: int,
) -> tuple[PreparedSelectedFile, ...]:
    validated: dict[Path, PreparedSelectedFile] = {}
    for raw_file in raw_files:
        path = raw_file.expanduser()
        if not path.is_absolute():
            path = repo_root / path
        if _has_symlink_component(path):
            msg = f"input path must be a regular non-symlink file: {raw_file}"
            raise WorkerInputError(msg)
        resolved = path.resolve()
        if not resolved.exists():
            msg = f"input file does not exist: {raw_file}"
            raise WorkerInputError(msg)
        if not resolved.is_file():
            msg = f"input path must be a regular non-symlink file: {raw_file}"
            raise WorkerInputError(msg)
        try:
            relative_path = resolved.relative_to(repo_root).as_posix()
        except ValueError as exc:
            msg = f"input file must be inside repository: {raw_file}"
            raise WorkerInputError(msg) from exc
        sensitive_reason = sensitive_selected_path_reason(relative_path)
        if sensitive_reason is not None:
            msg = (
                "refusing to send selected file to OpenCode: "
                f"{relative_path} {sensitive_reason}"
            )
            raise WorkerInputError(msg)
        try:
            size = resolved.stat().st_size
        except OSError as exc:
            msg = f"could not stat selected file: {relative_path}"
            raise WorkerInputError(msg) from exc
        if size > max_file_bytes:
            msg = (
                "refusing to send selected file to OpenCode: "
                f"{relative_path} is {size} bytes and exceeds --max-file-bytes "
                f"({max_file_bytes})"
            )
            raise WorkerInputError(msg)
        try:
            raw_content = resolved.read_bytes()
        except OSError as exc:
            msg = f"could not read selected file: {relative_path}"
            raise WorkerInputError(msg) from exc
        if b"\x00" in raw_content:
            msg = (
                "refusing to send selected file to OpenCode: "
                f"{relative_path} contains binary content"
            )
            raise WorkerInputError(msg)
        try:
            content = raw_content.decode("utf-8")
        except UnicodeDecodeError as exc:
            msg = (
                "refusing to send selected file to OpenCode: "
                f"{relative_path} must be UTF-8 text"
            )
            raise WorkerInputError(msg) from exc
        content_reason = secret_like_content_reason(content)
        if content_reason is not None:
            msg = (
                "refusing to send selected file to OpenCode: "
                f"{relative_path} contains secret-like content ({content_reason})"
            )
            raise WorkerInputError(msg)
        validated.setdefault(
            resolved,
            PreparedSelectedFile(
                source_path=resolved,
                relative_path=relative_path,
                content=content,
                size_bytes=size,
            ),
        )
    return tuple(validated.values())


def _resolve_opencode_bin(raw_path: Path | None, *, required: bool) -> Path:
    if raw_path is not None:
        path = raw_path.expanduser().resolve()
        if not path.is_file():
            msg = f"OpenCode executable does not exist: {raw_path}"
            raise WorkerInputError(msg)
        return path
    discovered = shutil.which("opencode")
    if discovered is None:
        if not required:
            return Path("opencode")
        msg = "OpenCode executable not found on PATH; pass --opencode-bin"
        raise WorkerInputError(msg)
    return Path(discovered).resolve()


def _build_prompt(
    config: WorkerConfig,
    snapshot_paths: tuple[Path, ...],
) -> str:
    template = _template_path(config.repo_root, config.mode).read_text(encoding="utf-8")
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
    ]
    lines.extend(_opencode_host_capability_context(config))
    lines.extend(
        [
            "",
            "## Attached File Snapshots",
            "",
            (
                "OpenCode receives preflight-vetted snapshots through `--file`. "
                "Review only the attached snapshot files below; do not read "
                "selected files from the live repository during this worker run."
            ),
            "",
        ]
    )
    lines.extend(f"- {path}" for path in snapshot_paths)
    lines.extend(
        [
            "",
            "## Allowed Snapshot Files",
            "",
        ]
    )
    lines.extend(f"- {path}" for path in snapshot_paths)
    if config.instruction is not None:
        lines.extend(["", "## Task Instruction", "", config.instruction.strip()])
    return "\n".join(lines).rstrip() + "\n"


def _opencode_host_capability_context(config: WorkerConfig) -> list[str]:
    """Return deterministic OpenCode host capability and authority context."""

    if config.mode == "patch":
        mode_contract = (
            "Patch mode may propose a single unified diff only, scoped to the "
            "attached snapshots and allowed issue, with tests or docs only when "
            "that work is inside the listed scope."
        )
    else:
        mode_contract = (
            "Review mode returns concrete findings with file, line, severity, "
            "evidence, and a proposed fix; uncertain claims stay inconclusive."
        )

    return [
        "## OpenCode Host Capability Context",
        "",
        (
            "- OpenCode-hosted DeepSeek V4 Pro is the tool-enabled DeepSeek "
            f"lane; this worker run uses `{config.model}` through the OpenCode "
            "host, not the direct DeepSeek API worker."
        ),
        (
            "- This unattended worker cannot use host agents, plugins, MCP "
            "servers, hooks, shell/write/web tools, GitHub integrations, or "
            "nested agents. No model-issued tools are enabled; the trusted CLI "
            "ingests only the explicitly attached, wrapper-validated snapshots."
        ),
        (
            "- Codex-native plugins, skills, Codex Security, Browser, Computer "
            "Use, thread tools, and Codex-specific MCP state are not "
            "automatically available through OpenCode unless the OpenCode host "
            "exposes equivalent capabilities."
        ),
        (
            "- This harness must not pass `--dangerously-skip-permissions`; "
            "permission prompts, denials, and host policy are part of the "
            "safety boundary."
        ),
        (
            "- Use attached preflight snapshots as the selected-file truth. If "
            "additional repo inspection is needed, cite exact commands and "
            "evidence; do not turn generated context into authority."
        ),
        (
            "- Do not request, read, emit, or persist secrets, raw traffic, "
            "provider transcripts, prompt transcripts, environment values, "
            "local cache state, or ignored generated artifacts."
        ),
        (
            "- Product boundary: entroping run remains deterministic, "
            "Hurl-backed, QAnstitution-governed, and provider-free. Do not "
            "move OpenCode, DeepSeek, MCP, plugin, hook, or other provider "
            "calls into product runtime behavior."
        ),
        (
            "- Authority boundary: Codex or a human integrator owns Tier B/Tier "
            "C review, applying patches, opening or merging PRs, closing "
            "issues, and release/security/architecture decisions."
        ),
        f"- Mode contract: {mode_contract}",
    ]


def _template_path(repo_root: Path, mode: Mode) -> Path:
    path = repo_root / "prompts" / "opencode" / f"{mode}.md"
    if not path.is_file():
        msg = f"missing prompt template: {path}"
        raise WorkerInputError(msg)
    return path


def _new_artifact_dir(artifact_root: Path, mode: Mode) -> Path:
    timestamp = datetime.now(UTC_TZ).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid.uuid4().hex[:8]
    return artifact_root / f"{timestamp}-{mode}-{suffix}"


def _write_selected_file_snapshots(
    config: WorkerConfig,
    artifact_dir: Path,
) -> tuple[Path, ...]:
    snapshot_root = artifact_dir / "selected-files"
    snapshots: list[Path] = []
    for selected in config.files:
        snapshot_path = snapshot_root / selected.relative_path
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(selected.content, encoding="utf-8")
        snapshots.append(snapshot_path)
    return tuple(snapshots)


def _opencode_command(
    config: WorkerConfig,
    prompt: str,
    snapshot_paths: tuple[Path, ...],
) -> list[str]:
    command = [
        str(config.opencode_bin),
        "run",
        "--model",
        config.model,
        "--format",
        "json",
    ]
    for snapshot_path in snapshot_paths:
        command.extend(["--file", str(snapshot_path)])
    command.append(prompt)
    return command


def _classify_status(mode: Mode, returncode: int, stdout: str) -> Status:
    if returncode != 0:
        return "failed"
    if mode == "patch":
        if _extract_unified_diff(stdout) is not None:
            return "patch-proposed"
        return "inconclusive"
    if stdout.strip():
        return "completed"
    return "inconclusive"


def _classify_stream_status(
    mode: Mode,
    returncode: int,
    summary: OpenCodeStreamSummary,
) -> Status:
    if summary.saw_error_event or summary.accounting_reason == "malformed_event":
        return "failed"
    return _classify_status(mode, returncode, summary.output_text)


def _usage_receipt(
    config: WorkerConfig,
    artifact_dir: Path,
    summary: OpenCodeStreamSummary,
    override_reason: ReceiptReason | None,
) -> OpenCodeUsageReceipt:
    return build_usage_receipt(
        summary,
        job_id=config.job_id,
        requested_model=config.model,
        run_id=artifact_dir.name,
        override_reason=override_reason,
    )


def _sanitized_child_stderr(stderr: str) -> str:
    if not stderr:
        return ""
    reason = secret_like_content_reason(stderr)
    if reason is not None:
        return _withheld_output_message("stderr", reason)
    return "OpenCode emitted stderr; raw provider stderr was withheld.\n"


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


def _withhold_secret_like_worker_output(result: WorkerResult) -> WorkerResult:
    stdout_reason = secret_like_content_reason(result.stdout)
    stderr_reason = secret_like_content_reason(result.stderr)
    if stdout_reason is None and stderr_reason is None:
        return result

    return WorkerResult(
        status="failed",
        artifact_dir=result.artifact_dir,
        returncode=result.returncode,
        stdout=(
            _withheld_output_message("stdout", stdout_reason)
            if stdout_reason is not None
            else result.stdout
        ),
        stderr=(
            _withheld_output_message("stderr", stderr_reason)
            if stderr_reason is not None
            else result.stderr
        ),
        usage_receipt=(
            OpenCodeUsageReceipt(
                accounting_status="unaccounted",
                accounting_reason="secret_like_output",
                job_id=result.usage_receipt.job_id,
                requested_model=result.usage_receipt.requested_model,
                run_id=result.usage_receipt.run_id,
                session_fingerprint=result.usage_receipt.session_fingerprint,
                unique_step_count=result.usage_receipt.unique_step_count,
                usage=None,
            )
            if stdout_reason is not None or stderr_reason is not None
            else result.usage_receipt
        ),
    )


def _withheld_output_message(stream_name: str, reason: str) -> str:
    return (
        f"OpenCode {stream_name} withheld because it contained secret-like "
        f"content ({reason}).\n"
    )


def _write_execution_artifacts(
    config: WorkerConfig,
    result: WorkerResult,
    command: list[str],
    attestation: UnattendedAttestation,
) -> None:
    stdout = bounded_persisted_text(result.stdout, config.max_output_bytes)
    stderr = bounded_persisted_text(result.stderr, config.max_output_bytes)
    atomic_write_text(result.artifact_dir / "stdout.txt", stdout)
    atomic_write_text(result.artifact_dir / "stderr.txt", stderr)
    if config.mode == "patch":
        proposal = _extract_unified_diff(stdout)
        if proposal is not None:
            atomic_write_text(result.artifact_dir / "proposal.diff", proposal)
    _write_usage_receipt(result)
    _write_capability_receipt(result.artifact_dir, attestation)
    _write_metadata(config, result, command, attestation)


def _write_usage_receipt(result: WorkerResult) -> None:
    atomic_write_text(
        result.artifact_dir / "usage-receipt.json",
        json.dumps(result.usage_receipt.to_payload(), indent=2, sort_keys=True) + "\n",
    )


def _write_capability_receipt(
    artifact_dir: Path,
    attestation: UnattendedAttestation,
) -> None:
    atomic_write_text(
        artifact_dir / "capability-receipt.json",
        json.dumps(attestation.receipt_payload(), indent=2, sort_keys=True) + "\n",
    )


def _write_metadata(
    config: WorkerConfig,
    result: WorkerResult,
    command: list[str],
    attestation: UnattendedAttestation | None,
) -> None:
    redacted_command = [*command]
    if redacted_command:
        redacted_command[-1] = "<prompt-redacted>"
    metadata = {
        "schema_version": "entroping.opencode-worker.v2",
        "status": result.status,
        "mode": config.mode,
        "model": config.model,
        "issue": config.issue,
        "job_id": config.job_id,
        "files": [selected.relative_path for selected in config.files],
        "artifact_dir": str(result.artifact_dir),
        "returncode": result.returncode,
        "timeout_seconds": config.timeout_seconds,
        "max_file_bytes": config.max_file_bytes,
        "max_output_bytes": config.max_output_bytes,
        "capability_context_version": CAPABILITY_CONTEXT_VERSION,
        "command": redacted_command,
        "created_at": datetime.now(UTC_TZ).isoformat(),
        "dry_run": config.dry_run,
        "usage_receipt": {
            "accounting_reason": result.usage_receipt.accounting_reason,
            "accounting_status": result.usage_receipt.accounting_status,
            "path": "usage-receipt.json",
        },
        "capability_receipt": (
            {
                "path": "capability-receipt.json",
                "profile_id": attestation.profile.profile_id,
            }
            if attestation is not None
            else None
        ),
    }
    atomic_write_text(
        result.artifact_dir / "metadata.json",
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
    )


def _record_factory_metrics(
    config: WorkerConfig,
    result: WorkerResult,
    *,
    duration_seconds: float,
) -> None:
    if not config.record_factory_metrics:
        return

    provider, model = _factory_provider_model(config.model)
    context_bytes = _selected_files_bytes(config.files)
    observed_usage = result.usage_receipt.usage
    estimated_tokens = (
        observed_usage.input_tokens
        + observed_usage.output_tokens
        + observed_usage.reasoning_tokens
        if observed_usage is not None
        else max(1, (context_bytes + 3) // 4)
    )
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
        "OpenCode",
        "--tool",
        "scripts/opencode_worker.py",
        "--model",
        model,
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
    if provider is not None:
        command.extend(["--provider", provider])
    if observed_usage is not None:
        command.extend(["--cost-usd", f"{observed_usage.cost_usd:.12g}"])
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
        print(f"opencode_worker: factory metrics warning: {warning}", file=sys.stderr)


def _selected_files_bytes(files: tuple[PreparedSelectedFile, ...]) -> int:
    return sum(selected.size_bytes for selected in files)


def _factory_provider_model(model: str) -> tuple[str | None, str]:
    provider, separator, model_id = model.partition("/")
    if separator:
        return provider, model_id
    return None, model


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


def _factory_note(config: WorkerConfig, result: WorkerResult) -> str:
    parts = [
        f"mode={config.mode}",
        f"status={result.status}",
        f"accounting={result.usage_receipt.accounting_status}",
        f"accounting_reason={result.usage_receipt.accounting_reason}",
    ]
    ignored_root = (config.repo_root / ".entroping").resolve()
    try:
        relative_artifact_dir = result.artifact_dir.resolve().relative_to(ignored_root)
    except ValueError:
        return ";".join(parts)
    parts.append(f"artifact_dir=.entroping/{relative_artifact_dir.as_posix()}")
    return ";".join(parts)


if __name__ == "__main__":
    raise SystemExit(main())
