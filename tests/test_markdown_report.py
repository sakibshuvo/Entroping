from html import escape

from entroping.core.evidence_common import safe_evidence_text
from entroping.core.markdown_report import (
    markdown_cell,
    markdown_inline_code,
    markdown_table_row,
)


def _markdown_text(value: str, *, quote: bool) -> str:
    text = value.replace("\r", " ").replace("\\", "\0ENTROPING_BACKSLASH\0")
    text = escape(text, quote=quote).replace("|", "\\|")
    return text.replace("\0ENTROPING_BACKSLASH\0", "&#92;")


def test_markdown_table_row_preserves_cell_boundaries() -> None:
    assert (
        markdown_table_row("a", "b", "c")
        == "| a | b | c |"
    )


def test_notification_markdown_cell_preserves_raw_html_behavior() -> None:
    value = "a|b\\c\nline`<tag>"
    assert (
        markdown_cell(value, style="notification")
        == _markdown_text(value, quote=False).replace("\n", "<br>")
    )


def test_notification_markdown_inline_code_preserves_backtick_and_html_behavior() -> None:
    value = "`x|y\\z\r<hi>"
    assert (
        markdown_inline_code(value, style="notification")
        == _markdown_text(value, quote=False).replace("`", "'")
    )


def test_evidence_cloud_markdown_cell_matches_old_md_behavior() -> None:
    value = "<script>x|y\\z\nline`"
    assert markdown_cell(value, style="evidence_cloud") == (
        safe_evidence_text(value).replace("|", "\\|").replace("\n", " ")
    )


def test_observability_markdown_helpers_preserve_backslashes_and_punctuation() -> None:
    value = "a|b\\c\n*\n_`"
    cell = markdown_cell(value, style="observability")
    assert cell == (
        escape(value)
        .replace("\\", "&#92;")
        .replace("|", "\\|")
        .replace("*", "&#42;")
        .replace("_", "&#95;")
        .replace("`", "&#96;")
        .replace("\n", " ")
    )
    assert markdown_inline_code(value, style="observability") == escape(value).replace("`", "'")
