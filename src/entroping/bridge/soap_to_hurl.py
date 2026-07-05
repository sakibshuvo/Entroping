import re
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from defusedxml import ElementTree as SafeElementTree
from defusedxml.common import DefusedXmlException

from entroping.models.secrets import contains_secret_like_value, is_sensitive_key

_SAFE_STEM_RE: Final = re.compile(r"[^A-Za-z0-9_-]+")
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
) -> GeneratedSoapHurlFile:
    _validate_wsdl_text(wsdl_xml)
    root = _load_wsdl_document(wsdl_xml)
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
        'SOAPAction: ""',
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
        msg = f"Unsafe WSDL XML construct: {exc}"
        raise SoapHurlCompilationError(msg) from exc
    except SafeElementTree.ParseError as exc:
        msg = f"Invalid WSDL XML: {exc}"
        raise SoapHurlCompilationError(msg) from exc

    if _xml_local_name(root.tag) != "definitions":
        msg = "WSDL document must use a definitions root"
        raise SoapHurlCompilationError(msg)
    return root


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
            msg = f"SOAP target URL contains sensitive query key {key!r}"
            raise SoapHurlCompilationError(msg)
        if contains_secret_like_value(value):
            msg = f"SOAP target URL contains secret-like query value for {key!r}"
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
