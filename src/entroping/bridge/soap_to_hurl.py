import json
import re
from dataclasses import dataclass
from io import StringIO
from typing import Any, Final
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from defusedxml import ElementTree as SafeElementTree
from defusedxml.common import DefusedXmlException

from entroping.models.secrets import contains_secret_like_value, is_sensitive_key

_SAFE_STEM_RE: Final = re.compile(r"[^A-Za-z0-9_-]+")
_OPERATION_NAME_RE: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,127}\Z")
_WSDL_1_1_NAMESPACE: Final = "http://schemas.xmlsoap.org/wsdl/"
_SOAP_1_1_NAMESPACE: Final = "http://schemas.xmlsoap.org/wsdl/soap/"
_SOAP_1_2_NAMESPACE: Final = "http://schemas.xmlsoap.org/wsdl/soap12/"
_MAX_SELECTED_WSDL_BYTES: Final = 1_000_000
_MAX_SELECTED_WSDL_ELEMENTS: Final = 10_000
_MAX_SOAP_ACTION_LENGTH: Final = 1_024
_SOAP_OPERATION_NAMESPACES: Final = frozenset(
    {
        "http://schemas.xmlsoap.org/wsdl/soap/",
        "http://schemas.xmlsoap.org/wsdl/soap12/",
        "http://www.w3.org/ns/wsdl/soap",
    }
)


class SoapHurlCompilationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GeneratedSoapHurlFile:
    relative_path: str
    content: str


def compile_wsdl_to_soap_hurl(
    wsdl_xml: str,
    *,
    target_url: str,
    operation_name: str | None = None,
) -> GeneratedSoapHurlFile:
    _validate_wsdl_text(wsdl_xml)
    if operation_name is not None:
        _validate_operation_selector(operation_name)
        _validate_selected_wsdl_size(wsdl_xml)
        root, namespace_scopes = _load_selected_wsdl_document(wsdl_xml)
        soap_action = _select_soap_action(root, operation_name, namespace_scopes)
    else:
        root = _load_wsdl_document(wsdl_xml)
        soap_action = None
    operation_count = _wsdl_port_type_operation_count(root)
    if operation_count == 0:
        msg = "WSDL document must define at least one WSDL portType operation"
        raise SoapHurlCompilationError(msg)

    soap_action_count = _soap_action_count(root)
    normalized_url, target_origin = _safe_target_url(target_url)
    lines = [
        "# entroping: tags=smoke,soap",
        "# entroping: source=wsdl",
        f"# entroping: target_origin={target_origin}",
        f"# entroping: operation_count={operation_count}",
        f"# entroping: soap_action_count={soap_action_count}",
        "# entroping: scaffold=soap-envelope-smoke",
        "",
        f"POST {normalized_url}",
        "Content-Type: text/xml; charset=utf-8",
        f"SOAPAction: {json.dumps(soap_action)}" if soap_action is not None else 'SOAPAction: ""',
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
            'xmlns:ent="https://entroping.dev/scaffold/soap">'
        ),
        "  <soapenv:Body>",
        "    <ent:EntropingSmokeRequest/>",
        "  </soapenv:Body>",
        "</soapenv:Envelope>",
        "HTTP 200",
        "[Asserts]",
        'xpath "local-name(/*)" == "Envelope"',
        "",
    ]
    return GeneratedSoapHurlFile(
        relative_path=f"tests/generated/{_target_file_stem(normalized_url)}.hurl",
        content="\n".join(lines),
    )


def _validate_wsdl_text(wsdl_xml: str) -> None:
    if wsdl_xml.strip() == "":
        msg = "WSDL document is required"
        raise SoapHurlCompilationError(msg)
    if _contains_disallowed_control(wsdl_xml):
        msg = "WSDL document contains disallowed control characters"
        raise SoapHurlCompilationError(msg)
    if contains_secret_like_value(wsdl_xml):
        msg = "WSDL document contains secret-like material"
        raise SoapHurlCompilationError(msg)


def _load_wsdl_document(wsdl_xml: str) -> Any:
    try:
        root = SafeElementTree.fromstring(wsdl_xml)
    except DefusedXmlException as exc:
        msg = "Unsafe WSDL XML construct"
        raise SoapHurlCompilationError(msg) from exc
    except SafeElementTree.ParseError as exc:
        msg = "Invalid WSDL XML"
        raise SoapHurlCompilationError(msg) from exc

    if _xml_local_name(root.tag) != "definitions":
        msg = "WSDL document must use a definitions root"
        raise SoapHurlCompilationError(msg)
    return root


