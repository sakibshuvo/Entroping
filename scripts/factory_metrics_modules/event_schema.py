"""Factory metrics event schema constants."""

from __future__ import annotations

import re
from datetime import timezone as datetime_timezone
from pathlib import Path

EVENT_SCHEMA_VERSION = "entroping.factory-metrics.v1"

SUMMARY_SCHEMA_VERSION = "entroping.factory-metrics-summary.v1"

REPORT_SCHEMA_VERSION = "entroping.factory-metrics-report.v1"

CONTEXT_SCORECARD_SCHEMA_VERSION = "entroping.context-tool-scorecard.v1"

CONTEXT_SCORECARD_REPORT_SCHEMA_VERSION = "entroping.context-tool-scorecard-report.v1"

READINESS_SCHEMA_VERSION = "entroping.factory-readiness.v1"

DEFAULT_LEDGER = Path(".entroping") / "factory-metrics" / "events.jsonl"

FINISHED_ISSUES_DIR = Path(".entroping") / "factory-metrics" / "finished-issues"

FINISHED_ISSUE_DIR_RE = re.compile(r"^issue-(?P<issue>\d+)$")

UTC_TZ = datetime_timezone.utc  # noqa: UP017 - factory scripts run under Python 3.9.

ROLES = {
    "product_manager",
    "architect",
    "dev_agent",
    "qa_agent",
    "code_review_agent",
    "security_agent",
    "monitoring_agent",
    "integrator",
}

EVENT_TYPES = {
    "context_pack",
    "graph_probe",
    "worker_job",
    "gate_run",
    "code_review",
    "pr_check",
    "outcome",
}

OUTCOMES = {"success", "failure", "skipped", "blocked", "inconclusive"}

DECISIONS = {"accepted", "rejected", "needs_review", "escalated", "not_applicable"}

INTEGER_METRICS = (
    "context_bytes",
    "estimated_tokens",
    "candidate_files",
    "files_read",
    "files_touched",
    "tests_run",
    "gates_run",
)

FLOAT_METRICS = ("duration_seconds", "cost_usd")

ALL_METRICS = INTEGER_METRICS + FLOAT_METRICS

ALLOWED_METRIC_KEYS = set(ALL_METRICS)

ALLOWED_EVENT_KEYS = {
    "schema_version",
    "event_id",
    "recorded_at",
    "event_type",
    "role",
    "agent",
    "tool",
    "provider",
    "model",
    "issue",
    "pr",
    "worktree",
    "metrics",
    "gates",
    "checks",
    "outcome",
    "decision",
    "note",
}

TEXT_FIELDS = {
    "agent",
    "event_id",
    "tool",
    "provider",
    "recorded_at",
    "model",
    "issue",
    "pr",
    "worktree",
    "note",
}

CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x1f\x7f]")

SECRET_REDACTIONS = (
    (
        re.compile(r"(?i)\b(authorization\s*:\s*bearer\s+)([A-Za-z0-9._~+/=-]{8,})"),
        r"\1<redacted>",
    ),
    (
        re.compile(
            r"(?i)\b([A-Za-z0-9_.-]*(?:api[_-]?key|access[_-]?key|"
            r"access[_-]?token|refresh[_-]?token|id[_-]?token|token|secret|"
            r"password|credential|cookie)[A-Za-z0-9_.-]*)(\s*[:=]\s*)"
            r"([^\s,;]+)"
        ),
        r"\1\2<redacted>",
    ),
    (
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{8,}|github_pat_[A-Za-z0-9_]{8,})\b"),
        "<redacted>",
    ),
    (
        re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        "<redacted>",
    ),
    (
        re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
        "<redacted>",
    ),
)

NOTE_MAX_LENGTH = 512

NOTE_FORBIDDEN_PATTERN = re.compile(
    r"(?i)(\braw[\s_-]+prompt\b|\bprompt[\s_-]+text\b|"
    r"\bprovider[\s_-]+transcript\b|\braw[\s_-]+traffic\b|"
    r"\brequest[\s_-]+body\b|\bresponse[\s_-]+body\b|"
    r"(?<![A-Za-z0-9_])[\"']?(prompt|transcript|stdout|stderr)[\"']?\s*[:=])"
)
