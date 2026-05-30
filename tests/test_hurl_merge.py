"""Managed Hurl block merge tests."""

import pytest

from entroping.bridge.merge import HurlMergeError, merge_managed_hurl_blocks


def _managed_block(block_id: str, body: str) -> str:
    return (
        f"# entroping: managed-begin {block_id}\n"
        f"{body}"
        f"# entroping: managed-end {block_id}\n"
    )


def test_merge_managed_hurl_blocks_preserves_manual_content() -> None:
    existing = (
        "# manual setup\n"
        "GET {{base_url}}/health\n"
        "HTTP 200\n"
        "\n"
        "# entroping: managed-begin checkout-auth\n"
        "GET {{base_url}}/checkout\n"
        "HTTP 200\n"
        "# entroping: managed-end checkout-auth\n"
        "\n"
        "# manual footer\n"
    )
    generated = (
        "# entroping: managed-begin checkout-auth\n"
        "GET {{base_url}}/checkout\n"
        "Authorization: Bearer {{auth_token}}\n"
        "HTTP 200\n"
        "# entroping: managed-end checkout-auth\n"
    )

    result = merge_managed_hurl_blocks(existing, generated)

    assert result.replaced_blocks == ("checkout-auth",)
    assert result.content == (
        "# manual setup\n"
        "GET {{base_url}}/health\n"
        "HTTP 200\n"
        "\n"
        "# entroping: managed-begin checkout-auth\n"
        "GET {{base_url}}/checkout\n"
        "Authorization: Bearer {{auth_token}}\n"
        "HTTP 200\n"
        "# entroping: managed-end checkout-auth\n"
        "\n"
        "# manual footer\n"
    )


def test_merge_managed_hurl_blocks_replaces_multiple_blocks_in_existing_order() -> None:
    existing = (
        "# entroping: managed-begin first\n"
        "GET /old-first\n"
        "# entroping: managed-end first\n"
        "\n"
        "# manual middle\n"
        "\n"
        "# entroping: managed-begin second\n"
        "GET /old-second\n"
        "# entroping: managed-end second\n"
    )
    generated = (
        "# entroping: managed-begin second\n"
        "GET /new-second\n"
        "# entroping: managed-end second\n"
        "\n"
        "# entroping: managed-begin first\n"
        "GET /new-first\n"
        "# entroping: managed-end first\n"
    )

    result = merge_managed_hurl_blocks(existing, generated)

    assert result.replaced_blocks == ("first", "second")
    assert result.content == (
        "# entroping: managed-begin first\n"
        "GET /new-first\n"
        "# entroping: managed-end first\n"
        "\n"
        "# manual middle\n"
        "\n"
        "# entroping: managed-begin second\n"
        "GET /new-second\n"
        "# entroping: managed-end second\n"
    )


def test_merge_managed_hurl_blocks_leaves_missing_generated_blocks_unchanged() -> None:
    existing = (
        "# entroping: managed-begin changed\n"
        "GET /old-changed\n"
        "# entroping: managed-end changed\n"
        "\n"
        "# entroping: managed-begin unchanged\n"
        "GET /still-owned\n"
        "# entroping: managed-end unchanged\n"
    )
    generated = _managed_block("changed", "GET /new-changed\n")

    result = merge_managed_hurl_blocks(existing, generated)

    assert result.replaced_blocks == ("changed",)
    assert result.content == (
        "# entroping: managed-begin changed\n"
        "GET /new-changed\n"
        "# entroping: managed-end changed\n"
        "\n"
        "# entroping: managed-begin unchanged\n"
        "GET /still-owned\n"
        "# entroping: managed-end unchanged\n"
    )


@pytest.mark.parametrize(
    ("existing", "generated", "message"),
    [
        (
            "# manual only\nGET /health\n",
            _managed_block("checkout", "GET /checkout\n"),
            "existing Hurl does not contain managed blocks",
        ),
        (
            _managed_block("checkout", "GET /checkout\n"),
            "# generated manual only\nGET /checkout\n",
            "generated Hurl does not contain managed blocks",
        ),
        (
            _managed_block("checkout", "GET /checkout\n"),
            _managed_block("refund", "GET /refunds\n"),
            "generated block is not present in existing Hurl: refund",
        ),
        (
            "# entroping: managed-begin checkout\nGET /checkout\n",
            _managed_block("checkout", "GET /checkout\n"),
            "missing managed-end for block checkout",
        ),
        (
            "# entroping: managed-end checkout\n",
            _managed_block("checkout", "GET /checkout\n"),
            "managed-end without managed-begin",
        ),
        (
            "# entroping: managed-begin checkout\n"
            "# entroping: managed-begin nested\n"
            "# entroping: managed-end nested\n"
            "# entroping: managed-end checkout\n",
            _managed_block("checkout", "GET /checkout\n"),
            "nested managed block",
        ),
        (
            "# entroping: managed-begin checkout\nGET /checkout\n# entroping: managed-end other\n",
            _managed_block("checkout", "GET /checkout\n"),
            "managed-end other does not match managed-begin checkout",
        ),
        (
            "# entroping: managed-begin checkout\nGET /one\n# entroping: managed-end checkout\n"
            "# entroping: managed-begin checkout\nGET /two\n# entroping: managed-end checkout\n",
            _managed_block("checkout", "GET /checkout\n"),
            "duplicate managed block id: checkout",
        ),
    ],
)
def test_merge_managed_hurl_blocks_rejects_unsafe_shapes(
    existing: str,
    generated: str,
    message: str,
) -> None:
    with pytest.raises(HurlMergeError, match=message):
        merge_managed_hurl_blocks(existing, generated)
