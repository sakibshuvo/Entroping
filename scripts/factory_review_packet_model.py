from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.ai_worker_file_safety import secret_like_content_reason
from scripts.factory_patch_inspection import PatchInspectionError, inspect_proposal_diff
from scripts.script_safety import (
    ScriptSafetyError,
    read_json_file,
    read_text_file,
)

QUEUE_STATES = ("queued", "running", "completed", "failed")
RESULT_FILENAMES = ("result.md", "RESULT.md", "worker-result.md")
TEST_FILENAMES = ("tests.txt", "TESTS.txt", "test-output.txt")
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
SUMMARY_KEYS = (
    "STATUS",
    "FILES_CHANGED",
    "TESTS_RUN",
    "KNOWN_ISSUES",
    "SUMMARY",
    "VERIFICATION_LANE",
    "CI_STATUS",
)


class PacketError(ValueError):
    pass


def build_packet(
    *,
    job_id: str | None,
    raw_artifact_dir: Path | None,
    job_root: Path,
    artifact_root: Path,
) -> dict[str, Any]:
    job: dict[str, Any] | None = None
    job_path: Path | None = None
    if job_id is not None:
        job_path, job = _find_job(job_root, job_id)
        artifact_dir = _validated_artifact_dir(artifact_root, job.get("artifact_dir"))
    else:
        artifact_dir = _validated_artifact_dir(artifact_root, raw_artifact_dir)

    return {
        "schema_version": "entroping.factory-review-packet.v1",
        "review_rule": (
            "Review this compact packet, job metadata, diff artifacts, changed files, "
            "and tests before reading raw transcripts."
        ),
        "job": _job_packet(job, job_path),
        "artifact": _artifact_packet(artifact_dir),
    }


def _find_job(job_root: Path, job_id: str) -> tuple[Path, dict[str, Any]]:
    for state in QUEUE_STATES:
        path = job_root / state / f"{job_id}.json"
        if path.exists():
            return path, _read_json_object(path)
    raise PacketError(f"job id not found under {job_root}: {job_id}")


def _validated_artifact_dir(artifact_root: Path, raw_value: object) -> Path:
    if not isinstance(raw_value, (str, Path)) or not str(raw_value):
        raise PacketError("artifact directory is missing")
    artifact_dir = Path(raw_value).expanduser()
    if not artifact_dir.is_absolute():
        artifact_dir = artifact_root / artifact_dir
    if _has_symlink_component(artifact_dir):
        raise PacketError("artifact directory must not use symlink components")
    resolved = artifact_dir.resolve()
    try:
        resolved.relative_to(artifact_root)
    except ValueError as exc:
        raise PacketError("artifact directory must stay under artifact root") from exc
    if not resolved.is_dir():
        raise PacketError(f"artifact directory does not exist: {resolved}")
    return resolved


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = read_json_file(path)
    except ScriptSafetyError as exc:
        raise PacketError(f"could not read JSON object: {path}") from exc
    if not isinstance(payload, dict):
        raise PacketError(f"JSON file is not an object: {path}")
    return payload


def _job_packet(
    job: dict[str, Any] | None,
    job_path: Path | None,
) -> dict[str, Any] | None:
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
        try:
            packet["proposal_diff"] = inspect_proposal_diff(proposal_path)
        except PatchInspectionError as exc:
            raise PacketError(str(exc)) from exc
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
    content = read_text_file(path, errors="replace")
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


def _has_symlink_component(path: Path) -> bool:
    return any(candidate.is_symlink() for candidate in (path, *path.parents))
