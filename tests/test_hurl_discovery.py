"""Adapter tests for discovering Hurl tests from the filesystem."""

from pathlib import Path

import pytest

from entroping.core.hurl_discovery import discover_hurl_tests, normalize_tag_filters
from entroping.models.hurl import HurlMetadataSyntaxError


def _write_hurl(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_discover_hurl_tests_recurses_and_ignores_generated_state(tmp_path: Path) -> None:
    checkout = _write_hurl(
        tmp_path / "tests" / "checkout" / "smoke.hurl",
        "# entroping: tags=smoke,checkout\n"
        "# entroping: story_id=CHK-001\n"
        "GET /checkout\n"
        "HTTP 200\n",
    )
    billing = _write_hurl(
        tmp_path / "tests" / "billing.hurl",
        "# entroping: tags=regression,billing\nGET /billing\nHTTP 200\n",
    )
    _write_hurl(
        tmp_path / ".entroping" / "generated.hurl",
        "# entroping: tags=generated\nGET /generated\nHTTP 200\n",
    )
    _write_hurl(
        tmp_path / "reports" / "latest.hurl",
        "# entroping: tags=report\nGET /report\nHTTP 200\n",
    )

    discovered = discover_hurl_tests([tmp_path])

    assert [test.path for test in discovered] == [billing, checkout]
    assert discovered[1].tags == frozenset({"smoke", "checkout"})
    assert discovered[1].metadata.story_id == "CHK-001"


def test_discover_hurl_tests_filters_by_any_requested_tag(tmp_path: Path) -> None:
    checkout = _write_hurl(
        tmp_path / "tests" / "checkout.hurl",
        "# entroping: tags=smoke,checkout\nGET /checkout\nHTTP 200\n",
    )
    _write_hurl(
        tmp_path / "tests" / "billing.hurl",
        "# entroping: tags=regression,billing\nGET /billing\nHTTP 200\n",
    )

    discovered = discover_hurl_tests([tmp_path / "tests"], tag_filters=["smoke", "critical"])

    assert [test.path for test in discovered] == [checkout]


def test_discover_hurl_tests_reports_malformed_metadata_with_file_path(tmp_path: Path) -> None:
    malformed = _write_hurl(
        tmp_path / "tests" / "bad.hurl",
        "# entroping: tags smoke\nGET /bad\nHTTP 200\n",
    )

    with pytest.raises(HurlMetadataSyntaxError, match=str(malformed)):
        discover_hurl_tests([tmp_path])


def test_normalize_tag_filters_rejects_empty_filter_input() -> None:
    with pytest.raises(ValueError, match="Tag filters must not be empty"):
        normalize_tag_filters(["smoke", "  "])
