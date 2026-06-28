#!/usr/bin/env python3
"""Build compact review packets from bounded AI worker artifacts."""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path
from typing import Any

from ai_worker_file_safety import secret_like_content_reason

DEFAULT_JOB_ROOT = Path(".entroping") / "ai-jobs"
DEFAULT_ARTIFACT_ROOT = Path(".entroping") / "ai-reviews"
QUEUE_STATES = ("queued", "running", "completed", "failed")
RESULT_FILENAMES = ("result.md", "RESULT.md", "worker-result.md")
TEST_FILENAMES = ("tests.txt", "TESTS.txt", "test-output.txt")
SUMMARY_KEYS = (
    "STATUS",
    "FILES_CHANGED",
    "TESTS_RUN",
    "KNOWN_ISSUES",
    "SUMMARY",
    "VERIFICATION_LANE",
    "CI_STATUS",
)
HANDOFF_METADATA_KEYS = (
    "schema_version",
    "status",
    "mode",
    "model",
    "issue",
    "provider_lane",
    "provider_host",
    "billing_path",
    "autonomy_tier",
    "merge_authority",
    "worktree",
    "branch",
    "pr",
    "verification_lane",
    "artifact_dir",
    "returncode",
    "usage",
)
REQUIRED_READY_HANDOFF_KEYS = (
    "issue",
    "model",
    "provider_lane",
    "provider_host",
    "billing_path",
    "autonomy_tier",
    "merge_authority",
    "worktree",
    "branch",
    "verification_lane",
)


class PacketError(ValueError):
    """Raised when a compact review packet cannot be built."""


