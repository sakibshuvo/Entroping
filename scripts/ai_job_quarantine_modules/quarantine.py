from __future__ import annotations

import hashlib
from contextlib import ExitStack
from pathlib import Path

from scripts import ai_job_fs, ai_jobs
from scripts.ai_job_quarantine_modules.evidence import (
    QUARANTINE_SCHEMA_VERSION,
    json_object,
)


def quarantine_jobs(
    repo_root: Path,
    job_root: Path,
    *,
    apply: bool,
) -> dict[str, object]:
    candidates = _quarantine_candidates(repo_root, job_root)
    if apply:
        _apply_quarantine_candidates(job_root, candidates)
    return {
        "status": "quarantined" if apply else "planned",
        "job_root": str(job_root),
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def _quarantine_candidates(
    repo_root: Path,
    job_root: Path,
) -> list[dict[str, object]]:
    queued_dir = job_root / "queued"
    if not queued_dir.exists():
        return []
    candidates: list[dict[str, object]] = []
    try:
        with ai_job_fs.open_state_directory(
            job_root,
            "queued",
            create=False,
        ) as queued_fd:
            for name in ai_job_fs.list_json_names(queued_fd):
                raw = ai_job_fs.read_regular_bytes(queued_fd, name)
                reason, job_id = _quarantine_reason(repo_root, raw, name)
                if reason is None:
                    continue
                candidates.append(
                    {
                        "job_id": job_id,
                        "reason": reason,
                        "source_path": str(job_root / "queued" / name),
                        "target_path": str(job_root / "quarantined" / name),
                        "receipt_path": str(
                            job_root / "quarantine-receipts" / name
                        ),
                        "sha256": hashlib.sha256(raw).hexdigest(),
                    }
                )
    except ai_job_fs.SafeStateError as exc:
        raise ai_jobs.AiJobError(str(exc)) from exc
    return candidates


def _apply_quarantine_candidates(
    job_root: Path,
    candidates: list[dict[str, object]],
) -> None:
    try:
        ai_job_fs.ensure_job_root(job_root)
        with ExitStack() as stack:
            queued_fd = stack.enter_context(
                ai_job_fs.open_state_directory(job_root, "queued")
            )
            quarantined_fd = stack.enter_context(
                ai_job_fs.open_state_directory(job_root, "quarantined")
            )
            receipt_fd = stack.enter_context(
                ai_job_fs.open_state_directory(job_root, "quarantine-receipts")
            )
            for candidate in candidates:
                _apply_quarantine_candidate(
                    queued_fd,
                    quarantined_fd,
                    receipt_fd,
                    candidate,
                )
    except ai_job_fs.SafeStateError as exc:
        raise ai_jobs.AiJobError(str(exc)) from exc


def _apply_quarantine_candidate(
    queued_fd: int,
    quarantined_fd: int,
    receipt_fd: int,
    candidate: dict[str, object],
) -> None:
    name = Path(str(candidate["source_path"])).name
    digest = str(candidate["sha256"])
    source_bytes = ai_job_fs.read_regular_bytes(queued_fd, name)
    if hashlib.sha256(source_bytes).hexdigest() != digest:
        raise ai_jobs.AiJobError(f"queued job changed after quarantine plan: {name}")
    receipt: dict[str, object] = {
        "schema_version": QUARANTINE_SCHEMA_VERSION,
        "job_id": candidate["job_id"],
        "reason": candidate["reason"],
        "sha256": digest,
        "source_path": candidate["source_path"],
        "quarantined_path": candidate["target_path"],
        "quarantined_at": ai_jobs._now(),
    }
    if ai_job_fs.entry_exists(receipt_fd, name):
        existing_receipt = json_object(
            ai_job_fs.read_regular_bytes(receipt_fd, name),
            name,
        )
        if any(
            existing_receipt.get(key) != receipt[key]
            for key in (
                "schema_version",
                "job_id",
                "reason",
                "sha256",
                "source_path",
                "quarantined_path",
            )
        ):
            raise ai_jobs.AiJobError(f"quarantine receipt conflicts with plan: {name}")
    else:
        ai_job_fs.atomic_write_json(
            receipt_fd,
            name,
            receipt,
            exclusive=True,
        )
    if ai_job_fs.entry_exists(quarantined_fd, name):
        raise ai_jobs.AiJobError(f"quarantine target already exists: {name}")
    ai_job_fs.rename_entry(queued_fd, name, quarantined_fd, name)


def _quarantine_reason(
    repo_root: Path,
    raw: bytes,
    name: str,
) -> tuple[str | None, str]:
    try:
        job = json_object(raw, name)
    except ai_jobs.AiJobError:
        return "malformed-job", Path(name).stem
    structure_error = ai_jobs._job_structure_error(job)
    if structure_error is not None:
        return "malformed-job", str(job.get("job_id", Path(name).stem))
    routing_violation = ai_jobs._tier_a_routing_violation(job, repo_root / name)
    if routing_violation is not None:
        return "tier-a-routing-violation", str(job["job_id"])
    if job.get("autonomy_tier") != "tier_a":
        return None, str(job["job_id"])
    source_revision = job.get("source_revision")
    file_sha256 = job.get("file_sha256")
    if not isinstance(source_revision, str) or not isinstance(file_sha256, dict):
        return "legacy-revalidation-required", str(job["job_id"])
    if source_revision != ai_jobs._current_revision(repo_root):
        return "stale-revision", str(job["job_id"])
    files = ai_jobs._string_list(job.get("files"))
    try:
        validated_files = ai_jobs._validate_files(
            repo_root,
            tuple(Path(path) for path in files),
        )
        actual_digests = ai_jobs._selected_file_digests(repo_root, validated_files)
    except ai_jobs.AiJobError:
        return "selected-files-unavailable", str(job["job_id"])
    if file_sha256 != actual_digests:
        return "selected-files-changed", str(job["job_id"])
    try:
        issue = ai_jobs._issue_number(job.get("issue"), required=False)
        if issue is not None:
            _ = ai_jobs._github_issue_snapshot(issue)
    except ai_jobs.AiJobError:
        return "issue-revalidation-failed", str(job["job_id"])
    return None, str(job["job_id"])
