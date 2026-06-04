"""Auditor-backed Architect review orchestration tests."""

import json
from pathlib import Path

import pytest

from entroping.brain.architect_audit import (
    ArchitectAuditorReviewResult,
    ArchitectAuditReviewParseError,
    _auditor_source_context,
    parse_auditor_review,
    render_auditor_review_json,
    render_auditor_review_markdown,
    run_architect_auditor_review,
)
from entroping.brain.litellm_client import LiteLLMClient, LiteLLMCompletionResult, LiteLLMUsage
from entroping.brain.prompt_builder import ArchitectPromptPackage
from entroping.bridge.openapi_audit import OpenApiAuditFinding, OpenApiAuditReport
from entroping.core.config_loader import load_qanstitution
from entroping.models import ArchitectAuditReview, ArchitectAuditReviewFinding


def _write_project(tmp_path: Path) -> None:
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "auditor.md").write_text(
        "Review test coverage and policy risk. Do not edit files.",
        encoding="utf-8",
    )
    (tmp_path / "qanstitution.yaml").write_text(
        """
project: checkout-api
sources:
  spec: openapi.yaml
agents:
  auditor:
    source: agents/auditor.md
    model: openai/auditor-model
    temperature: 0.0
gates:
  - id: global_latency
    condition: "true"
    gate: duration < 2000
    enforcement: block
""".lstrip(),
        encoding="utf-8",
    )


def _coverage_report() -> OpenApiAuditReport:
    return OpenApiAuditReport(
        total_operations=2,
        covered_operations=1,
        missing_operations=1,
        findings=(
            OpenApiAuditFinding(
                code="OPENAPI_COVERAGE_MISSING",
                severity="error",
                operation_id="createCheckout",
                method="POST",
                path="/checkout",
                message="OpenAPI operation 'createCheckout' has no committed Hurl coverage.",
            ),
        ),
    )


def test_run_architect_auditor_review_parses_provider_findings_without_writing(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    law = load_qanstitution(tmp_path / "qanstitution.yaml")
    packages: list[ArchitectPromptPackage] = []

    def fake_completion(**kwargs: object) -> dict[str, object]:
        _ = kwargs
        return {
            "model": "openai/auditor-model",
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "summary": "Auth coverage is too thin.",
                                "findings": [
                                    {
                                        "code": "AUTH_NEGATIVE_COVERAGE",
                                        "severity": "error",
                                        "title": "Missing unauthorized checkout test",
                                        "detail": (
                                            "Checkout has generated coverage but no committed "
                                            "401 or 403 assertion."
                                        ),
                                        "recommendation": (
                                            "Add a Breaker-generated invalid-token checkout test."
                                        ),
                                        "evidence": [
                                            "operation:createCheckout",
                                            "gate:global_latency",
                                        ],
                                    }
                                ],
                                "warnings": ["Review with the service owner before merging."],
                            },
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 15, "total_tokens": 27},
        }

    class CapturingClient(LiteLLMClient):
        def complete(self, package: ArchitectPromptPackage) -> LiteLLMCompletionResult:
            packages.append(package)
            return super().complete(package)

    result = run_architect_auditor_review(
        law=law,
        deterministic_report=_coverage_report(),
        project_root=tmp_path,
        config_path=tmp_path / "qanstitution.yaml",
        client=CapturingClient(completion_func=fake_completion),
    )

    assert result.agent == "auditor"
    assert result.model == "openai/auditor-model"
    assert result.usage.total_tokens == 27
    assert not result.passed
    assert result.review.summary == "Auth coverage is too thin."
    assert result.review.findings[0].code == "AUTH_NEGATIVE_COVERAGE"
    assert not (tmp_path / "reports").exists()
    assert packages
    assert packages[0].role == "auditor"
    assert packages[0].model == "openai/auditor-model"
    assert "Review test coverage and policy risk" in packages[0].messages[0].content
    assert "Return structured JSON matching the Auditor review schema" in (
        packages[0].messages[0].content
    )
    assert "OPENAPI_COVERAGE_MISSING" in packages[0].messages[1].content
    assert "global_latency" in packages[0].messages[0].content

    markdown = render_auditor_review_markdown(result)
    assert "# Architect Auditor Review" in markdown
    assert "AUTH_NEGATIVE_COVERAGE" in markdown
    assert "Missing unauthorized checkout test" in markdown

    payload = json.loads(render_auditor_review_json(result))
    assert payload["status"] == "fail"
    assert payload["agent"] == "auditor"
    assert payload["summary"] == "Auth coverage is too thin."
    assert payload["findings"][0]["recommendation"].startswith("Add a Breaker")


def test_run_architect_auditor_review_rejects_invalid_provider_output(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    law = load_qanstitution(tmp_path / "qanstitution.yaml")

    def fake_completion(**kwargs: object) -> dict[str, object]:
        _ = kwargs
        return {"choices": [{"message": {"content": '{"summary": "ok", "edits": []}'}}]}

    with pytest.raises(ArchitectAuditReviewParseError, match="findings"):
        run_architect_auditor_review(
            law=law,
            deterministic_report=_coverage_report(),
            project_root=tmp_path,
            config_path=tmp_path / "qanstitution.yaml",
            client=LiteLLMClient(completion_func=fake_completion),
        )


def test_run_architect_auditor_review_rejects_secret_like_provider_output(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    law = load_qanstitution(tmp_path / "qanstitution.yaml")

    def fake_completion(**kwargs: object) -> dict[str, object]:
        _ = kwargs
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "summary": "Leaked sk-proj-live-secret in review",
                                "findings": [],
                            },
                        )
                    }
                }
            ],
        }

    with pytest.raises(ArchitectAuditReviewParseError) as excinfo:
        run_architect_auditor_review(
            law=law,
            deterministic_report=_coverage_report(),
            project_root=tmp_path,
            config_path=tmp_path / "qanstitution.yaml",
            client=LiteLLMClient(completion_func=fake_completion),
        )

    assert "sk-proj-live-secret" not in str(excinfo.value)
    assert "[REDACTED]" in str(excinfo.value)


