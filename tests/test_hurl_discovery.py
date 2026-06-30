"""Adapter tests for discovering Hurl tests from the filesystem."""

from pathlib import Path

import pytest

import entroping.hurl_source as hurl_source
from entroping.core.hurl_discovery import (
    discover_hurl_test_selection,
    discover_hurl_tests,
    normalize_operation_id_filters,
    normalize_tag_filters,
)
from entroping.core.tag_expression import compile_tag_expression
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


def test_discover_hurl_tests_ignores_dot_directories_not_explicitly_named(
    tmp_path: Path,
) -> None:
    visible = _write_hurl(
        tmp_path / "tests" / "visible.hurl",
        "# entroping: tags=visible\nGET /visible\nHTTP 200\n",
    )
    _write_hurl(
        tmp_path / "tests" / ".custom-state" / "hidden.hurl",
        "# entroping: tags=hidden\nGET /hidden\nHTTP 200\n",
    )

    discovered = discover_hurl_tests([tmp_path / "tests"])

    assert [test.path for test in discovered] == [visible.resolve()]


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


def test_discover_hurl_test_selection_filters_by_tag_expression(tmp_path: Path) -> None:
    checkout = _write_hurl(
        tmp_path / "tests" / "checkout.hurl",
        "# entroping: tags=smoke,checkout\nGET /checkout\nHTTP 200\n",
    )
    _write_hurl(
        tmp_path / "tests" / "slow.hurl",
        "# entroping: tags=smoke,slow\nGET /slow\nHTTP 200\n",
    )
    _write_hurl(
        tmp_path / "tests" / "billing.hurl",
        "# entroping: tags=regression,billing\nGET /billing\nHTTP 200\n",
    )

    selected = discover_hurl_test_selection(
        [tmp_path / "tests"],
        tag_expression=compile_tag_expression("smoke and not slow"),
    )

    assert [test.path for test in selected.tests] == [checkout]
    assert selected.discovered_count == 3
    assert selected.selected_count == 1
    assert selected.skipped_count == 2


def test_discover_hurl_test_selection_filters_by_operation_id(tmp_path: Path) -> None:
    checkout = _write_hurl(
        tmp_path / "tests" / "checkout.hurl",
        "# entroping: operation_id=createCheckout\nGET /checkout\nHTTP 200\n",
    )
    refund = _write_hurl(
        tmp_path / "tests" / "refund.hurl",
        "# entroping: operation_id=createRefund\nGET /refund\nHTTP 200\n",
    )
    _write_hurl(
        tmp_path / "tests" / "health.hurl",
        "# entroping: operation_id=getHealth\nGET /health\nHTTP 200\n",
    )

    selected = discover_hurl_test_selection(
        [tmp_path / "tests"],
        operation_id_filters=("createRefund", "createCheckout"),
    )

    assert [test.path for test in selected.tests] == [checkout, refund]
    assert [test.metadata.operation_id for test in selected.tests] == [
        "createCheckout",
        "createRefund",
    ]
    assert selected.discovered_count == 3
    assert selected.selected_count == 2
    assert selected.skipped_count == 1


def test_discover_hurl_test_selection_honors_explicit_empty_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_hurl(
        tmp_path / "tests" / "health.hurl",
        "# entroping: tags=smoke\nGET /health\nHTTP 200\n",
    )
    monkeypatch.chdir(tmp_path)

    selected = discover_hurl_test_selection(())

    assert selected.tests == ()
    assert selected.discovered_count == 0
    assert selected.selected_count == 0
    assert selected.skipped_count == 0


def test_discover_hurl_test_selection_rejects_tag_filter_and_expression_mix(
    tmp_path: Path,
) -> None:
    _write_hurl(
        tmp_path / "tests" / "checkout.hurl",
        "# entroping: tags=smoke,checkout\nGET /checkout\nHTTP 200\n",
    )

    with pytest.raises(ValueError, match="cannot combine tag filters with tag expressions"):
        discover_hurl_test_selection(
            [tmp_path / "tests"],
            tag_filters=("smoke",),
            tag_expression=compile_tag_expression("checkout"),
        )


def test_discover_hurl_test_selection_rejects_operation_id_and_tag_filter_mix(
    tmp_path: Path,
) -> None:
    _write_hurl(
        tmp_path / "tests" / "checkout.hurl",
        "# entroping: tags=smoke\n# entroping: operation_id=createCheckout\n"
        "GET /checkout\nHTTP 200\n",
    )

    with pytest.raises(ValueError, match="cannot combine operation ID filters with tag filters"):
        discover_hurl_test_selection(
            [tmp_path / "tests"],
            tag_filters=("smoke",),
            operation_id_filters=("createCheckout",),
        )


