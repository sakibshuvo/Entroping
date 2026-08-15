import shutil
from pathlib import Path

import pytest

from entroping.bridge.soap_to_hurl import (
    SoapHurlCompilationError,
    compile_wsdl_to_soap_hurl,
)
from entroping.core.hurl_validator import validate_hurl_content
from entroping.models.hurl import parse_hurl_exchanges, parse_hurl_metadata

REPO_ROOT = Path(__file__).resolve().parents[1]
WSDL_CONTRACT = REPO_ROOT / "examples" / "soap-api" / "contracts" / "orders.wsdl"


def _selectable_wsdl(
    operation_name: str,
    soap_action: str,
    *,
    binding_type: str = "tns:OrderPortType",
    extra_namespaces: str = "",
) -> str:
    return (
        '<definitions xmlns="http://schemas.xmlsoap.org/wsdl/" '
        'xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/" '
        'xmlns:tns="https://example.test/orders" '
        f"{extra_namespaces}"
        'targetNamespace="https://example.test/orders">'
        '<portType name="OrderPortType">'
        f'<operation name="{operation_name}" />'
        "</portType>"
        f'<binding name="OrderBinding" type="{binding_type}">'
        '<soap:binding transport="http://schemas.xmlsoap.org/soap/http" />'
        f'<operation name="{operation_name}">'
        f'<soap:operation soapAction="{soap_action}" />'
        "</operation>"
        "</binding>"
        "</definitions>"
    )


def test_compile_wsdl_to_soap_hurl_generates_deterministic_smoke_scaffold() -> None:
    generated = compile_wsdl_to_soap_hurl(
        WSDL_CONTRACT.read_text(encoding="utf-8"),
        target_url="https://soap.example.test/soap/orders",
    )

    assert generated.relative_path == (
        "tests/generated/soap-soap-example-test-soap-orders-smoke.hurl"
    )
    assert generated.content == (
        "# entroping: tags=smoke,soap\n"
        "# entroping: source=wsdl\n"
        "# entroping: target_origin=https://soap.example.test\n"
        "# entroping: operation_count=1\n"
        "# entroping: soap_action_count=1\n"
        "# entroping: scaffold=soap-envelope-smoke\n"
        "\n"
        "POST https://soap.example.test/soap/orders\n"
        "Content-Type: text/xml; charset=utf-8\n"
        'SOAPAction: ""\n'
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
        'xmlns:ent="https://entroping.dev/scaffold/soap">\n'
        "  <soapenv:Body>\n"
        "    <ent:EntropingSmokeRequest/>\n"
        "  </soapenv:Body>\n"
        "</soapenv:Envelope>\n"
        "HTTP 200\n"
        "[Asserts]\n"
        'xpath "local-name(/*)" == "Envelope"\n'
    )
    assert "GetOrder" not in generated.content
    assert "OrderService" not in generated.content
    assert "https://internal.example.test" not in generated.content
    assert "get-order" not in generated.content
    assert parse_hurl_metadata(generated.content).tags == frozenset({"smoke", "soap"})
    exchange = parse_hurl_exchanges(generated.content)[0]
    assert exchange.method == "POST"
    assert exchange.url == "https://soap.example.test/soap/orders"


def test_compile_wsdl_to_soap_hurl_selects_unique_wsdl_operation() -> None:
    generated = compile_wsdl_to_soap_hurl(
        WSDL_CONTRACT.read_text(encoding="utf-8"),
        target_url="https://soap.example.test/soap/orders",
        operation_name="GetOrder",
    )

    assert 'SOAPAction: "https://internal.example.test/actions/get-order"\n' in generated.content
    assert "    <ent:EntropingSmokeRequest/>\n" in generated.content
    assert "GetOrder" not in generated.content
    assert "OrderService" not in generated.content


def test_compile_wsdl_to_soap_hurl_uses_xml_decoded_action_without_rendering_wsdl_names() -> None:
    generated = compile_wsdl_to_soap_hurl(
        _selectable_wsdl("SendOrder", "urn:orders&amp;mode=smoke"),
        target_url="https://soap.example.test/soap/orders",
        operation_name="SendOrder",
    )

    assert 'SOAPAction: "urn:orders&mode=smoke"\n' in generated.content
    assert "SendOrder" not in generated.content
    assert "OrderPortType" not in generated.content


