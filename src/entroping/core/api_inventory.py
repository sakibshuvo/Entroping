"""Deterministic local API surface inventory reports."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path, PureWindowsPath
from typing import Final, Literal, cast
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field

from entroping.core.config_loader import QanstitutionLoadError, load_qanstitution
from entroping.core.evidence_common import (
    LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES,
    contains_unredacted_evidence_secret,
    safe_evidence_text,
)
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.safe_write import SafeWriteError, safe_write_text
from entroping.models.hurl import (
    HurlMetadataSyntaxError,
    parse_hurl_exchanges,
    parse_hurl_metadata,
)

API_INVENTORY_SCHEMA_VERSION: Final = "entroping.api-inventory.v1"

ApiInventoryOutput = Literal["md", "json"]
ApiInventoryStatus = Literal["ready", "partial", "insufficient"]
ApiSourceState = Literal["present", "missing", "invalid", "unsafe"]
ApiStyle = Literal[
    "rest_openapi",
    "graphql",
    "soap_xml",
    "grpc_proto",
    "asyncapi",
    "webhook_event",
    "websocket_realtime",
    "unknown_http",
]
ApiSourceKind = Literal[
    "configured_openapi",
    "conventional_openapi",
    "hurl_test",
    "schema_file",
]

_MAX_API_INVENTORY_ARTIFACT_BYTES: Final = LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES
_DEFAULT_OUTPUTS: Final[dict[ApiInventoryOutput, Path]] = {
    "md": Path("reports") / "api-inventory.md",
    "json": Path("reports") / "api-inventory.json",
}
_IGNORED_DIRECTORY_NAMES: Final[frozenset[str]] = frozenset(
    {
        ".entroping",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "reports",
        "venv",
    }
)
_OPENAPI_FILENAMES: Final[frozenset[str]] = frozenset(
    {
        "openapi.json",
        "openapi.yaml",
        "openapi.yml",
        "swagger.json",
        "swagger.yaml",
        "swagger.yml",
    }
)
_SCHEMA_EXTENSIONS: Final[dict[str, ApiStyle]] = {
    ".graphql": "graphql",
    ".graphqls": "graphql",
    ".gql": "graphql",
    ".wsdl": "soap_xml",
    ".proto": "grpc_proto",
}
_ASYNCAPI_FILENAMES: Final[frozenset[str]] = frozenset(
    {"asyncapi.json", "asyncapi.yaml", "asyncapi.yml"}
)
_ASYNCAPI_SUFFIXES: Final[tuple[str, ...]] = (
    ".asyncapi.json",
    ".asyncapi.yaml",
    ".asyncapi.yml",
)
_WEBHOOK_EVENT_SUFFIXES: Final[tuple[str, ...]] = (
    ".event-contract.json",
    ".event-contract.yaml",
    ".event-contract.yml",
    ".event_contract.json",
    ".event_contract.yaml",
    ".event_contract.yml",
    ".webhook.json",
    ".webhook.yaml",
    ".webhook.yml",
    ".webhooks.json",
    ".webhooks.yaml",
    ".webhooks.yml",
)
_WEBSOCKET_REALTIME_SUFFIXES: Final[tuple[str, ...]] = (
    ".websocket.json",
    ".websocket.yaml",
    ".websocket.yml",
    ".websocket-contract.json",
    ".websocket-contract.yaml",
    ".websocket-contract.yml",
    ".websocket_contract.json",
    ".websocket_contract.yaml",
    ".websocket_contract.yml",
    ".realtime.json",
    ".realtime.yaml",
    ".realtime.yml",
    ".socketio.json",
    ".socketio.yaml",
    ".socketio.yml",
)
_WEBSOCKET_REALTIME_MAPPING_KEYS: Final[tuple[str, ...]] = (
    "channels",
    "messages",
    "events",
    "websockets",
    "sockets",
    "subscriptions",
    "socketio",
    "socketio_events",
)
_HTTP_METHODS: Final[frozenset[str]] = frozenset(
    {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
)
_SHA256_RE: Final = re.compile(r"\b[0-9a-f]{64}\b")
_GRAPHQL_BLOCK_STRING_RE: Final = re.compile(r'"""(?:.|\n)*?"""')
_GRAPHQL_LINE_COMMENT_RE: Final = re.compile(r"(?m)#.*$")
_GRAPHQL_ROOT_OPERATION_BLOCK_RE: Final = re.compile(
    r"\b(?:extend\s+)?type\s+(?:Query|Mutation|Subscription)\b[^{]*\{(?P<body>.*?)\}",
    re.DOTALL,
)
_GRAPHQL_ROOT_FIELD_RE: Final = re.compile(
    r"(?m)^[ \t]*[_A-Za-z][_0-9A-Za-z]*\s*(?:\([^{}]*\)\s*)?:"
)
_PROTO_STRING_RE: Final = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
_PROTO_BLOCK_COMMENT_RE: Final = re.compile(r"/\*.*?\*/", re.DOTALL)
_PROTO_LINE_COMMENT_RE: Final = re.compile(r"(?m)//.*$")
_PROTO_RPC_RE: Final = re.compile(r"(?m)^[ \t]*rpc\s+[_A-Za-z][_0-9A-Za-z]*\s*\(")
_STYLE_LABELS: Final[dict[ApiStyle, str]] = {
    "rest_openapi": "REST/OpenAPI",
    "graphql": "GraphQL",
    "soap_xml": "SOAP/XML",
    "grpc_proto": "gRPC/proto",
    "asyncapi": "AsyncAPI",
    "webhook_event": "Webhook/Event",
    "websocket_realtime": "WebSocket/realtime",
    "unknown_http": "Unknown HTTP",
}
_STYLE_ACTIONS: Final[dict[ApiStyle, str]] = {
    "rest_openapi": "Use Architect OpenAPI generation and audit reports.",
    "graphql": "Keep GraphQL coverage in committed Hurl while schema-aware generation is added.",
    "soap_xml": "Use SOAP-over-HTTP Hurl assertions and QAnstitution XML gates.",
    "grpc_proto": "Use proto evidence as future gRPC/proto adapter input.",
    "asyncapi": "Use AsyncAPI evidence as future message-contract adapter input.",
    "webhook_event": "Use webhook/event contract evidence with replayable Hurl coverage.",
    "websocket_realtime": (
        "Use WebSocket/realtime contract evidence before state-machine test adapters."
    ),
    "unknown_http": (
        "Add protocol tags or source specs so inventory can classify this HTTP surface."
    ),
}


class ApiInventoryError(ValueError):
    """Raised when an API inventory report cannot be generated safely."""


class ApiInventorySummary(BaseModel):
    """Aggregate API inventory state."""

    model_config = ConfigDict(extra="forbid")

    status: ApiInventoryStatus
    sources_total: int = Field(ge=0)
    sources_present: int = Field(ge=0)
    sources_missing: int = Field(ge=0)
    sources_invalid: int = Field(ge=0)
    sources_unsafe: int = Field(ge=0)
    styles_total: int = Field(ge=0)
    hurl_tests_total: int = Field(ge=0)
    operations_total: int = Field(ge=0)


class ApiInventorySource(BaseModel):
    """One local source or evidence artifact in the API inventory."""

    model_config = ConfigDict(extra="forbid")

    kind: ApiSourceKind
    style: ApiStyle
    path: str
    state: ApiSourceState
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    tags: tuple[str, ...] = ()
    operations: int = Field(ge=0)
    summary: str


class ApiInventoryStyleSummary(BaseModel):
    """Aggregated source and operation counts for one API style."""

    model_config = ConfigDict(extra="forbid")

    style: ApiStyle
    label: str
    sources: int = Field(ge=0)
    hurl_tests: int = Field(ge=0)
    operations: int = Field(ge=0)
    tags: tuple[str, ...] = ()
    source_paths: tuple[str, ...] = ()
    next_action: str


class ApiInventoryPacket(BaseModel):
    """Schema-versioned local API inventory packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.api-inventory.v1"] = API_INVENTORY_SCHEMA_VERSION
    generated_at: str
    project: str | None
    summary: ApiInventorySummary
    sources: tuple[ApiInventorySource, ...]
    styles: tuple[ApiInventoryStyleSummary, ...]


