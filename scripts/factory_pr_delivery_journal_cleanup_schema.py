"""Cleanup intent persistence schema with ordered proof replay constraints."""

from __future__ import annotations

CLEANUP_DDL = (
    "CREATE TABLE delivery_cleanup("
    "request_id TEXT PRIMARY KEY, "
    "remote_branch TEXT NOT NULL, "
    "expected_remote_head TEXT NOT NULL, "
    "scheduler_owner_id TEXT NOT NULL, "
    "scheduler_owner_pid INTEGER NOT NULL CHECK(scheduler_owner_pid BETWEEN 1 AND 2147483647), "
    "scheduler_owner_start_token TEXT NOT NULL, "
    "scheduler_owner_epoch INTEGER NOT NULL CHECK(scheduler_owner_epoch > 0), "
    "scheduler_phase_version INTEGER NOT NULL CHECK(scheduler_phase_version > 0), "
    "cleanup_intent_at_utc TEXT NOT NULL, "
    "remote_absent_at_utc TEXT, "
    "finish_cleanup_at_utc TEXT, "
    "scheduler_completion_at_utc TEXT, "
    "scheduler_completed_at_utc TEXT, "
    "phase_version INTEGER NOT NULL CHECK(phase_version > 0 AND phase_version = 1 + "
    "(CAST(remote_absent_at_utc IS NOT NULL AS INTEGER) + "
    "CAST(finish_cleanup_at_utc IS NOT NULL AS INTEGER) + "
    "CAST(scheduler_completion_at_utc IS NOT NULL AS INTEGER) + "
    "CAST(scheduler_completed_at_utc IS NOT NULL AS INTEGER))), "
    "FOREIGN KEY(request_id) REFERENCES delivery_lifecycle(request_id), "
    "CHECK(finish_cleanup_at_utc IS NULL OR finish_cleanup_at_utc >= cleanup_intent_at_utc), "
    "CHECK(remote_absent_at_utc IS NULL OR (finish_cleanup_at_utc IS NOT NULL AND "
    "remote_absent_at_utc >= finish_cleanup_at_utc)), "
    "CHECK(scheduler_completion_at_utc IS NULL OR (remote_absent_at_utc IS NOT NULL AND "
    "scheduler_completion_at_utc >= remote_absent_at_utc)), "
    "CHECK(scheduler_completed_at_utc IS NULL OR (scheduler_completion_at_utc IS NOT NULL AND "
    "scheduler_completed_at_utc = scheduler_completion_at_utc))"
    ") STRICT"
)

CLEANUP_TRIGGER_IMMUTABLE_IDENTITY = (
    "CREATE TRIGGER trg_delivery_cleanup_immutable_identity BEFORE UPDATE ON delivery_cleanup "
    "WHEN NEW.request_id != OLD.request_id OR NEW.remote_branch != OLD.remote_branch OR "
    "NEW.expected_remote_head != OLD.expected_remote_head OR NEW.scheduler_owner_id != "
    "OLD.scheduler_owner_id OR NEW.scheduler_owner_pid != OLD.scheduler_owner_pid OR "
    "NEW.scheduler_owner_start_token != OLD.scheduler_owner_start_token OR "
    "NEW.scheduler_owner_epoch != OLD.scheduler_owner_epoch OR "
    "NEW.scheduler_phase_version != OLD.scheduler_phase_version OR "
    "NEW.cleanup_intent_at_utc != OLD.cleanup_intent_at_utc "
    "BEGIN SELECT RAISE(ABORT, 'journal-invalid'); END"
)

CLEANUP_TRIGGER_NO_REWRITE_PROOFS = (
    "CREATE TRIGGER trg_delivery_cleanup_no_rewrite_proofs BEFORE UPDATE ON "
    "delivery_cleanup "
    "WHEN (OLD.remote_absent_at_utc IS NOT NULL AND (NEW.remote_absent_at_utc IS NULL OR "
    "NEW.remote_absent_at_utc != OLD.remote_absent_at_utc)) OR "
    "(OLD.finish_cleanup_at_utc IS NOT NULL AND (NEW.finish_cleanup_at_utc IS NULL OR "
    "NEW.finish_cleanup_at_utc != OLD.finish_cleanup_at_utc)) OR "
    "(OLD.scheduler_completion_at_utc IS NOT NULL AND (NEW.scheduler_completion_at_utc IS NULL OR "
    "NEW.scheduler_completion_at_utc != OLD.scheduler_completion_at_utc)) OR "
    "(OLD.scheduler_completed_at_utc IS NOT NULL AND (NEW.scheduler_completed_at_utc IS NULL OR "
    "NEW.scheduler_completed_at_utc != OLD.scheduler_completed_at_utc)) "
    "BEGIN SELECT RAISE(ABORT, 'journal-invalid'); END"
)

CLEANUP_TRIGGER_NO_DELETE = (
    "CREATE TRIGGER trg_delivery_cleanup_no_delete BEFORE DELETE ON delivery_cleanup "
    "BEGIN SELECT RAISE(ABORT, 'journal-invalid'); END"
)

CLEANUP_TRIGGER_CREATORS = (
    CLEANUP_TRIGGER_IMMUTABLE_IDENTITY,
    CLEANUP_TRIGGER_NO_REWRITE_PROOFS,
    CLEANUP_TRIGGER_NO_DELETE,
)
