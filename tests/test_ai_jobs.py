"""Tests for the queued AI worker job supervisor."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import cast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "ai_jobs.py"


def load_ai_jobs_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("entroping_ai_jobs_script", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_ai_jobs(
    *args: str,
    cwd: Path = REPO_ROOT,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, **env} if env is not None else None,
    )


def write_fake_opencode(path: Path, *, body: str) -> Path:
    binary = path / "opencode"
    binary.write_text(body, encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    return binary


def write_fake_counting_opencode(
    path: Path,
    *,
    sleep_seconds: float = 0.0,
) -> tuple[Path, Path]:
    binary = path / "opencode"
    marker_dir = path / "invocations"
    binary.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib\n"
        "import time\n\n"
        "import uuid\n\n"
        f"MARKER_DIR = pathlib.Path({str(marker_dir)!r})\n"
        "MARKER_DIR.mkdir(parents=True, exist_ok=True)\n"
        "(MARKER_DIR / f'{uuid.uuid4().hex}.txt').write_text('1', encoding='utf-8')\n"
        f"time.sleep({sleep_seconds!r})\n"
        "print('worker review output')\n"
    )
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    return binary, marker_dir


def read_job(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return cast(dict[str, object], payload)


def read_metrics_events(ledger: Path) -> list[dict[str, object]]:
    return [
        cast(dict[str, object], json.loads(line))
        for line in ledger.read_text(encoding="utf-8").splitlines()
    ]


class DeepSeekQueueStubHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, object]] = []

    def do_POST(self) -> None:  # noqa: N802
        content_length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(content_length).decode("utf-8"))
        self.__class__.requests.append(
            {
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "body": body,
            }
        )
        response = {
            "choices": [{"message": {"content": "Concrete finding"}}],
            "usage": {
                "completion_tokens": 7,
                "prompt_tokens": 11,
                "total_tokens": 18,
            },
        }
        encoded = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return


def test_ai_jobs_state_writes_do_not_truncate_visible_job_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ai_jobs = load_ai_jobs_module()
    target = tmp_path / "running" / "job.json"
    target.parent.mkdir()
    target.write_text('{"job_id": "old", "queue_status": "running"}\n', encoding="utf-8")

    original_write_text = Path.write_text
    wrote_visible_path = False

    def spy_write_text(
        path: Path,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> int:
        nonlocal wrote_visible_path
        if path == target:
            wrote_visible_path = True
        return original_write_text(path, data, encoding=encoding, errors=errors, newline=newline)

    monkeypatch.setattr(Path, "write_text", spy_write_text)

    ai_jobs._write_job(target, {"job_id": "new", "queue_status": "running"})

    assert wrote_visible_path is False
    assert read_job(target)["job_id"] == "new"
    assert not list(target.parent.glob("*.tmp"))


def test_ai_jobs_help_documents_queue_subcommands() -> None:
    result = run_ai_jobs("--help")

    assert result.returncode == 0
    assert "submit" in result.stdout
    assert "run-next" in result.stdout
    assert "status" in result.stdout
    assert "collect" in result.stdout


def test_ai_jobs_run_next_help_documents_factory_metrics_options() -> None:
    result = run_ai_jobs("run-next", "--help")

    assert result.returncode == 0
    assert "--record-factory-metrics" in result.stdout
    assert "--factory-role" in result.stdout
    assert "--factory-metrics-ledger" in result.stdout


def test_ai_jobs_submit_writes_queued_job_with_model_profile(tmp_path: Path) -> None:
    job_root = tmp_path / "ai-jobs"

    result = run_ai_jobs(
        "submit",
        "--mode",
        "review",
        "--profile",
        "flash-free",
        "--file",
        "README.md",
        "--issue",
        "579",
        "--instruction",
        "Find concrete risks only.",
        "--job-root",
        str(job_root),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    job_path = Path(str(payload["job_path"]))
    job = read_job(job_path)

    assert job_path.parent == job_root / "queued"
    assert job["queue_status"] == "queued"
    assert job["mode"] == "review"
    assert job["profile"] == "flash-free"
    assert job["model"] == "opencode/deepseek-v4-flash-free"
    assert job["files"] == ["README.md"]
    assert job["issue"] == "579"
    assert job["instruction"] == "Find concrete risks only."


def test_ai_jobs_submit_writes_deepseek_api_engine_with_provider_model(
    tmp_path: Path,
) -> None:
    job_root = tmp_path / "ai-jobs"

    result = run_ai_jobs(
        "submit",
        "--mode",
        "review",
        "--engine",
        "deepseek-api",
        "--profile",
        "pro",
        "--file",
        "README.md",
        "--job-root",
        str(job_root),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    job = read_job(Path(str(payload["job_path"])))

    assert job["engine"] == "deepseek-api"
    assert job["profile"] == "pro"
    assert job["model"] == "deepseek-v4-pro"


def test_ai_jobs_submit_rejects_opencode_only_profile_for_deepseek_api(
    tmp_path: Path,
) -> None:
    result = run_ai_jobs(
        "submit",
        "--mode",
        "review",
        "--engine",
        "deepseek-api",
        "--profile",
        "flash-free",
        "--file",
        "README.md",
        "--job-root",
        str(tmp_path / "ai-jobs"),
    )

    assert result.returncode == 2
    assert "not supported by engine 'deepseek-api'" in result.stderr


def test_ai_jobs_submit_rejects_unknown_model_profile(tmp_path: Path) -> None:
    result = run_ai_jobs(
        "submit",
        "--mode",
        "review",
        "--profile",
        "expensive-mystery",
        "--file",
        "README.md",
        "--job-root",
        str(tmp_path / "ai-jobs"),
    )

    assert result.returncode == 2
    assert "unknown model profile" in result.stderr


def test_ai_jobs_submit_rejects_symlinked_input_files(tmp_path: Path) -> None:
    symlink = tmp_path / "linked-readme.md"
    symlink.symlink_to(REPO_ROOT / "README.md")

    result = run_ai_jobs(
        "submit",
        "--mode",
        "review",
        "--profile",
        "flash-free",
        "--file",
        str(symlink),
        "--job-root",
        str(tmp_path / "ai-jobs"),
    )

    assert result.returncode == 2
    assert "input path must be a regular non-symlink file" in result.stderr


def test_ai_jobs_submit_rejects_input_files_under_symlinked_directories(
    tmp_path: Path,
) -> None:
    symlinked_repo = tmp_path / "repo-link"
    symlinked_repo.symlink_to(REPO_ROOT, target_is_directory=True)

    result = run_ai_jobs(
        "submit",
        "--mode",
        "review",
        "--profile",
        "flash-free",
        "--file",
        str(symlinked_repo / "README.md"),
        "--job-root",
        str(tmp_path / "ai-jobs"),
    )

    assert result.returncode == 2
    assert "input path must be a regular non-symlink file" in result.stderr


def test_ai_jobs_run_next_routes_deepseek_api_engine_to_direct_worker(
    tmp_path: Path,
) -> None:
    job_root = tmp_path / "ai-jobs"
    artifact_root = tmp_path / "ai-reviews"

    submit = run_ai_jobs(
        "submit",
        "--mode",
        "review",
        "--engine",
        "deepseek-api",
        "--profile",
        "pro",
        "--file",
        "README.md",
        "--job-root",
        str(job_root),
        "--json",
    )
    assert submit.returncode == 0, submit.stderr

    result = run_ai_jobs(
        "run-next",
        "--job-root",
        str(job_root),
        "--artifact-root",
        str(artifact_root),
        "--worker-dry-run",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    completed_path = Path(str(payload["job_path"]))
    job = read_job(completed_path)
    artifact_dir = Path(str(job["artifact_dir"]))
    metadata = read_job(artifact_dir / "metadata.json")

    assert job["queue_status"] == "completed"
    assert job["engine"] == "deepseek-api"
    assert job["worker_status"] == "dry-run"
    assert metadata["schema_version"] == "entroping.deepseek-worker.v1"
    assert metadata["model"] == "deepseek-v4-pro"
    assert not (artifact_dir / "stdout.txt").exists()


def test_ai_jobs_run_next_records_opencode_factory_metrics_when_requested(
    tmp_path: Path,
) -> None:
    job_root = tmp_path / "ai-jobs"
    artifact_root = tmp_path / "ai-reviews"
    ledger = (
        Path(".entroping")
        / "factory-metrics"
        / "tests"
        / f"ai-jobs-opencode-{uuid.uuid4().hex}.jsonl"
    )
    full_ledger = REPO_ROOT / ledger

    submit = run_ai_jobs(
        "submit",
        "--mode",
        "review",
        "--profile",
        "pro",
        "--file",
        "README.md",
        "--issue",
        "656",
        "--job-root",
        str(job_root),
        "--json",
    )
    assert submit.returncode == 0, submit.stderr

    try:
        result = run_ai_jobs(
            "run-next",
            "--job-root",
            str(job_root),
            "--artifact-root",
            str(artifact_root),
            "--worker-dry-run",
            "--record-factory-metrics",
            "--factory-role",
            "code_review_agent",
            "--factory-metrics-ledger",
            ledger.as_posix(),
            "--json",
        )

        assert result.returncode == 0, result.stderr
        event = read_metrics_events(full_ledger)[0]
        metrics = cast(dict[str, object], event["metrics"])
        assert event["event_type"] == "worker_job"
        assert event["role"] == "code_review_agent"
        assert event["agent"] == "OpenCode"
        assert event["tool"] == "scripts/opencode_worker.py"
        assert event["issue"] == "656"
        assert event["outcome"] == "success"
        assert metrics["candidate_files"] == 1
        assert metrics["files_read"] == 1
        assert "Codex remains the integrator" not in full_ledger.read_text(
            encoding="utf-8"
        )
    finally:
        full_ledger.unlink(missing_ok=True)


def test_ai_jobs_run_next_records_deepseek_factory_metrics_when_requested(
    tmp_path: Path,
) -> None:
    job_root = tmp_path / "ai-jobs"
    artifact_root = tmp_path / "ai-reviews"
    ledger = (
        Path(".entroping")
        / "factory-metrics"
        / "tests"
        / f"ai-jobs-deepseek-{uuid.uuid4().hex}.jsonl"
    )
    full_ledger = REPO_ROOT / ledger

    submit = run_ai_jobs(
        "submit",
        "--mode",
        "review",
        "--engine",
        "deepseek-api",
        "--profile",
        "pro",
        "--file",
        "README.md",
        "--issue",
        "656",
        "--job-root",
        str(job_root),
        "--json",
    )
    assert submit.returncode == 0, submit.stderr

    try:
        result = run_ai_jobs(
            "run-next",
            "--job-root",
            str(job_root),
            "--artifact-root",
            str(artifact_root),
            "--worker-dry-run",
            "--record-factory-metrics",
            "--factory-role",
            "code_review_agent",
            "--factory-metrics-ledger",
            ledger.as_posix(),
            "--json",
        )

        assert result.returncode == 0, result.stderr
        event = read_metrics_events(full_ledger)[0]
        metrics = cast(dict[str, object], event["metrics"])
        assert event["event_type"] == "worker_job"
        assert event["role"] == "code_review_agent"
        assert event["agent"] == "DeepSeek"
        assert event["tool"] == "scripts/deepseek_worker.py"
        assert event["issue"] == "656"
        assert event["outcome"] == "success"
        assert metrics["candidate_files"] == 1
        assert metrics["files_read"] == 1
        assert "## Bounded File Contents" not in full_ledger.read_text(encoding="utf-8")
    finally:
        full_ledger.unlink(missing_ok=True)


def test_ai_jobs_run_next_metrics_failure_does_not_mask_worker_result(
    tmp_path: Path,
) -> None:
    job_root = tmp_path / "ai-jobs"
    artifact_root = tmp_path / "ai-reviews"
    unsafe_ledger = tmp_path / "unsafe-ledger.jsonl"

    submit = run_ai_jobs(
        "submit",
        "--mode",
        "review",
        "--profile",
        "pro",
        "--file",
        "README.md",
        "--job-root",
        str(job_root),
        "--json",
    )
    assert submit.returncode == 0, submit.stderr

    result = run_ai_jobs(
        "run-next",
        "--job-root",
        str(job_root),
        "--artifact-root",
        str(artifact_root),
        "--worker-dry-run",
        "--record-factory-metrics",
        "--factory-metrics-ledger",
        str(unsafe_ledger),
        "--json",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    job = read_job(Path(str(payload["job_path"])))
    assert job["queue_status"] == "completed"
    assert job["worker_status"] == "dry-run"
    assert not unsafe_ledger.exists()


def test_ai_jobs_worker_command_does_not_record_metrics_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ai_jobs = load_ai_jobs_module()
    captured_command: list[str] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured_command[:] = command
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=json.dumps(
                {
                    "status": "dry-run",
                    "returncode": 0,
                    "artifact_dir": str(tmp_path / "artifact"),
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(ai_jobs.subprocess, "run", fake_run)
    args = SimpleNamespace(
        artifact_root=tmp_path / "ai-reviews",
        opencode_bin=None,
        worker_dry_run=True,
        record_factory_metrics=False,
        factory_role=None,
        factory_metrics_ledger=None,
    )
    job = {
        "engine": "opencode",
        "mode": "review",
        "model": "deepseek/deepseek-v4-pro",
        "files": ["README.md"],
        "timeout_seconds": 1,
    }

    payload, returncode = ai_jobs._run_worker(args, REPO_ROOT, job)

    assert returncode == 0
    assert payload["status"] == "dry-run"
    assert "--record-factory-metrics" not in captured_command
    assert "--factory-role" not in captured_command
    assert "--factory-metrics-ledger" not in captured_command


def test_ai_jobs_run_next_preserves_deepseek_usage_for_budget_review(
    tmp_path: Path,
) -> None:
    job_root = tmp_path / "ai-jobs"
    artifact_root = tmp_path / "ai-reviews"
    DeepSeekQueueStubHandler.requests = []
    server = HTTPServer(("127.0.0.1", 0), DeepSeekQueueStubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    submit = run_ai_jobs(
        "submit",
        "--mode",
        "review",
        "--engine",
        "deepseek-api",
        "--profile",
        "pro",
        "--file",
        "README.md",
        "--job-root",
        str(job_root),
        "--json",
    )
    assert submit.returncode == 0, submit.stderr

    try:
        result = run_ai_jobs(
            "run-next",
            "--job-root",
            str(job_root),
            "--artifact-root",
            str(artifact_root),
            "--deepseek-base-url",
            base_url,
            "--deepseek-api-key-env",
            "ENTROPING_TEST_DEEPSEEK_KEY",
            "--json",
            env={"ENTROPING_TEST_DEEPSEEK_KEY": "test-secret-token"},
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    expected_usage = {
        "completion_tokens": 7,
        "prompt_tokens": 11,
        "total_tokens": 18,
    }
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    completed_path = Path(str(payload["job_path"]))
    job = read_job(completed_path)
    collect = run_ai_jobs("collect", "--job-root", str(job_root), "--json")
    collect_payload = json.loads(collect.stdout)

    assert payload["usage"] == expected_usage
    assert job["usage"] == expected_usage
    assert collect_payload["completed_jobs"][0]["usage"] == expected_usage
    assert collect_payload["summary"]["by_engine"] == {"deepseek-api": 1}
    assert collect_payload["summary"]["by_profile"] == {"pro": 1}
    assert collect_payload["summary"]["by_mode"] == {"review": 1}
    assert collect_payload["summary"]["by_worker_status"] == {"completed": 1}
    assert collect_payload["summary"]["by_model"] == {"deepseek-v4-pro": 1}
    assert collect_payload["summary"]["usage"] == {
        "known_jobs": 1,
        "totals": expected_usage,
        "unknown_jobs": 0,
    }
    assert collect_payload["completed_jobs"][0]["metadata_path"] == str(
        Path(str(job["artifact_dir"])) / "metadata.json"
    )
    assert "Concrete finding" not in completed_path.read_text(encoding="utf-8")
    assert "Concrete finding" not in collect.stdout
    assert "test-secret-token" not in result.stdout
    assert "test-secret-token" not in collect.stdout


def test_ai_jobs_run_next_concurrent_invocations_process_distinct_jobs_once(tmp_path: Path) -> None:
    job_root = tmp_path / "ai-jobs"
    artifact_root = tmp_path / "ai-reviews"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode, invocation_markers = write_fake_counting_opencode(
        fake_bin,
        sleep_seconds=0.15,
    )

    for _ in range(2):
        submit = run_ai_jobs(
            "submit",
            "--mode",
            "review",
            "--profile",
            "pro",
            "--file",
            "README.md",
            "--job-root",
            str(job_root),
        )
        assert submit.returncode == 0, submit.stderr

    start = threading.Barrier(2)
    lock = threading.Lock()
    run_next_results: list[subprocess.CompletedProcess[str]] = []

    def run_next_once() -> None:
        start.wait()
        result = run_ai_jobs(
            "run-next",
            "--job-root",
            str(job_root),
            "--artifact-root",
            str(artifact_root),
            "--opencode-bin",
            str(fake_opencode),
            "--json",
        )
        with lock:
            run_next_results.append(result)

    threads = [threading.Thread(target=run_next_once) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(run_next_results) == 2
    terminal_job_paths = []
    for result in run_next_results:
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        terminal_job_paths.append(Path(str(payload["job_path"])))

    assert len(terminal_job_paths) == 2
    assert len({path.name for path in terminal_job_paths}) == 2
    assert all((job_root / "queued" / path.name).exists() is False for path in terminal_job_paths)
    assert len(list((job_root / "running").glob("*.json"))) == 0
    assert len(list((job_root / "queued").glob("*.json"))) == 0
    assert len(list(invocation_markers.glob("*.txt"))) == 2
    terminal_job_ids = [read_job(path)["job_id"] for path in terminal_job_paths]
    assert len(set(terminal_job_ids)) == 2


def test_ai_jobs_run_next_completes_oldest_job_and_records_worker_result(
    tmp_path: Path,
) -> None:
    job_root = tmp_path / "ai-jobs"
    artifact_root = tmp_path / "ai-reviews"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = write_fake_opencode(
        fake_bin,
        body="#!/usr/bin/env bash\nprintf '%s\\n' 'worker review output'\n",
    )

    submit = run_ai_jobs(
        "submit",
        "--mode",
        "review",
        "--profile",
        "flash",
        "--file",
        "README.md",
        "--job-root",
        str(job_root),
        "--json",
    )
    assert submit.returncode == 0, submit.stderr

    result = run_ai_jobs(
        "run-next",
        "--job-root",
        str(job_root),
        "--artifact-root",
        str(artifact_root),
        "--opencode-bin",
        str(fake_opencode),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    completed_path = Path(str(payload["job_path"]))
    job = read_job(completed_path)

    assert not list((job_root / "queued").glob("*.json"))
    assert not list((job_root / "running").glob("*.json"))
    assert completed_path.parent == job_root / "completed"
    assert job["queue_status"] == "completed"
    assert job["worker_status"] == "completed"
    assert job["worker_returncode"] == 0
    artifact_dir = Path(str(job["artifact_dir"]))
    assert artifact_dir.is_dir()
    assert artifact_dir.parent == artifact_root
    assert "worker review output" in (artifact_dir / "stdout.txt").read_text(
        encoding="utf-8"
    )
    assert "worker review output" not in completed_path.read_text(encoding="utf-8")


def test_ai_jobs_run_next_moves_failed_job_to_failed(tmp_path: Path) -> None:
    job_root = tmp_path / "ai-jobs"
    artifact_root = tmp_path / "ai-reviews"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = write_fake_opencode(
        fake_bin,
        body="#!/usr/bin/env bash\nprintf '%s\\n' 'worker failed' >&2\nexit 7\n",
    )

    submit = run_ai_jobs(
        "submit",
        "--mode",
        "review",
        "--profile",
        "pro",
        "--file",
        "README.md",
        "--job-root",
        str(job_root),
        "--json",
    )
    assert submit.returncode == 0, submit.stderr

    result = run_ai_jobs(
        "run-next",
        "--job-root",
        str(job_root),
        "--artifact-root",
        str(artifact_root),
        "--opencode-bin",
        str(fake_opencode),
        "--json",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    failed_path = Path(str(payload["job_path"]))
    job = read_job(failed_path)

    assert failed_path.parent == job_root / "failed"
    assert job["queue_status"] == "failed"
    assert job["worker_status"] == "failed"
    assert job["worker_returncode"] == 7
    assert job["worker_process_returncode"] == 1
    assert Path(str(job["artifact_dir"])).is_dir()
    assert not list((job_root / "running").glob("*.json"))


def test_ai_jobs_run_next_recoverable_from_corrupt_queued_artifact(tmp_path: Path) -> None:
    job_root = tmp_path / "ai-jobs"
    artifact_root = tmp_path / "ai-reviews"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = write_fake_opencode(
        fake_bin,
        body="#!/usr/bin/env bash\nprintf '%s\\n' 'worker review output'\\n",
    )
    submit = run_ai_jobs(
        "submit",
        "--mode",
        "review",
        "--profile",
        "pro",
        "--file",
        "README.md",
        "--job-root",
        str(job_root),
        "--json",
    )
    assert submit.returncode == 0, submit.stderr
    good_job = read_job(Path(json.loads(submit.stdout)["job_path"]))

    corrupt_path = job_root / "queued" / "000-corrupt.json"
    corrupt_path.write_text("not-json", encoding="utf-8")

    first = run_ai_jobs(
        "run-next",
        "--job-root",
        str(job_root),
        "--artifact-root",
        str(artifact_root),
        "--opencode-bin",
        str(fake_opencode),
        "--json",
    )
    assert first.returncode in {0, 1, 2}
    first_payload = json.loads(first.stdout)
    assert first.returncode == 1
    assert first_payload["status"] == "failed"
    assert first_payload["worker_status"] == "corrupt-queued-job"

    second = run_ai_jobs(
        "run-next",
        "--job-root",
        str(job_root),
        "--artifact-root",
        str(artifact_root),
        "--opencode-bin",
        str(fake_opencode),
        "--json",
    )
    assert second.returncode == 0
    second_payload = json.loads(second.stdout)
    assert second_payload["status"] == "completed"

    terminal_jobs = [
        read_job(path)
        for state in ("completed", "failed")
        for path in (job_root / state).glob("*.json")
    ]
    assert len(terminal_jobs) == 2
    assert any(
        job["job_id"] == good_job["job_id"] and job["queue_status"] == "completed"
        for job in terminal_jobs
    )
    assert any(
        job["job_id"] == "000-corrupt"
        and job["queue_status"] == "failed"
        and job["worker_status"] == "corrupt-queued-job"
        for job in terminal_jobs
    )
    assert not (job_root / "queued" / Path(json.loads(submit.stdout)["job_path"]).name).exists()
    assert not corrupt_path.exists()
    assert not list((job_root / "running").glob("*.json"))


def test_ai_jobs_run_next_fails_stale_running_job_before_new_work(tmp_path: Path) -> None:
    job_root = tmp_path / "ai-jobs"
    running = job_root / "running"
    running.mkdir(parents=True)
    stale_path = running / "stale-job.json"
    stale_path.write_text(
        json.dumps(
            {
                "schema_version": "entroping.ai-job.v1",
                "job_id": "stale-job",
                "queue_status": "running",
                "engine": "opencode",
                "mode": "review",
                "profile": "pro",
                "model": "deepseek/deepseek-v4-pro",
                "files": ["README.md"],
                "timeout_seconds": 1,
                "attempts": 1,
                "started_at": "1970-01-01T00:00:00+00:00",
                "updated_at": "1970-01-01T00:00:00+00:00",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_ai_jobs(
        "run-next",
        "--job-root",
        str(job_root),
        "--json",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    failed_path = Path(str(payload["job_path"]))
    job = read_job(failed_path)

    assert payload["worker_status"] == "stale-running-job"
    assert failed_path.parent == job_root / "failed"
    assert job["job_id"] == "stale-job"
    assert job["queue_status"] == "failed"
    assert job["worker_status"] == "stale-running-job"
    assert not stale_path.exists()
    assert not list(running.glob("*.json"))


def test_ai_jobs_status_summarizes_counts_without_raw_output(tmp_path: Path) -> None:
    job_root = tmp_path / "ai-jobs"
    queued = job_root / "queued"
    completed = job_root / "completed"
    queued.mkdir(parents=True)
    completed.mkdir(parents=True)
    (queued / "queued.json").write_text('{"queue_status": "queued"}\n', encoding="utf-8")
    (completed / "done.json").write_text(
        '{"queue_status": "completed", "raw": "do not print me"}\n',
        encoding="utf-8",
    )

    result = run_ai_jobs("status", "--job-root", str(job_root), "--json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["counts"] == {
        "queued": 1,
        "running": 0,
        "completed": 1,
        "failed": 0,
    }
    assert "do not print me" not in result.stdout


def test_ai_jobs_collect_lists_completed_artifacts_for_codex_review(
    tmp_path: Path,
) -> None:
    job_root = tmp_path / "ai-jobs"
    completed = job_root / "completed"
    completed.mkdir(parents=True)
    artifact_dir = tmp_path / "ai-reviews" / "review-1"
    artifact_dir.mkdir(parents=True)
    (completed / "job-1.json").write_text(
        json.dumps(
            {
                "job_id": "job-1",
                "queue_status": "completed",
                "mode": "patch",
                "model": "deepseek/deepseek-v4-pro",
                "issue": "579",
                "worker_status": "patch-proposed",
                "artifact_dir": str(artifact_dir),
                "raw": "do not print me",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_ai_jobs("collect", "--job-root", str(job_root), "--json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["completed_jobs"] == [
        {
            "job_id": "job-1",
            "engine": "opencode",
            "profile": None,
            "mode": "patch",
            "model": "deepseek/deepseek-v4-pro",
            "issue": "579",
            "worker_status": "patch-proposed",
            "artifact_dir": str(artifact_dir),
            "metadata_path": str(artifact_dir / "metadata.json"),
        }
    ]
    assert payload["summary"] == {
        "total_completed": 1,
        "by_engine": {"opencode": 1},
        "by_profile": {"unknown": 1},
        "by_mode": {"patch": 1},
        "by_worker_status": {"patch-proposed": 1},
        "by_model": {"deepseek/deepseek-v4-pro": 1},
        "usage": {"known_jobs": 0, "totals": {}, "unknown_jobs": 1},
    }
    assert "do not print me" not in result.stdout


def test_ai_jobs_collect_sanitizes_malformed_usage_without_raw_output(
    tmp_path: Path,
) -> None:
    job_root = tmp_path / "ai-jobs"
    completed = job_root / "completed"
    completed.mkdir(parents=True)
    artifact_dir = tmp_path / "ai-reviews" / "review-usage"
    artifact_dir.mkdir(parents=True)
    (completed / "job-usage.json").write_text(
        json.dumps(
            {
                "job_id": "job-usage",
                "queue_status": "completed",
                "engine": "deepseek-api",
                "profile": "pro",
                "mode": "review",
                "model": "deepseek-v4-pro",
                "worker_status": "completed",
                "artifact_dir": str(artifact_dir),
                "usage": {
                    "prompt_tokens": 11,
                    "total_tokens": 18,
                    "raw": {"secret": "do not print me"},
                    "note": "do not print me",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_ai_jobs("collect", "--job-root", str(job_root), "--json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["completed_jobs"][0]["usage"] == {
        "prompt_tokens": 11,
        "total_tokens": 18,
    }
    assert payload["summary"]["usage"] == {
        "known_jobs": 1,
        "totals": {"prompt_tokens": 11, "total_tokens": 18},
        "unknown_jobs": 0,
    }
    assert "do not print me" not in result.stdout


def test_ai_jobs_run_next_reports_empty_queue(tmp_path: Path) -> None:
    result = run_ai_jobs("run-next", "--job-root", str(tmp_path / "ai-jobs"), "--json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "empty"
