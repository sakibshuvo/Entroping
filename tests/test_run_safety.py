"""Unit tests for protected run safety preflight."""

from pathlib import Path
from types import MappingProxyType

import pytest

from entroping.core.run_safety import (
    RunSafetyError,
    evaluate_run_safety,
    is_protected_environment,
)
from entroping.models.hurl import HurlExchange, HurlMetadata, HurlTest


def _hurl_test(
    *,
    path: str = "tests/unsafe.hurl",
    methods: tuple[str, ...] = ("POST",),
    tags: frozenset[str] = frozenset(),
    meta: dict[str, str] | None = None,
) -> HurlTest:
    return HurlTest(
        path=Path(path),
        metadata=HurlMetadata(
            tags=tags,
            meta=MappingProxyType(dict(meta or {})),
        ),
        exchanges=tuple(
            HurlExchange(method=method, url=f"http://api.test/{method.lower()}", path="/")
            for method in methods
        ),
    )


def test_evaluate_run_safety_ignores_read_only_protected_tests_without_metadata() -> None:
    result = evaluate_run_safety(
        [_hurl_test(methods=("GET",))],
        environment="prod",
        protected_run=False,
        suite_safety=None,
        protected_environments=("prod",),
    )

    assert result.protected_environment is True
    assert result.evidence_by_path == {}
    assert result.blocks == ()


def test_evaluate_run_safety_reports_tag_and_suite_safety_sources() -> None:
    tag_result = evaluate_run_safety(
        [_hurl_test(tags=frozenset({"teardown-backed"}))],
        environment="production",
        protected_run=False,
        suite_safety=None,
        protected_environments=("production",),
    )
    suite_result = evaluate_run_safety(
        [_hurl_test(path="tests/suite.hurl", methods=("GET",))],
        environment="staging",
        protected_run=True,
        suite_safety="read_only",
        protected_environments=("production",),
    )

    tag_evidence = next(iter(tag_result.evidence_by_path.values()))
    suite_evidence = next(iter(suite_result.evidence_by_path.values()))
    assert tag_evidence.safety == "teardown-backed"
    assert tag_evidence.safety_source == "test tag"
    assert tag_evidence.blocked_reason is None
    assert suite_evidence.safety == "read-only"
    assert suite_evidence.safety_source == "suite metadata"
    assert suite_evidence.blocked_reason is None


def test_evaluate_run_safety_keeps_explicit_safety_evidence_outside_protected_envs() -> None:
    result = evaluate_run_safety(
        [_hurl_test(methods=("GET",), meta={"safety": "read-only"})],
        environment="dev",
        protected_run=False,
        suite_safety=None,
        protected_environments=("prod",),
    )

    evidence = next(iter(result.evidence_by_path.values()))
    assert result.protected_environment is False
    assert evidence.protected_environment is False
    assert evidence.methods == ()
    assert evidence.blocked_reason is None


def test_evaluate_run_safety_ignores_unprotected_tests_without_safety_metadata() -> None:
    result = evaluate_run_safety(
        [_hurl_test()],
        environment="dev",
        protected_run=False,
        suite_safety=None,
        protected_environments=("prod",),
    )

    assert result.protected_environment is False
    assert result.evidence_by_path == {}
    assert result.blocks == ()


def test_evaluate_run_safety_reports_multiple_mutating_methods_without_values() -> None:
    result = evaluate_run_safety(
        [_hurl_test(methods=("post", "DELETE"))],
        environment="prod",
        protected_run=False,
        suite_safety=None,
        protected_environments=("prod",),
    )

    evidence = result.blocks[0].evidence
    assert evidence.methods == ("DELETE", "POST")
    assert evidence.blocked_reason == (
        "mutating methods DELETE, POST require safety metadata in protected environments"
    )