def _load_selected_wsdl_document(wsdl_xml: str) -> tuple[Any, dict[int, dict[str, str]]]:
    pending_namespaces: dict[str, str] = {}
    namespace_scopes: dict[int, dict[str, str]] = {}
    namespace_stack: list[dict[str, str]] = []
    root: Any | None = None
    try:
        parse_events: Any = SafeElementTree.iterparse(
            StringIO(wsdl_xml),
            events=("start-ns", "start", "end"),
        )
        for event, value in parse_events:
            if event == "start-ns":
                prefix, namespace = value
                pending_namespaces[prefix] = namespace
                continue
            if event == "start":
                namespace_scope = namespace_stack[-1].copy() if namespace_stack else {}
                namespace_scope.update(pending_namespaces)
                pending_namespaces.clear()
                namespace_scopes[id(value)] = namespace_scope
                namespace_stack.append(namespace_scope)
                if len(namespace_scopes) > _MAX_SELECTED_WSDL_ELEMENTS:
                    msg = "SOAP WSDL selection exceeds complexity limits"
                    raise SoapHurlCompilationError(msg)
                if root is None:
                    root = value
                continue
            namespace_stack.pop()
    except DefusedXmlException as exc:
        msg = "Unsafe WSDL XML construct"
        raise SoapHurlCompilationError(msg) from exc
    except SafeElementTree.ParseError as exc:
        msg = "Invalid WSDL XML"
        raise SoapHurlCompilationError(msg) from exc

    if root is None:
        msg = "Invalid WSDL XML"
        raise SoapHurlCompilationError(msg)
    return root, namespace_scopes


def _validate_operation_selector(operation_name: str) -> None:
    if _OPERATION_NAME_RE.fullmatch(operation_name) is None:
        msg = "SOAP operation selector is invalid"
        raise SoapHurlCompilationError(msg)
    if contains_secret_like_value(operation_name):
        msg = "SOAP operation selector is unsafe"
        raise SoapHurlCompilationError(msg)


def _validate_selected_wsdl_size(wsdl_xml: str) -> None:
    if len(wsdl_xml.encode("utf-8")) > _MAX_SELECTED_WSDL_BYTES:
        msg = "SOAP WSDL selection exceeds complexity limits"
        raise SoapHurlCompilationError(msg)


def _select_soap_action(
    root: Any,
    operation_name: str,
    namespace_scopes: dict[int, dict[str, str]],
) -> str:
    if root.tag != f"{{{_WSDL_1_1_NAMESPACE}}}definitions":
        msg = "SOAP WSDL selection requires a WSDL 1.1 definitions root"
        raise SoapHurlCompilationError(msg)

    elements = tuple(root.iter())
    if len(elements) > _MAX_SELECTED_WSDL_ELEMENTS:
        msg = "SOAP WSDL selection exceeds complexity limits"
        raise SoapHurlCompilationError(msg)
    _reject_unsupported_selected_wsdl_elements(elements)

    matching_operations = _matching_port_type_operations(root, operation_name)
    if len(matching_operations) != 1:
        msg = "SOAP operation selection is missing or ambiguous"
        raise SoapHurlCompilationError(msg)

    port_type, _ = matching_operations[0]
    port_type_name = port_type.attrib.get("name")
    if port_type_name is None:
        msg = "SOAP operation selection is missing or ambiguous"
        raise SoapHurlCompilationError(msg)
    target_namespace = root.attrib.get("targetNamespace")
    if not isinstance(target_namespace, str) or target_namespace == "":
        msg = "SOAP operation selection is missing or ambiguous"
        raise SoapHurlCompilationError(msg)

    matching_binding_operations = _matching_binding_operations(
        root,
        target_namespace,
        port_type_name,
        operation_name,
        namespace_scopes,
    )
    if len(matching_binding_operations) != 1:
        msg = "SOAP binding operation selection is missing or ambiguous"
        raise SoapHurlCompilationError(msg)

    soap_operations = tuple(
        child
        for child in list(matching_binding_operations[0])
        if child.tag == f"{{{_SOAP_1_1_NAMESPACE}}}operation"
    )
    if len(soap_operations) != 1:
        msg = "SOAP action selection is missing or ambiguous"
        raise SoapHurlCompilationError(msg)
    soap_action = soap_operations[0].attrib.get("soapAction")
    if not isinstance(soap_action, str) or soap_action.strip() == "":
        msg = "SOAP action selection is missing or ambiguous"
        raise SoapHurlCompilationError(msg)
    if not _is_safe_soap_action(soap_action):
        msg = "SOAP action selection is unsafe"
        raise SoapHurlCompilationError(msg)
    return soap_action


def _reject_unsupported_selected_wsdl_elements(elements: tuple[Any, ...]) -> None:
    for element in elements:
        local_name = _xml_local_name(element.tag)
        if local_name in {"import", "include"}:
            msg = "SOAP WSDL selection does not support import or include"
            raise SoapHurlCompilationError(msg)
        if _xml_namespace(element.tag) == _SOAP_1_2_NAMESPACE:
            msg = "SOAP WSDL selection does not support SOAP 1.2"
            raise SoapHurlCompilationError(msg)


def _matching_port_type_operations(root: Any, operation_name: str) -> tuple[tuple[Any, Any], ...]:
    return tuple(
        (port_type, operation)
        for port_type in list(root)
        if port_type.tag == f"{{{_WSDL_1_1_NAMESPACE}}}portType"
        for operation in list(port_type)
        if operation.tag == f"{{{_WSDL_1_1_NAMESPACE}}}operation"
        and operation.attrib.get("name") == operation_name
    )


