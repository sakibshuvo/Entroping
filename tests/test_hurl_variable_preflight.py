"""Tests for unresolved Hurl variable preflight checks."""

from pathlib import Path

import pytest

import entroping.core.hurl_variable_preflight as hurl_variable_preflight
import entroping.hurl_source as hurl_source
from entroping.core.gate_injector import HurlExecutionCopy
from entroping.core.hurl_variable_preflight import (
    HurlVariablePreflightError,
    preflight_hurl_variables,
)


def test_preflight_rejects_non_utf8_execution_copy(tmp_path: Path) -> None:
    execution_path = tmp_path / "execution.hurl"
    execution_path.write_bytes(b"\xff\xfe")

    with pytest.raises(HurlVariablePreflightError, match="not valid UTF-8"):
        preflight_hurl_variables(
            (
                HurlExecutionCopy(
                    source_path=tmp_path / "tests" / "source.hurl",
                    execution_path=execution_path,
                    injected_gates=(),
                ),
            ),
            variables={},
            project_root=tmp_path,
        )


def test_preflight_wraps_execution_copy_read_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution_path = tmp_path / "execution.hurl"
    execution_path.write_text("GET {{base_url}}/health\nHTTP 200\n", encoding="utf-8")

    def fail_execution_read(path: Path, *, label: str = "Hurl source") -> str:
        if path == execution_path:
            raise OSError("disk unavailable")
        return hurl_source.read_hurl_source_text(path, label=label)

    monkeypatch.setattr(
        hurl_variable_preflight,
        "read_hurl_source_text",
        fail_execution_read,
    )

    with pytest.raises(HurlVariablePreflightError, match="Could not read execution Hurl copy"):
        preflight_hurl_variables(
            (
                HurlExecutionCopy(
                    source_path=tmp_path / "tests" / "source.hurl",
                    execution_path=execution_path,
                    injected_gates=(),
                ),
            ),
            variables={},
            project_root=tmp_path,
        )


def test_preflight_rejects_oversized_execution_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hurl_source, "HURL_SOURCE_MAX_BYTES", 16)
    execution_path = tmp_path / "execution.hurl"
    execution_path.write_bytes(b"GET /health\nHTTP 200\n")

    with pytest.raises(
        HurlVariablePreflightError,
        match=r"execution Hurl copy .* exceeds 16 bytes",
    ):
        preflight_hurl_variables(
            (
                HurlExecutionCopy(
                    source_path=tmp_path / "tests" / "source.hurl",
                    execution_path=execution_path,
                    injected_gates=(),
                ),
            ),
            variables={},
            project_root=tmp_path,
        )


def test_preflight_reports_absolute_source_path_outside_project(tmp_path: Path) -> None:
    outside_source = tmp_path.parent / "outside.hurl"
    execution_path = tmp_path / "execution.hurl"
    execution_path.write_text("GET {{missing_host}}/health\nHTTP 200\n", encoding="utf-8")

    with pytest.raises(HurlVariablePreflightError) as excinfo:
        preflight_hurl_variables(
            (
                HurlExecutionCopy(
                    source_path=outside_source,
                    execution_path=execution_path,
                    injected_gates=(),
                ),
            ),
            variables={},
            project_root=tmp_path,
        )

    assert outside_source.resolve().as_posix() in str(excinfo.value)
    assert "missing_host" in str(excinfo.value)


def test_preflight_treats_hurl_captures_as_chained_variables(tmp_path: Path) -> None:
    execution_path = tmp_path / "execution.hurl"
    execution_path.write_text(
        "\n".join(
            [
                "POST {{base_url}}/login",
                "HTTP 200",
                "[Captures]",
                "access_token: jsonpath \"$.token\"",
                "",
                "GET {{base_url}}/profile",
                "Authorization: Bearer {{access_token}}",
                "HTTP 200",
            ],
        ),
        encoding="utf-8",
    )

    preflight_hurl_variables(
        (
            HurlExecutionCopy(
                source_path=tmp_path / "tests" / "auth_chain.hurl",
                execution_path=execution_path,
                injected_gates=(),
            ),
        ),
        variables={"base_url": "http://localhost:18080"},
        project_root=tmp_path,
    )
