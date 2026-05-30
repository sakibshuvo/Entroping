"""Tests for dependency map export orchestration."""

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

import entroping.core.dependency_mapper as dependency_mapper
from entroping.core.dependency_mapper import DependencyMapError, run_dependency_map
from entroping.core.safe_write import SafeWriteError
from entroping.core.traffic_redactor import redact_traffic_exchange
from entroping.core.traffic_store import TrafficStore
from entroping.models.traffic import TrafficBody, TrafficExchange, TrafficRequest, TrafficResponse


def _record_exchange(project_root: Path, *, secret: str = "map-secret") -> None:
    exchange = TrafficExchange(
        captured_at=datetime(2026, 5, 30, 12, 0, tzinfo=UTC),
        duration_ms=25,
        request=TrafficRequest(
            method="POST",
            url=f"https://api.example.test/checkout?token={secret}",
            headers={"Authorization": f"Bearer {secret}"},
            body=TrafficBody(
                content_type="application/json",
                size_bytes=44,
                text=f'{{"password":"{secret}"}}',
            ),
        ),
        response=TrafficResponse(status_code=201),
    )
    TrafficStore.open_project(project_root).record_exchange(redact_traffic_exchange(exchange))


def test_run_dependency_map_png_writes_graphviz_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_exchange(tmp_path)
    calls: list[dict[str, object]] = []

    def fake_run(
        args: list[str],
        *,
        input: bytes,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
        shell: bool,
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append(
                {
                    "args": args,
                    "input": input,
                    "capture_output": capture_output,
                    "text": text,
                    "timeout": timeout,
                    "check": check,
                    "shell": shell,
                }
            )
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=b"\x89PNG\r\n",
            stderr=b"",
        )

    monkeypatch.setattr("entroping.core.dependency_mapper.shutil.which", lambda name: "/bin/dot")
    monkeypatch.setattr("entroping.core.dependency_mapper.subprocess.run", fake_run)

    result = run_dependency_map(project_root=tmp_path, export_format="png")

    assert result.export_format == "png"
    assert result.content == ""
    assert result.output_path == tmp_path / "reports" / "dependency-map.png"
    assert result.output_path.read_bytes() == b"\x89PNG\r\n"
    assert calls == [
        {
            "args": ["/bin/dot", "-Tpng"],
            "input": (
                b"digraph entroping_dependency_map {\n"
                b"  rankdir=LR;\n"
                b"  node [shape=box];\n"
                b'  source [label="client"];\n'
                b'  host_1 [label="api.example.test"];\n'
                b'  source -> host_1 [label="POST /checkout\\\\n'
                b'calls=1, failures=0, avg=25ms"];\n'
                b"}\n"
            ),
            "capture_output": True,
            "text": False,
            "timeout": 15,
            "check": False,
            "shell": False,
        }
    ]


def test_run_dependency_map_png_reports_missing_graphviz(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_exchange(tmp_path)
    monkeypatch.setattr("entroping.core.dependency_mapper.shutil.which", lambda name: None)

    with pytest.raises(DependencyMapError, match="Graphviz dot is required"):
        run_dependency_map(project_root=tmp_path, export_format="png")


def test_run_dependency_map_png_renderer_failure_does_not_echo_dot_or_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_exchange(tmp_path, secret="renderer-secret")

    def fake_run(
        args: list[str],
        *,
        input: bytes,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
        shell: bool,
    ) -> subprocess.CompletedProcess[bytes]:
        _ = input, capture_output, text, timeout, check, shell
        return subprocess.CompletedProcess(
            args=args,
            returncode=1,
            stdout=b"",
            stderr=b"renderer echoed digraph and renderer-secret",
        )

    monkeypatch.setattr("entroping.core.dependency_mapper.shutil.which", lambda name: "/bin/dot")
    monkeypatch.setattr("entroping.core.dependency_mapper.subprocess.run", fake_run)

    with pytest.raises(DependencyMapError) as exc_info:
        run_dependency_map(project_root=tmp_path, export_format="png")

    message = str(exc_info.value)
    assert "Graphviz dot failed with exit code 1" in message
    assert "digraph" not in message
    assert "renderer-secret" not in message


def test_run_dependency_map_png_timeout_is_actionable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_exchange(tmp_path)

    def fake_run(
        args: list[str],
        *,
        input: bytes,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
        shell: bool,
    ) -> subprocess.CompletedProcess[bytes]:
        _ = input, capture_output, text, check, shell
        raise subprocess.TimeoutExpired(cmd=args, timeout=timeout)

    monkeypatch.setattr("entroping.core.dependency_mapper.shutil.which", lambda name: "/bin/dot")
    monkeypatch.setattr("entroping.core.dependency_mapper.subprocess.run", fake_run)

    with pytest.raises(DependencyMapError, match="Graphviz dot timed out after 15s"):
        run_dependency_map(project_root=tmp_path, export_format="png")


def test_run_dependency_map_png_refuses_symlink_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_exchange(tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    victim = tmp_path / "victim.png"
    victim.write_bytes(b"victim")
    (reports_dir / "dependency-map.png").symlink_to(victim)

    def fake_run(
        args: list[str],
        *,
        input: bytes,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
        shell: bool,
    ) -> subprocess.CompletedProcess[bytes]:
        _ = input, capture_output, text, timeout, check, shell
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=b"\x89PNG\r\n",
            stderr=b"",
        )

    monkeypatch.setattr("entroping.core.dependency_mapper.shutil.which", lambda name: "/bin/dot")
    monkeypatch.setattr("entroping.core.dependency_mapper.subprocess.run", fake_run)

    with pytest.raises(DependencyMapError, match="symlinked dependency map"):
        run_dependency_map(project_root=tmp_path, export_format="png")

    assert victim.read_bytes() == b"victim"


def test_run_dependency_map_png_preserves_existing_target_when_atomic_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_exchange(tmp_path)
    output = tmp_path / "reports" / "dependency-map.png"
    output.parent.mkdir()
    output.write_bytes(b"old")

    def fake_run(
        args: list[str],
        *,
        input: bytes,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
        shell: bool,
    ) -> subprocess.CompletedProcess[bytes]:
        _ = input, capture_output, text, timeout, check, shell
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=b"\x89PNG\r\n",
            stderr=b"",
        )

    def fail_safe_write(
        path: Path,
        content: bytes,
        *,
        artifact: str,
        root: Path | None = None,
    ) -> Path:
        _ = path, content, artifact, root
        raise SafeWriteError("temporary write failed")

    monkeypatch.setattr("entroping.core.dependency_mapper.shutil.which", lambda name: "/bin/dot")
    monkeypatch.setattr("entroping.core.dependency_mapper.subprocess.run", fake_run)
    monkeypatch.setattr(dependency_mapper, "safe_write_bytes", fail_safe_write)

    with pytest.raises(DependencyMapError, match="temporary write failed"):
        run_dependency_map(project_root=tmp_path, export_format="png")

    assert output.read_bytes() == b"old"
