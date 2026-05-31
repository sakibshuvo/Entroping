"""Tests for safe captured-traffic redaction review reports."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from entroping.bridge.redaction_review import (
    RedactionReviewCategory,
    compile_redaction_review,
    render_redaction_review_html,
    render_redaction_review_markdown,
)
from entroping.core import redaction_review_report
from entroping.core.redaction_review_report import RedactionReviewError, run_redaction_review
from entroping.core.traffic_redactor import redact_traffic_exchange
from entroping.core.traffic_store import TrafficStore, TrafficStoreError
from entroping.models.traffic import TrafficBody, TrafficExchange, TrafficRequest, TrafficResponse


def _raw_exchange(secret: str = "review-secret") -> TrafficExchange:
    return TrafficExchange(
        captured_at=datetime(2026, 5, 31, 12, 0, tzinfo=UTC),
        duration_ms=33,
        request=TrafficRequest(
            method="POST",
            url=f"https://api.example.test/checkout?token={secret}&cart_id=cart-1",
            headers={
                "Authorization": f"Bearer {secret}",
                "Content-Type": "application/json",
                "X-Request-Id": "req-123",
            },
            body=TrafficBody(
                content_type="application/json",
                size_bytes=96,
                text=f'{{"password":"{secret}","nested":{{"api_key":"{secret}"}}}}',
            ),
        ),
        response=TrafficResponse(
            status_code=201,
            headers={
                "Content-Type": "application/json",
                "Set-Cookie": f"session={secret}",
            },
            body=TrafficBody(
                content_type="application/json",
                size_bytes=48,
                text=f'{{"token":"{secret}","ok":true}}',
            ),
        ),
    )


def _counts(rows: tuple[RedactionReviewCategory, ...]) -> dict[str, int]:
    return {row.category: row.count for row in rows}


def test_compile_redaction_review_counts_categories_without_secret_values() -> None:
    redacted = redact_traffic_exchange(_raw_exchange(secret="captured-secret"))

    report = compile_redaction_review([redacted])

    assert report.total_records == 1
    assert report.redacted_records == 1
    assert report.unredacted_records == 0
    assert _counts(report.header_categories) == {
        "request authorization header": 1,
        "response cookie header": 1,
    }
    assert _counts(report.query_categories) == {"token-like query parameter": 1}
    assert _counts(report.body_categories) == {
        "request password body field": 1,
        "request API key body field": 1,
        "response token body field": 1,
    }
    assert _counts(report.body_summary_categories) == {
        "request JSON body summary": 1,
        "response JSON body summary": 1,
    }
    assert "captured-secret" not in report.model_dump_json()


def test_redaction_review_renderers_do_not_emit_raw_secrets() -> None:
    redacted = redact_traffic_exchange(_raw_exchange(secret="html-secret"))
    report = compile_redaction_review([redacted])

    markdown = render_redaction_review_markdown(report)
    html = render_redaction_review_html(report)

    assert "# Entroping Redaction Review" in markdown
    assert "Counts only" in markdown
    assert "<h1>Entroping Redaction Review</h1>" in html
    assert "request authorization header" in markdown
    assert "response token body field" in html
    assert "html-secret" not in markdown
    assert "html-secret" not in html
    assert "[REDACTED]" not in markdown
    assert "[REDACTED]" not in html


def test_redaction_review_surfaces_unredacted_records_without_rendering_values() -> None:
    report = compile_redaction_review([_raw_exchange(secret="unsafe-secret")])

    markdown = render_redaction_review_markdown(report)
    html = render_redaction_review_html(report)

    assert report.redacted_records == 0
    assert report.unredacted_records == 1
    assert "Unredacted records: 1" in markdown
    assert "unsafe-secret" not in markdown
    assert "No categories found." in html


def test_redaction_review_counts_text_and_binary_body_summaries() -> None:
    text_exchange = _raw_exchange(secret="text-secret").model_copy(
        update={
            "request": _raw_exchange().request.model_copy(
                update={
                    "headers": {"Content-Type": "text/plain"},
                    "body": TrafficBody(
                        content_type="text/plain",
                        size_bytes=64,
                        text="token=text-secret",
                        truncated=True,
                    ),
                }
            ),
            "response": None,
        }
    )
    binary_exchange = _raw_exchange(secret="binary-secret").model_copy(
        update={
            "request": _raw_exchange().request.model_copy(
                update={
                    "headers": {"Content-Type": "application/octet-stream"},
                    "body": TrafficBody(
                        content_type="application/octet-stream",
                        size_bytes=128,
                        text=None,
                    ),
                }
            ),
            "response": None,
        }
    )

    report = compile_redaction_review(
        [
            redact_traffic_exchange(text_exchange),
            redact_traffic_exchange(binary_exchange),
        ]
    )

    assert _counts(report.body_categories) == {"request text body redaction": 1}
    assert _counts(report.body_summary_categories) == {
        "request binary body metadata": 1,
        "request text body summary": 1,
        "request truncated body summary": 1,
    }


def test_redaction_review_counts_all_safe_category_fallbacks() -> None:
    redacted_exchange = TrafficExchange(
        captured_at=datetime(2026, 5, 31, 12, 2, tzinfo=UTC),
        duration_ms=14,
        redacted=True,
        request=TrafficRequest(
            method="POST",
            url=(
                "https://api.example.test/audit?"
                "api_key=[REDACTED]&custom_secret=[REDACTED]"
            ),
            headers={
                "X-Api-Key": "[REDACTED]",
                "X-CSRF-Token": "[REDACTED]",
                "X-Auth-Token": "[REDACTED]",
                "X-Custom-Secret": "[REDACTED]",
            },
            body=TrafficBody(
                content_type="application/json",
                size_bytes=180,
                text=(
                    '{"authorization":"[REDACTED]","cookie":"[REDACTED]",'
                    '"session_id":"[REDACTED]","client_secret":"[REDACTED]",'
                    '"api_key":"[REDACTED]","safe_label":"[REDACTED]",'
                    '"items":["[REDACTED]"]}'
                ),
            ),
        ),
        response=TrafficResponse(
            status_code=200,
            headers={},
            body=TrafficBody(
                content_type="application/problem+json",
                size_bytes=24,
                text='["[REDACTED]"]',
            ),
        ),
    )
    no_body_exchange = TrafficExchange(
        captured_at=datetime(2026, 5, 31, 12, 3, tzinfo=UTC),
        duration_ms=7,
        redacted=True,
        request=TrafficRequest(
            method="GET",
            url="https://api.example.test/health",
            headers={},
            body=None,
        ),
        response=None,
    )
    invalid_json_exchange = TrafficExchange(
        captured_at=datetime(2026, 5, 31, 12, 4, tzinfo=UTC),
        duration_ms=9,
        redacted=True,
        request=TrafficRequest(
            method="POST",
            url="https://api.example.test/broken",
            headers={},
            body=TrafficBody(
                content_type="application/json",
                size_bytes=24,
                text='{"token":"[REDACTED]"',
            ),
        ),
        response=None,
    )

    report = compile_redaction_review(
        [redacted_exchange, no_body_exchange, invalid_json_exchange]
    )

    assert _counts(report.header_categories) == {
        "request API key header": 1,
        "request CSRF header": 1,
        "request redacted header": 1,
        "request token-like header": 1,
    }
    assert _counts(report.query_categories) == {
        "API key query parameter": 1,
        "redacted query parameter": 1,
    }
    assert _counts(report.body_categories) == {
        "request API key body field": 1,
        "request authorization body field": 1,
        "request cookie body field": 1,
        "request redacted body field": 2,
        "request secret body field": 1,
        "request session body field": 1,
        "request text body redaction": 1,
        "response text body redaction": 1,
    }


def test_run_redaction_review_wraps_traffic_store_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    (state_dir / "state.db").write_text("not sqlite\n", encoding="utf-8")

    def fail_open(project_root: Path) -> object:
        _ = project_root
        raise TrafficStoreError("traffic store failed")

    monkeypatch.setattr(
        "entroping.core.redaction_review_report.TrafficStore.open_project",
        staticmethod(fail_open),
    )

    with pytest.raises(RedactionReviewError, match="traffic store failed"):
        run_redaction_review(project_root=tmp_path, output="md")


def test_run_redaction_review_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = TrafficStore.open_project(tmp_path)
    store.record_exchange(redact_traffic_exchange(_raw_exchange()))

    def fail_write(path: Path, content: str, *, artifact: str, root: Path | None = None) -> Path:
        _ = path, content, artifact, root
        from entroping.core.safe_write import SafeWriteError

        raise SafeWriteError("cannot write redaction report")

    monkeypatch.setattr(redaction_review_report, "safe_write_text", fail_write)

    with pytest.raises(RedactionReviewError, match="cannot write redaction report"):
        run_redaction_review(project_root=tmp_path, output="md")