@pytest.mark.parametrize("content", ["", "   \n"])
def test_parse_auditor_review_rejects_empty_output(content: str) -> None:
    with pytest.raises(ArchitectAuditReviewParseError, match="must not be empty"):
        parse_auditor_review(content)


def test_parse_auditor_review_rejects_invalid_json() -> None:
    with pytest.raises(ArchitectAuditReviewParseError, match="valid JSON object"):
        parse_auditor_review("{not-json")


def test_parse_auditor_review_rejects_non_object_json() -> None:
    with pytest.raises(ArchitectAuditReviewParseError, match="valid JSON object"):
        parse_auditor_review('["not", "an", "object"]')


def test_render_auditor_review_markdown_handles_no_findings(tmp_path: Path) -> None:
    result = ArchitectAuditorReviewResult(
        review=ArchitectAuditReview(
            summary="Coverage looks clean.",
            findings=[],
        ),
        model="openai/auditor-model",
        latency_ms=25,
        usage=LiteLLMUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
        manifest_path=tmp_path / ".entroping" / "agent-runs" / "auditor.json",
    )

    assert render_auditor_review_markdown(result).endswith("No Auditor findings.")


def test_auditor_source_context_reports_empty_hurl_inventory(tmp_path: Path) -> None:
    context = _auditor_source_context(
        deterministic_report=_coverage_report(),
        project_root=tmp_path,
    )

    assert context["tests/hurl-inventory.txt"] == "No committed Hurl tests discovered."


def test_auditor_source_context_reports_empty_existing_tests_dir(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()

    context = _auditor_source_context(
        deterministic_report=_coverage_report(),
        project_root=tmp_path,
    )

    assert context["tests/hurl-inventory.txt"] == "No committed Hurl tests discovered."


def test_auditor_source_context_lists_hurl_inventory(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests" / "api"
    tests_dir.mkdir(parents=True)
    (tests_dir / "checkout.hurl").write_text("GET {{base_url}}/checkout\nHTTP 200\n")

    context = _auditor_source_context(
        deterministic_report=_coverage_report(),
        project_root=tmp_path,
    )

    assert context["tests/hurl-inventory.txt"] == "tests/api/checkout.hurl"


def test_auditor_source_context_truncates_large_hurl_inventory(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    for index in range(201):
        (tests_dir / f"case_{index:03d}.hurl").write_text("GET {{base_url}}/\nHTTP 200\n")

    context = _auditor_source_context(
        deterministic_report=_coverage_report(),
        project_root=tmp_path,
    )

    assert "... truncated after 200 Hurl files" in context["tests/hurl-inventory.txt"]


def test_auditor_review_finding_validates_text_fields() -> None:
    with pytest.raises(ValueError, match="code must not be empty"):
        ArchitectAuditReviewFinding(
            code=" ",
            severity="warn",
            title="Title",
            detail="Detail",
            recommendation="Recommendation",
        )
    with pytest.raises(ValueError, match="code must not contain control characters"):
        ArchitectAuditReviewFinding(
            code="BAD\x01CODE",
            severity="warn",
            title="Title",
            detail="Detail",
            recommendation="Recommendation",
        )
    with pytest.raises(ValueError, match="text must not be empty"):
        ArchitectAuditReviewFinding(
            code="VALID",
            severity="warn",
            title=" ",
            detail="Detail",
            recommendation="Recommendation",
        )
    with pytest.raises(ValueError, match="text must not contain control characters"):
        ArchitectAuditReviewFinding(
            code="VALID",
            severity="warn",
            title="Title",
            detail="Bad\x01detail",
            recommendation="Recommendation",
        )


def test_auditor_review_finding_validates_evidence() -> None:
    with pytest.raises(ValueError, match="evidence must not be empty"):
        ArchitectAuditReviewFinding(
            code="VALID",
            severity="warn",
            title="Title",
            detail="Detail",
            recommendation="Recommendation",
            evidence=[" "],
        )
    with pytest.raises(ValueError, match="evidence must not contain control characters"):
        ArchitectAuditReviewFinding(
            code="VALID",
            severity="warn",
            title="Title",
            detail="Detail",
            recommendation="Recommendation",
            evidence=["operation\x01id"],
        )


def test_auditor_review_validates_summary_and_warnings() -> None:
    with pytest.raises(ValueError, match="summary must not be empty"):
        ArchitectAuditReview(summary=" ", findings=[])
    with pytest.raises(ValueError, match="summary must not contain control characters"):
        ArchitectAuditReview(summary="Bad\x01summary", findings=[])
    with pytest.raises(ValueError, match="warning must not contain control characters"):
        ArchitectAuditReview(summary="Summary", findings=[], warnings=["Bad\x01warning"])
