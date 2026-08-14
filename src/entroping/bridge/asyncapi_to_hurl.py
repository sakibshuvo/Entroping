import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Final, cast
from urllib.parse import parse_qsl, urlsplit, urlunsplit

import yaml
from yaml.events import (
    AliasEvent,
    CollectionEndEvent,
    CollectionStartEvent,
    MappingEndEvent,
    MappingStartEvent,
    ScalarEvent,
    SequenceEndEvent,
    SequenceStartEvent,
)

from entroping.models.secrets import contains_secret_like_value, is_sensitive_key

_SAFE_STEM_RE: Final = re.compile(r"[^A-Za-z0-9_-]+")
_OPERATION_KEYS: Final = frozenset({"publish", "subscribe"})
_MAX_YAML_COLLECTION_DEPTH: Final = 128
_MAX_YAML_EXPANDED_NODES: Final = 10_000


class AsyncapiHurlCompilationError(ValueError):
    pass


class _YamlResourceError(ValueError):
    pass


@dataclass(slots=True)
class _YamlCollectionFrame:
    anchor: str | None
    expanded_nodes: int = 1


@dataclass(slots=True)
class _YamlPreflightState:
    stack: list[_YamlCollectionFrame] = field(default_factory=list)
    anchors: dict[str, int | None] = field(default_factory=dict)
    syntactic_nodes: int = 0


@dataclass(frozen=True, slots=True)
class GeneratedAsyncapiWebhookHurlFile:
    relative_path: str
    content: str


def compile_asyncapi_webhook_to_hurl(
    asyncapi_yaml: str,
    *,
    target_url: str,
) -> GeneratedAsyncapiWebhookHurlFile:
    _validate_asyncapi_text(asyncapi_yaml)
    document = _load_asyncapi_document(asyncapi_yaml)
    operation_count = _asyncapi_operation_count(document)
    if operation_count == 0:
        msg = "AsyncAPI document must define at least one publish or subscribe operation"
        raise AsyncapiHurlCompilationError(msg)

    normalized_url, target_origin = _safe_target_url(target_url)
    lines = [
        "# entroping: tags=smoke,asyncapi,webhook",
        "# entroping: source=asyncapi",
        f"# entroping: target_origin={target_origin}",
        f"# entroping: operation_count={operation_count}",
        "# entroping: scaffold=webhook-ack-smoke",
        "",
        f"POST {normalized_url}",
        "Content-Type: application/json",
        "{",
        '  "entroping": "asyncapi-webhook-smoke"',
        "}",
        "HTTP 202",
        "",
    ]
    return GeneratedAsyncapiWebhookHurlFile(
        relative_path=f"tests/generated/{_target_file_stem(normalized_url)}.hurl",
        content="\n".join(lines),
    )


def _validate_asyncapi_text(asyncapi_yaml: str) -> None:
    if asyncapi_yaml.strip() == "":
        msg = "AsyncAPI document is required"
        raise AsyncapiHurlCompilationError(msg)
    if _contains_disallowed_control(asyncapi_yaml):
        msg = "AsyncAPI document contains disallowed control characters"
        raise AsyncapiHurlCompilationError(msg)
    if contains_secret_like_value(asyncapi_yaml):
        msg = "AsyncAPI document contains secret-like material"
        raise AsyncapiHurlCompilationError(msg)


