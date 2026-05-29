"""Adapter tests for the deterministic Hurl subprocess runner."""

import subprocess
from pathlib import Path
from typing import BinaryIO

import pytest

from entroping.core.hurl_runner import (
    HurlBinaryNotFoundError,
    HurlRunOptions,
    run_hurl_file,
    run_hurl_files,
)


def _write_hurl(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("GET {{base_url}}/health\nHTTP 200\n", encoding="utf-8")
    return path


def test_run_hurl_file_invokes_hurl_with_argument_array_and_redacts_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "health.hurl")
    calls: list[dict[str, object]] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(
            {
                "args": args,
                "timeout": timeout,
                "check": check,
                "shell": shell,
            }
        )
        stdout.write(b"Authorization: Bearer live-secret\nbody ok\n")
        stderr.write(b"token=live-secret\n")
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(
        hurl_file,
        HurlRunOptions(
            binary="hurl",
            timeout_ms=1500,
            output_limit_bytes=4096,
            redacted_values=("live-secret",),
        ),
    )

    assert calls == [
        {
            "args": ["/bin/hurl", str(hurl_file.resolve())],
            "timeout": 1.5,
            "check": False,
            "shell": False,
        }
    ]
    assert result.passed
    assert result.status == "passed"
    assert result.exit_code == 0
    assert "live-secret" not in result.stdout
    assert "live-secret" not in result.stderr
    assert "Authorization: [REDACTED]" in result.stdout
    assert "token=[REDACTED]" in result.stderr


def test_run_hurl_file_returns_failed_result_for_non_zero_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "failing.hurl")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (timeout, check, shell)
        stderr.write(b"Assert status < 500 failed\n")
        return subprocess.CompletedProcess(args=args, returncode=42)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(hurl_file, HurlRunOptions(binary="hurl"))

    assert not result.passed
    assert result.status == "failed"
    assert result.exit_code == 42
    assert "Assert status < 500 failed" in result.stderr


@pytest.mark.security
def test_run_hurl_file_returns_timeout_result_with_redacted_partial_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "slow.hurl")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (check, shell)
        stdout.write(b"Cookie: session=live-secret\n")
        raise subprocess.TimeoutExpired(cmd=args, timeout=timeout)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(
        hurl_file,
        HurlRunOptions(binary="hurl", timeout_ms=250, redacted_values=("live-secret",)),
    )

    assert not result.passed
    assert result.status == "timeout"
    assert result.exit_code == 124
    assert "live-secret" not in result.stdout
    assert "Cookie: [REDACTED]" in result.stdout


@pytest.mark.security
def test_run_hurl_file_bounds_stdout_and_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "noisy.hurl")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (timeout, check, shell)
        stdout.write(b"a" * 128)
        stderr.write(b"b" * 128)
        return subprocess.CompletedProcess(args=args, returncode=1)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(
        hurl_file,
        HurlRunOptions(binary="hurl", output_limit_bytes=32),
    )

    assert result.stdout == ("a" * 32) + "\n[entroping: stdout truncated]\n"
    assert result.stderr == ("b" * 32) + "\n[entroping: stderr truncated]\n"
    assert result.stdout_truncated
    assert result.stderr_truncated


def test_run_hurl_file_reports_missing_binary_before_subprocess(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "health.hurl")
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: None)

    with pytest.raises(HurlBinaryNotFoundError, match="Hurl binary not found"):
        run_hurl_file(hurl_file, HurlRunOptions(binary="missing-hurl"))


def test_run_hurl_files_aggregates_deterministic_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _write_hurl(tmp_path / "tests" / "first.hurl")
    second = _write_hurl(tmp_path / "tests" / "second.hurl")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stdout, stderr, timeout, check, shell)
        return subprocess.CompletedProcess(
            args=args,
            returncode=1 if args[-1].endswith("second.hurl") else 0,
        )

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    suite = run_hurl_files([first, second], HurlRunOptions(binary="hurl"))

    assert suite.total == 2
    assert suite.passed == 1
    assert suite.failed == 1
    assert suite.exit_code == 1
