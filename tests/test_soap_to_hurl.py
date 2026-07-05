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


def test_compile_wsdl_to_soap_hurl_validates_with_hurlfmt_when_available() -> None:
    if shutil.which("hurlfmt") is None:
        pytest.skip("hurlfmt is not installed")

    generated = compile_wsdl_to_soap_hurl(
        WSDL_CONTRACT.read_text(encoding="utf-8"),
        target_url="https://soap.example.test/soap/orders",
    )

    validate_hurl_content(generated.content, display_path=generated.relative_path)
