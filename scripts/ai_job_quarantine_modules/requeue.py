from __future__ import annotations

from pathlib import Path

from scripts import ai_jobs
from scripts.ai_job_quarantine_modules.evidence import validated_quarantined_job
from scripts.ai_job_quarantine_modules.idempotency import write_requeued_job
from scripts.ai_job_quarantine_modules.revalidation import (
    github_issue_snapshot,
    issue_number,
)


def requeue_job(
    repo_root: Path,
    job_root: Path,
    *,
    job_id: str,
    engine: ai_jobs.WorkerEngine,
    profile: str,
    model: str | None,
    apply: bool,
) -> dict[str, object]:
    source_path, source_job, source_digest = validated_quarantined_job(
        job_root,
        job_id,
    )
    issue = issue_number(source_job.get("issue"))
    issue_snapshot = github_issue_snapshot(issue)
    files = ai_jobs._validate_files(
        repo_root,
        tuple(Path(path) for path in ai_jobs._string_list(source_job.get("files"))),
    )
    resolved_model, resolved_profile = ai_jobs._resolve_model(
        engine=engine,
        profile=profile,
        model=model,
    )
    revalidated_job: dict[str, object] = {
        **source_job,
        "engine": engine,
        "profile": resolved_profile,
        "model": resolved_model,
        "files": files,
    }
    if ai_jobs._tier_a_routing_violation(revalidated_job, source_path) is not None:
        msg = f"explicit routing still violates Tier A policy for {job_id}"
        raise ai_jobs.AiJobError(msg)
    revision = ai_jobs._current_revision(repo_root)
    file_sha256 = ai_jobs._selected_file_digests(repo_root, files)
    payload: dict[str, object] = {
        "status": "requeued" if apply else "planned",
        "job_root": str(job_root),
        "source_job_path": str(source_path),
        "revalidation": {
            "issue": issue,
            "issue_state": issue_snapshot["state"],
            "issue_ready": issue_snapshot["ready"],
            "engine": engine,
            "profile": resolved_profile,
            "model": resolved_model,
            "files": files,
            "file_sha256": file_sha256,
            "source_revision": revision,
        },
    }
    if apply:
        payload["job_path"] = str(
            write_requeued_job(
                job_root,
                revalidated_job,
                source_job_id=job_id,
                source_digest=source_digest,
                revision=revision,
                engine=engine,
                profile=resolved_profile,
                model=resolved_model,
                files=files,
                file_sha256=file_sha256,
            )
        )
    return payload