@dataclass(frozen=True, slots=True)
class ApiInventoryResult:
    """Result of writing one API inventory packet."""

    output_path: Path
    packet: ApiInventoryPacket


def run_api_inventory_report(
    *,
    project_root: Path,
    output: ApiInventoryOutput,
    output_path: Path | None = None,
) -> ApiInventoryResult:
    """Write a local API inventory report."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported API inventory output: {output}"
        raise ApiInventoryError(msg)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUTS[output], root=root)
    packet = build_api_inventory(project_root=root)
    content = _render_packet_content(packet, output=output)
    if _contains_unredacted_secret_like_value(_content_for_secret_scan(content)):
        msg = "API inventory contains secret-like content"
        raise ApiInventoryError(msg)
    try:
        written = safe_write_text(destination, content, artifact="API inventory", root=root)
    except SafeWriteError as exc:
        raise ApiInventoryError(str(exc)) from exc
    return ApiInventoryResult(output_path=written, packet=packet)


def build_api_inventory(*, project_root: Path) -> ApiInventoryPacket:
    """Build a value-free API inventory from local files."""

    root = project_root.expanduser().resolve()
    configured = _configured_openapi_source(root=root)
    configured_paths = {source.path for source in configured}
    discovered_sources = (
        *configured,
        *_conventional_openapi_sources(root=root, skip_paths=configured_paths),
        *_hurl_test_sources(root=root),
        *_schema_file_sources(root=root),
    )
    sources = tuple(sorted(discovered_sources, key=lambda source: (source.path, source.kind)))
    styles = _style_summaries(sources)
    summary = _summary(sources=sources, styles=styles)
    return ApiInventoryPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=_project_name(root=root),
        summary=summary,
        sources=sources,
        styles=styles,
    )


def render_api_inventory_markdown(packet: ApiInventoryPacket) -> str:
    """Render a human-readable API inventory packet."""

    lines = [
        "# Entroping API Inventory",
        "",
        f"- Status: `{packet.summary.status}`",
        f"- Project: `{_inline_code(packet.project or 'unknown')}`",
        "- Sources: "
        f"`{packet.summary.sources_present}/{packet.summary.sources_total}` present, "
        f"`{packet.summary.sources_missing}` missing, "
        f"`{packet.summary.sources_invalid}` invalid, "
        f"`{packet.summary.sources_unsafe}` unsafe",
        f"- API styles: `{packet.summary.styles_total}`",
        f"- Hurl tests: `{packet.summary.hurl_tests_total}`",
        f"- Operations: `{packet.summary.operations_total}`",
        "",
        "## Styles",
        "",
    ]
    if not packet.styles:
        lines.append("No API styles were detected.")
    else:
        lines.extend(
            [
                "| Style | Sources | Hurl Tests | Operations | Tags | Next Action |",
                "| --- | ---: | ---: | ---: | --- | --- |",
            ]
        )
        for style in packet.styles:
            lines.append(
                "| "
                f"{_markdown_cell(style.label)} | "
                f"{style.sources} | "
                f"{style.hurl_tests} | "
                f"{style.operations} | "
                f"{_markdown_cell(', '.join(style.tags) or 'n/a')} | "
                f"{_markdown_cell(style.next_action)} |"
            )

    lines.extend(
        [
            "",
            "## Sources",
            "",
            "| Kind | Style | State | Path | Operations | Tags | SHA-256 | Summary |",
            "| --- | --- | --- | --- | ---: | --- | --- | --- |",
        ]
    )
    for source in packet.sources:
        lines.append(
            "| "
            f"{_markdown_cell(source.kind)} | "
            f"{_markdown_cell(source.style)} | "
            f"{_markdown_cell(source.state)} | "
            f"{_markdown_cell(source.path)} | "
            f"{source.operations} | "
            f"{_markdown_cell(', '.join(source.tags) or 'n/a')} | "
            f"{_markdown_cell(source.sha256 or 'n/a')} | "
            f"{_markdown_cell(source.summary)} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_packet_content(packet: ApiInventoryPacket, *, output: ApiInventoryOutput) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_api_inventory_markdown(packet)


def _configured_openapi_source(*, root: Path) -> tuple[ApiInventorySource, ...]:
    qanstitution_path = root / "qanstitution.yaml"
    if not qanstitution_path.exists():
        return ()
    try:
        law = load_qanstitution(qanstitution_path)
    except QanstitutionLoadError as exc:
        return (
            _source(
                kind="configured_openapi",
                style="rest_openapi",
                path="qanstitution.yaml",
                state="invalid",
                sha256=None,
                operations=0,
                summary=_safe_text(str(exc)),
            ),
        )
    if law.sources is None or law.sources.spec is None or not law.sources.spec.strip():
        return ()
    spec_ref = law.sources.spec.strip()
    path_error = _reject_unsafe_relative_reference(spec_ref)
    if path_error is not None:
        return (
            _source(
                kind="configured_openapi",
                style="rest_openapi",
                path=_safe_text(spec_ref),
                state="unsafe",
                sha256=None,
                operations=0,
                summary=path_error,
            ),
        )
    return (_load_openapi_source(root=root, raw_path=Path(spec_ref), kind="configured_openapi"),)


def _conventional_openapi_sources(
    *,
    root: Path,
    skip_paths: set[str],
) -> tuple[ApiInventorySource, ...]:
    sources: list[ApiInventorySource] = []
    for path in _iter_candidate_files(root=root):
        if path.name.lower() not in _OPENAPI_FILENAMES:
            continue
        relative_path = _relative_path(path, root=root)
        if relative_path in skip_paths:
            continue
        sources.append(
            _load_openapi_source(
                root=root,
                raw_path=Path(relative_path),
                kind="conventional_openapi",
            )
        )
    return tuple(sources)


def _hurl_test_sources(*, root: Path) -> tuple[ApiInventorySource, ...]:
    tests_root = root / "tests"
    if not tests_root.exists():
        return ()
    sources: list[ApiInventorySource] = []
    for path in sorted(tests_root.rglob("*.hurl"), key=lambda candidate: str(candidate)):
        if _ignored(path, root=root):
            continue
        sources.append(_load_hurl_source(root=root, raw_path=Path(_relative_path(path, root=root))))
    return tuple(sources)


def _schema_file_sources(*, root: Path) -> tuple[ApiInventorySource, ...]:
    sources: list[ApiInventorySource] = []
    for path in _iter_candidate_files(root=root):
        style = _schema_style_for_path(path)
        if style is None:
            continue
        relative_path = _relative_path(path, root=root)
        sources.append(
            _load_schema_source(root=root, raw_path=Path(relative_path), style=style)
        )
    return tuple(sources)


def _load_openapi_source(
    *,
    root: Path,
    raw_path: Path,
    kind: Literal["configured_openapi", "conventional_openapi"],
) -> ApiInventorySource:
    path_text = raw_path.as_posix()
    resolved = _resolve_source_path(raw_path, root=root)
    if isinstance(resolved, ApiInventorySource):
        return resolved.model_copy(update={"kind": kind, "style": "rest_openapi"})
    if not resolved.exists():
        return _source(
            kind=kind,
            style="rest_openapi",
            path=path_text,
            state="missing",
            sha256=None,
            operations=0,
            summary="OpenAPI source is missing.",
        )
    loaded = _read_source_bytes(
        resolved,
        artifact="OpenAPI source",
        root=root,
        kind=kind,
        style="rest_openapi",
    )
    if isinstance(loaded, ApiInventorySource):
        return loaded
    raw_bytes, raw_text = loaded
    try:
        document = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        return _source(
            kind=kind,
            style="rest_openapi",
            path=path_text,
            state="invalid",
            sha256=None,
            operations=0,
            summary=_safe_text(f"Invalid OpenAPI YAML: {exc}"),
        )
    operations = _openapi_operation_count(document)
    if operations is None:
        return _source(
            kind=kind,
            style="rest_openapi",
            path=path_text,
            state="invalid",
            sha256=None,
            operations=0,
            summary="OpenAPI document must contain a paths mapping.",
        )
    return _source(
        kind=kind,
        style="rest_openapi",
        path=path_text,
        state="present",
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        operations=operations,
        summary=f"{operations} OpenAPI operations.",
    )


def _load_hurl_source(*, root: Path, raw_path: Path) -> ApiInventorySource:
    path_text = raw_path.as_posix()
    resolved = _resolve_source_path(raw_path, root=root)
    if isinstance(resolved, ApiInventorySource):
        return resolved.model_copy(update={"kind": "hurl_test"})
    loaded = _read_source_bytes(
        resolved,
        artifact="Hurl test",
        root=root,
        kind="hurl_test",
        style="unknown_http",
    )
    if isinstance(loaded, ApiInventorySource):
        return loaded
    raw_bytes, raw_text = loaded
    try:
        metadata = parse_hurl_metadata(raw_text, source=raw_path)
        exchanges = parse_hurl_exchanges(raw_text)
    except HurlMetadataSyntaxError as exc:
        return _source(
            kind="hurl_test",
            style="unknown_http",
            path=path_text,
            state="invalid",
            sha256=None,
            operations=0,
            summary=_safe_text(str(exc)),
        )
    style = _style_from_tags(metadata.tags)
    if style is None:
        style = "unknown_http"
    return _source(
        kind="hurl_test",
        style=style,
        path=path_text,
        state="present",
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        tags=tuple(sorted(metadata.tags)),
        operations=len(exchanges),
        summary=f"{len(exchanges)} Hurl exchanges.",
    )


def _load_schema_source(*, root: Path, raw_path: Path, style: ApiStyle) -> ApiInventorySource:
    path_text = raw_path.as_posix()
    resolved = _resolve_source_path(raw_path, root=root)
    if isinstance(resolved, ApiInventorySource):
        return resolved.model_copy(update={"kind": "schema_file", "style": style})
    loaded = _read_source_bytes(
        resolved,
        artifact="API schema",
        root=root,
        kind="schema_file",
        style=style,
    )
    if isinstance(loaded, ApiInventorySource):
        return loaded
    raw_bytes, raw_text = loaded
    if style == "graphql":
        graphql_operations = _graphql_operation_count(raw_text)
        return _source(
            kind="schema_file",
            style=style,
            path=path_text,
            state="present",
            sha256=hashlib.sha256(raw_bytes).hexdigest(),
            operations=graphql_operations,
            summary=(
                f"{graphql_operations} GraphQL root "
                f"{_operation_word(graphql_operations)}."
            ),
        )
    if style == "grpc_proto":
        proto_operations = _proto_rpc_operation_count(raw_text)
        return _source(
            kind="schema_file",
            style=style,
            path=path_text,
            state="present",
            sha256=hashlib.sha256(raw_bytes).hexdigest(),
            operations=proto_operations,
            summary=f"{proto_operations} proto RPC {_operation_word(proto_operations)}.",
        )
    if style == "asyncapi":
        document = _load_yaml_document(
            raw_text,
            kind="schema_file",
            style=style,
            path=path_text,
            label="AsyncAPI",
        )
        if isinstance(document, ApiInventorySource):
            return document
        asyncapi_operations = _asyncapi_operation_count(document)
        if asyncapi_operations is None:
            return _source(
                kind="schema_file",
                style=style,
                path=path_text,
                state="invalid",
                sha256=None,
                operations=0,
                summary="AsyncAPI document must contain operations or channels.",
            )
        return _source(
            kind="schema_file",
            style=style,
            path=path_text,
            state="present",
            sha256=hashlib.sha256(raw_bytes).hexdigest(),
            operations=asyncapi_operations,
            summary=f"{asyncapi_operations} AsyncAPI operations/channels.",
        )
    if style == "webhook_event":
        document = _load_yaml_document(
            raw_text,
            kind="schema_file",
            style=style,
            path=path_text,
            label="webhook/event contract",
        )
        if isinstance(document, ApiInventorySource):
            return document
        webhook_operations = _webhook_event_operation_count(document)
        if webhook_operations is None:
            return _source(
                kind="schema_file",
                style=style,
                path=path_text,
                state="invalid",
                sha256=None,
                operations=0,
                summary=(
                    "Webhook/event contract document must contain a webhooks or events "
                    "mapping."
                ),
            )
        return _source(
            kind="schema_file",
            style=style,
            path=path_text,
            state="present",
            sha256=hashlib.sha256(raw_bytes).hexdigest(),
            operations=webhook_operations,
            summary=(
                f"{webhook_operations} webhook/event contract "
                f"{_entry_word(webhook_operations)}."
            ),
        )
    if style == "websocket_realtime":
        document = _load_yaml_document(
            raw_text,
            kind="schema_file",
            style=style,
            path=path_text,
            label="WebSocket/realtime contract",
        )
        if isinstance(document, ApiInventorySource):
            return document
        websocket_operations = _websocket_realtime_operation_count(document)
        if websocket_operations is None:
            return _source(
                kind="schema_file",
                style=style,
                path=path_text,
                state="invalid",
                sha256=None,
                operations=0,
                summary="WebSocket/realtime document must contain a realtime mapping.",
            )
        return _source(
            kind="schema_file",
            style=style,
            path=path_text,
            state="present",
            sha256=hashlib.sha256(raw_bytes).hexdigest(),
            operations=websocket_operations,
            summary=(
                f"{websocket_operations} WebSocket/realtime "
                f"{_entry_word(websocket_operations)}."
            ),
        )
    return _source(
        kind="schema_file",
        style=style,
        path=path_text,
        state="present",
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        operations=0,
        summary=f"{_STYLE_LABELS[style]} schema file.",
    )


def _resolve_source_path(
    raw_path: Path,
    *,
    root: Path,
) -> Path | ApiInventorySource:
    path = root / raw_path
    try:
        symlink_path = first_symlink_path_component(path, root=root)
    except ValueError:
        return _source(
            kind="schema_file",
            style="unknown_http",
            path=raw_path.as_posix(),
            state="unsafe",
            sha256=None,
            operations=0,
            summary="API inventory source path must stay under the project root",
        )
    if symlink_path is not None:
        return _source(
            kind="schema_file",
            style="unknown_http",
            path=raw_path.as_posix(),
            state="unsafe",
            sha256=None,
            operations=0,
            summary=(
                "API inventory source path uses symlinked component: "
                f"{_relative_path(symlink_path, root=root)}"
            ),
        )
    if path.exists() and not path.is_file():
        return _source(
            kind="schema_file",
            style="unknown_http",
            path=raw_path.as_posix(),
            state="unsafe",
            sha256=None,
            operations=0,
            summary=f"API inventory source path is not a file: {raw_path.as_posix()}",
        )
    return path


def _read_source_bytes(
    path: Path,
    *,
    artifact: str,
    root: Path,
    kind: ApiSourceKind,
    style: ApiStyle,
) -> tuple[bytes, str] | ApiInventorySource:
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        return _source(
            kind=kind,
            style=style,
            path=_relative_path(path, root=root),
            state="invalid",
            sha256=None,
            operations=0,
            summary=_safe_text(f"Could not read {artifact}: {exc}"),
        )
    if len(raw_bytes) > _MAX_API_INVENTORY_ARTIFACT_BYTES:
        return _source(
            kind=kind,
            style=style,
            path=_relative_path(path, root=root),
            state="invalid",
            sha256=None,
            operations=0,
            summary=f"{artifact} {path.name} exceeds {_MAX_API_INVENTORY_ARTIFACT_BYTES} bytes",
        )
    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        return _source(
            kind=kind,
            style=style,
            path=_relative_path(path, root=root),
            state="invalid",
            sha256=None,
            operations=0,
            summary=_safe_text(f"Could not decode {artifact} as UTF-8: {exc}"),
        )
    if _contains_unredacted_secret_like_value(raw_text):
        return _source(
            kind=kind,
            style=style,
            path=_relative_path(path, root=root),
            state="unsafe",
            sha256=None,
            operations=0,
            summary=f"{artifact} contains secret-like content.",
        )
    return raw_bytes, raw_text


def _openapi_operation_count(document: object) -> int | None:
    if not isinstance(document, dict):
        return None
    paths = document.get("paths")
    if not isinstance(paths, dict):
        return None
    operations = 0
    for path_item in paths.values():
        if not isinstance(path_item, dict):
            continue
        operations += sum(
            1
            for method, operation in path_item.items()
            if isinstance(method, str)
            and method.lower() in _HTTP_METHODS
            and isinstance(operation, dict)
        )
    return operations


def _load_yaml_document(
    raw_text: str,
    *,
    kind: ApiSourceKind,
    style: ApiStyle,
    path: str,
    label: str,
) -> object | ApiInventorySource:
    try:
        return cast(object, yaml.safe_load(raw_text))
    except yaml.YAMLError as exc:
        return _source(
            kind=kind,
            style=style,
            path=path,
            state="invalid",
            sha256=None,
            operations=0,
            summary=_safe_text(f"Invalid {label} YAML: {exc}"),
        )


def _graphql_operation_count(raw_text: str) -> int:
    normalized = _strip_graphql_ignored_text(raw_text)
    return sum(
        len(_GRAPHQL_ROOT_FIELD_RE.findall(match.group("body")))
        for match in _GRAPHQL_ROOT_OPERATION_BLOCK_RE.finditer(normalized)
    )


def _strip_graphql_ignored_text(raw_text: str) -> str:
    without_block_strings = _GRAPHQL_BLOCK_STRING_RE.sub("", raw_text)
    return _GRAPHQL_LINE_COMMENT_RE.sub("", without_block_strings)


def _proto_rpc_operation_count(raw_text: str) -> int:
    normalized = _strip_proto_ignored_text(raw_text)
    return len(_PROTO_RPC_RE.findall(normalized))


def _strip_proto_ignored_text(raw_text: str) -> str:
    without_strings = _PROTO_STRING_RE.sub("", raw_text)
    without_block_comments = _PROTO_BLOCK_COMMENT_RE.sub("", without_strings)
    return _PROTO_LINE_COMMENT_RE.sub("", without_block_comments)


def _asyncapi_operation_count(document: object) -> int | None:
    if not isinstance(document, dict):
        return None
    operations = document.get("operations")
    if isinstance(operations, dict):
        return len(operations)
    channels = document.get("channels")
    if not isinstance(channels, dict):
        return None
    channel_operations = 0
    for channel in channels.values():
        if not isinstance(channel, dict):
            continue
        channel_operations += sum(
            1
            for operation_id in ("publish", "subscribe")
            if isinstance(channel.get(operation_id), dict)
        )
    return channel_operations or len(channels)


def _webhook_event_operation_count(document: object) -> int | None:
    if not isinstance(document, dict):
        return None
    for key in ("webhooks", "events", "event_contracts"):
        entries = document.get(key)
        if isinstance(entries, dict):
            return len(entries)
    return None


def _websocket_realtime_operation_count(document: object) -> int | None:
    if not isinstance(document, dict):
        return None
    for key in _WEBSOCKET_REALTIME_MAPPING_KEYS:
        entries = document.get(key)
        if isinstance(entries, dict):
            return len(entries)
    return None


def _entry_word(count: int) -> str:
    if count == 1:
        return "entry"
    return "entries"


def _operation_word(count: int) -> str:
    if count == 1:
        return "operation"
    return "operations"


def _style_from_tags(tags: frozenset[str]) -> ApiStyle | None:
    """Map explicit protocol tags with deterministic priority.

    When a test carries multiple protocol tags, the report prefers the more
    specialized API style in this order: GraphQL, SOAP/XML, gRPC/proto,
    AsyncAPI, webhook/event, WebSocket/realtime, REST.
    """

    normalized = {tag.lower() for tag in tags}
    if "graphql" in normalized:
        return "graphql"
    if "soap" in normalized or "soap_xml" in normalized:
        return "soap_xml"
    if "grpc" in normalized or "grpc_proto" in normalized or "proto" in normalized:
        return "grpc_proto"
    if "asyncapi" in normalized or "async_api" in normalized:
        return "asyncapi"
    if (
        "webhook" in normalized
        or "webhooks" in normalized
        or "event-contract" in normalized
        or "event_contract" in normalized
    ):
        return "webhook_event"
    if (
        "websocket" in normalized
        or "websocket_realtime" in normalized
        or "ws" in normalized
        or "wss" in normalized
        or "socketio" in normalized
        or "realtime" in normalized
    ):
        return "websocket_realtime"
    if "openapi" in normalized or "rest" in normalized or "rest_openapi" in normalized:
        return "rest_openapi"
    return None


def _schema_style_for_path(path: Path) -> ApiStyle | None:
    name = path.name.lower()
    if name in _ASYNCAPI_FILENAMES or name.endswith(_ASYNCAPI_SUFFIXES):
        return "asyncapi"
    if name.endswith(_WEBHOOK_EVENT_SUFFIXES):
        return "webhook_event"
    if name.endswith(_WEBSOCKET_REALTIME_SUFFIXES):
        return "websocket_realtime"
    return _SCHEMA_EXTENSIONS.get(path.suffix.lower())


def _style_summaries(
    sources: tuple[ApiInventorySource, ...],
) -> tuple[ApiInventoryStyleSummary, ...]:
    summaries: list[ApiInventoryStyleSummary] = []
    for style in _STYLE_LABELS:
        present_sources = [
            source for source in sources if source.state == "present" and source.style == style
        ]
        if not present_sources:
            continue
        tags = sorted({tag for source in present_sources for tag in source.tags})
        summaries.append(
            ApiInventoryStyleSummary(
                style=style,
                label=_STYLE_LABELS[style],
                sources=len(present_sources),
                hurl_tests=sum(1 for source in present_sources if source.kind == "hurl_test"),
                operations=sum(source.operations for source in present_sources),
                tags=tuple(tags),
                source_paths=tuple(source.path for source in present_sources),
                next_action=_STYLE_ACTIONS[style],
            )
        )
    return tuple(summaries)


def _summary(
    *,
    sources: tuple[ApiInventorySource, ...],
    styles: tuple[ApiInventoryStyleSummary, ...],
) -> ApiInventorySummary:
    present = sum(1 for source in sources if source.state == "present")
    missing = sum(1 for source in sources if source.state == "missing")
    invalid = sum(1 for source in sources if source.state == "invalid")
    unsafe = sum(1 for source in sources if source.state == "unsafe")
    if present > 0 and not (missing or invalid or unsafe):
        status: ApiInventoryStatus = "ready"
    elif present > 0 or missing > 0 or invalid > 0 or unsafe > 0:
        status = "partial"
    else:
        status = "insufficient"
    return ApiInventorySummary(
        status=status,
        sources_total=len(sources),
        sources_present=present,
        sources_missing=missing,
        sources_invalid=invalid,
        sources_unsafe=unsafe,
        styles_total=len(styles),
        hurl_tests_total=sum(
            1
            for source in sources
            if source.kind == "hurl_test" and source.state == "present"
        ),
        operations_total=sum(source.operations for source in sources if source.state == "present"),
    )


def _project_name(*, root: Path) -> str | None:
    try:
        law = load_qanstitution(root / "qanstitution.yaml")
    except QanstitutionLoadError:
        return None
    return _safe_optional_text(law.project)


def _iter_candidate_files(*, root: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if _ignored(path, root=root):
            continue
        paths.append(path)
    return tuple(sorted(paths, key=lambda candidate: _relative_path(candidate, root=root)))


def _ignored(path: Path, *, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    for part in relative.parts[:-1]:
        if part in _IGNORED_DIRECTORY_NAMES or part.startswith("."):
            return True
    return False


def _reject_unsafe_relative_reference(value: str) -> str | None:
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        return "API inventory source reference must not contain control characters"
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"}:
        return "Remote API source references are not supported"
    if parsed.scheme:
        return f"Unsupported API source reference scheme: {parsed.scheme}"
    if Path(value).is_absolute() or PureWindowsPath(value).is_absolute():
        return "API source reference must be project-relative"
    if ".." in Path(value).parts:
        return "API source reference must stay under the project root"
    return None


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    path = raw_path.expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        symlink_path = first_symlink_path_component(path, root=root)
    except ValueError as exc:
        msg = "API inventory output path must stay under the project root"
        raise ApiInventoryError(msg) from exc
    if symlink_path is not None:
        display_path = symlink_path.relative_to(root).as_posix()
        msg = f"API inventory output path uses symlinked component: {display_path}"
        raise ApiInventoryError(msg)
    resolved = path.resolve(strict=False)
    try:
        relative_parts = resolved.relative_to(root).parts
    except ValueError as exc:
        msg = "API inventory output path must stay under the project root"
        raise ApiInventoryError(msg) from exc
    if relative_parts and relative_parts[0] in {".entroping", "envs"}:
        msg = "API inventory must not be written into .entroping or envs"
        raise ApiInventoryError(msg)
    return resolved


def _source(
    *,
    kind: ApiSourceKind,
    style: ApiStyle,
    path: str,
    state: ApiSourceState,
    sha256: str | None,
    operations: int,
    summary: str,
    tags: tuple[str, ...] = (),
) -> ApiInventorySource:
    return ApiInventorySource(
        kind=kind,
        style=style,
        path=_safe_text(path),
        state=state,
        sha256=sha256,
        tags=tuple(_safe_text(tag) for tag in tags),
        operations=operations,
        summary=_safe_text(summary),
    )


def _relative_path(path: Path, *, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return _safe_text(path.name)


def _safe_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    safe = _safe_text(value)
    return safe or None


def _safe_text(value: object) -> str:
    return safe_evidence_text(str(value))


def _contains_unredacted_secret_like_value(value: str) -> bool:
    return contains_unredacted_evidence_secret(value)


def _content_for_secret_scan(value: str) -> str:
    return _SHA256_RE.sub("[SHA256]", value)


def _inline_code(value: str) -> str:
    return _markdown_text(value).replace("`", "'")


def _markdown_cell(value: str) -> str:
    return _markdown_text(value).replace("\n", "<br>")


def _markdown_text(value: str) -> str:
    backslash_placeholder = "\0ENTROPING_BACKSLASH\0"
    text = value.replace("\r", " ").replace("\\", backslash_placeholder)
    text = escape(text, quote=False).replace("|", "\\|")
    return text.replace(backslash_placeholder, "&#92;")
