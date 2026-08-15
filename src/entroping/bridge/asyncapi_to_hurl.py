"""Compile bounded AsyncAPI webhook metadata into deterministic Hurl.

The compiler emits only deterministic request scaffolds after strict validation.
It never probes a target or resolves provider/runtime state.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final, Literal, cast
from urllib.parse import parse_qsl, urlsplit, urlunsplit

import yaml
from yaml import events
from yaml.nodes import MappingNode, Node, ScalarNode

from entroping.models.secrets import contains_secret_like_value, is_sensitive_key

_SAFE_STEM_RE: Final = re.compile(r"[^A-Za-z0-9_-]+")
_SAFE_HOSTNAME_RE: Final = re.compile(
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?|[0-9A-Fa-f:]+)"
)
_OPERATION_KEYS: Final = frozenset({"publish", "subscribe"})
_ASYNCAPI_2_VERSION_RE: Final = re.compile(r"^2\.\d+\.\d+$")
_CHANNEL_PATH_RE: Final = re.compile(r"^/(?:[A-Za-z0-9._~-]+)(?:/[A-Za-z0-9._~-]+)*$")
_HTTP_WEBHOOK_METHODS: Final = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
_BODY_METHODS: Final = frozenset({"POST", "PUT", "PATCH"})
_HTTP_OPERATION_BINDING_KEYS: Final = frozenset({"method", "bindingVersion"})
_MAX_YAML_COLLECTION_DEPTH: Final = 128
_MAX_YAML_EXPANDED_NODES: Final = 10_000
_CHANNEL_BINDING_ERROR: Final = "AsyncAPI webhook channel binding is invalid"
_OPERATION_BINDING_ERROR: Final = "AsyncAPI webhook operation binding is invalid"
_TARGET_ERROR: Final = "AsyncAPI webhook target URL is invalid"


class AsyncapiHurlCompilationError(ValueError):
    pass


@dataclass(slots=True)
class _YamlPreflightState:
    stack: list[tuple[str | None, int]] = field(default_factory=list)
    anchors: dict[str, int | None] = field(default_factory=dict)
    syntactic_nodes: int = 0

    def handle(self, event: object) -> None:
        if isinstance(event, (events.CollectionStartEvent, events.ScalarEvent, events.AliasEvent)):
            self.syntactic_nodes += 1
            self.require_resource(self.syntactic_nodes <= _MAX_YAML_EXPANDED_NODES)
        if isinstance(event, events.CollectionStartEvent):
            self.require_resource(len(self.stack) < _MAX_YAML_COLLECTION_DEPTH)
            anchor = event.anchor if isinstance(event.anchor, str) else None
            self.stack.append((anchor, 1))
            self.remember_anchor(anchor, None)
        elif isinstance(event, events.ScalarEvent):
            self.add_yaml_expanded_nodes(1)
            anchor = event.anchor if isinstance(event.anchor, str) else None
            self.remember_anchor(anchor, 1)
        elif isinstance(event, events.AliasEvent):
            anchor = event.anchor if isinstance(event.anchor, str) else None
            nodes = self.anchors.get(anchor) if anchor is not None else None
            self.require_resource(nodes is not None)
            self.add_yaml_expanded_nodes(cast(int, nodes))
        else:
            anchor, nodes = self.stack.pop()
            self.remember_anchor(anchor, nodes)
            self.add_yaml_expanded_nodes(nodes)

    def add_yaml_expanded_nodes(self, nodes: int) -> None:
        if not self.stack:
            return
        anchor, expanded_nodes = self.stack[-1]
        total = expanded_nodes + nodes
        self.require_resource(total <= _MAX_YAML_EXPANDED_NODES)
        self.stack[-1] = (anchor, total)

    def require_resource(self, condition: bool) -> None:
        if not condition:
            raise AsyncapiHurlCompilationError

    def remember_anchor(self, anchor: str | None, nodes: int | None) -> None:
        self.anchors.update({anchor: nodes} if anchor is not None else {})


@dataclass(frozen=True, slots=True)
class GeneratedAsyncapiWebhookHurlFile:
    relative_path: str
    content: str


def compile_asyncapi_webhook_to_hurl(
    asyncapi_yaml: str,
    *,
    target_url: str,
    channel: str | None = None,
    operation: Literal["publish", "subscribe"] | None = None,
) -> GeneratedAsyncapiWebhookHurlFile:
    _validate_asyncapi_text(asyncapi_yaml)
    document = _load_asyncapi_document(asyncapi_yaml)
    selection = _validate_selection(channel, operation)
    if selection is not None:
        selected_channel, selected_operation = selection
        method = _selected_http_webhook_method(
            document,
            asyncapi_yaml,
            channel=selected_channel,
            operation=selected_operation,
        )
        target_origin = _safe_selected_target_origin(target_url)
        selected_url = f"{target_origin}{selected_channel}"
        return _render_selected_webhook_hurl(
            target_origin=target_origin,
            target_url=selected_url,
            channel=selected_channel,
            operation=selected_operation,
            method=method,
        )
    operation_count = _asyncapi_operation_count(document)
    if operation_count == 0:
        raise AsyncapiHurlCompilationError(
            "AsyncAPI document must define at least one publish or subscribe operation"
        )
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
        f"tests/generated/{_target_file_stem(normalized_url)}.hurl", "\n".join(lines)
    )


def _validate_selection(
    channel: str | None,
    operation: Literal["publish", "subscribe"] | None,
) -> tuple[str, Literal["publish", "subscribe"]] | None:
    if all(value is None for value in (channel, operation)):
        return None
    if not all(
        (isinstance(channel, str), isinstance(operation, str), operation in _OPERATION_KEYS)
    ):
        raise AsyncapiHurlCompilationError("AsyncAPI webhook selection is invalid")
    if not _is_safe_channel_path(cast(str, channel)):
        raise AsyncapiHurlCompilationError("AsyncAPI webhook channel is invalid")
    return cast(str, channel), cast(Literal["publish", "subscribe"], operation)


def _is_safe_channel_path(channel: str) -> bool:
    try:
        channel_size = len(channel.encode("utf-8"))
    except UnicodeEncodeError:
        return False
    return (
        1 <= channel_size <= 1024
        and _CHANNEL_PATH_RE.fullmatch(channel) is not None
        and all(segment not in {".", ".."} for segment in channel.split("/")[1:])
        and not contains_secret_like_value(channel)
        and not _has_hurl_template_delimiter(channel)
    )


def _selected_http_webhook_method(
    document: Mapping[str, object],
    asyncapi_yaml: str,
    *,
    channel: str,
    operation: Literal["publish", "subscribe"],
) -> str:
    version = document.get("asyncapi")
    _require(
        isinstance(version, str) and _ASYNCAPI_2_VERSION_RE.fullmatch(version) is not None,
        "AsyncAPI webhook selection requires an AsyncAPI 2.x document",
    )
    _reject_ambiguous_selected_yaml_entries(asyncapi_yaml, channel=channel, operation=operation)
    channels = cast(Mapping[str, object], document["channels"])
    channel_item = cast(Mapping[object, object], channels[channel])
    bindings = channel_item.get("bindings")
    _require(
        isinstance(bindings, Mapping)
        and set(bindings) == {"http"}
        and isinstance(bindings.get("http"), Mapping)
        and not bindings["http"],
        _CHANNEL_BINDING_ERROR,
    )
    operation_item = cast(Mapping[object, object], channel_item[operation])
    return _validate_operation_http_binding(operation_item)


def _validate_operation_http_binding(operation_item: Mapping[object, object]) -> str:
    bindings = operation_item.get("bindings")
    _require(
        isinstance(bindings, Mapping)
        and set(bindings) == {"http"}
        and isinstance(bindings.get("http"), Mapping),
        _OPERATION_BINDING_ERROR,
    )
    http_binding = cast(Mapping[object, object], cast(Mapping[object, object], bindings)["http"])
    method = http_binding.get("method")
    binding_version = http_binding.get("bindingVersion")
    for condition in (
        not set(http_binding) - _HTTP_OPERATION_BINDING_KEYS,
        isinstance(method, str) and method in _HTTP_WEBHOOK_METHODS,
        binding_version is None or binding_version == "0.3.0",
    ):
        _require(condition, _OPERATION_BINDING_ERROR)
    return cast(str, method)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AsyncapiHurlCompilationError(message)


def _reject_ambiguous_selected_yaml_entries(
    asyncapi_yaml: str,
    *,
    channel: str,
    operation: Literal["publish", "subscribe"],
) -> None:
    try:
        root = cast(MappingNode, yaml.compose(asyncapi_yaml, Loader=yaml.SafeLoader))
    except (MemoryError, RecursionError) as exc:
        raise AsyncapiHurlCompilationError("AsyncAPI YAML exceeds resource limits") from exc
    except yaml.YAMLError as exc:
        raise AsyncapiHurlCompilationError("Invalid AsyncAPI YAML") from exc
    _require(
        len(_mapping_values(root, "asyncapi")) == 1,
        "AsyncAPI webhook selection requires an AsyncAPI 2.x document",
    )
    channels_node = _selected_mapping_node(root, "channels")
    channel_node = _selected_mapping_node(channels_node, channel)
    operation_node = _selected_mapping_node(channel_node, operation)
    _reject_duplicate_binding_entries(channel_node)
    _reject_duplicate_binding_entries(operation_node)


def _selected_mapping_node(parent: MappingNode, key: str) -> MappingNode:
    node = _single_mapping_node(_mapping_values(parent, key))
    _require(node is not None, "AsyncAPI selected channel operation is invalid")
    return cast(MappingNode, node)


def _single_mapping_node(nodes: list[Node]) -> MappingNode | None:
    if len(nodes) != 1 or not isinstance(nodes[0], MappingNode):
        return None
    return nodes[0]


def _reject_duplicate_binding_entries(mapping_node: MappingNode) -> None:
    binding_nodes = _mapping_values(mapping_node, "bindings")
    _require(len(binding_nodes) <= 1, "AsyncAPI selected channel operation is invalid")
    binding_node = _single_mapping_node(binding_nodes)
    if binding_node is None:
        return
    http_nodes = _mapping_values(binding_node, "http")
    _require(len(http_nodes) <= 1, "AsyncAPI selected channel operation is invalid")
    http_node = _single_mapping_node(http_nodes)
    if http_node is None:
        return
    for key in ("method", "bindingVersion"):
        _require(len(_mapping_values(http_node, key)) <= 1, _OPERATION_BINDING_ERROR)


def _mapping_values(mapping_node: MappingNode, key: str) -> list[Node]:
    return [
        value_node
        for key_node, value_node in mapping_node.value
        if isinstance(key_node, ScalarNode)
        and key_node.tag == "tag:yaml.org,2002:str"
        and key_node.value == key
    ]


def _safe_selected_target_origin(value: str) -> str:
    _require(isinstance(value, str) and bool(value), _TARGET_ERROR)
    _require(
        all(
            (
                not _contains_disallowed_control(value),
                not any(character.isspace() for character in value),
                not _has_hurl_template_delimiter(value),
                not contains_secret_like_value(value),
            )
        ),
        _TARGET_ERROR,
    )
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as exc:
        raise AsyncapiHurlCompilationError(_TARGET_ERROR) from exc
    _require(
        parts.scheme.lower() in {"http", "https"}
        and parts.username is None
        and parts.password is None,
        _TARGET_ERROR,
    )
    hostname = parts.hostname
    _require(
        hostname is not None and _SAFE_HOSTNAME_RE.fullmatch(hostname) is not None,
        _TARGET_ERROR,
    )
    _reject_selected_query(parts.query)
    assert hostname is not None
    return urlunsplit((parts.scheme.lower(), _host_with_port(hostname.lower(), port), "", "", ""))


def _render_selected_webhook_hurl(
    *,
    target_origin: str,
    target_url: str,
    channel: str,
    operation: Literal["publish", "subscribe"],
    method: str,
) -> GeneratedAsyncapiWebhookHurlFile:
    lines = [
        "# entroping: tags=smoke,asyncapi,webhook",
        "# entroping: source=asyncapi",
        f"# entroping: target_origin={target_origin}",
        f"# entroping: channel={channel}",
        f"# entroping: operation={operation}",
        "# entroping: scaffold=http-webhook-operation",
        "",
        f"{method} {target_url}",
    ]
    if method in _BODY_METHODS:
        lines.extend(
            [
                "Content-Type: application/json",
                "{",
                '  "entroping": "asyncapi-webhook-smoke"',
                "}",
            ]
        )
    lines.extend(("HTTP 202", ""))
    return GeneratedAsyncapiWebhookHurlFile(
        f"tests/generated/{_target_file_stem(target_url)}.hurl", "\n".join(lines)
    )


def _reject_selected_query(query: str) -> None:
    for key, value in parse_qsl(query, keep_blank_values=True):
        _require(not is_sensitive_key(key) and not contains_secret_like_value(value), _TARGET_ERROR)


def _validate_asyncapi_text(asyncapi_yaml: str) -> None:
    for condition, message in (
        (asyncapi_yaml.strip() != "", "AsyncAPI document is required"),
        (
            not _contains_disallowed_control(asyncapi_yaml),
            "AsyncAPI document contains disallowed control characters",
        ),
        (
            not contains_secret_like_value(asyncapi_yaml),
            "AsyncAPI document contains secret-like material",
        ),
    ):
        _require(condition, message)


def _load_asyncapi_document(asyncapi_yaml: str) -> Mapping[str, object]:
    try:
        _preflight_yaml_structure(asyncapi_yaml)
        loaded = cast(object, yaml.safe_load(asyncapi_yaml))
    except (AsyncapiHurlCompilationError, MemoryError, RecursionError) as exc:
        raise AsyncapiHurlCompilationError("AsyncAPI YAML exceeds resource limits") from exc
    except yaml.YAMLError as exc:
        raise AsyncapiHurlCompilationError("Invalid AsyncAPI YAML") from exc
    _require(isinstance(loaded, Mapping), "AsyncAPI document must be a mapping")
    document = cast(Mapping[str, object], loaded)
    _require(
        document.get("asyncapi") is not None, "AsyncAPI document must declare an asyncapi version"
    )
    channels = document.get("channels")
    _require(
        isinstance(channels, Mapping) and bool(channels),
        "AsyncAPI document must define a channels mapping",
    )
    return document


def _preflight_yaml_structure(content: str) -> None:
    state = _YamlPreflightState()
    for event in yaml.parse(content, Loader=yaml.SafeLoader):  # pyright: ignore[reportUnknownMemberType]
        if not isinstance(
            event,
            (
                events.StreamStartEvent,
                events.StreamEndEvent,
                events.DocumentStartEvent,
                events.DocumentEndEvent,
            ),
        ):
            state.handle(event)


def _asyncapi_operation_count(document: Mapping[str, object]) -> int:
    channels = cast(Mapping[object, object], document["channels"])
    return sum(
        sum(1 for key in _OPERATION_KEYS if key in channel)
        for channel in channels.values()
        if isinstance(channel, Mapping)
    )


def _safe_target_url(value: str) -> tuple[str, str]:
    for condition, message in (
        (bool(value), "AsyncAPI webhook target URL is required"),
        (
            not _contains_disallowed_control(value),
            "AsyncAPI webhook target URL contains control characters",
        ),
        (
            not any(character.isspace() for character in value),
            "AsyncAPI webhook target URL must not contain whitespace",
        ),
        (
            not _has_hurl_template_delimiter(value),
            "AsyncAPI webhook target URL contains Hurl template delimiters",
        ),
    ):
        _require(condition, message)
    parts = urlsplit(value)
    scheme = parts.scheme.lower()
    for condition, message in (
        (scheme in {"http", "https"}, "AsyncAPI webhook target URL scheme must be http or https"),
        (
            parts.username is None and parts.password is None,
            "AsyncAPI webhook target URL must not contain credentials",
        ),
        (not parts.fragment, "AsyncAPI webhook target URL must not contain a fragment"),
    ):
        _require(condition, message)
    try:
        port = parts.port
    except ValueError as exc:
        raise AsyncapiHurlCompilationError(
            "AsyncAPI webhook target URL contains an invalid port"
        ) from exc
    hostname = parts.hostname
    _require(hostname is not None, "AsyncAPI webhook target URL must include a host")
    _reject_sensitive_query(parts.query)
    normalized_host = cast(str, hostname).lower()
    normalized_netloc = _host_with_port(normalized_host, port)
    normalized_path = parts.path or "/webhooks"
    normalized_url = urlunsplit(
        (scheme, normalized_netloc, normalized_path, parts.query, ""),
    )
    _require(
        not contains_secret_like_value(normalized_url),
        "AsyncAPI webhook target URL contains secret-like material",
    )
    return normalized_url, urlunsplit((scheme, normalized_netloc, "", "", ""))


def _reject_sensitive_query(query: str) -> None:
    for key, value in parse_qsl(query, keep_blank_values=True):
        _require(
            not is_sensitive_key(key),
            f"AsyncAPI webhook target URL contains sensitive query key {key!r}",
        )
        _require(
            not contains_secret_like_value(value),
            f"AsyncAPI webhook target URL contains secret-like query value for {key!r}",
        )


def _host_with_port(hostname: str, port: int | None) -> str:
    host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    return host if port is None else f"{host}:{port}"


def _target_file_stem(target_url: str) -> str:
    parts = urlsplit(target_url)
    path = parts.path.strip("/") or "webhooks"
    raw_stem = f"asyncapi-{parts.hostname or 'target'}-{path}-smoke"
    return _SAFE_STEM_RE.sub("-", raw_stem).strip(".-_").lower()


def _contains_disallowed_control(value: str) -> bool:
    return any(ord(character) < 32 and character not in "\n\r\t" for character in value)


def _has_hurl_template_delimiter(value: str) -> bool:
    return "{{" in value or "}}" in value