def _matching_binding_operations(
    root: Any,
    port_type_namespace: str,
    port_type_name: str,
    operation_name: str,
    namespace_scopes: dict[int, dict[str, str]],
) -> tuple[Any, ...]:
    return tuple(
        operation
        for binding in list(root)
        if binding.tag == f"{{{_WSDL_1_1_NAMESPACE}}}binding"
        and _resolve_qname(binding.attrib.get("type"), namespace_scopes.get(id(binding)))
        == (port_type_namespace, port_type_name)
        if any(child.tag == f"{{{_SOAP_1_1_NAMESPACE}}}binding" for child in list(binding))
        for operation in list(binding)
        if operation.tag == f"{{{_WSDL_1_1_NAMESPACE}}}operation"
        and operation.attrib.get("name") == operation_name
    )


def _resolve_qname(
    value: str | None, namespace_scope: dict[str, str] | None
) -> tuple[str, str] | None:
    if value is None or namespace_scope is None:
        return None
    if ":" not in value:
        return "", value
    if value.count(":") != 1:
        return None
    prefix, local_name = value.split(":")
    if prefix == "" or local_name == "":
        return None
    namespace = namespace_scope.get(prefix)
    if namespace is None:
        return None
    return namespace, local_name


def _is_safe_soap_action(value: str) -> bool:
    return (
        len(value) <= _MAX_SOAP_ACTION_LENGTH
        and not _contains_disallowed_control(value)
        and not _has_hurl_template_delimiter(value)
        and not contains_secret_like_value(value)
    )


def _wsdl_port_type_operation_count(root: Any) -> int:
    return sum(
        1
        for port_type in list(root)
        if _xml_local_name(port_type.tag) == "portType"
        for child in list(port_type)
        if _xml_local_name(child.tag) == "operation"
    )


def _soap_action_count(root: Any) -> int:
    count = 0
    for element in root.iter():
        if _xml_local_name(element.tag) != "operation":
            continue
        namespace = _xml_namespace(element.tag)
        if namespace not in _SOAP_OPERATION_NAMESPACES:
            continue
        if "soapAction" in element.attrib:
            count += 1
    return count


def _safe_target_url(value: str) -> tuple[str, str]:
    if not value:
        msg = "SOAP target URL is required"
        raise SoapHurlCompilationError(msg)
    if _contains_disallowed_control(value):
        msg = "SOAP target URL contains control characters"
        raise SoapHurlCompilationError(msg)
    if any(character.isspace() for character in value):
        msg = "SOAP target URL must not contain whitespace"
        raise SoapHurlCompilationError(msg)
    if _has_hurl_template_delimiter(value):
        msg = "SOAP target URL contains Hurl template delimiters"
        raise SoapHurlCompilationError(msg)

    parts = urlsplit(value)
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        msg = "SOAP target URL scheme must be http or https"
        raise SoapHurlCompilationError(msg)
    if parts.username is not None or parts.password is not None:
        msg = "SOAP target URL must not contain credentials"
        raise SoapHurlCompilationError(msg)
    if parts.fragment:
        msg = "SOAP target URL must not contain a fragment"
        raise SoapHurlCompilationError(msg)

    try:
        port = parts.port
    except ValueError as exc:
        msg = "SOAP target URL contains an invalid port"
        raise SoapHurlCompilationError(msg) from exc

    hostname = parts.hostname
    if hostname is None:
        msg = "SOAP target URL must include a host"
        raise SoapHurlCompilationError(msg)

    _reject_sensitive_query(parts.query)
    normalized_host = hostname.lower()
    normalized_netloc = _host_with_port(normalized_host, port)
    normalized_path = parts.path or "/soap"
    normalized_url = urlunsplit(
        (scheme, normalized_netloc, normalized_path, parts.query, ""),
    )
    if contains_secret_like_value(normalized_url):
        msg = "SOAP target URL contains secret-like material"
        raise SoapHurlCompilationError(msg)
    return normalized_url, urlunsplit((scheme, normalized_netloc, "", "", ""))


def _reject_sensitive_query(query: str) -> None:
    for key, value in parse_qsl(query, keep_blank_values=True):
        if is_sensitive_key(key):
            msg = "SOAP target URL contains sensitive query key"
            raise SoapHurlCompilationError(msg)
        if contains_secret_like_value(value):
            msg = "SOAP target URL contains secret-like query value"
            raise SoapHurlCompilationError(msg)


def _host_with_port(hostname: str, port: int | None) -> str:
    host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    if port is None:
        return host
    return f"{host}:{port}"


def _target_file_stem(target_url: str) -> str:
    parts = urlsplit(target_url)
    path = parts.path.strip("/") or "soap"
    raw_stem = f"soap-{parts.hostname or 'target'}-{path}-smoke"
    return _SAFE_STEM_RE.sub("-", raw_stem).strip(".-_").lower()


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_namespace(tag: str) -> str:
    if not tag.startswith("{"):
        return ""
    return tag[1:].split("}", 1)[0]


def _contains_disallowed_control(value: str) -> bool:
    return any(ord(character) < 32 and character not in "\n\r\t" for character in value)


def _has_hurl_template_delimiter(value: str) -> bool:
    return "{{" in value or "}}" in value
