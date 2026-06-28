import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

import entroping.core.evidence.handoff_packet as handoff_packet
from entroping.core.evidence.handoff_packet import (
    HandoffError,
    build_handoff_packet,
    render_handoff_markdown,
    run_handoff_report,
)
from entroping.core.safe_write import SafeWriteError


def test_run_handoff_report_writes_value_free_json_from_local_artifacts(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    _write_handoff_inputs(tmp_path)

    result = run_handoff_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "handoff.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.handoff.v1"
    assert payload["project"] == "checkout-api"
    assert payload["git"]["branch"] == "main"
    assert len(payload["git"]["commit"]) == 40
    assert payload["summary"] == {
        "status": "ready",
        "artifacts_total": 5,
        "artifacts_present": 5,
        "artifacts_missing": 0,
        "artifacts_invalid": 0,
        "artifacts_unsafe": 0,
    }
    assert payload["runtime"] == {
        "status": "attention",
        "findings": 2,
        "evidence_links": 3,
        "failed_gate_ids": 2,
        "pilot_readiness_status": "ready",
        "test_pyramid_status": "complete",
    }
    artifacts = {artifact["id"]: artifact for artifact in payload["artifacts"]}
    runtime_path = tmp_path / "reports" / "runtime-card.json"
    assert artifacts["runtime_card"] == {
        "id": "runtime_card",
        "label": "Runtime card",
        "path": "reports/runtime-card.json",
        "state": "present",
        "schema_version": "entroping.runtime-card.v1",
        "sha256": hashlib.sha256(runtime_path.read_bytes()).hexdigest(),
        "summary": "attention; 2 findings",
    }
    assert artifacts["test_pyramid"]["summary"] == (
        "complete; 6/6 runtime-governance layers present"
    )
    assert {target["id"] for target in payload["targets"]} == {
        "cli",
        "pr",
        "desktop",
        "cloud",
        "mobile",
        "agent",
    }
    targets = {target["id"]: target for target in payload["targets"]}
    assert targets["cli"]["artifact_paths"][0] == "reports/handoff.json"
    assert targets["pr"]["artifact_paths"] == [
        "reports/handoff.json",
        "reports/runtime-card.json",
    ]
    assert "sk-proj" not in json.dumps(payload)
    markdown = render_handoff_markdown(result.packet)
    assert "- Runtime status: `attention`" in markdown
    assert "- Failed gates: `2`" in markdown


def test_run_handoff_report_writes_markdown_from_core(tmp_path: Path) -> None:
    _write_handoff_inputs(tmp_path)

    result = run_handoff_report(project_root=tmp_path, output="md")

    assert result.output_path == tmp_path / "reports" / "handoff.md"
    markdown = result.output_path.read_text(encoding="utf-8")
    assert "# Entroping Evidence Handoff" in markdown
    assert "| runtime_card | present | reports/runtime-card.json |" in markdown
    assert (
        "| cli | Open the local handoff packet and referenced reports. | "
        "reports/handoff.md, reports/runtime-card.json,"
    ) in markdown


def test_handoff_markdown_escapes_backslash_pipe_cells(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {
                "status": r"attention\|split",
                "findings": 2,
                "evidence_links": 3,
            },
        },
    )

    markdown = render_handoff_markdown(build_handoff_packet(project_root=tmp_path))

    assert "attention&#92;\\|split; 2 findings" in markdown


def test_handoff_packet_marks_missing_artifacts_non_blocking(tmp_path: Path) -> None:
    packet = build_handoff_packet(project_root=tmp_path)

    assert packet.project is None
    assert packet.git.branch is None
    assert packet.git.commit is None
    assert packet.runtime is None
    assert packet.summary.status == "insufficient"
    assert packet.summary.artifacts_missing == 5
    assert {artifact.state for artifact in packet.artifacts} == {"missing"}
    markdown = render_handoff_markdown(packet)
    assert "# Entroping Evidence Handoff" in markdown
    assert "| runtime_card | missing | reports/runtime-card.json |" in markdown


def test_handoff_packet_marks_unsafe_and_invalid_sources(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "runtime-card.json",
        {"schema_version": "entroping.runtime-card.v999", "summary": {"status": "pass"}},
    )
    (reports / "evidence-bundle.json").mkdir()
    real_pilot = reports / "pilot-source.json"
    _write_json(
        real_pilot,
        {
            "schema_version": "entroping.pilot-metrics.v1",
            "summary": {"status": "partial"},
        },
    )
    os.symlink(real_pilot, reports / "pilot-metrics.json")
    _write_json(
        reports / "artifact-manifest.json",
        {
            "schema_version": "entroping.report-artifact-manifest.v1",
            "secret": "sk-proj-" + ("a" * 24),
        },
    )
    (reports / "test-pyramid.json").write_text("not json\n", encoding="utf-8")

    packet = build_handoff_packet(project_root=tmp_path)

    artifacts = {artifact.id: artifact for artifact in packet.artifacts}
    assert artifacts["runtime_card"].state == "invalid"
    assert artifacts["runtime_card"].schema_version == "entroping.runtime-card.v999"
    assert artifacts["evidence_bundle"].state == "unsafe"
    assert "not a file" in artifacts["evidence_bundle"].summary
    assert artifacts["pilot_metrics"].state == "unsafe"
    assert "symlinked component" in artifacts["pilot_metrics"].summary
    assert artifacts["artifact_manifest"].state == "unsafe"
    assert "secret-like content" in artifacts["artifact_manifest"].summary
    assert artifacts["test_pyramid"].state == "invalid"
    assert packet.summary.status == "insufficient"