def test_discover_hurl_test_selection_rejects_operation_id_and_tag_expression_mix(
    tmp_path: Path,
) -> None:
    _write_hurl(
        tmp_path / "tests" / "checkout.hurl",
        "# entroping: tags=smoke\n# entroping: operation_id=createCheckout\n"
        "GET /checkout\nHTTP 200\n",
    )

    with pytest.raises(
        ValueError,
        match="cannot combine operation ID filters with tag expressions",
    ):
        discover_hurl_test_selection(
            [tmp_path / "tests"],
            tag_expression=compile_tag_expression("checkout"),
            operation_id_filters=("createCheckout",),
        )


def test_discover_hurl_tests_accepts_single_hurl_file_root(tmp_path: Path) -> None:
    hurl_file = _write_hurl(
        tmp_path / "single.hurl",
        "# entroping: tags=smoke\nGET /single\nHTTP 200\n",
    )

    discovered = discover_hurl_tests([hurl_file])

    assert [test.path for test in discovered] == [hurl_file.resolve()]
    assert discovered[0].exchanges[0].path == "/single"


def test_discover_hurl_tests_deduplicates_roots_and_preserves_sorted_order(tmp_path: Path) -> None:
    zeta = _write_hurl(
        tmp_path / "tests" / "zeta.hurl",
        "# entroping: tags=regression\nGET /zeta\nHTTP 200\n",
    )
    alpha = _write_hurl(
        tmp_path / "tests" / "alpha.hurl",
        "# entroping: tags=smoke\nGET /alpha\nHTTP 200\n",
    )

    discovered = discover_hurl_tests([tmp_path, tmp_path / "tests", alpha])

    assert [test.path for test in discovered] == [
        alpha.resolve(),
        zeta.resolve(),
    ]


def test_discover_hurl_tests_reports_malformed_metadata_with_file_path(tmp_path: Path) -> None:
    malformed = _write_hurl(
        tmp_path / "tests" / "bad.hurl",
        "# entroping: tags smoke\nGET /bad\nHTTP 200\n",
    )

    with pytest.raises(HurlMetadataSyntaxError, match=str(malformed)):
        discover_hurl_tests([tmp_path])


def test_discover_hurl_tests_rejects_control_characters_in_metadata_values(
    tmp_path: Path,
) -> None:
    malformed = _write_hurl(
        tmp_path / "tests" / "bad.hurl",
        "# entroping: operation_id=create\x1bCheckout\nGET /bad\nHTTP 200\n",
    )

    with pytest.raises(HurlMetadataSyntaxError, match=f"{malformed}: line 1:"):
        discover_hurl_tests([tmp_path])


def test_discover_hurl_tests_reports_non_utf8_hurl_with_file_path(tmp_path: Path) -> None:
    bad_encoding = tmp_path / "tests" / "bad-encoding.hurl"
    bad_encoding.parent.mkdir(parents=True, exist_ok=True)
    bad_encoding.write_bytes(b"\xff\xfe\x00")

    with pytest.raises(HurlMetadataSyntaxError, match=f"{bad_encoding}: file is not valid UTF-8"):
        discover_hurl_tests([tmp_path])


def test_discover_hurl_tests_rejects_oversized_hurl_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hurl_source, "HURL_SOURCE_MAX_BYTES", 32)
    oversized = tmp_path / "tests" / "oversized.hurl"
    oversized.parent.mkdir(parents=True, exist_ok=True)
    oversized.write_bytes(b"# entroping: tags=smoke\n" + (b"x" * 32))

    with pytest.raises(HurlMetadataSyntaxError, match=r"Hurl source .* exceeds 32 bytes"):
        discover_hurl_tests([tmp_path])


def test_discover_hurl_tests_rejects_missing_root(tmp_path: Path) -> None:
    missing_root = tmp_path / "missing"

    expected = f"Hurl discovery root does not exist: {missing_root}"
    with pytest.raises(FileNotFoundError, match=expected):
        discover_hurl_tests([missing_root])


def test_discover_hurl_tests_rejects_non_hurl_file_root(tmp_path: Path) -> None:
    notes = tmp_path / "notes.md"
    notes.write_text("not a Hurl file\n", encoding="utf-8")

    with pytest.raises(ValueError, match=f"Expected a .hurl file or directory, got: {notes}"):
        discover_hurl_tests([notes])


