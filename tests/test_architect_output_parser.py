"""Architect provider-output parser tests."""

import json

import pytest
from pydantic import ValidationError

from entroping.brain.output_parser import ArchitectOutputParseError, parse_architect_edit_set
from entroping.models import ArchitectEditSet


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


def test_parse_architect_edit_set_does_not_echo_invalid_input_values() -> None:
    secret_provider_context = "provider-private-context"
    json_with_invalid_content = json.dumps(
        {
            "summary": "ok",
            "edits": [
                {
                    "path": "tests/x.hurl",
                    "content": f"GET /health\n# {secret_provider_context}\u0000",
                }
            ],
        },
    )

    with pytest.raises(ArchitectOutputParseError) as exc_info:
        parse_architect_edit_set(json_with_invalid_content)

    assert "content must not contain control characters" in str(exc_info.value)
    assert secret_provider_context not in str(exc_info.value)
    assert json_with_invalid_content not in str(exc_info.value)


def test_parse_architect_edit_set_formats_root_validation_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_root_error(payload: object) -> None:
        _ = payload
        raise ValidationError.from_exception_data(
            "ArchitectEditSet",
            [
                {
                    "type": "value_error",
                    "loc": (),
                    "input": {},
                    "ctx": {"error": ValueError("root object invalid")},
                }
            ],
        )

    monkeypatch.setattr(
        ArchitectEditSet,
        "model_validate",
        staticmethod(raise_root_error),
    )

    with pytest.raises(ArchitectOutputParseError) as exc_info:
        parse_architect_edit_set(
            '{"summary":"ok","edits":[{"path":"tests/x.hurl","content":"GET /\\n"}]}'
        )

    assert str(exc_info.value) == "Invalid Architect edit set: Value error, root object invalid"
