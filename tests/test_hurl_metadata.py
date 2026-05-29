"""Unit tests for Entroping Hurl metadata comments."""

import pytest

from entroping.models.hurl import HurlMetadataSyntaxError, parse_hurl_exchanges, parse_hurl_metadata


def test_parse_hurl_metadata_extracts_tags_and_traceability_fields() -> None:
    metadata = parse_hurl_metadata(
        "\n".join(
            [
                "# entroping: tags=smoke,checkout,critical",
                "# entroping: story_id=CHK-001",
                "# entroping: owner=payments",
                "# entroping: doc_url=https://notion.so/workspace/CHK-001",
                "",
                "GET {{base_url}}/checkout/{{checkout_id}}",
                "HTTP 200",
            ],
        ),
    )

    assert metadata.tags == frozenset({"smoke", "checkout", "critical"})
    assert metadata.meta == {
        "story_id": "CHK-001",
        "owner": "payments",
        "doc_url": "https://notion.so/workspace/CHK-001",
    }
    assert metadata.story_id == "CHK-001"


def test_parse_hurl_metadata_rejects_missing_key_value_separator() -> None:
    with pytest.raises(
        HurlMetadataSyntaxError,
        match="line 1: expected 'key=value' after '# entroping:'",
    ):
        parse_hurl_metadata("# entroping: tags smoke")


def test_parse_hurl_metadata_rejects_empty_tag_values() -> None:
    with pytest.raises(HurlMetadataSyntaxError, match="line 1: empty tag value"):
        parse_hurl_metadata("# entroping: tags=smoke,,critical")


def test_parse_hurl_metadata_rejects_duplicate_traceability_keys() -> None:
    with pytest.raises(
        HurlMetadataSyntaxError,
        match="line 2: duplicate metadata key 'story_id'",
    ):
        parse_hurl_metadata(
            "\n".join(
                [
                    "# entroping: story_id=CHK-001",
                    "# entroping: story_id=CHK-002",
                ],
            ),
        )


def test_parse_hurl_exchanges_extracts_request_method_url_and_path() -> None:
    exchanges = parse_hurl_exchanges(
        "\n".join(
            [
                "GET {{base_url}}/health",
                "HTTP 200",
                "",
                "POST https://api.example.test/v1/checkout?expand=true",
                "Content-Type: application/json",
                "HTTP 201",
            ],
        ),
    )

    assert [(exchange.method, exchange.url, exchange.path) for exchange in exchanges] == [
        ("GET", "{{base_url}}/health", "/health"),
        ("POST", "https://api.example.test/v1/checkout?expand=true", "/v1/checkout"),
    ]