def _load_asyncapi_document(asyncapi_yaml: str) -> Mapping[str, object]:
    try:
        _preflight_yaml_structure(asyncapi_yaml)
        loaded = cast(object, yaml.safe_load(asyncapi_yaml))
    except _YamlResourceError as exc:
        msg = "AsyncAPI YAML exceeds resource limits"
        raise AsyncapiHurlCompilationError(msg) from exc
    except (MemoryError, RecursionError) as exc:
        msg = "AsyncAPI YAML exceeds resource limits"
        raise AsyncapiHurlCompilationError(msg) from exc
    except yaml.YAMLError as exc:
        msg = "Invalid AsyncAPI YAML"
        raise AsyncapiHurlCompilationError(msg) from exc
    if not isinstance(loaded, Mapping):
        msg = "AsyncAPI document must be a mapping"
        raise AsyncapiHurlCompilationError(msg)
    document = cast(Mapping[str, object], loaded)
    if document.get("asyncapi") is None:
        msg = "AsyncAPI document must declare an asyncapi version"
        raise AsyncapiHurlCompilationError(msg)
    channels = document.get("channels")
    if not isinstance(channels, Mapping) or not channels:
        msg = "AsyncAPI document must define a channels mapping"
        raise AsyncapiHurlCompilationError(msg)
    return document


def _preflight_yaml_structure(content: str) -> None:
    state = _YamlPreflightState()
    events = cast(
        Iterable[object],
        yaml.parse(content, Loader=yaml.SafeLoader),  # pyright: ignore[reportUnknownMemberType]
    )
    for event in events:
        _process_yaml_event(state, event)


def _process_yaml_event(state: _YamlPreflightState, event: object) -> None:
    handler = _YAML_PRE_FLIGHT_EVENT_HANDLERS.get(type(event))
    if handler is not None:
        handler(state, event)


def _handle_collection_start(state: _YamlPreflightState, event: object) -> None:
    collection_start_event = cast(CollectionStartEvent, event)
    _count_yaml_node(state)
    if len(state.stack) >= _MAX_YAML_COLLECTION_DEPTH:
        raise _YamlResourceError
    anchor = _yaml_anchor(collection_start_event)
    state.stack.append(_YamlCollectionFrame(anchor=anchor))
    if anchor is not None:
        state.anchors[anchor] = None


def _handle_scalar(state: _YamlPreflightState, event: object) -> None:
    scalar_event = cast(ScalarEvent, event)
    _count_yaml_node(state)
    _add_yaml_expanded_nodes(state, 1)
    anchor = _yaml_anchor(scalar_event)
    if anchor is not None:
        state.anchors[anchor] = 1


def _handle_alias(state: _YamlPreflightState, event: object) -> None:
    alias_event = cast(AliasEvent, event)
    _count_yaml_node(state)
    anchor = _yaml_anchor(alias_event)
    anchor_nodes = state.anchors.get(anchor) if anchor is not None else None
    if anchor_nodes is None:
        raise _YamlResourceError
    _add_yaml_expanded_nodes(state, anchor_nodes)


def _handle_collection_end(state: _YamlPreflightState, event: object) -> None:
    _ = cast(CollectionEndEvent, event)
    frame = state.stack.pop()
    if frame.anchor is not None:
        state.anchors[frame.anchor] = frame.expanded_nodes
    _add_yaml_expanded_nodes(state, frame.expanded_nodes)


_YAML_PRE_FLIGHT_EVENT_HANDLERS: Final[
    dict[type[object], Callable[[_YamlPreflightState, object], None]
    ]
] = {
    CollectionEndEvent: _handle_collection_end,
    CollectionStartEvent: _handle_collection_start,
    MappingEndEvent: _handle_collection_end,
    SequenceEndEvent: _handle_collection_end,
    MappingStartEvent: _handle_collection_start,
    SequenceStartEvent: _handle_collection_start,
    ScalarEvent: _handle_scalar,
    AliasEvent: _handle_alias,
}


def _yaml_anchor(event: CollectionStartEvent | ScalarEvent | AliasEvent) -> str | None:
    anchor = cast(object, event.anchor)
    return anchor if isinstance(anchor, str) else None


def _count_yaml_node(state: _YamlPreflightState) -> None:
    state.syntactic_nodes += 1
    if state.syntactic_nodes > _MAX_YAML_EXPANDED_NODES:
        raise _YamlResourceError


