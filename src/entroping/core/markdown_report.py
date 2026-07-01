from __future__ import annotations

from html import escape
from typing import Literal

from entroping.core.evidence_common import safe_evidence_text

MarkdownCellStyle = Literal["notification", "observability", "evidence_cloud"]


def markdown_table_row(*cells: str) -> str:
    return "| " + " | ".join(cells) + " |"


def markdown_inline_code(value: str, *, style: MarkdownCellStyle) -> str:
    if style == "evidence_cloud":
        raise ValueError("evidence_cloud has no inline-code helper")
    if style == "notification":
        return _markdown_text(value, sanitize=False, quote=False).replace("`", "'")
    return escape(value).replace("`", "'")


def markdown_cell(value: object, *, style: MarkdownCellStyle) -> str:
    if style == "notification":
        return _markdown_text(str(value), sanitize=False, quote=False).replace("\n", "<br>")
    if style == "observability":
        escaped = escape(str(value))
        return (
            escaped.replace("\\", "&#92;")
            .replace("|", "\\|")
            .replace("*", "&#42;")
            .replace("_", "&#95;")
            .replace("`", "&#96;")
            .replace("\n", " ")
        )
    return safe_evidence_text(str(value)).replace("|", "\\|").replace("\n", " ")


def _markdown_text(
    value: str,
    *,
    sanitize: bool,
    quote: bool,
) -> str:
    text = safe_evidence_text(value) if sanitize else value
    placeholder = "\0ENTROPING_BACKSLASH\0"
    text = text.replace("\r", " ").replace("\\", placeholder)
    text = escape(text, quote=quote).replace("|", "\\|")
    return text.replace(placeholder, "&#92;")
