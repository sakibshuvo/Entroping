"""Architect provider-output parser tests."""

import pytest

from entroping.brain.output_parser import ArchitectOutputParseError, parse_architect_edit_set


def test_parse_architect_edit_set_accepts_valid_json_object() -> None:
    parsed = parse_architect_edit_set(
        """
{
  "summary": "Add refund smoke test",
  "edits": [
    {
      "path": "tests/generated/refund_flow.hurl",
      "content": "GET {{base_url}}/refunds\\nHTTP 200\\n",
      "rationale": "Refund coverage"
    }
  ],
  "warnings": []
}
""".strip()
    )

    assert parsed.summary == "Add refund smoke test"
    assert parsed.edits[0].path == "tests/generated/refund_flow.hurl"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("", "must not be empty"),
        ("not json", "valid JSON object"),
        ('["not", "object"]', "valid JSON object"),
        ('{"summary":"ok","edits":[]}', "List should have at least 1 item"),
        (
            '{"summary":"ok","edits":[{"path":"../x.hurl","content":"GET /\\nHTTP 200\\n"}]}',
            "path must not contain parent traversal",
        ),
        (
            '{"summary":"ok","edits":[{"path":"tests/x.hurl","content":"GET /\\u0000"}]}',
            "content must not contain control characters",
        ),
        (
            '{"summary":"ok","edits":[{"path":"tests/x.hurl","content":"GET /\\nHTTP 200\\n",'
            '"extra":"bad"}]}',
            "Extra inputs are not permitted",
        ),
    ],
)
def test_parse_architect_edit_set_rejects_unsafe_provider_content(
    content: str,
    message: str,
) -> None:
    with pytest.raises(ArchitectOutputParseError, match=message):
        parse_architect_edit_set(content)