@pytest.mark.parametrize(
    ("binding_type", "extra_namespaces"),
    [
        ("evil:OrderPortType", 'xmlns:evil="https://evil.example.test/wsdl" '),
        ("evil:OrderPortType", ""),
    ],
)
def test_compile_wsdl_to_soap_hurl_rejects_nonmatching_binding_type_qnames(
    binding_type: str,
    extra_namespaces: str,
) -> None:
    with pytest.raises(
        SoapHurlCompilationError,
        match="SOAP binding operation selection is missing or ambiguous",
    ) as error:
        compile_wsdl_to_soap_hurl(
            _selectable_wsdl(
                "GetOrder",
                "urn:orders:get",
                binding_type=binding_type,
                extra_namespaces=extra_namespaces,
            ),
            target_url="https://soap.example.test/soap/orders",
            operation_name="GetOrder",
        )

    assert "evil" not in str(error.value)


@pytest.mark.parametrize(
    "operation_name",
    [
        "",
        " ",
        "get order",
        "get/order",
        "get{{order}}",
        "x" * 129,
        "sk-proj-secret123",
    ],
)
def test_compile_wsdl_to_soap_hurl_rejects_unsafe_operation_selectors(
    operation_name: str,
) -> None:
    with pytest.raises(SoapHurlCompilationError, match="SOAP operation selector"):
        compile_wsdl_to_soap_hurl(
            _selectable_wsdl("GetOrder", "urn:orders:get"),
            target_url="https://soap.example.test/soap/orders",
            operation_name=operation_name,
        )


@pytest.mark.parametrize(
    ("wsdl_xml", "message"),
    [
        (
            _selectable_wsdl("GetOrder", "urn:orders:get").replace(
                'name="GetOrder"',
                'name="GetOther"',
                1,
            ),
            "SOAP operation selection is missing or ambiguous",
        ),
        (
            _selectable_wsdl("GetOrder", "urn:orders:get").replace(
                "</portType>",
                '<operation name="GetOrder" /></portType>',
            ),
            "SOAP operation selection is missing or ambiguous",
        ),
        (
            _selectable_wsdl("GetOrder", "urn:orders:get").replace(
                'soapAction="urn:orders:get"',
                'soapAction=""',
            ),
            "SOAP action selection is missing or ambiguous",
        ),
        (
            _selectable_wsdl("GetOrder", "urn:orders:get").replace(
                'soapAction="urn:orders:get"',
                'soapAction="{{token}}"',
            ),
            "SOAP action selection is unsafe",
        ),
        (
            _selectable_wsdl("GetOrder", "urn:orders:get").replace(
                'xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"',
                'xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap12/"',
            ),
            "SOAP WSDL selection does not support SOAP 1.2",
        ),
        (
            _selectable_wsdl("GetOrder", "urn:orders:get").replace(
                '<portType name="OrderPortType">',
                '<import location="local.wsdl" /><portType name="OrderPortType">',
            ),
            "SOAP WSDL selection does not support import or include",
        ),
        (
            '<definitions><portType><operation name="GetOrder" /></portType></definitions>',
            "SOAP WSDL selection requires a WSDL 1.1 definitions root",
        ),
    ],
)
def test_compile_wsdl_to_soap_hurl_rejects_invalid_selected_wsdl(
    wsdl_xml: str,
    message: str,
) -> None:
    with pytest.raises(SoapHurlCompilationError, match=message):
        compile_wsdl_to_soap_hurl(
            wsdl_xml,
            target_url="https://soap.example.test/soap/orders",
            operation_name="GetOrder",
        )


def test_compile_wsdl_to_soap_hurl_rejects_overly_complex_selected_wsdl() -> None:
    wsdl_xml = (
        '<definitions xmlns="http://schemas.xmlsoap.org/wsdl/">'
        f"{'<documentation />' * 10_001}"
        "</definitions>"
    )

    with pytest.raises(SoapHurlCompilationError, match="SOAP WSDL selection exceeds complexity"):
        compile_wsdl_to_soap_hurl(
            wsdl_xml,
            target_url="https://soap.example.test/soap/orders",
            operation_name="GetOrder",
        )


def test_compile_wsdl_to_soap_hurl_selected_output_validates_with_hurlfmt_when_available() -> None:
    if shutil.which("hurlfmt") is None:
        pytest.skip("hurlfmt is not installed")

    generated = compile_wsdl_to_soap_hurl(
        WSDL_CONTRACT.read_text(encoding="utf-8"),
        target_url="https://soap.example.test/soap/orders",
        operation_name="GetOrder",
    )

    validate_hurl_content(generated.content, display_path=generated.relative_path)


def test_compile_wsdl_to_soap_hurl_accepts_local_fixture_target() -> None:
    generated = compile_wsdl_to_soap_hurl(
        WSDL_CONTRACT.read_text(encoding="utf-8"),
        target_url="http://127.0.0.1:18083/soap/orders",
    )

    assert "POST http://127.0.0.1:18083/soap/orders\n" in generated.content
    assert "# entroping: target_origin=http://127.0.0.1:18083\n" in generated.content


