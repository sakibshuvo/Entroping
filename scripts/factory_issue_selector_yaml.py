from __future__ import annotations

from typing import TypeGuard

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

_STRING_TAG = "tag:yaml.org,2002:str"


class _StringNode(ScalarNode):
    value: str


class _SequenceNode(SequenceNode):
    value: list[Node]


class _MappingNode(MappingNode):
    value: list[tuple[Node, Node]]


def compose_yaml(text: str) -> Node | None:
    try:
        return yaml.SafeLoader(text).get_single_node()
    except yaml.YAMLError as exc:
        raise ValueError("invalid YAML") from exc


def closed_mapping(node: Node | None) -> dict[str, Node] | None:
    if not _is_mapping(node):
        return None
    result: dict[str, Node] = {}
    for key_node, value_node in node.value:
        if not _is_string(key_node):
            return None
        key = key_node.value
        if key == "<<" or key in result:
            return None
        result[key] = value_node
    return result


def string_value(node: Node) -> str | None:
    return node.value if _is_string(node) and node.tag == _STRING_TAG else None


def sequence_items(node: Node) -> tuple[Node, ...] | None:
    return tuple(node.value) if _is_sequence(node) else None


def has_duplicate_key(node: Node, seen_nodes: set[int] | None = None) -> bool:
    visited: set[int] = seen_nodes if seen_nodes is not None else set()
    identity = id(node)
    if identity in visited:
        return True
    visited.add(identity)
    if _is_mapping(node):
        keys: set[str] = set()
        for key_node, value_node in node.value:
            if not _is_string(key_node):
                return True
            key = key_node.value
            if key == "<<" or key in keys:
                return True
            keys.add(key)
            if has_duplicate_key(value_node, visited):
                return True
        return False
    if _is_sequence(node):
        return any(has_duplicate_key(item, visited) for item in node.value)
    return False


def _is_string(node: Node | None) -> TypeGuard[_StringNode]:
    return isinstance(node, ScalarNode)


def _is_sequence(node: Node | None) -> TypeGuard[_SequenceNode]:
    return isinstance(node, SequenceNode)


def _is_mapping(node: Node | None) -> TypeGuard[_MappingNode]:
    return isinstance(node, MappingNode)
