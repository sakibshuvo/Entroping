"""Tests for deterministic Hurl tag expressions."""

import pytest

from entroping.core.tag_expression import TagExpressionSyntaxError, compile_tag_expression


def test_tag_expression_matches_and_or_not_with_parentheses() -> None:
    expression = compile_tag_expression("smoke and (checkout or billing) and not slow")

    assert expression.matches(frozenset({"smoke", "checkout"}))
    assert expression.matches(frozenset({"smoke", "billing", "critical"}))
    assert not expression.matches(frozenset({"smoke", "checkout", "slow"}))
    assert not expression.matches(frozenset({"checkout"}))


def test_tag_expression_treats_tags_as_case_sensitive_and_operators_as_case_insensitive() -> None:
    expression = compile_tag_expression("Smoke AND not slow")

    assert expression.matches(frozenset({"Smoke"}))
    assert not expression.matches(frozenset({"smoke"}))


def test_tag_expression_rejects_excessive_nesting_before_recursion_limit() -> None:
    expression = ("(" * 300) + "smoke" + (")" * 300)

    with pytest.raises(TagExpressionSyntaxError, match="too complex"):
        compile_tag_expression(expression)


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        ("", "must not be empty"),
        ("smoke and", "Expected tag"),
        ("smoke slow", "Expected 'and' or 'or'"),
        ("smoke or )", "Expected tag"),
        ("(smoke or slow", "Expected closing"),
        ("__import__('os')", "Invalid tag token"),
        ("smoke\nslow", "control characters"),
    ],
)
def test_tag_expression_rejects_invalid_or_eval_like_input(
    expression: str,
    message: str,
) -> None:
    with pytest.raises(TagExpressionSyntaxError, match=message):
        compile_tag_expression(expression)
