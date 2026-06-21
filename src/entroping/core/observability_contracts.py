"""Shared value-free observability report contracts."""

from __future__ import annotations

from typing import Final

OBSERVABILITY_FORBIDDEN_VALUE_FIELDS: Final[tuple[str, ...]] = (
    "raw_urls",
    "headers",
    "bodies",
    "cookies",
    "prompts",
    "provider_outputs",
    "credentials",
    "environment_values",
    "webhook_urls",
    "ticket_mutation_payloads",
    "dashboard_payloads",
    "monitor_payloads",
    "source_hurl_contents",
    "raw_traffic",
    "full_report_contents",
)
