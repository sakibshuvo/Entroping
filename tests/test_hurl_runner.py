"""Adapter tests for the deterministic Hurl subprocess runner."""

import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

import pytest

from entroping.core.hurl_runner import (
    HurlBinaryNotFoundError,
    HurlRunnerError,
    HurlRunOptions,
    discover_hurl,
    run_hurl_file,
    run_hurl_files,
    validate_hurl_path,
)


def _write_hurl(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("GET {{base_url}}/health\nHTTP 200\n", encoding="utf-8")
    return path


def test_discover_hurl_reports_binary_availability(monkeypatch: pytest.MonkeyPatch) -> None:
    def resolve_binary(binary: str) -> str:
        return f"/opt/bin/{binary}"

    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", resolve_binary)

    assert discover_hurl("custom-hurl").available
    assert discover_hurl("custom-hurl").path == "/opt/bin/custom-hurl"

    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: None)

    assert not discover_hurl("missing-hurl").available
    assert discover_hurl("missing-hurl").path is None


def test_discover_hurl_reports_compatible_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str],
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(
            {
                "args": args,
                "timeout": timeout,
                "check": check,
                "env": env,
                "shell": shell,
            }
        )
        stdout.write(b"hurl 8.0.1 (x86_64-apple-darwin)\n")
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/opt/bin/hurl")
    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)

    status = discover_hurl("hurl")

    assert status.available is True
    assert status.path == "/opt/bin/hurl"
    assert status.version_checked is True
    assert status.version == "8.0.1"
    assert status.version_parts == (8, 0, 1)
    assert status.version_output == "hurl 8.0.1 (x86_64-apple-darwin)"
    assert status.version_error is None
    assert calls == [
        {
            "args": ["/opt/bin/hurl", "--version"],
            "timeout": 2.0,
            "check": False,
            "env": {"PATH": "/opt/bin:/usr/bin:/bin"},
            "shell": False,
        }
    ]


def test_discover_hurl_reports_unparsable_version_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str],
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stderr, timeout, check, env, shell)
        stdout.write(b"hurl dev-build\n")
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/opt/bin/hurl")
    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)

    status = discover_hurl("hurl")

    assert status.version_checked is True
    assert status.version is None
    assert status.version_parts is None
    assert status.version_output == "hurl dev-build"
    assert status.version_error is None


def test_discover_hurl_reports_version_command_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str],
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stdout, timeout, check, env, shell)
        stderr.write(b"unexpected option\n")
        return subprocess.CompletedProcess(args=args, returncode=2)

    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/opt/bin/hurl")
    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)

    status = discover_hurl("hurl")

    assert status.version_checked is True
    assert status.version is None
    assert status.version_error == "hurl --version exited with code 2: unexpected option"


def test_discover_hurl_reports_version_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str],
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stdout, stderr, check, env, shell)
        raise subprocess.TimeoutExpired(cmd=args, timeout=timeout)

    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/opt/bin/hurl")
    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)

    status = discover_hurl("hurl")

    assert status.version_checked is True
    assert status.version is None
    assert status.version_error == "hurl --version timed out after 2 seconds"


def test_discover_hurl_reports_version_os_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str],
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (args, stdout, stderr, timeout, check, env, shell)
        raise OSError("permission denied")

    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/opt/bin/hurl")
    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)

    status = discover_hurl("hurl")

    assert status.version_checked is True
    assert status.version is None
    assert status.version_error == "hurl --version failed: permission denied"


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: HurlRunOptions(binary="  "), "Hurl binary must not be empty"),
        (lambda: HurlRunOptions(timeout_ms=0), "Hurl timeout must be greater than zero"),
        (
            lambda: HurlRunOptions(output_limit_bytes=0),
            "Hurl output limit must be greater than zero",
        ),
        (lambda: HurlRunOptions(retry=-1), "Hurl retry count must not be negative"),
        (lambda: HurlRunOptions(variables={"bad-name": "value"}), "Invalid Hurl variable name"),
        (lambda: HurlRunOptions(variables={"token": "line1\nline2"}), "must be single-line"),
    ],
)
def test_hurl_run_options_reject_invalid_runtime_options(
    factory: Callable[[], HurlRunOptions],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        factory()


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
        env: dict[str, str] | None = None,
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


def test_run_hurl_file_uses_minimal_subprocess_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "health.hurl")
    calls: list[dict[str, str]] = []
    monkeypatch.setenv("DB_URL", "postgres://user:secret-host/db")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str],
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (args, stderr, timeout, check, shell)
        calls.append(env)
        stdout.write(f"DB_URL={env.get('DB_URL', '')}\n".encode())
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(hurl_file, HurlRunOptions(binary="hurl"))

    expected_path = ":".join(
        dict.fromkeys(
            [
                str(Path("/bin/hurl").resolve().parent),
                "/usr/bin",
                "/bin",
            ]
        )
    )
    assert calls == [{"PATH": expected_path}]
    assert "secret-host" not in result.stdout


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
        env: dict[str, str] | None = None,
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
        env: dict[str, str] | None = None,
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
    assert result.retry_count == 0
    assert not result.unstable
    assert [attempt.status for attempt in result.attempts] == ["failed"]


