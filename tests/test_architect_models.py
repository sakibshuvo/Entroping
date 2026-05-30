"""Architect domain model tests."""

import pytest
from pydantic import ValidationError

from entroping.models import ArchitectEdit, ArchitectEditSet


def test_architect_edit_accepts_safe_hurl_target() -> None:
    edit = ArchitectEdit(
        path="tests/generated/refund_flow.hurl",
        content="# entroping: tags=generated\n\nGET {{base_url}}/refunds\nHTTP 200\n",
        rationale="Add refund smoke coverage.",
    )

    assert edit.path == "tests/generated/refund_flow.hurl"


@pytest.mark.parametrize(
    ("path", "message"),
    [
        ("", "path must not be empty"),
        ("/tmp/refund.hurl", "path must be relative"),
        ("../refund.hurl", "path must not contain parent traversal"),
        ("docs/refund.hurl", "path must stay under tests/"),
        ("tests/refund.txt", "path must end with .hurl"),
        ("tests\\refund.hurl", "path must use POSIX separators"),
        ("tests/generated/bad\nsecret.hurl", "path must not contain control characters"),
    ],
)
def test_architect_edit_rejects_unsafe_target_path(path: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        ArchitectEdit(path=path, content="GET {{base_url}}/health\nHTTP 200\n")


def test_architect_edit_rejects_empty_or_control_character_content() -> None:
    with pytest.raises(ValidationError, match="content must not be empty"):
        ArchitectEdit(path="tests/refund.hurl", content="")

    with pytest.raises(ValidationError, match="content must not contain control characters"):
        ArchitectEdit(path="tests/refund.hurl", content="GET /health\x00\nHTTP 200\n")


def test_architect_edit_set_requires_edits() -> None:
    with pytest.raises(ValidationError, match="List should have at least 1 item"):
        ArchitectEditSet(summary="Generate checkout tests", edits=[])


def test_architect_edit_set_rejects_empty_or_control_character_summary() -> None:
    edit = ArchitectEdit(path="tests/refund.hurl", content="GET {{base_url}}/health\nHTTP 200\n")

    with pytest.raises(ValidationError, match="summary must not be empty"):
        ArchitectEditSet(summary="", edits=[edit])

    with pytest.raises(ValidationError, match="summary must not contain control characters"):
        ArchitectEditSet(summary="Generate\x00coverage", edits=[edit])


def test_architect_edit_set_rejects_control_character_warning() -> None:
    edit = ArchitectEdit(path="tests/refund.hurl", content="GET {{base_url}}/health\nHTTP 200\n")

    with pytest.raises(ValidationError, match="warning must not contain control characters"):
        ArchitectEditSet(
            summary="Generate checkout tests",
            edits=[edit],
            warnings=["bad\x00warning"],
        )


def test_architect_edit_set_rejects_duplicate_paths() -> None:
    with pytest.raises(ValidationError, match="duplicate Architect edit path"):
        ArchitectEditSet(
            summary="Generate checkout tests",
            edits=[
                ArchitectEdit(path="tests/generated/refund.hurl", content="GET /a\nHTTP 200\n"),
                ArchitectEdit(path="tests/generated/refund.hurl", content="GET /b\nHTTP 200\n"),
            ],
        )
