"""Resource-bounded construction for untrusted YAML documents."""

from dataclasses import dataclass, field
from typing import Final

import yaml
from yaml.events import AliasEvent, CollectionEndEvent, CollectionStartEvent, ScalarEvent

MAX_YAML_COLLECTION_DEPTH: Final = 128
MAX_YAML_EXPANDED_NODES: Final = 10_000


class YamlSafetyError(ValueError):
    """Raised when YAML structure exceeds a safe construction budget."""


@dataclass(slots=True)
class _CollectionFrame:
    anchor: str | None
    expanded_nodes: int = 1


@dataclass(slots=True)
class _PreflightState:
    stack: list[_CollectionFrame] = field(default_factory=list)
    anchors: dict[str, int | None] = field(default_factory=dict)
    syntactic_nodes: int = 0


def load_yaml_bounded(content: str) -> object:
    """Preflight YAML structure before constructing Python objects."""

    _preflight_yaml_structure(content)
    try:
        return yaml.safe_load(content)
    except (MemoryError, RecursionError) as exc:
        msg = "YAML parser resource limit exceeded"
        raise YamlSafetyError(msg) from exc


def _preflight_yaml_structure(content: str) -> None:
    state = _PreflightState()
    try:
        for event in yaml.parse(content, Loader=yaml.SafeLoader):
            _consume_event(state, event)
    except YamlSafetyError:
        raise
    except (MemoryError, RecursionError) as exc:
        msg = "YAML parser resource limit exceeded"
        raise YamlSafetyError(msg) from exc


def _consume_event(state: _PreflightState, event: yaml.events.Event) -> None:
    if isinstance(event, CollectionStartEvent):
        _begin_collection(state, event)
    elif isinstance(event, ScalarEvent):
        _consume_scalar(state, event)
    elif isinstance(event, AliasEvent):
        _consume_alias(state, event)
    elif isinstance(event, CollectionEndEvent):
        _end_collection(state)


def _begin_collection(state: _PreflightState, event: CollectionStartEvent) -> None:
    _count_syntactic_node(state)
    if len(state.stack) >= MAX_YAML_COLLECTION_DEPTH:
        msg = f"YAML nesting exceeds {MAX_YAML_COLLECTION_DEPTH} collections"
        raise YamlSafetyError(msg)
    state.stack.append(_CollectionFrame(anchor=event.anchor))
    if event.anchor is not None:
        state.anchors[event.anchor] = None


def _consume_scalar(state: _PreflightState, event: ScalarEvent) -> None:
    _count_syntactic_node(state)
    _add_expanded_nodes(state, 1)
    if event.anchor is not None:
        state.anchors[event.anchor] = 1


def _consume_alias(state: _PreflightState, event: AliasEvent) -> None:
    _count_syntactic_node(state)
    anchor_nodes = state.anchors.get(event.anchor)
    if anchor_nodes is None:
        msg = "YAML recursive or unresolved aliases are not allowed"
        raise YamlSafetyError(msg)
    _add_expanded_nodes(state, anchor_nodes)


def _end_collection(state: _PreflightState) -> None:
    if not state.stack:
        msg = "YAML collection structure is invalid"
        raise YamlSafetyError(msg)
    frame = state.stack.pop()
    if frame.anchor is not None:
        state.anchors[frame.anchor] = frame.expanded_nodes
    _add_expanded_nodes(state, frame.expanded_nodes)


def _add_expanded_nodes(state: _PreflightState, nodes: int) -> None:
    if not state.stack:
        return
    total = state.stack[-1].expanded_nodes + nodes
    if total > MAX_YAML_EXPANDED_NODES:
        _raise_expansion_error()
    state.stack[-1].expanded_nodes = total


def _count_syntactic_node(state: _PreflightState) -> None:
    state.syntactic_nodes += 1
    if state.syntactic_nodes > MAX_YAML_EXPANDED_NODES:
        _raise_node_error()


def _raise_node_error() -> None:
    msg = f"YAML document exceeds {MAX_YAML_EXPANDED_NODES} nodes"
    raise YamlSafetyError(msg)


def _raise_expansion_error() -> None:
    msg = f"YAML expansion exceeds {MAX_YAML_EXPANDED_NODES} nodes"
    raise YamlSafetyError(msg)
