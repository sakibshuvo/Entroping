"""Deterministic boolean expressions over Entroping Hurl tags."""

from __future__ import annotations

import re
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import Final, Literal, cast

_TAG_TOKEN_RE: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")

_TokenKind = Literal["tag", "and", "or", "not", "lparen", "rparen"]


class TagExpressionSyntaxError(ValueError):
    """Raised when a tag expression cannot be parsed safely."""


@dataclass(frozen=True, slots=True)
class CompiledTagExpression:
    """Compiled boolean expression over a test's tag set."""

    source: str
    _root: _Node

    def matches(self, tags: AbstractSet[str]) -> bool:
        """Return whether the expression matches the supplied tags."""

        return _matches(self._root, tags)


@dataclass(frozen=True, slots=True)
class _Token:
    kind: _TokenKind
    value: str
    column: int


@dataclass(frozen=True, slots=True)
class _TagNode:
    tag: str


@dataclass(frozen=True, slots=True)
class _NotNode:
    operand: _Node


@dataclass(frozen=True, slots=True)
class _AndNode:
    left: _Node
    right: _Node


@dataclass(frozen=True, slots=True)
class _OrNode:
    left: _Node
    right: _Node


type _Node = _TagNode | _NotNode | _AndNode | _OrNode


def compile_tag_expression(expression: str) -> CompiledTagExpression:
    """Compile a small ``and``/``or``/``not`` expression over Hurl tags."""

    source = expression.strip()
    if not source:
        msg = "Tag expression must not be empty"
        raise TagExpressionSyntaxError(msg)
    if any(ord(character) < 32 or ord(character) == 127 for character in expression):
        msg = "Tag expression must not contain control characters"
        raise TagExpressionSyntaxError(msg)

    parser = _Parser(_tokenize(source))
    root = parser.parse()
    return CompiledTagExpression(source=source, _root=root)


def _tokenize(source: str) -> tuple[_Token, ...]:
    tokens: list[_Token] = []
    index = 0
    while index < len(source):
        character = source[index]
        if character == " ":
            index += 1
            continue
        if character == "(":
            tokens.append(_Token(kind="lparen", value=character, column=index + 1))
            index += 1
            continue
        if character == ")":
            tokens.append(_Token(kind="rparen", value=character, column=index + 1))
            index += 1
            continue

        start = index
        while index < len(source) and source[index] not in {" ", "(", ")"}:
            index += 1
        value = source[start:index]
        lowered = value.lower()
        if lowered in {"and", "or", "not"}:
            tokens.append(_Token(kind=cast(_TokenKind, lowered), value=value, column=start + 1))
            continue
        if not _TAG_TOKEN_RE.fullmatch(value):
            msg = (
                f"Invalid tag token {value!r} at column {start + 1}; "
                "use letters, digits, '.', '_', '-', '/', or ':'"
            )
            raise TagExpressionSyntaxError(msg)
        tokens.append(_Token(kind="tag", value=value, column=start + 1))

    return tuple(tokens)


class _Parser:
    def __init__(self, tokens: tuple[_Token, ...]) -> None:
        self._tokens = tokens
        self._index = 0

    def parse(self) -> _Node:
        node = self._parse_or()
        remaining = self._current()
        if remaining is not None:
            msg = f"Expected 'and' or 'or' before {remaining.value!r} at column {remaining.column}"
            raise TagExpressionSyntaxError(msg)
        return node

    def _parse_or(self) -> _Node:
        node = self._parse_and()
        while self._match("or") is not None:
            node = _OrNode(left=node, right=self._parse_and())
        return node

    def _parse_and(self) -> _Node:
        node = self._parse_not()
        while self._match("and") is not None:
            node = _AndNode(left=node, right=self._parse_not())
        return node

    def _parse_not(self) -> _Node:
        if self._match("not") is not None:
            return _NotNode(operand=self._parse_not())
        return self._parse_primary()

    def _parse_primary(self) -> _Node:
        tag = self._match("tag")
        if tag is not None:
            return _TagNode(tag=tag.value)

        left = self._match("lparen")
        if left is not None:
            node = self._parse_or()
            if self._match("rparen") is None:
                msg = f"Expected closing ')' for group opened at column {left.column}"
                raise TagExpressionSyntaxError(msg)
            return node

        current = self._current()
        if current is None:
            msg = "Expected tag or '(' at end of expression"
        else:
            msg = f"Expected tag or '(' at column {current.column}"
        raise TagExpressionSyntaxError(msg)

    def _match(self, kind: _TokenKind) -> _Token | None:
        current = self._current()
        if current is None or current.kind != kind:
            return None
        self._index += 1
        return current

    def _current(self) -> _Token | None:
        if self._index >= len(self._tokens):
            return None
        return self._tokens[self._index]


def _matches(node: _Node, tags: AbstractSet[str]) -> bool:
    if isinstance(node, _TagNode):
        return node.tag in tags
    if isinstance(node, _NotNode):
        return not _matches(node.operand, tags)
    if isinstance(node, _AndNode):
        return _matches(node.left, tags) and _matches(node.right, tags)
    return _matches(node.left, tags) or _matches(node.right, tags)
