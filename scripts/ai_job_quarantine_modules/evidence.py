from __future__ import annotations

import hashlib
import json
from contextlib import ExitStack
from pathlib import Path

from scripts import ai_job_fs, ai_jobs

QUARANTINE_SCHEMA_VERSION = "entroping.ai-job-quarantine.v1"
REQUEUE_SCHEMA_VERSION = "entroping.ai-job-requeue.v1"
QUARANTINE_REASONS = frozenset(
    {
        "issue-revalidation-failed",
        "legacy-revalidation-required",
        "malformed-job",
        "provider-route-violation",
        "selected-files-changed",
        "selected-files-unavailable",
        "stale-revision",
        "tier-a-routing-violation",
    }
)


def validated_quarantined_job(
    job_root: Path,
    job_id: str,
) -> tuple[Path, dict[str, object], str]:
    if not job_id or Path(job_id).name != job_id:
        raise ai_jobs.AiJobError("--job-id must be one path-safe job identifier")
    name = f"{job_id}.json"
    try:
        with ExitStack() as stack:
            quarantined_fd = stack.enter_context(
                ai_job_fs.open_state_directory(
                    job_root,
                    "quarantined",
                    create=False,
                )
            )
            receipt_fd = stack.enter_context(
                ai_job_fs.open_state_directory(
                    job_root,
                    "quarantine-receipts",
                    create=False,
                )
            )
            source_bytes = ai_job_fs.read_regular_bytes(quarantined_fd, name)
            receipt = json_object(
                ai_job_fs.read_regular_bytes(receipt_fd, name),
                name,
            )
    except (FileNotFoundError, ai_job_fs.SafeStateError) as exc:
        msg = f"quarantine evidence is missing or unsafe: {job_id}"
        raise ai_jobs.AiJobError(msg) from exc
    digest = hashlib.sha256(source_bytes).hexdigest()
    if receipt.get("sha256") != digest:
        raise ai_jobs.AiJobError(
            f"quarantined job digest does not match receipt: {job_id}"
        )
    expected_receipt = {
        "schema_version": QUARANTINE_SCHEMA_VERSION,
        "job_id": job_id,
        "source_path": str(job_root / "queued" / name),
        "quarantined_path": str(job_root / "quarantined" / name),
    }
    if any(receipt.get(key) != value for key, value in expected_receipt.items()):
        raise ai_jobs.AiJobError(f"quarantine receipt provenance is invalid: {job_id}")
    if receipt.get("reason") not in QUARANTINE_REASONS:
        raise ai_jobs.AiJobError(f"quarantine receipt reason is invalid: {job_id}")
    quarantined_at = receipt.get("quarantined_at")
    if not isinstance(quarantined_at, str) or not quarantined_at:
        raise ai_jobs.AiJobError(f"quarantine receipt timestamp is invalid: {job_id}")
    job = json_object(source_bytes, name)
    structure_error = ai_jobs._job_structure_error(job)
    if structure_error is not None:
        raise ai_jobs.AiJobError(
            f"quarantined job is structurally invalid: {structure_error}"
        )
    if job.get("job_id") != job_id:
        raise ai_jobs.AiJobError(
            f"quarantined job id does not match filename: {job_id}"
        )
    if job.get("autonomy_tier") != "tier_a":
        raise ai_jobs.AiJobError(
            f"only quarantined Tier A jobs can be requeued here: {job_id}"
        )
    return job_root / "quarantined" / name, job, digest


def json_object(raw: bytes, name: str) -> dict[str, object]:
    try:
        raw_payload: object = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ai_jobs.AiJobError(f"state entry is malformed JSON: {name}") from exc
    if not isinstance(raw_payload, dict):
        raise ai_jobs.AiJobError(f"state entry is not an object: {name}")
    payload: dict[str, object] = {}
    for key, value in raw_payload.items():
        if not isinstance(key, str):
            raise ai_jobs.AiJobError(f"state entry has a non-string key: {name}")
        payload[key] = value
    return payload


def validate_requeue_record(
    record: dict[str, object],
    *,
    source_job_id: str,
    source_digest: str,
    new_job_id: str,
) -> None:
    expected = {
        "schema_version": REQUEUE_SCHEMA_VERSION,
        "source_job_id": source_job_id,
        "source_sha256": source_digest,
        "new_job_id": new_job_id,
    }
    if any(record.get(key) != value for key, value in expected.items()):
        raise ai_jobs.AiJobError("requeue idempotency record does not match source")