def test_discover_hurl_tests_skips_symlinked_hurl_files(tmp_path: Path) -> None:
    target = _write_hurl(
        tmp_path / "outside.hurl",
        "# entroping: tags=outside\nGET /outside\nHTTP 200\n",
    )
    symlink = tmp_path / "tests" / "linked.hurl"
    symlink.parent.mkdir(parents=True, exist_ok=True)
    symlink.symlink_to(target)

    discovered = discover_hurl_tests([tmp_path / "tests"])

    assert discovered == []


def test_discover_hurl_tests_skips_hurl_files_under_symlinked_directories(
    tmp_path: Path,
) -> None:
    local = _write_hurl(
        tmp_path / "tests" / "local.hurl",
        "# entroping: tags=local\nGET /local\nHTTP 200\n",
    )
    outside = _write_hurl(
        tmp_path / "outside" / "external.hurl",
        "# entroping: tags=outside\nGET /outside\nHTTP 200\n",
    )
    linked_directory = tmp_path / "tests" / "linked"
    linked_directory.symlink_to(outside.parent, target_is_directory=True)

    selection = discover_hurl_test_selection([tmp_path / "tests"])

    assert [test.path for test in selection.tests] == [local.resolve()]
    assert selection.discovered_count == 1


def test_discover_hurl_tests_rejects_resolved_candidates_outside_discovery_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outside = _write_hurl(
        tmp_path / "outside" / "external.hurl",
        "# entroping: tags=outside\nGET /outside\nHTTP 200\n",
    )
    root = tmp_path / "tests"
    root.mkdir()
    linked_directory = root / "linked"
    linked_directory.symlink_to(outside.parent, target_is_directory=True)
    escaped_candidate = linked_directory / outside.name

    def fake_rglob(path: Path, pattern: str) -> tuple[Path, ...]:
        assert path == root.resolve()
        assert pattern == "*.hurl"
        return (escaped_candidate,)

    monkeypatch.setattr(Path, "rglob", fake_rglob)

    selection = discover_hurl_test_selection([root])

    assert selection.tests == ()
    assert selection.discovered_count == 0


def test_discover_hurl_tests_rejects_symlink_alias_to_hidden_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hidden = _write_hurl(
        tmp_path / "tests" / ".hidden-target" / "hidden.hurl",
        "# entroping: tags=hidden\nGET /hidden\nHTTP 200\n",
    )
    root = tmp_path / "tests"
    linked_directory = root / "visible-alias"
    linked_directory.symlink_to(hidden.parent, target_is_directory=True)
    hidden_alias = linked_directory / hidden.name

    def fake_rglob(path: Path, pattern: str) -> tuple[Path, ...]:
        assert path == root.resolve()
        assert pattern == "*.hurl"
        return (hidden_alias,)

    monkeypatch.setattr(Path, "rglob", fake_rglob)

    selection = discover_hurl_test_selection([root])

    assert selection.tests == ()
    assert selection.discovered_count == 0


def test_discover_hurl_tests_allows_symlink_alias_to_visible_directory_inside_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = _write_hurl(
        tmp_path / "tests" / "versioned" / "visible.hurl",
        "# entroping: tags=visible\nGET /visible\nHTTP 200\n",
    )
    root = tmp_path / "tests"
    linked_directory = root / "current"
    linked_directory.symlink_to(target.parent, target_is_directory=True)
    visible_alias = linked_directory / target.name

    def fake_rglob(path: Path, pattern: str) -> tuple[Path, ...]:
        assert path == root.resolve()
        assert pattern == "*.hurl"
        return (visible_alias,)

    monkeypatch.setattr(Path, "rglob", fake_rglob)

    selection = discover_hurl_test_selection([root])

    assert [test.path for test in selection.tests] == [target.resolve()]
    assert selection.discovered_count == 1


def test_normalize_tag_filters_rejects_empty_filter_input() -> None:
    with pytest.raises(ValueError, match="Tag filters must not be empty"):
        normalize_tag_filters(["smoke", "  "])


def test_normalize_tag_filters_strips_and_deduplicates_values() -> None:
    normalized = normalize_tag_filters([" smoke ", "smoke", "critical"])

    assert normalized == frozenset({"smoke", "critical"})


def test_normalize_operation_id_filters_rejects_empty_or_control_character_input() -> None:
    with pytest.raises(ValueError, match="Operation ID filters must not be empty"):
        normalize_operation_id_filters(["createCheckout", "  "])

    with pytest.raises(
        ValueError,
        match="Operation ID filters must not contain control characters",
    ):
        normalize_operation_id_filters(["create\x1bCheckout"])


def test_normalize_operation_id_filters_strips_and_deduplicates_values() -> None:
    normalized = normalize_operation_id_filters(
        [" createCheckout ", "createCheckout", "createRefund"],
    )

    assert normalized == frozenset({"createCheckout", "createRefund"})
