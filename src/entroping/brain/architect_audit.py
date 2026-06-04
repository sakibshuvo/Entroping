"""Auditor-backed Architect review orchestration."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from html import escape
from pathlib import Path

from pydantic import ValidationError

from entroping.brain.litellm_client import LiteLLMClient, LiteLLMUsage
from entroping.brain.output_parser import _format_validation_error
from entroping.brain.persona_loader import load_agent_persona
from entroping.brain.prompt_builder import build_auditor_prompt_package
from entroping.brain.safety import contains_secret_like_value, redact_secret_like_values
from entroping.bridge.openapi_audit import OpenApiAuditReport, audit_report_to_dict
from entroping.core.agent_manifest import (
    AgentRunManifestInput,
    AgentRunUsageEvidence,
    write_agent_run_manifest,
)
from entroping.models import ArchitectAuditReview
from entroping.models.qanstitution import Qanstitution

_MAX_HURL_INVENTORY = 200


class ArchitectAuditReviewParseError(ValueError):
    """Raised when provider output cannot become a validated Auditor review."""


@dataclass(frozen=True)
class ArchitectAuditorReviewResult:
    """Result of a validated Auditor-backed review."""

    review: ArchitectAuditReview
    model: str
    latency_ms: int
    usage: LiteLLMUsage
    manifest_path: Path
    agent: str = "auditor"

    @property
    def passed(self) -> bool:
        """Return true when the review has no blocking findings."""

        return self.review.passed


def run_architect_auditor_review(
    *,
    law: Qanstitution,
    deterministic_report: OpenApiAuditReport,
    project_root: str | Path = ".",
    config_path: str | Path = "qanstitution.yaml",
    client: LiteLLMClient | None = None,
) -> ArchitectAuditorReviewResult:
    """Run an explicit Auditor-backed review without modifying project files."""

    persona = load_agent_persona(law, "auditor", config_path=config_path)
    package = build_auditor_prompt_package(
        law=law,
        persona=persona,
        source_context=_auditor_source_context(
            deterministic_report=deterministic_report,
            project_root=Path(project_root),
        ),
    )
    completion = (client or LiteLLMClient()).complete(package)
    review = parse_auditor_review(completion.content)
    manifest = write_agent_run_manifest(
        AgentRunManifestInput(
            project_root=Path(project_root),
            command="architect audit",
            mode="review",
            agent="auditor",
            model=completion.model,
            persona_source_path=persona.source_path,
            persona_content=persona.content,
            prompt_intent="architect audit --focus auditor",
            prompt_package_messages=tuple(message.content for message in package.messages),
            output_paths=(),
            tags=(),
            validation_status="passed",
            structured_output_validated=True,
            hurl_validated=False,
            latency_ms=completion.latency_ms,
            usage=AgentRunUsageEvidence(
                prompt_tokens=completion.usage.prompt_tokens,
                completion_tokens=completion.usage.completion_tokens,
                total_tokens=completion.usage.total_tokens,
            ),
        )
    )
    return ArchitectAuditorReviewResult(
        review=review,
        model=completion.model,
        latency_ms=completion.latency_ms,
        usage=completion.usage,
        manifest_path=manifest.manifest_path,
    )


def parse_auditor_review(content: str) -> ArchitectAuditReview:
    """Parse provider JSON content into a strict Auditor review."""

    if not content.strip():
        msg = "Auditor output must not be empty"
        raise ArchitectAuditReviewParseError(msg)
    if contains_secret_like_value(content):
        msg = (
            "Auditor output must not contain secret-like values: "
            f"{redact_secret_like_values(content)}"
        )
        raise ArchitectAuditReviewParseError(msg)

    try:
        payload: object = json.loads(content)
    except json.JSONDecodeError as exc:
        message = redact_secret_like_values(exc.msg)
        msg = f"Auditor output must be a valid JSON object: {message}"
        raise ArchitectAuditReviewParseError(msg) from exc
    if not isinstance(payload, Mapping):
        msg = "Auditor output must be a valid JSON object"
        raise ArchitectAuditReviewParseError(msg)

    try:
        return ArchitectAuditReview.model_validate(payload)
    except ValidationError as exc:
        msg = f"Invalid Auditor review: {_format_validation_error(exc)}"
        raise ArchitectAuditReviewParseError(msg) from exc


def render_auditor_review_json(result: ArchitectAuditorReviewResult) -> str:
    """Render a machine-readable Auditor review payload."""

    payload = {
        "agent": result.agent,
        "findings": [finding.model_dump() for finding in result.review.findings],
        "latency_ms": result.latency_ms,
        "model": result.model,
        "status": "pass" if result.passed else "fail",
        "summary": result.review.summary,
        "usage": {
            "completion_tokens": result.usage.completion_tokens,
            "prompt_tokens": result.usage.prompt_tokens,
            "total_tokens": result.usage.total_tokens,
        },
        "warnings": result.review.warnings,
    }
    return f"{json.dumps(payload, indent=2, sort_keys=True)}\n"


def render_auditor_review_markdown(result: ArchitectAuditorReviewResult) -> str:
    """Render a compact Markdown Auditor review for humans."""

    lines = [
        "# Architect Auditor Review",
        "",
        f"Status: {'pass' if result.passed else 'fail'}",
        f"Agent: {result.agent}",
        f"Model: {result.model} ({result.latency_ms} ms)",
        "",
        "## Summary",
        "",
        result.review.summary,
        "",
    ]
    if result.review.warnings:
        lines.extend(["## Warnings", ""])
        for warning in result.review.warnings:
            lines.append(f"- {_markdown_text(warning)}")
        lines.append("")

    lines.extend(["## Findings", ""])
    if not result.review.findings:
        lines.append("No Auditor findings.")
        return "\n".join(lines)

    lines.extend(
        [
            "| Severity | Code | Title | Recommendation |",
            "| --- | --- | --- | --- |",
        ]
    )
    for finding in result.review.findings:
        lines.append(
            "| "
            f"{_markdown_cell(finding.severity)} | "
            f"{_markdown_cell(finding.code)} | "
            f"{_markdown_cell(finding.title)} | "
            f"{_markdown_cell(finding.recommendation)} |"
        )
    return "\n".join(lines)


def _auditor_source_context(
    *,
    deterministic_report: OpenApiAuditReport,
    project_root: Path,
) -> dict[str, str]:
    return {
        "reports/architect-openapi-audit.json": json.dumps(
            audit_report_to_dict(deterministic_report),
            indent=2,
            sort_keys=True,
        ),
        "tests/hurl-inventory.txt": _hurl_inventory(project_root),
    }


def _hurl_inventory(project_root: Path) -> str:
    tests_root = project_root / "tests"
    if not tests_root.exists():
        return "No committed Hurl tests discovered."

    paths: list[str] = []
    for path in sorted(tests_root.rglob("*.hurl")):
        if len(paths) >= _MAX_HURL_INVENTORY:
            paths.append(f"... truncated after {_MAX_HURL_INVENTORY} Hurl files")
            break
        relative = path.relative_to(project_root)
        paths.append(relative.as_posix())
    if not paths:
        return "No committed Hurl tests discovered."
    return "\n".join(paths)


def _markdown_cell(value: str) -> str:
    return _markdown_text(value).replace("|", "\\|")


def _markdown_text(value: str) -> str:
    return escape(value, quote=True)
