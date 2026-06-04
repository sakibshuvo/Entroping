"""Tests for dependency map export orchestration."""

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

import entroping.core.dependency_mapper as dependency_mapper
from entroping.bridge.traffic_sessions import build_traffic_session_candidate
from entroping.bridge.traffic_to_graph import compile_traffic_dependency_graph
from entroping.core.dependency_mapper import DependencyMapError, run_dependency_map
from entroping.core.safe_write import SafeWriteError
from entroping.core.traffic_filters import TrafficCaptureFilters
from entroping.core.traffic_redactor import redact_traffic_exchange
from entroping.core.traffic_store import TrafficStore, TrafficStoreError
from entroping.models.traffic import TrafficBody, TrafficExchange, TrafficRequest, TrafficResponse


def test_run_dependency_map_reports_missing_traffic_state(tmp_path: Path) -> None:
    with pytest.raises(DependencyMapError, match="No traffic state found"):
        run_dependency_map(project_root=tmp_path, export_format=None)


def test_run_dependency_map_rejects_unknown_export_format(tmp_path: Path) -> None:
    with pytest.raises(DependencyMapError, match="Unsupported map export"):
        run_dependency_map(project_root=tmp_path, export_format="svg")


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


@pytest.mark.parametrize(
    ("export_format", "expected"),
    [
        ("mermaid", "flowchart LR"),
        ("dot", "digraph entroping_dependency_map"),
        ("md", "| Host | Method | Path | Calls | Failures | Min ms | Avg ms | Max ms |"),
        (None, "flowchart LR"),
    ],
)
def test_run_dependency_map_printable_exports(
    tmp_path: Path,
    export_format: str | None,
    expected: str,
) -> None:
    _record_exchange(tmp_path)

    result = run_dependency_map(project_root=tmp_path, export_format=export_format)

    assert result.export_format == (export_format or "mermaid")
    assert expected in result.content
    assert result.route_count == 1
    assert result.output_path is None


def test_run_dependency_map_applies_capture_filters_before_graph_export(tmp_path: Path) -> None:
    _record_exchange(tmp_path)
    exchange = TrafficExchange(
        captured_at=datetime(2026, 5, 30, 12, 1, tzinfo=UTC),
        duration_ms=10,
        request=TrafficRequest(
            method="GET",
            url="https://static.example.test/assets/app.js?token=map-secret",
        ),
        response=TrafficResponse(status_code=200),
    )
    TrafficStore.open_project(tmp_path).record_exchange(redact_traffic_exchange(exchange))

    result = run_dependency_map(
        project_root=tmp_path,
        export_format="md",
        capture_filters=TrafficCaptureFilters(include_hosts=("api.example.test",)),
    )

    assert result.route_count == 1
    assert "api.example.test" in result.content
    assert "static.example.test" not in result.content
    assert "map-secret" not in result.content


def test_run_dependency_map_reports_empty_filtered_session(tmp_path: Path) -> None:
    _record_exchange(tmp_path)

    with pytest.raises(DependencyMapError, match="No traffic records matched capture filters"):
        run_dependency_map(
            project_root=tmp_path,
            export_format="mermaid",
            capture_filters=TrafficCaptureFilters(include_hosts=("missing.example.test",)),
        )


def test_run_dependency_map_wraps_traffic_store_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / ".entroping").mkdir()
    (tmp_path / ".entroping" / "state.db").write_bytes(b"sqlite")

    def fail_open_project(project_root: Path) -> TrafficStore:
        _ = project_root
        raise TrafficStoreError("store unavailable")

    monkeypatch.setattr(TrafficStore, "open_project", fail_open_project)

    with pytest.raises(DependencyMapError, match="store unavailable"):
        run_dependency_map(project_root=tmp_path, export_format="mermaid")


def test_render_printable_export_rejects_png_internal_misuse(tmp_path: Path) -> None:
    _record_exchange(tmp_path)
    store = TrafficStore.open_project(tmp_path)
    session = build_traffic_session_candidate(
        store.list_exchanges(),
        name="dependency_map",
        target_url=None,
    )
    graph = compile_traffic_dependency_graph(session)

    with pytest.raises(DependencyMapError, match="PNG map export requires"):
        dependency_mapper._render_printable_export(graph, "png")


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


def test_run_dependency_map_png_os_error_is_actionable(
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
        _ = args, input, capture_output, text, timeout, check, shell
        raise OSError("dot crashed")

    monkeypatch.setattr("entroping.core.dependency_mapper.shutil.which", lambda name: "/bin/dot")
    monkeypatch.setattr("entroping.core.dependency_mapper.subprocess.run", fake_run)

    with pytest.raises(DependencyMapError, match="Could not run Graphviz dot"):
        run_dependency_map(project_root=tmp_path, export_format="png")


def test_run_dependency_map_png_rejects_empty_renderer_output(
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
        _ = input, capture_output, text, timeout, check, shell
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr("entroping.core.dependency_mapper.shutil.which", lambda name: "/bin/dot")
    monkeypatch.setattr("entroping.core.dependency_mapper.subprocess.run", fake_run)

    with pytest.raises(DependencyMapError, match="did not produce PNG output"):
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