def main() -> int:
    try:
        args = _parse_args()
        repo_root = _repo_root()
        job_root = _resolve_root(repo_root, args.job_root, "job root")
        artifact_root = _resolve_root(repo_root, args.artifact_root, "artifact root")
        packet = _packet_for_args(args, job_root=job_root, artifact_root=artifact_root)
    except PacketError as exc:
        print(f"factory_review_packet: {exc}", file=sys.stderr)
        return 2

    _print_packet(packet, json_output=args.json)
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Print compact, transcript-free evidence for Codex review of AI worker artifacts."
        )
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--job-id", help="AI job id to find under the job root.")
    source.add_argument("--artifact-dir", type=Path, help="Worker artifact directory.")
    parser.add_argument(
        "--job-root",
        type=Path,
        default=DEFAULT_JOB_ROOT,
        help="AI job queue root. Default: .entroping/ai-jobs",
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_ARTIFACT_ROOT,
        help="Worker artifact root. Default: .entroping/ai-reviews",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable output.")
    return parser.parse_args()


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
        raise PacketError(msg) from exc
    return Path(completed.stdout.strip()).resolve()


def _resolve_root(repo_root: Path, raw_root: Path, purpose: str) -> Path:
    root = raw_root.expanduser()
    relative_root = not root.is_absolute()
    if relative_root:
        root = repo_root / root
    if _has_symlink_component(root):
        msg = f"{purpose} must not use symlink components"
        raise PacketError(msg)
    resolved = root.resolve()
    if relative_root:
        try:
            resolved.relative_to(repo_root)
        except ValueError as exc:
            msg = f"{purpose} must stay inside repository"
            raise PacketError(msg) from exc
    elif not (
        _path_is_relative_to(resolved, repo_root)
        or _path_is_relative_to(resolved, _system_temp_root())
    ):
        msg = f"{purpose} must stay inside repository or system temp directory"
        raise PacketError(msg)
    return resolved


def _packet_for_args(
    args: argparse.Namespace,
    *,
    job_root: Path,
    artifact_root: Path,
) -> dict[str, Any]:
    job: dict[str, Any] | None = None
    job_path: Path | None = None
    if args.job_id is not None:
        job_path, job = _find_job(job_root, str(args.job_id))
        artifact_dir = _validated_artifact_dir(artifact_root, job.get("artifact_dir"))
    else:
        artifact_dir = _validated_artifact_dir(artifact_root, args.artifact_dir)

    packet: dict[str, Any] = {
        "schema_version": "entroping.factory-review-packet.v1",
        "review_rule": (
            "Review this compact packet, job metadata, diff artifacts, changed files, "
            "and tests before reading raw transcripts."
        ),
        "job": _job_packet(job, job_path),
        "artifact": _artifact_packet(artifact_dir),
    }
    _validate_packet(packet)
    return packet


def _find_job(job_root: Path, job_id: str) -> tuple[Path, dict[str, Any]]:
    for state in QUEUE_STATES:
        path = job_root / state / f"{job_id}.json"
        if not path.exists():
            continue
        job = _read_json_object(path)
        return path, job
    msg = f"job id not found under {job_root}: {job_id}"
    raise PacketError(msg)


def _validated_artifact_dir(artifact_root: Path, raw_value: object) -> Path:
    if not isinstance(raw_value, (str, Path)) or not str(raw_value):
        msg = "artifact directory is missing"
        raise PacketError(msg)
    artifact_dir = Path(raw_value).expanduser()
    if not artifact_dir.is_absolute():
        artifact_dir = artifact_root / artifact_dir
    if _has_symlink_component(artifact_dir):
        msg = "artifact directory must not use symlink components"
        raise PacketError(msg)
    resolved = artifact_dir.resolve()
    try:
        resolved.relative_to(artifact_root)
    except ValueError as exc:
        msg = "artifact directory must stay under artifact root"
        raise PacketError(msg) from exc
    if not resolved.is_dir():
        msg = f"artifact directory does not exist: {resolved}"
        raise PacketError(msg)
    return resolved


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        msg = f"could not read JSON object: {path}"
        raise PacketError(msg) from exc
    if not isinstance(payload, dict):
        msg = f"JSON file is not an object: {path}"
        raise PacketError(msg)
    return payload


def _job_packet(job: dict[str, Any] | None, job_path: Path | None) -> dict[str, Any] | None:
    if job is None:
        return None
    keys = (
        "job_id",
        "queue_status",
        "issue",
        "autonomy_tier",
        "engine",
        "profile",
        "mode",
        "model",
        "provider_lane",
        "provider_host",
        "billing_path",
        "merge_authority",
        "worker_status",
        "artifact_dir",
    )
    packet = {key: job.get(key) for key in keys if job.get(key) is not None}
    if job_path is not None:
        packet["job_path"] = str(job_path)
    return packet


def _artifact_packet(artifact_dir: Path) -> dict[str, Any]:
    packet: dict[str, Any] = {"artifact_dir": str(artifact_dir)}
    metadata_path = artifact_dir / "metadata.json"
    if metadata_path.exists():
        metadata = _read_json_object(metadata_path)
        packet["metadata_path"] = str(metadata_path)
        packet["metadata"] = _safe_metadata(metadata)

    result_path = _first_existing(artifact_dir, RESULT_FILENAMES)
    if result_path is not None:
        packet["result_summary_path"] = str(result_path)
        packet["result_summary"] = _result_summary(result_path)

    tests_path = _first_existing(artifact_dir, TEST_FILENAMES)
    if tests_path is not None:
        packet["tests_path"] = str(tests_path)

    proposal_path = artifact_dir / "proposal.diff"
    if proposal_path.exists():
        packet["proposal_diff"] = _proposal_diff_packet(proposal_path)

    return packet


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    packet = {
        key: metadata.get(key)
        for key in HANDOFF_METADATA_KEYS
        if metadata.get(key) is not None
    }
    review_flags = _metadata_review_flags(metadata)
    if review_flags:
        packet["review_flags"] = review_flags
    return packet


def _metadata_review_flags(metadata: dict[str, Any]) -> list[str]:
    if not _looks_like_handoff(metadata):
        return []

    flags: list[str] = []
    if metadata.get("status") != "ready_for_codex":
        flags.append("metadata status is not ready_for_codex")

    for key in REQUIRED_READY_HANDOFF_KEYS:
        if not metadata.get(key):
            flags.append(f"metadata missing {key}")
    return flags


def _looks_like_handoff(metadata: dict[str, Any]) -> bool:
    if metadata.get("status") == "ready_for_codex":
        return True
    handoff_keys = (
        "provider_lane",
        "provider_host",
        "billing_path",
        "autonomy_tier",
        "merge_authority",
        "worktree",
        "branch",
        "verification_lane",
    )
    return any(key in metadata for key in handoff_keys)


def _first_existing(root: Path, filenames: tuple[str, ...]) -> Path | None:
    for filename in filenames:
        path = root / filename
        if path.exists():
            return path
    return None


def _result_summary(path: Path) -> dict[str, str]:
    content = path.read_text(encoding="utf-8", errors="replace")
    secret_reason = secret_like_content_reason(content)
    if secret_reason is not None:
        return {"WITHHELD": f"secret-like result summary withheld: {secret_reason}"}
    summary: dict[str, str] = {}
    for raw_line in content.splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", maxsplit=1)
        key = key.strip().upper()
        if key in SUMMARY_KEYS:
            summary[key] = value.strip()
    return summary


def _validate_packet(packet: dict[str, Any]) -> None:
    artifact = packet.get("artifact")
    if not isinstance(artifact, dict):
        msg = "artifact is required in packet"
        raise PacketError(msg)
    job = packet.get("job")
    if job is not None and not isinstance(job, dict):
        msg = "job must be an object when present"
        raise PacketError(msg)

    metadata_value = artifact.get("metadata")
    result_summary = artifact.get("result_summary")
    if metadata_value is not None and not isinstance(metadata_value, dict):
        msg = "artifact metadata must be an object when present"
        raise PacketError(msg)
    if result_summary is not None and not isinstance(result_summary, dict):
        msg = "artifact result_summary must be an object when present"
        raise PacketError(msg)

    metadata = metadata_value if isinstance(metadata_value, dict) else {}
    summary = result_summary if isinstance(result_summary, dict) else {}
    job_payload = job if isinstance(job, dict) else {}

    status = _first_value(metadata, "status")
    issue = _first_non_empty(
        _first_value(job_payload, "issue"),
        _first_value(metadata, "issue"),
    )
    provider_lane = _first_non_empty(
        _first_value(job_payload, "provider_lane"),
        _first_value(metadata, "provider_lane"),
    )
    merge_authority = _first_non_empty(
        _first_value(job_payload, "merge_authority"),
        _first_value(metadata, "merge_authority"),
    )
    verification_lane = _first_non_empty(
        _first_value(summary, "VERIFICATION_LANE"),
        _first_value(metadata, "verification_lane"),
    )
    ci_status = _first_non_empty(
        _first_value(summary, "CI_STATUS"),
        _first_value(metadata, "ci_status"),
    )

    if status == "completed":
        missing: list[str] = []
        if issue is None:
            missing.append("issue")
        if provider_lane is None:
            missing.append("provider_lane")
        if verification_lane is None:
            missing.append("verification_lane")
        if ci_status is None:
            missing.append("ci_status")
        if merge_authority is None:
            missing.append("merge_authority")
        if missing:
            msg = ", ".join(missing)
            raise PacketError(f"review packet missing required fields: {msg}")


def _first_value(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return None


def _first_non_empty(*values: str | None) -> str | None:
    for value in values:
        if value is not None:
            return value
    return None


def _proposal_diff_packet(path: Path) -> dict[str, Any]:
    additions = 0
    deletions = 0
    changed_files: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("diff --git "):
            changed_file = _changed_file_from_diff_header(line)
            if changed_file is not None and changed_file not in changed_files:
                changed_files.append(changed_file)
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return {
        "proposal_diff_path": str(path),
        "changed_files": changed_files,
        "files_changed": len(changed_files),
        "additions": additions,
        "deletions": deletions,
    }


def _changed_file_from_diff_header(line: str) -> str | None:
    parts = line.split()
    if len(parts) < 4:
        return None
    target = parts[3]
    if target.startswith("b/"):
        return target[2:]
    return target


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


def _print_packet(packet: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(packet, indent=2, sort_keys=True))
        return

    job = packet.get("job")
    artifact = packet.get("artifact")
    print(f"Factory review packet: {packet['schema_version']}")
    if isinstance(job, dict):
        print(f"Job: {job.get('job_id')} issue={job.get('issue')} model={job.get('model')}")
        print(f"Worker status: {job.get('worker_status')}")
    if isinstance(artifact, dict):
        print(f"Artifact: {artifact.get('artifact_dir')}")
        if "metadata_path" in artifact:
            print(f"Metadata: {artifact['metadata_path']}")
        if "result_summary_path" in artifact:
            print(f"Result summary: {artifact['result_summary_path']}")
        if "tests_path" in artifact:
            print(f"Tests: {artifact['tests_path']}")
        proposal = artifact.get("proposal_diff")
        if isinstance(proposal, dict):
            print(
                "Proposal diff: "
                f"{proposal.get('files_changed', 0)} files, "
                f"+{proposal.get('additions', 0)} "
                f"-{proposal.get('deletions', 0)}"
            )


if __name__ == "__main__":
    raise SystemExit(main())
