from __future__ import annotations

import hashlib
from contextlib import ExitStack
from pathlib import Path

from scripts import ai_job_fs, ai_jobs
from scripts.ai_job_quarantine_modules.evidence import (
    REQUEUE_SCHEMA_VERSION,
    json_object,
    validate_requeue_record,
)


def write_requeued_job(
    job_root: Path,
    source_job: dict[str, object],
    *,
    source_job_id: str,
    source_digest: str,
    revision: str,
    engine: ai_jobs.WorkerEngine,
    profile: str,
    model: str,
    files: list[str],
    file_sha256: dict[str, str],
) -> Path:
    marker_name = f"{source_job_id}.json"
    new_job_id = f"requeued-{hashlib.sha256(source_job_id.encode()).hexdigest()[:24]}"
    job_name = f"{new_job_id}.json"
    try:
        ai_job_fs.ensure_job_root(job_root)
        with ExitStack() as stack:
            directories = {
                state: stack.enter_context(
                    ai_job_fs.open_state_directory(job_root, state)
                )
                for state in (*ai_jobs.QUEUE_STATES, "requeue-records")
            }
            record_fd = directories["requeue-records"]
            existing_record = _read_record_if_present(record_fd, marker_name)
            if existing_record is not None:
                return _existing_requeue_path(
                    job_root,
                    directories,
                    job_name,
                    marker_name,
                    source_job_id,
                    source_digest,
                    new_job_id,
                    existing_record,
                )

            created_at = ai_jobs._now()
            new_job = _build_requeued_job(
                source_job,
                source_job_id=source_job_id,
                source_digest=source_digest,
                new_job_id=new_job_id,
                revision=revision,
                engine=engine,
                profile=profile,
                model=model,
                files=files,
                file_sha256=file_sha256,
                created_at=created_at,
            )
            record: dict[str, object] = {
                "schema_version": REQUEUE_SCHEMA_VERSION,
                "status": "prepared",
                "source_job_id": source_job_id,
                "source_sha256": source_digest,
                "new_job_id": new_job_id,
                "created_at": created_at,
            }
            try:
                ai_job_fs.atomic_write_json(
                    record_fd,
                    marker_name,
                    record,
                    exclusive=True,
                )
            except FileExistsError as exc:
                raise ai_jobs.AiJobError(
                    "concurrent requeue is already in progress; inspect before retry"
                ) from exc
            ai_job_fs.atomic_write_json(
                directories["queued"],
                job_name,
                new_job,
                exclusive=True,
            )
            record["status"] = "committed"
            ai_job_fs.atomic_write_json(record_fd, marker_name, record)
            return job_root / "queued" / job_name
    except ai_job_fs.SafeStateError as exc:
        raise ai_jobs.AiJobError(str(exc)) from exc


def _existing_requeue_path(
    job_root: Path,
    directories: dict[str, int],
    job_name: str,
    marker_name: str,
    source_job_id: str,
    source_digest: str,
    new_job_id: str,
    record: dict[str, object],
) -> Path:
    validate_requeue_record(
        record,
        source_job_id=source_job_id,
        source_digest=source_digest,
        new_job_id=new_job_id,
    )
    existing_path = _find_existing_job(
        job_root,
        directories,
        job_name,
        source_job_id,
        source_digest,
        new_job_id,
    )
    if existing_path is not None:
        if record.get("status") != "committed":
            record["status"] = "committed"
            ai_job_fs.atomic_write_json(
                directories["requeue-records"],
                marker_name,
                record,
            )
        return existing_path
    raise ai_jobs.AiJobError(
        "requeue idempotency record is incomplete; inspect before retry"
    )


def _build_requeued_job(
    source_job: dict[str, object],
    *,
    source_job_id: str,
    source_digest: str,
    new_job_id: str,
    revision: str,
    engine: ai_jobs.WorkerEngine,
    profile: str,
    model: str,
    files: list[str],
    file_sha256: dict[str, str],
    created_at: str,
) -> dict[str, object]:
    mode = ai_jobs._string_value(source_job.get("mode"), default="review")
    autonomy_tier = ai_jobs._normalize_autonomy_tier(
        str(source_job.get("autonomy_tier", "tier_a")).replace("_", "-")
    )
    if autonomy_tier is None:
        raise ai_jobs.AiJobError(
            f"quarantined job has no autonomy tier: {source_job_id}"
        )
    new_job: dict[str, object] = {
        "schema_version": ai_jobs.SCHEMA_VERSION,
        "job_id": new_job_id,
        "queue_status": "queued",
        "engine": engine,
        "mode": mode,
        "profile": profile,
        "model": model,
        "issue": source_job.get("issue"),
        "instruction": source_job.get("instruction"),
        "files": files,
        "file_sha256": file_sha256,
        "source_revision": revision,
        "timeout_seconds": ai_jobs._float_value(
            source_job.get("timeout_seconds"),
            default=ai_jobs.DEFAULT_TIMEOUT_SECONDS,
        ),
        "attempts": 0,
        "autonomy_tier": autonomy_tier,
        "requeued_from": source_job_id,
        "quarantined_sha256": source_digest,
        "revalidated_revision": revision,
        "revalidated_at": created_at,
        "created_at": created_at,
        "updated_at": created_at,
    }
    new_job.update(
        ai_jobs._routing_metadata(
            autonomy_tier=autonomy_tier,
            engine=engine,
            profile=profile,
            model=model,
        )
    )
    worker_instruction = ai_jobs._worker_instruction(
        autonomy_tier=autonomy_tier,
        engine=engine,
        profile=profile,
        model=model,
        instruction=ai_jobs._optional_string(source_job.get("instruction")),
    )
    if worker_instruction is not None:
        new_job["worker_instruction"] = worker_instruction
    return new_job


def _read_record_if_present(
    directory_fd: int,
    name: str,
) -> dict[str, object] | None:
    if not ai_job_fs.entry_exists(directory_fd, name):
        return None
    return json_object(ai_job_fs.read_regular_bytes(directory_fd, name), name)


def _find_existing_job(
    job_root: Path,
    directories: dict[str, int],
    job_name: str,
    source_job_id: str,
    source_digest: str,
    new_job_id: str,
) -> Path | None:
    for state in ai_jobs.QUEUE_STATES:
        directory_fd = directories[state]
        if not ai_job_fs.entry_exists(directory_fd, job_name):
            continue
        payload = json_object(
            ai_job_fs.read_regular_bytes(directory_fd, job_name),
            job_name,
        )
        expected = {
            "job_id": new_job_id,
            "queue_status": state,
            "requeued_from": source_job_id,
            "quarantined_sha256": source_digest,
        }
        if any(payload.get(key) != value for key, value in expected.items()):
            raise ai_jobs.AiJobError(
                "existing requeue job does not match its provenance record"
            )
        return job_root / state / job_name
    return None
