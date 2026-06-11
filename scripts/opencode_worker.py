#!/usr/bin/env python3
"""Run bounded OpenCode workers and capture review or patch artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess  # nosec B404
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

DEFAULT_MODEL = "deepseek/deepseek-v4-pro"
DEFAULT_ARTIFACT_ROOT = Path(".entroping") / "ai-reviews"
DEFAULT_TIMEOUT_SECONDS = 300.0
Mode = Literal["review", "patch"]
Status = Literal["completed", "dry-run", "failed", "inconclusive", "patch-proposed", "timed-out"]


@dataclass(frozen=True, slots=True)
class WorkerConfig:
    """Validated OpenCode worker configuration."""

    mode: Mode
    model: str
    repo_root: Path
    files: tuple[Path, ...]
    artifact_root: Path
    opencode_bin: Path
    timeout_seconds: float
    issue: str | None
    instruction: str | None
    dry_run: bool
    json_output: bool


@dataclass(frozen=True, slots=True)
class WorkerResult:
    """OpenCode worker execution result."""

    status: Status
    artifact_dir: Path
    returncode: int
    stdout: str
    stderr: str


def main() -> int:
    try:
        config = _parse_args()
        result = run_worker(config)
    except WorkerInputError as exc:
        print(f"opencode_worker: {exc}", file=sys.stderr)
        return 2

    payload = {
        "status": result.status,
        "artifact_dir": str(result.artifact_dir),
        "returncode": result.returncode,
    }
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

    artifact_dir = _new_artifact_dir(config.artifact_root, config.mode)
    artifact_dir.mkdir(parents=True, exist_ok=False)

    prompt = _build_prompt(config)
    (artifact_dir / "prompt.md").write_text(prompt, encoding="utf-8")

    command = [str(config.opencode_bin), "run", "--model", config.model, prompt]
    if config.dry_run:
        result = WorkerResult(
            status="dry-run",
            artifact_dir=artifact_dir,
            returncode=0,
            stdout="",
            stderr="",
        )
        _write_metadata(config, result, command)
        return result

    try:
        completed = subprocess.run(  # nosec B603
            command,
            cwd=config.repo_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=config.timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _decode_timeout_output(exc.stdout)
        stderr = _decode_timeout_output(exc.stderr)
        if stderr:
            stderr = f"{stderr}\nOpenCode worker timed out after {config.timeout_seconds} seconds."
        else:
            stderr = f"OpenCode worker timed out after {config.timeout_seconds} seconds."
        result = WorkerResult(
            status="timed-out",
            artifact_dir=artifact_dir,
            returncode=124,
            stdout=stdout,
            stderr=stderr,
        )
        _write_execution_artifacts(config, result, command)
        return result

    status = _classify_status(config.mode, completed.returncode, completed.stdout)
    result = WorkerResult(
        status=status,
        artifact_dir=artifact_dir,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
    _write_execution_artifacts(config, result, command)
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
        "--dry-run",
        action="store_true",
        help="Write prompt and metadata without invoking OpenCode.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary.")
    args = parser.parse_args()

    repo_root = _repo_root()
    files = _validate_files(repo_root, tuple(Path(path) for path in args.files))
    if not files:
        msg = "at least one --file is required"
        raise WorkerInputError(msg)
    if args.timeout_seconds <= 0:
        msg = "--timeout-seconds must be greater than zero"
        raise WorkerInputError(msg)

    opencode_bin = _resolve_opencode_bin(args.opencode_bin, required=not args.dry_run)
    artifact_root = args.artifact_root
    if not artifact_root.is_absolute():
        artifact_root = repo_root / artifact_root

    mode: Mode = args.mode
    return WorkerConfig(
        mode=mode,
        model=args.model,
        repo_root=repo_root,
        files=files,
        artifact_root=artifact_root.expanduser().resolve(),
        opencode_bin=opencode_bin,
        timeout_seconds=args.timeout_seconds,
        issue=args.issue,
        instruction=args.instruction,
        dry_run=args.dry_run,
        json_output=args.json,
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


def _validate_files(repo_root: Path, raw_files: tuple[Path, ...]) -> tuple[Path, ...]:
    validated: list[Path] = []
    for raw_file in raw_files:
        path = raw_file.expanduser()
        if not path.is_absolute():
            path = repo_root / path
        resolved = path.resolve()
        if not resolved.exists():
            msg = f"input file does not exist: {raw_file}"
            raise WorkerInputError(msg)
        if not resolved.is_file() or resolved.is_symlink():
            msg = f"input path must be a regular non-symlink file: {raw_file}"
            raise WorkerInputError(msg)
        try:
            resolved.relative_to(repo_root)
        except ValueError as exc:
            msg = f"input file must be inside repository: {raw_file}"
            raise WorkerInputError(msg) from exc
        validated.append(resolved)
    return tuple(dict.fromkeys(validated))


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


def _build_prompt(config: WorkerConfig) -> str:
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
    if config.instruction is not None:
        lines.extend(["", "## Task Instruction", "", config.instruction.strip()])
    return "\n".join(lines).rstrip() + "\n"


def _template_path(repo_root: Path, mode: Mode) -> Path:
    path = repo_root / "prompts" / "opencode" / f"{mode}.md"
    if not path.is_file():
        msg = f"missing prompt template: {path}"
        raise WorkerInputError(msg)
    return path


def _new_artifact_dir(artifact_root: Path, mode: Mode) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid.uuid4().hex[:8]
    return artifact_root / f"{timestamp}-{mode}-{suffix}"


def _decode_timeout_output(output: bytes | str | None) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output


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
    config: WorkerConfig,
    result: WorkerResult,
    command: list[str],
) -> None:
    (result.artifact_dir / "stdout.txt").write_text(result.stdout, encoding="utf-8")
    (result.artifact_dir / "stderr.txt").write_text(result.stderr, encoding="utf-8")
    if config.mode == "patch":
        proposal = _extract_unified_diff(result.stdout)
        if proposal is not None:
            (result.artifact_dir / "proposal.diff").write_text(proposal, encoding="utf-8")
    _write_metadata(config, result, command)


def _write_metadata(config: WorkerConfig, result: WorkerResult, command: list[str]) -> None:
    metadata = {
        "schema_version": "entroping.opencode-worker.v1",
        "status": result.status,
        "mode": config.mode,
        "model": config.model,
        "issue": config.issue,
        "files": [path.relative_to(config.repo_root).as_posix() for path in config.files],
        "artifact_dir": str(result.artifact_dir),
        "returncode": result.returncode,
        "timeout_seconds": config.timeout_seconds,
        "command": command,
        "created_at": datetime.now(UTC).isoformat(),
        "dry_run": config.dry_run,
    }
    (result.artifact_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