def test_run_hurl_file_retries_until_pass_and_marks_unstable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "eventual.hurl")
    return_codes = [7, 0]
    calls: list[list[str]] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (timeout, check, env, shell)
        calls.append(args)
        return_code = return_codes.pop(0)
        stdout.write(f"attempt={len(calls)} secret=live-secret\n".encode())
        stderr.write(f"stderr attempt={len(calls)}\n".encode())
        return subprocess.CompletedProcess(args=args, returncode=return_code)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(
        hurl_file,
        HurlRunOptions(binary="hurl", retry=2, redacted_values=("live-secret",)),
    )

    assert len(calls) == 2
    assert result.passed
    assert result.status == "passed"
    assert result.exit_code == 0
    assert result.retry_count == 1
    assert result.unstable
    assert [attempt.attempt for attempt in result.attempts] == [1, 2]
    assert [attempt.status for attempt in result.attempts] == ["failed", "passed"]
    assert [attempt.exit_code for attempt in result.attempts] == [7, 0]
    assert result.stdout == "attempt=2 secret=[REDACTED]\n"
    assert "live-secret" not in result.stdout


def test_run_hurl_file_exhausts_retry_budget_without_hiding_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "always-fails.hurl")
    calls = 0

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        _ = (stdout, timeout, check, env, shell)
        calls += 1
        stderr.write(f"failed attempt {calls}\n".encode())
        return subprocess.CompletedProcess(args=args, returncode=42)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(hurl_file, HurlRunOptions(binary="hurl", retry=2))

    assert calls == 3
    assert not result.passed
    assert result.status == "failed"
    assert result.exit_code == 42
    assert result.retry_count == 2
    assert not result.unstable
    assert [attempt.status for attempt in result.attempts] == ["failed", "failed", "failed"]
    assert result.stderr == "failed attempt 3\n"


def test_run_hurl_file_returns_error_result_for_subprocess_oserror(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "error.hurl")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (args, stdout, timeout, check, env, shell)
        stderr.write(b"stderr before failure\n")
        raise OSError("permission denied")

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(hurl_file, HurlRunOptions(binary="hurl"))

    assert not result.passed
    assert result.status == "error"
    assert result.exit_code == 126
    assert "stderr before failure" in result.stderr
    assert "Hurl subprocess failed: permission denied" in result.stderr


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
        env: dict[str, str] | None = None,
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
    assert result.timeout_ms == 250
    assert "live-secret" not in result.stdout
    assert "Cookie: [REDACTED]" in result.stdout
    assert "timed out after 250 ms" in result.stderr


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
        env: dict[str, str] | None = None,
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
        env: dict[str, str] | None = None,
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


def test_validate_hurl_path_rejects_unsafe_or_invalid_paths(tmp_path: Path) -> None:
    target = _write_hurl(tmp_path / "real" / "health.hurl")
    symlink = tmp_path / "tests" / "linked.hurl"
    symlink.parent.mkdir(parents=True, exist_ok=True)
    symlink.symlink_to(target)

    with pytest.raises(ValueError, match="symlinked Hurl file"):
        validate_hurl_path(symlink)

    notes = tmp_path / "tests" / "notes.txt"
    notes.write_text("not hurl\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Expected a .hurl file"):
        validate_hurl_path(notes)

    with pytest.raises(ValueError, match="Hurl file not found"):
        validate_hurl_path(tmp_path / "tests" / "missing.hurl")


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
        env: dict[str, str] | None = None,
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