def test_handoff_packet_marks_bad_utf8_and_non_object_json_invalid(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "runtime-card.json").write_bytes(b"\xff")
    _write_json(reports / "test-pyramid.json", [])

    packet = build_handoff_packet(project_root=tmp_path)

    artifacts = {artifact.id: artifact for artifact in packet.artifacts}
    assert artifacts["runtime_card"].state == "invalid"
    assert "Could not decode runtime card as UTF-8" in artifacts["runtime_card"].summary
    assert artifacts["test_pyramid"].state == "invalid"
    assert "must be a JSON object" in artifacts["test_pyramid"].summary


def test_handoff_packet_marks_oversized_and_unreadable_artifacts_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "pass", "findings": 0, "evidence_links": 0},
        },
    )
    (reports / "pilot-metrics.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(handoff_packet, "_MAX_HANDOFF_ARTIFACT_BYTES", 4)

    original_read_bytes = Path.read_bytes

    def maybe_fail_read(path: Path) -> bytes:
        if path.name == "pilot-metrics.json":
            raise OSError("permission denied")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", maybe_fail_read)

    packet = build_handoff_packet(project_root=tmp_path)

    artifacts = {artifact.id: artifact for artifact in packet.artifacts}
    assert artifacts["runtime_card"].state == "invalid"
    assert "exceeds 4 bytes" in artifacts["runtime_card"].summary
    assert artifacts["pilot_metrics"].state == "invalid"
    assert "Could not read pilot metrics" in artifacts["pilot_metrics"].summary


def test_handoff_packet_marks_malformed_present_runtime_card_invalid(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "", "findings": -1, "evidence_links": 0},
            "pilot_readiness": "not-object",
        },
    )

    packet = build_handoff_packet(project_root=tmp_path)

    runtime_card = {artifact.id: artifact for artifact in packet.artifacts}["runtime_card"]
    assert runtime_card.state == "invalid"
    assert "status must be a non-empty string" in runtime_card.summary
    assert packet.project is None
    assert packet.runtime is None


def test_handoff_packet_accepts_runtime_card_without_optional_nested_blocks(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "pass", "findings": 0, "evidence_links": 0},
        },
    )

    packet = build_handoff_packet(project_root=tmp_path)

    assert packet.project is None
    assert packet.runtime is not None
    assert packet.runtime.pilot_readiness_status is None
    assert packet.runtime.test_pyramid_status is None


def test_handoff_packet_marks_missing_objects_and_bad_counts_invalid(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "pass", "findings": -1, "evidence_links": 0},
        },
    )
    _write_json(
        reports / "evidence-bundle.json",
        {"schema_version": "entroping.evidence-bundle.v1"},
    )

    packet = build_handoff_packet(project_root=tmp_path)

    artifacts = {artifact.id: artifact for artifact in packet.artifacts}
    assert artifacts["runtime_card"].state == "invalid"
    assert "findings must be a non-negative integer" in artifacts["runtime_card"].summary
    assert artifacts["evidence_bundle"].state == "invalid"
    assert "summary must be an object" in artifacts["evidence_bundle"].summary


def test_run_handoff_report_rejects_unsupported_output(tmp_path: Path) -> None:
    with pytest.raises(HandoffError, match="Unsupported handoff output"):
        run_handoff_report(project_root=tmp_path, output="html")  # type: ignore[arg-type]


def test_run_handoff_report_rejects_unsafe_output_path(tmp_path: Path) -> None:
    with pytest.raises(HandoffError, match="must stay under"):
        run_handoff_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "handoff.json",
        )


def test_run_handoff_report_rejects_resolved_output_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_symlink_path_component(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        handoff_packet,
        "first_symlink_path_component",
        no_symlink_path_component,
    )

    with pytest.raises(HandoffError, match="must stay under"):
        run_handoff_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "handoff.json",
        )


def test_run_handoff_report_rejects_output_inside_local_state(tmp_path: Path) -> None:
    with pytest.raises(HandoffError, match="must not be written into"):
        run_handoff_report(
            project_root=tmp_path,
            output="json",
            output_path=Path(".entroping") / "handoff.json",
        )