def test_compile_wsdl_to_soap_hurl_counts_multiple_operations_without_leaking_names() -> None:
    generated = compile_wsdl_to_soap_hurl(
        (
            '<definitions xmlns="http://schemas.xmlsoap.org/wsdl/">'
            "<portType>"
            '<operation name="CreatePayment" />'
            '<operation name="RefundPayment" />'
            "</portType>"
            "</definitions>"
        ),
        target_url="https://soap.example.test/soap/orders",
    )

    assert "# entroping: operation_count=2\n" in generated.content
    assert "CreatePayment" not in generated.content
    assert "RefundPayment" not in generated.content


def test_compile_wsdl_to_soap_hurl_ignores_unnamespaced_soap_action_shape() -> None:
    generated = compile_wsdl_to_soap_hurl(
        (
            "<definitions>"
            "<portType><operation /></portType>"
            '<binding><operation soapAction="not-soap-namespaced" /></binding>'
            "</definitions>"
        ),
        target_url="https://soap.example.test/soap/orders",
    )

    assert "# entroping: operation_count=1\n" in generated.content
    assert "# entroping: soap_action_count=0\n" in generated.content
    assert "not-soap-namespaced" not in generated.content


@pytest.mark.parametrize(
    ("wsdl_xml", "message"),
    [
        ("", "WSDL document is required"),
        ("<definitions>\x00</definitions>", "control characters"),
        (
            "<definitions><documentation>sk-proj-secret123</documentation></definitions>",
            "secret-like",
        ),
        ("<definitions><portType></definitions>", "Invalid WSDL XML"),
        (
            '<!DOCTYPE definitions [<!ENTITY payload SYSTEM "file:///etc/passwd">]>'
            "<definitions>&payload;</definitions>",
            "Unsafe WSDL XML construct",
        ),
        ("<notDefinitions />", "must use a definitions root"),
        ("<definitions />", "at least one WSDL portType operation"),
    ],
)
def test_compile_wsdl_to_soap_hurl_rejects_unsupported_or_unsafe_documents(
    wsdl_xml: str,
    message: str,
) -> None:
    with pytest.raises(SoapHurlCompilationError, match=message):
        compile_wsdl_to_soap_hurl(
            wsdl_xml,
            target_url="https://soap.example.test/soap/orders",
        )


@pytest.mark.parametrize(
    ("target_url", "message"),
    [
        ("", "SOAP target URL is required"),
        ("ftp://soap.example.test/soap/orders", "scheme must be http or https"),
        ("https://user:pass@soap.example.test/soap/orders", "must not contain credentials"),
        ("https://soap.example.test/soap/orders#fragment", "must not contain a fragment"),
        ("https://soap.example.test/soap/orders\x00", "contains control characters"),
        ("https://soap.example.test/has space", "must not contain whitespace"),
        ("https://soap.example.test/{{secret}}", "contains Hurl template delimiters"),
        ("https://soap.example.test:abc/soap/orders", "contains an invalid port"),
        ("https:///soap/orders", "must include a host"),
        ("https://soap.example.test/soap/orders?token=placeholder", "sensitive query key"),
        ("https://soap.example.test/soap/orders?ready=sk-proj-secret123", "secret-like"),
        ("https://soap.example.test/sk-proj-secret123", "secret-like"),
    ],
)
def test_compile_wsdl_to_soap_hurl_rejects_unsafe_targets(
    target_url: str,
    message: str,
) -> None:
    with pytest.raises(SoapHurlCompilationError, match=message):
        compile_wsdl_to_soap_hurl(
            '<definitions xmlns="http://schemas.xmlsoap.org/wsdl/">'
            "<portType><operation /></portType>"
            "</definitions>",
            target_url=target_url,
        )


def test_compile_wsdl_to_soap_hurl_does_not_echo_sensitive_query_keys() -> None:
    with pytest.raises(SoapHurlCompilationError, match="sensitive query key") as error:
        compile_wsdl_to_soap_hurl(
            WSDL_CONTRACT.read_text(encoding="utf-8"),
            target_url="https://soap.example.test/soap/orders?topsecret=placeholder",
        )

    assert "topsecret" not in str(error.value)


def test_compile_wsdl_to_soap_hurl_validates_with_hurlfmt_when_available() -> None:
    if shutil.which("hurlfmt") is None:
        pytest.skip("hurlfmt is not installed")

    generated = compile_wsdl_to_soap_hurl(
        WSDL_CONTRACT.read_text(encoding="utf-8"),
        target_url="https://soap.example.test/soap/orders",
    )

    validate_hurl_content(generated.content, display_path=generated.relative_path)