def test_run_hurl_files_fail_fast_stops_sequential_scheduling_after_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _write_hurl(tmp_path / "tests" / "first.hurl")
    second = _write_hurl(tmp_path / "tests" / "second.hurl")
    third = _write_hurl(tmp_path / "tests" / "third.hurl")
    calls: list[str] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stdout, stderr, timeout, check, env, shell)
        calls.append(Path(args[-1]).name)
        return subprocess.CompletedProcess(
            args=args,
            returncode=1 if args[-1].endswith("second.hurl") else 0,
        )

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    suite = run_hurl_files(
        [first, second, third],
        HurlRunOptions(binary="hurl"),
        fail_fast=True,
    )

    assert calls == ["first.hurl", "second.hurl"]
    assert [result.path for result in suite.results] == [first.resolve(), second.resolve()]
    assert suite.total == 2
    assert suite.selected_count == 3
    assert suite.not_scheduled == 1
    assert suite.fail_fast is True
    assert suite.exit_code == 1


def test_run_hurl_files_fail_fast_parallel_preserves_order_and_stops_new_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _write_hurl(tmp_path / "tests" / "first.hurl")
    second = _write_hurl(tmp_path / "tests" / "second.hurl")
    third = _write_hurl(tmp_path / "tests" / "third.hurl")
    calls: list[str] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stdout, stderr, timeout, check, env, shell)
        name = Path(args[-1]).name
        calls.append(name)
        time.sleep(0.01 if name == "first.hurl" else 0.03)
        return subprocess.CompletedProcess(
            args=args,
            returncode=1 if name == "first.hurl" else 0,
        )

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    suite = run_hurl_files(
        [first, second, third],
        HurlRunOptions(binary="hurl"),
        max_workers=2,
        fail_fast=True,
    )

    assert sorted(calls) == ["first.hurl", "second.hurl"]
    assert [result.path for result in suite.results] == [first.resolve(), second.resolve()]
    assert [result.status for result in suite.results] == ["failed", "passed"]
    assert suite.selected_count == 3
    assert suite.not_scheduled == 1
    assert suite.fail_fast is True


def test_run_hurl_files_fail_fast_parallel_schedules_while_results_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _write_hurl(tmp_path / "tests" / "first.hurl")
    second = _write_hurl(tmp_path / "tests" / "second.hurl")
    third = _write_hurl(tmp_path / "tests" / "third.hurl")
    calls: list[str] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stdout, stderr, timeout, check, env, shell)
        name = Path(args[-1]).name
        calls.append(name)
        time.sleep(0.01 if name != "second.hurl" else 0.03)
        return subprocess.CompletedProcess(
            args=args,
            returncode=1 if name == "second.hurl" else 0,
        )

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    suite = run_hurl_files(
        [first, second, third],
        HurlRunOptions(binary="hurl"),
        max_workers=2,
        fail_fast=True,
    )

    assert sorted(calls) == ["first.hurl", "second.hurl", "third.hurl"]
    assert [result.path for result in suite.results] == [
        first.resolve(),
        second.resolve(),
        third.resolve(),
    ]
    assert [result.status for result in suite.results] == ["passed", "failed", "passed"]
    assert suite.selected_count == 3
    assert suite.not_scheduled == 0
    assert suite.fail_fast is True


def test_run_hurl_files_rejects_invalid_worker_count(tmp_path: Path) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "health.hurl")

    with pytest.raises(ValueError, match="Hurl worker count must be greater than zero"):
        run_hurl_files([hurl_file], HurlRunOptions(binary="hurl"), max_workers=0)


def test_run_hurl_files_surfaces_missing_worker_result(
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
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stdout, stderr, timeout, check, env, shell)
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")
    monkeypatch.setattr("entroping.core.hurl_runner.as_completed", lambda futures: ())

    with pytest.raises(HurlRunnerError, match="Hurl worker did not produce a result"):
        run_hurl_files([first, second], HurlRunOptions(binary="hurl"), max_workers=2)


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
        env: dict[str, str] | None = None,
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