def _add_yaml_expanded_nodes(state: _YamlPreflightState, nodes: int) -> None:
    if not state.stack:
        return
    total = state.stack[-1].expanded_nodes + nodes
    if total > _MAX_YAML_EXPANDED_NODES:
        raise _YamlResourceError
    state.stack[-1].expanded_nodes = total


def _asyncapi_operation_count(document: Mapping[str, object]) -> int:
    channels = cast(Mapping[object, object], document["channels"])
    operation_count = 0
    for channel in channels.values():
        if not isinstance(channel, Mapping):
            continue
        operation_count += sum(1 for key in _OPERATION_KEYS if key in channel)
    return operation_count


def _safe_target_url(value: str) -> tuple[str, str]:
    if not value:
        msg = "AsyncAPI webhook target URL is required"
        raise AsyncapiHurlCompilationError(msg)
    if _contains_disallowed_control(value):
        msg = "AsyncAPI webhook target URL contains control characters"
        raise AsyncapiHurlCompilationError(msg)
    if any(character.isspace() for character in value):
        msg = "AsyncAPI webhook target URL must not contain whitespace"
        raise AsyncapiHurlCompilationError(msg)
    if _has_hurl_template_delimiter(value):
        msg = "AsyncAPI webhook target URL contains Hurl template delimiters"
        raise AsyncapiHurlCompilationError(msg)

    parts = urlsplit(value)
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        msg = "AsyncAPI webhook target URL scheme must be http or https"
        raise AsyncapiHurlCompilationError(msg)
    if parts.username is not None or parts.password is not None:
        msg = "AsyncAPI webhook target URL must not contain credentials"
        raise AsyncapiHurlCompilationError(msg)
    if parts.fragment:
        msg = "AsyncAPI webhook target URL must not contain a fragment"
        raise AsyncapiHurlCompilationError(msg)

    try:
        port = parts.port
    except ValueError as exc:
        msg = "AsyncAPI webhook target URL contains an invalid port"
        raise AsyncapiHurlCompilationError(msg) from exc

    hostname = parts.hostname
    if hostname is None:
        msg = "AsyncAPI webhook target URL must include a host"
        raise AsyncapiHurlCompilationError(msg)

    _reject_sensitive_query(parts.query)
    normalized_host = hostname.lower()
    normalized_netloc = _host_with_port(normalized_host, port)
    normalized_path = parts.path or "/webhooks"
    normalized_url = urlunsplit(
        (scheme, normalized_netloc, normalized_path, parts.query, ""),
    )
    if contains_secret_like_value(normalized_url):
        msg = "AsyncAPI webhook target URL contains secret-like material"
        raise AsyncapiHurlCompilationError(msg)
    return normalized_url, urlunsplit((scheme, normalized_netloc, "", "", ""))


def _reject_sensitive_query(query: str) -> None:
    for key, value in parse_qsl(query, keep_blank_values=True):
        if is_sensitive_key(key):
            msg = f"AsyncAPI webhook target URL contains sensitive query key {key!r}"
            raise AsyncapiHurlCompilationError(msg)
        if contains_secret_like_value(value):
            msg = f"AsyncAPI webhook target URL contains secret-like query value for {key!r}"
            raise AsyncapiHurlCompilationError(msg)


def _host_with_port(hostname: str, port: int | None) -> str:
    host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    if port is None:
        return host
    return f"{host}:{port}"


def _target_file_stem(target_url: str) -> str:
    parts = urlsplit(target_url)
    path = parts.path.strip("/") or "webhooks"
    raw_stem = f"asyncapi-{parts.hostname or 'target'}-{path}-smoke"
    return _SAFE_STEM_RE.sub("-", raw_stem).strip(".-_").lower()


def _contains_disallowed_control(value: str) -> bool:
    return any(ord(character) < 32 and character not in "\n\r\t" for character in value)


def _has_hurl_template_delimiter(value: str) -> bool:
    return "{{" in value or "}}" in value
