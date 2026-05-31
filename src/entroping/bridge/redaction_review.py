"""Compile redacted traffic into safe review reports."""

import json
from collections import Counter
from collections.abc import Sequence
from html import escape
from urllib.parse import parse_qsl, urlsplit

from pydantic import BaseModel, ConfigDict, Field

from entroping.models.traffic import TrafficBody, TrafficExchange

REDACTED = "[REDACTED]"


class RedactionReviewCategory(BaseModel):
    """Count for a safe redaction category."""

    model_config = ConfigDict(extra="forbid")

    category: str
    count: int = Field(ge=0)


class RedactionReviewReport(BaseModel):
    """Summary of what was captured and what redaction categories fired."""

    model_config = ConfigDict(extra="forbid")

    total_records: int = Field(ge=0)
    redacted_records: int = Field(ge=0)
    unredacted_records: int = Field(ge=0)
    request_count: int = Field(ge=0)
    response_count: int = Field(ge=0)
    header_categories: tuple[RedactionReviewCategory, ...] = ()
    query_categories: tuple[RedactionReviewCategory, ...] = ()
    body_categories: tuple[RedactionReviewCategory, ...] = ()
    body_summary_categories: tuple[RedactionReviewCategory, ...] = ()


def compile_redaction_review(exchanges: Sequence[TrafficExchange]) -> RedactionReviewReport:
    """Build a counts-only redaction review from traffic records."""

    header_counter: Counter[str] = Counter()
    query_counter: Counter[str] = Counter()
    body_counter: Counter[str] = Counter()
    body_summary_counter: Counter[str] = Counter()
    response_count = 0
    redacted_count = 0

    for exchange in exchanges:
        if exchange.redacted:
            redacted_count += 1
        _count_headers(exchange.request.headers, direction="request", counter=header_counter)
        _count_query(exchange.request.url, counter=query_counter)
        _count_body(
            exchange.request.body,
            direction="request",
            body_counter=body_counter,
            summary_counter=body_summary_counter,
        )
        if exchange.response is None:
            continue
        response_count += 1
        _count_headers(exchange.response.headers, direction="response", counter=header_counter)
        _count_body(
            exchange.response.body,
            direction="response",
            body_counter=body_counter,
            summary_counter=body_summary_counter,
        )

    total_records = len(exchanges)
    return RedactionReviewReport(
        total_records=total_records,
        redacted_records=redacted_count,
        unredacted_records=total_records - redacted_count,
        request_count=total_records,
        response_count=response_count,
        header_categories=_category_rows(header_counter),
        query_categories=_category_rows(query_counter),
        body_categories=_category_rows(body_counter),
        body_summary_categories=_category_rows(body_summary_counter),
    )


def render_redaction_review_markdown(report: RedactionReviewReport) -> str:
    """Render a safe Markdown redaction review."""

    lines = [
        "# Entroping Redaction Review",
        "",
        "Counts only; raw header, query, and body values are not rendered.",
        "",
        "## Summary",
        "",
        f"- Total traffic records: {report.total_records}",
        f"- Redacted records: {report.redacted_records}",
        f"- Unredacted records: {report.unredacted_records}",
        f"- Requests: {report.request_count}",
        f"- Responses: {report.response_count}",
        "",
    ]
    lines.extend(_markdown_table("Header Redactions", report.header_categories))
    lines.extend(_markdown_table("Query Redactions", report.query_categories))
    lines.extend(_markdown_table("Body Redactions", report.body_categories))
    lines.extend(_markdown_table("Body Summaries", report.body_summary_categories))
    return "\n".join(lines).rstrip() + "\n"


