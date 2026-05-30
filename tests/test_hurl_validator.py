"""Parser-backed Hurl syntax validation tests."""

import subprocess
from pathlib import Path
from typing import BinaryIO

import pytest

from entroping.core.hurl_validator import HurlValidationError, validate_hurl_content


def test_validate_hurl_content_invokes_hurlfmt_with_argument_array(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    temp_paths: list[Path] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stdout, stderr)
        hurl_file = Path(args[-1])
        temp_paths.append(hurl_file)
        assert hurl_file.is_file()
        assert hurl_file.read_text(encoding="utf-8") == "GET {{base_url}}/health\nHTTP 200\n"
        calls.append({"args": args, "timeout": timeout, "check": check, "shell": shell})
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_validator.shutil.which", lambda binary: "/bin/hurlfmt")
    monkeypatch.setattr("entroping.core.hurl_validator.subprocess.run", fake_run)

    validate_hurl_content(
        "GET {{base_url}}/health\nHTTP 200\n",
        display_path="tests/generated/health.hurl",
        timeout_ms=1500,
    )

    assert calls == [
        {
            "args": ["/bin/hurlfmt", "--out", "json", str(temp_paths[0])],
            "timeout": 1.5,
            "check": False,
            "shell": False,
        }
    ]
    assert not temp_paths[0].exists()


def test_validate_hurl_content_rejects_missing_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("entroping.core.hurl_validator.shutil.which", lambda binary: None)

    with pytest.raises(HurlValidationError, match="Hurl validation binary not found"):
        validate_hurl_content("GET /health\nHTTP 200\n", display_path="tests/generated/health.hurl")


def test_validate_hurl_content_rejects_non_zero_without_echoing_raw_hurl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stdout, timeout, check, shell)
        stderr.write(b"GET {{base_url}}/secret\nprovider-private-context\n")
        return subprocess.CompletedProcess(args=args, returncode=1)

    monkeypatch.setattr("entroping.core.hurl_validator.shutil.which", lambda binary: "/bin/hurlfmt")
    monkeypatch.setattr("entroping.core.hurl_validator.subprocess.run", fake_run)

    with pytest.raises(HurlValidationError) as exc_info:
        validate_hurl_content("GET /secret\nBAD\n", display_path="tests/generated/bad.hurl")

    message = str(exc_info.value)
    assert "Generated Hurl failed parser validation: tests/generated/bad.hurl" in message
    assert "provider-private-context" not in message
    assert "GET /secret" not in message


def test_validate_hurl_content_rejects_timeout_and_cleans_temp_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    temp_paths: list[Path] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stdout, stderr, check, shell)
        temp_paths.append(Path(args[-1]))
        raise subprocess.TimeoutExpired(cmd=args, timeout=timeout)

    monkeypatch.setattr("entroping.core.hurl_validator.shutil.which", lambda binary: "/bin/hurlfmt")
    monkeypatch.setattr("entroping.core.hurl_validator.subprocess.run", fake_run)

    with pytest.raises(HurlValidationError, match="timed out"):
        validate_hurl_content("GET /health\nHTTP 200\n", display_path="tests/generated/slow.hurl")

    assert temp_paths and not temp_paths[0].exists()