def test_run_handoff_report_rejects_symlinked_output_path(tmp_path: Path) -> None:
    (tmp_path / "real-reports").mkdir()
    os.symlink(tmp_path / "real-reports", tmp_path / "linked-reports")

    with pytest.raises(HandoffError, match="symlinked component"):
        run_handoff_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("linked-reports") / "handoff.json",
        )


def test_run_handoff_report_rejects_secret_like_rendered_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = build_handoff_packet(project_root=tmp_path)
    monkeypatch.setattr(
        handoff_packet,
        "build_handoff_packet",
        lambda **_: packet.model_copy(
            update={"project": "sk-proj-" + ("a" * 24)}
        ),
    )

    with pytest.raises(HandoffError, match="contains secret-like content"):
        run_handoff_report(project_root=tmp_path, output="json")


def test_run_handoff_report_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_safe_write(*args: object, **kwargs: object) -> Path:
        raise SafeWriteError("disk full")

    monkeypatch.setattr(handoff_packet, "safe_write_text", fail_safe_write)

    with pytest.raises(HandoffError, match="disk full"):
        run_handoff_report(project_root=tmp_path, output="json")


def test_handoff_packet_tolerates_git_subprocess_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_git(*args: object, **kwargs: object) -> object:
        raise subprocess.TimeoutExpired(cmd=["git"], timeout=2)

    monkeypatch.setattr("entroping.core.evidence.handoff_packet.subprocess.run", fail_git)

    packet = build_handoff_packet(project_root=tmp_path)

    assert packet.git.branch is None
    assert packet.git.commit is None


def test_handoff_packet_git_subprocess_uses_minimal_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    git_binary = str(tmp_path / "trusted-bin" / "git")
    calls: list[tuple[list[str], dict[str, str] | None]] = []
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-" + ("a" * 24))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
    monkeypatch.setattr(
        "entroping.core.evidence.handoff_packet.shutil.which",
        lambda binary: git_binary,
    )

    def fake_run(
        args: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        timeout: float,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((args, env))
        assert check is False
        assert capture_output is True
        assert text is True
        assert timeout == handoff_packet._GIT_TIMEOUT_SECONDS
        if args[-2:] == ["branch", "--show-current"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="main\n")
        if args[-2:] == ["rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=("a" * 40) + "\n")
        return subprocess.CompletedProcess(args=args, returncode=1, stdout="")

    monkeypatch.setattr("entroping.core.evidence.handoff_packet.subprocess.run", fake_run)

    packet = build_handoff_packet(project_root=tmp_path)

    expected_path = ":".join(
        dict.fromkeys(
            [
                str(Path(git_binary).resolve().parent),
                "/usr/bin",
                "/bin",
            ]
        )
    )
    expected_env = {"PATH": expected_path}
    assert packet.git.branch == "main"
    assert packet.git.commit == "a" * 40
    assert calls == [
        ([git_binary, "-C", str(tmp_path), "branch", "--show-current"], expected_env),
        ([git_binary, "-C", str(tmp_path), "rev-parse", "HEAD"], expected_env),
    ]
    assert "OPENAI_API_KEY" not in expected_env
    assert "DEEPSEEK_API_KEY" not in expected_env


def test_handoff_packet_tolerates_missing_git_binary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("entroping.core.evidence.handoff_packet.shutil.which", lambda _: None)

    packet = build_handoff_packet(project_root=tmp_path)

    assert packet.git.branch is None
    assert packet.git.commit is None


def _init_git_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    (root / "README.md").write_text("# fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=root,
        check=True,
        capture_output=True,
    )


def _write_handoff_inputs(root: Path) -> None:
    reports = root / "reports"
    reports.mkdir()
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "attention", "findings": 2, "evidence_links": 3},
            "run": {
                "project": "checkout-api",
                "failed_gate_ids": ["global_latency", "request_id_header"],
            },
            "pilot_readiness": {"status": "ready"},
            "test_pyramid": {"status": "complete"},
        },
    )
    _write_json(
        reports / "evidence-bundle.json",
        {
            "schema_version": "entroping.evidence-bundle.v1",
            "summary": {
                "status": "ready",
                "required_present": 2,
                "required_total": 2,
            },
        },
    )
    _write_json(
        reports / "pilot-metrics.json",
        {
            "schema_version": "entroping.pilot-metrics.v1",
            "summary": {"status": "partial"},
        },
    )
    _write_json(
        reports / "artifact-manifest.json",
        {
            "schema_version": "entroping.report-artifact-manifest.v1",
            "audit": {"verification": {"status": "verified"}},
        },
    )
    _write_json(
        reports / "test-pyramid.json",
        {
            "schema_version": "entroping.test-pyramid-report.v1",
            "summary": {
                "runtime_governance_status": "complete",
                "total_layers": 6,
                "present_layers": 6,
                "attention_layers": 0,
                "findings": 0,
            },
        },
    )


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
