"""Adapter tests for the deterministic Hurl subprocess runner."""

import subprocess
import threading
import time
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


def test_run_hurl_file_passes_variables_as_argument_array_and_redacts_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "health.hurl")
    calls: list[list[str]] = []
    variables_files: list[Path] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stderr, timeout, check, shell)
        calls.append(args)
        variables_file = Path(args[args.index("--variables-file") + 1])
        variables_files.append(variables_file)
        assert variables_file.is_file()
        assert variables_file.read_text(encoding="utf-8") == (
            "base_url=http://localhost:18080\ncart_id=demo-cart-001\n"
        )
        stdout.write(b"base_url=http://localhost:18080\n")
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(
        hurl_file,
        HurlRunOptions(
            binary="hurl",
            variables={"base_url": "http://localhost:18080", "cart_id": "demo-cart-001"},
        ),
    )

    assert calls == [
        [
            "/bin/hurl",
            "--variables-file",
            str(variables_files[0]),
            str(hurl_file.resolve()),
        ]
    ]
    assert "http://localhost:18080" not in " ".join(calls[0])
    assert not variables_files[0].exists()
    assert "http://localhost:18080" not in result.stdout
    assert "base_url=[REDACTED]" in result.stdout


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
def test_run_hurl_file_removes_variables_file_after_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "slow.hurl")
    variables_files: list[Path] = []

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
        variables_file = Path(args[args.index("--variables-file") + 1])
        variables_files.append(variables_file)
        assert variables_file.is_file()
        raise subprocess.TimeoutExpired(cmd=args, timeout=timeout)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(
        hurl_file,
        HurlRunOptions(binary="hurl", variables={"base_url": "http://localhost:18080"}),
    )

    assert result.status == "timeout"
    assert variables_files and not variables_files[0].exists()


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


def test_run_hurl_files_bounds_parallel_workers_and_preserves_input_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _write_hurl(tmp_path / "tests" / "first.hurl")
    second = _write_hurl(tmp_path / "tests" / "second.hurl")
    third = _write_hurl(tmp_path / "tests" / "third.hurl")
    active = 0
    max_active = 0
    lock = threading.Lock()

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        nonlocal active, max_active
        _ = (stderr, timeout, check, shell)
        with lock:
            active += 1
            max_active = max(max_active, active)
        try:
            path_name = Path(args[-1]).name
            time.sleep(0.03 if path_name == "third.hurl" else 0.01)
            stdout.write(f"ran {path_name}\n".encode())
            return subprocess.CompletedProcess(
                args=args,
                returncode=1 if path_name == "second.hurl" else 0,
            )
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    suite = run_hurl_files(
        [third, first, second],
        HurlRunOptions(binary="hurl"),
        max_workers=2,
    )

    assert max_active == 2
    assert [result.path for result in suite.results] == [
        third.resolve(),
        first.resolve(),
        second.resolve(),
    ]
    assert [result.stdout for result in suite.results] == [
        "ran third.hurl\n",
        "ran first.hurl\n",
        "ran second.hurl\n",
    ]
    assert [result.status for result in suite.results] == ["passed", "passed", "failed"]
    assert suite.exit_code == 1
