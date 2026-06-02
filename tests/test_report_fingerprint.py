"""Tests for report response fingerprint extraction."""

from entroping.core import report_fingerprint


def test_response_fingerprint_ignores_malformed_http_output_and_shapes_nulls() -> None:
    status_code, headers, body_shape = report_fingerprint._extract_response_fingerprint(
        'HTTP 200\nnot-a-header\n{"ok":true}\n',
    )

    assert status_code == 200
    assert headers == ()
    assert body_shape == ()
    assert report_fingerprint._walk_json_shape(
        {1: "ignored", "bad\n": "ignored", "ok": None},
        "$",
    ) == ["$:object", "$.ok:null"]