def render_redaction_review_html(report: RedactionReviewReport) -> str:
    """Render a safe dependency-free HTML redaction review."""

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Entroping Redaction Review</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    body {{ margin: 2rem; color: #161616; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0 1.5rem; }}
    th, td {{ border: 1px solid #d8d8d8; padding: 0.5rem; text-align: left; }}
    th {{ background: #f4f4f4; }}
  </style>
</head>
<body>
  <h1>Entroping Redaction Review</h1>
  <p>Counts only; raw header, query, and body values are not rendered.</p>
  <h2>Summary</h2>
  <dl>
    <dt>Total traffic records</dt><dd>{report.total_records}</dd>
    <dt>Redacted records</dt><dd>{report.redacted_records}</dd>
    <dt>Unredacted records</dt><dd>{report.unredacted_records}</dd>
    <dt>Requests</dt><dd>{report.request_count}</dd>
    <dt>Responses</dt><dd>{report.response_count}</dd>
  </dl>
  {_html_table("Header Redactions", report.header_categories)}
  {_html_table("Query Redactions", report.query_categories)}
  {_html_table("Body Redactions", report.body_categories)}
  {_html_table("Body Summaries", report.body_summary_categories)}
</body>
</html>
"""


def _count_headers(
    headers: dict[str, str],
    *,
    direction: str,
    counter: Counter[str],
) -> None:
    for name, value in headers.items():
        if REDACTED in value:
            counter[f"{direction} {_header_category(name)}"] += 1


def _count_query(url: str, *, counter: Counter[str]) -> None:
    for key, value in parse_qsl(urlsplit(url).query, keep_blank_values=True):
        if REDACTED in value:
            counter[_query_category(key)] += 1


def _count_body(
    body: TrafficBody | None,
    *,
    direction: str,
    body_counter: Counter[str],
    summary_counter: Counter[str],
) -> None:
    if body is None:
        return

    summary_counter[f"{direction} {_body_summary_category(body)}"] += 1
    if body.truncated:
        summary_counter[f"{direction} truncated body summary"] += 1
    if body.text is None or REDACTED not in body.text:
        return

    content_type = _base_content_type(body)
    if _is_json_content_type(content_type):
        try:
            parsed: object = json.loads(body.text)
        except json.JSONDecodeError:
            body_counter[f"{direction} text body redaction"] += body.text.count(REDACTED)
            return
        _count_json_redactions(parsed, direction=direction, counter=body_counter)
        return

    body_counter[f"{direction} text body redaction"] += body.text.count(REDACTED)


def _count_json_redactions(
    value: object,
    *,
    direction: str,
    counter: Counter[str],
    key: str | None = None,
) -> None:
    if isinstance(value, dict):
        for item_key, item_value in value.items():
            _count_json_redactions(
                item_value,
                direction=direction,
                counter=counter,
                key=str(item_key),
            )
        return
    if isinstance(value, list):
        for item in value:
            _count_json_redactions(item, direction=direction, counter=counter, key=key)
        return
    if isinstance(value, str) and REDACTED in value:
        counter[f"{direction} {_body_field_category(key)}"] += 1


def _header_category(name: str) -> str:
    normalized = name.lower().replace("-", "_")
    if "authorization" in normalized:
        return "authorization header"
    if "cookie" in normalized:
        return "cookie header"
    if "api_key" in normalized or "apikey" in normalized:
        return "API key header"
    if "csrf" in normalized:
        return "CSRF header"
    if _is_token_like(normalized):
        return "token-like header"
    return "redacted header"


def _query_category(name: str) -> str:
    normalized = name.lower().replace("-", "_")
    if "api_key" in normalized or "apikey" in normalized:
        return "API key query parameter"
    if _is_token_like(normalized):
        return "token-like query parameter"
    return "redacted query parameter"


def _body_field_category(name: str | None) -> str:
    if name is None:
        return "text body redaction"
    normalized = name.lower().replace("-", "_")
    if "password" in normalized or "passwd" in normalized:
        return "password body field"
    if "api_key" in normalized or "apikey" in normalized:
        return "API key body field"
    if "authorization" in normalized or normalized == "auth":
        return "authorization body field"
    if "cookie" in normalized:
        return "cookie body field"
    if "session" in normalized:
        return "session body field"
    if _is_token_like(normalized):
        return "token body field"
    if "secret" in normalized:
        return "secret body field"
    return "redacted body field"


def _body_summary_category(body: TrafficBody) -> str:
    if body.text is None:
        return "binary body metadata"
    content_type = _base_content_type(body)
    if _is_json_content_type(content_type):
        return "JSON body summary"
    return "text body summary"


def _is_token_like(normalized_name: str) -> bool:
    return "token" in normalized_name or "jwt" in normalized_name


def _base_content_type(body: TrafficBody) -> str:
    return (body.content_type or "").split(";", maxsplit=1)[0].strip().lower()


def _is_json_content_type(content_type: str) -> bool:
    return content_type == "application/json" or content_type.endswith("+json")


def _category_rows(counter: Counter[str]) -> tuple[RedactionReviewCategory, ...]:
    return tuple(
        RedactionReviewCategory(category=category, count=count)
        for category, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    )


def _markdown_table(title: str, rows: tuple[RedactionReviewCategory, ...]) -> list[str]:
    lines = [f"## {title}", ""]
    if not rows:
        lines.extend(["No categories found.", ""])
        return lines
    lines.extend(["| Category | Count |", "| --- | ---: |"])
    for row in rows:
        lines.append(f"| {row.category} | {row.count} |")
    lines.append("")
    return lines


def _html_table(title: str, rows: tuple[RedactionReviewCategory, ...]) -> str:
    if not rows:
        return f"<h2>{escape(title)}</h2><p>No categories found.</p>"
    table_rows = "\n".join(
        f"      <tr><td>{escape(row.category)}</td><td>{row.count}</td></tr>" for row in rows
    )
    return f"""<h2>{escape(title)}</h2>
  <table>
    <thead><tr><th>Category</th><th>Count</th></tr></thead>
    <tbody>
{table_rows}
    </tbody>
  </table>"""
