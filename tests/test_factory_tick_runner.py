from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from entroping.models import secrets  # noqa: E402
from scripts.factory_tick_runner import TickRunnerError, run_tick  # noqa: E402


def _executable(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "factoryctl"
    _ = path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_factory_tick_runner_persists_bounded_streams(tmp_path: Path) -> None:
    executable = _executable(
        tmp_path,
        "printf 'tick ok\\n'; printf 'tick warning\\n' >&2",
    )
    log_directory = tmp_path / ".entroping" / "factory-logs"

    returncode = run_tick(
        repo_root=tmp_path,
        factoryctl=executable,
        log_directory=log_directory,
        timeout_seconds=5,
        max_output_bytes=128,
        max_log_bytes=256,
    )

    assert returncode == 0
    assert (log_directory / "factory-tick.out.log").read_text() == "tick ok\n"
    assert (log_directory / "factory-tick.err.log").read_text() == "tick warning\n"


def test_factory_tick_runner_rotates_once_and_caps_total_bytes(tmp_path: Path) -> None:
    executable = _executable(tmp_path, "printf '12345678'")
    log_directory = tmp_path / ".entroping" / "factory-logs"
    for _ in range(4):
        assert (
            run_tick(
                repo_root=tmp_path,
                factoryctl=executable,
                log_directory=log_directory,
                timeout_seconds=5,
                max_output_bytes=8,
                max_log_bytes=10,
            )
            == 0
        )

    stream_logs = tuple(log_directory.glob("factory-tick.out.log*"))
    assert {item.name for item in stream_logs} == {
        "factory-tick.out.log",
        "factory-tick.out.log.1",
    }
    assert sum(item.stat().st_size for item in stream_logs) <= 20


def test_factory_tick_runner_kills_output_flood_before_persistence(tmp_path: Path) -> None:
    executable = _executable(tmp_path, "yes x")
    log_directory = tmp_path / ".entroping" / "factory-logs"

    returncode = run_tick(
        repo_root=tmp_path,
        factoryctl=executable,
        log_directory=log_directory,
        timeout_seconds=5,
        max_output_bytes=128,
        max_log_bytes=256,
    )

    output = (log_directory / "factory-tick.out.log").read_bytes()
    error_output = (log_directory / "factory-tick.err.log").read_bytes()
    assert returncode == 1
    assert len(output) <= 128
    assert b"output truncated" in output
    assert len(error_output) <= 256
    assert b"Factory tick exceeded the 128-byte output limit" in error_output


def test_factory_tick_runner_rejects_symlinked_log_root(tmp_path: Path) -> None:
    executable = _executable(tmp_path, "exit 0")
    external = tmp_path / "external"
    external.mkdir()
    entroping = tmp_path / ".entroping"
    entroping.mkdir()
    log_directory = entroping / "factory-logs"
    try:
        log_directory.symlink_to(external, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    with pytest.raises(TickRunnerError, match="bounded tick execution failed"):
        _ = run_tick(
            repo_root=tmp_path,
            factoryctl=executable,
            log_directory=log_directory,
            timeout_seconds=5,
            max_output_bytes=128,
            max_log_bytes=256,
        )

    assert os.listdir(external) == []


def test_factory_tick_runner_redacts_secret_like_streams(tmp_path: Path) -> None:
    executable = _executable(
        tmp_path,
        " ".join(
            (
                "printf 'Authorization: Bearer sk-proj-abcdefghijklmnopqrstuv\\n';",
                "printf 'api_key=ghp_abcdefghijklmnopqrstuvwxyz\\n' >&2",
            )
        ),
    )
    log_directory = tmp_path / ".entroping" / "factory-logs"

    returncode = run_tick(
        repo_root=tmp_path,
        factoryctl=executable,
        log_directory=log_directory,
        timeout_seconds=5,
        max_output_bytes=256,
        max_log_bytes=512,
    )

    stdout = (log_directory / "factory-tick.out.log").read_text(encoding="utf-8")
    stderr = (log_directory / "factory-tick.err.log").read_text(encoding="utf-8")
    assert returncode == 0
    assert "[REDACTED]" in stdout and "[REDACTED]" in stderr
    assert "sk-proj-" not in stdout
    assert "ghp_" not in stderr


def test_factory_tick_runner_fails_before_persisting_unredacted_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = _executable(tmp_path, "printf 'token=sk-proj-abcdefghijklmnopqrstuv\n'")
    log_directory = tmp_path / ".entroping" / "factory-logs"

    def identity(value: str) -> str:
        return value

    monkeypatch.setattr(secrets, "redact_secret_like_values", identity)

    with pytest.raises(TickRunnerError, match="secret-like"):
        _ = run_tick(
            repo_root=tmp_path,
            factoryctl=executable,
            log_directory=log_directory,
            timeout_seconds=5,
            max_output_bytes=256,
            max_log_bytes=512,
        )

    assert not (log_directory / "factory-tick.out.log").exists()
    assert not (log_directory / "factory-tick.err.log").exists()