def test_evaluate_run_safety_reports_single_mutating_and_destructive_blockers() -> None:
    unsafe = evaluate_run_safety(
        [_hurl_test(methods=("PUT",))],
        environment="prod",
        protected_run=False,
        suite_safety=None,
        protected_environments=("prod",),
    )
    destructive = evaluate_run_safety(
        [_hurl_test(methods=("DELETE",), meta={"safety": "destructive"})],
        environment="prod",
        protected_run=False,
        suite_safety=None,
        protected_environments=("prod",),
    )

    assert unsafe.blocks[0].evidence.blocked_reason == (
        "mutating method PUT requires safety metadata in protected environments"
    )
    assert destructive.blocks[0].evidence.blocked_reason == (
        "destructive tests are blocked in protected environments"
    )


def test_evaluate_run_safety_blocks_read_only_metadata_on_mutating_methods() -> None:
    single = evaluate_run_safety(
        [_hurl_test(methods=("DELETE",), meta={"safety": "read-only"})],
        environment="prod",
        protected_run=False,
        suite_safety=None,
        protected_environments=("prod",),
    )
    multiple = evaluate_run_safety(
        [_hurl_test(methods=("post", "DELETE"), meta={"safety": "read-only"})],
        environment="prod",
        protected_run=False,
        suite_safety=None,
        protected_environments=("prod",),
    )

    evidence = single.blocks[0].evidence
    assert evidence.safety == "read-only"
    assert evidence.safety_source == "test metadata"
    assert evidence.methods == ("DELETE",)
    assert evidence.blocked_reason == (
        "read-only safety metadata conflicts with mutating method DELETE in protected environments"
    )
    multiple_evidence = multiple.blocks[0].evidence
    assert multiple_evidence.methods == ("DELETE", "POST")
    assert multiple_evidence.blocked_reason == (
        "read-only safety metadata conflicts with mutating methods DELETE, POST "
        "in protected environments"
    )


def test_evaluate_run_safety_rejects_ambiguous_safety_tags() -> None:
    hurl_test = _hurl_test(tags=frozenset({"read-only", "idempotent"}))

    with pytest.raises(RunSafetyError, match="multiple safety tags are ambiguous"):
        evaluate_run_safety(
            [hurl_test],
            environment="prod",
            protected_run=False,
            suite_safety=None,
            protected_environments=("prod",),
        )


@pytest.mark.parametrize(
    ("safety", "message"),
    [
        (" ", "must not be empty"),
        ("idem\x1fpotent", "must not contain control characters"),
        ("reviewed", "Unsupported suite metadata safety value"),
    ],
)
def test_evaluate_run_safety_rejects_invalid_suite_safety_values(
    safety: str,
    message: str,
) -> None:
    with pytest.raises(RunSafetyError, match=message):
        evaluate_run_safety(
            [_hurl_test()],
            environment="prod",
            protected_run=False,
            suite_safety=safety,
            protected_environments=("prod",),
        )


def test_is_protected_environment_returns_false_without_environment_name() -> None:
    assert is_protected_environment(None, protected_environments=("prod",)) is False


@pytest.mark.parametrize(
    ("protected_environments", "message"),
    [
        ((" ",), "must not be empty"),
        (("pro\x1fd",), "must not contain control characters"),
    ],
)
def test_is_protected_environment_rejects_malformed_policy_names(
    protected_environments: tuple[str, ...],
    message: str,
) -> None:
    with pytest.raises(RunSafetyError, match=message):
        is_protected_environment(
            "prod",
            protected_environments=protected_environments,
        )


@pytest.mark.parametrize("method", ("GET", "HEAD", "OPTIONS"))
def test_evaluate_run_safety_blocks_destructive_read_only_methods_in_protected_environment(
    method: str,
) -> None:
    result = evaluate_run_safety(
        [_hurl_test(methods=(method,), meta={"safety": "destructive"})],
        environment="prod",
        protected_run=False,
        suite_safety=None,
        protected_environments=("prod",),
    )

    assert len(result.blocks) == 1
    evidence = result.blocks[0].evidence
    assert evidence.methods == ()
    assert evidence.safety == "destructive"
    assert evidence.blocked_reason == "destructive tests are blocked in protected environments"
