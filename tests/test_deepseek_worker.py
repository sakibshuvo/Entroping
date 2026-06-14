"""Tests for the bounded direct DeepSeek API worker harness."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import ClassVar, cast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "deepseek_worker.py"


def run_worker(
    *args: str,
    cwd: Path = REPO_ROOT,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command_env = os.environ.copy()
    if env is not None:
        command_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        env=command_env,
    )


def read_metadata(artifact_dir: Path) -> dict[str, object]:
    payload = json.loads((artifact_dir / "metadata.json").read_text(encoding="utf-8"))
    return cast(dict[str, object], payload)


def read_metrics_events(ledger: Path) -> list[dict[str, object]]:
    return [
        cast(dict[str, object], json.loads(line))
        for line in ledger.read_text(encoding="utf-8").splitlines()
    ]


def make_worker_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "worker-repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    prompt_dir = repo / "prompts" / "deepseek"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "review.md").write_text("Review template\n", encoding="utf-8")
    (prompt_dir / "patch.md").write_text("Patch template\n", encoding="utf-8")
    return repo


class DeepSeekStubHandler(BaseHTTPRequestHandler):
    """Tiny local OpenAI-compatible endpoint for direct-worker tests."""

    requests: ClassVar[list[dict[str, object]]] = []
    response_payload: ClassVar[dict[str, object] | None] = None

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        DeepSeekStubHandler.requests.append(
            {
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "body": json.loads(body),
            }
        )
        response = DeepSeekStubHandler.response_payload or {
            "id": "chatcmpl-test",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": (
                            "Concrete finding: README should explain direct DeepSeek routing."
                        ),
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 7,
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


def test_deepseek_worker_help_documents_direct_api_options() -> None:
    result = run_worker("--help")

    assert result.returncode == 0
    assert "--api-key-env" in result.stdout
    assert "--base-url" in result.stdout
    assert "--max-file-bytes" in result.stdout
    assert "--record-factory-metrics" in result.stdout
    assert "--factory-metrics-ledger" in result.stdout
    assert "Default: disabled" in result.stdout
    assert "deepseek-v4-pro" in result.stdout


def test_deepseek_worker_dry_run_writes_prompt_and_metadata_without_api_key(
    tmp_path: Path,
) -> None:
    target_file = REPO_ROOT / "README.md"

    result = run_worker(
        "--mode",
        "review",
        "--file",
        str(target_file),
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--dry-run",
        "--json",
        env={"DEEPSEEK_API_KEY": ""},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    artifact_dir = Path(str(payload["artifact_dir"]))
    metadata = read_metadata(artifact_dir)

    assert metadata["schema_version"] == "entroping.deepseek-worker.v1"
    assert metadata["status"] == "dry-run"
    assert metadata["mode"] == "review"
    assert metadata["model"] == "deepseek-v4-pro"
    assert metadata["api_key_env"] == "DEEPSEEK_API_KEY"
    assert (
        metadata["capability_context_version"]
        == "entroping.deepseek-capability-context.v1"
    )
    prompt = (artifact_dir / "prompt.md").read_text(encoding="utf-8")
    assert "Codex remains the integrator" in prompt
    assert "## Factory Capability Context" in prompt
    assert "Direct DeepSeek API workers do not have live MCP" in prompt
    assert "scripts/context_pack.sh --mode implementation" in prompt
    assert "scripts/agent_context_probe.py" in prompt
    assert "scripts/factory_metrics.py" in prompt
    assert "scripts/ai_jobs.py" in prompt
    assert "scripts/opencode_worker.py" in prompt
    assert "scripts/deepseek_worker.py" in prompt
    assert "Graphify, CodeGraph, Headroom, Spark, Kimi, or MCP" in prompt
    assert "entroping run remains deterministic" in prompt
    assert str(target_file.resolve()) in prompt
    assert "## Bounded File Contents" in prompt
    assert "### File: README.md" in prompt
    assert "# Entroping" in prompt
    assert not (artifact_dir / "stdout.txt").exists()
    assert "secret" not in (artifact_dir / "metadata.json").read_text(encoding="utf-8")


def test_deepseek_worker_patch_dry_run_includes_capability_context(
    tmp_path: Path,
) -> None:
    target_file = REPO_ROOT / "README.md"

    result = run_worker(
        "--mode",
        "patch",
        "--file",
        str(target_file),
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--dry-run",
        "--json",
        env={"DEEPSEEK_API_KEY": ""},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    artifact_dir = Path(str(payload["artifact_dir"]))
    metadata = read_metadata(artifact_dir)
    prompt = (artifact_dir / "prompt.md").read_text(encoding="utf-8")

    assert metadata["mode"] == "patch"
    assert (
        metadata["capability_context_version"]
        == "entroping.deepseek-capability-context.v1"
    )
    assert "# Entroping Direct DeepSeek Patch Worker" in prompt
    assert "## Factory Capability Context" in prompt
    assert "Direct DeepSeek API workers do not have live MCP" in prompt
    assert "Return a single unified diff only" in prompt


def test_deepseek_worker_records_opt_in_factory_metrics_for_dry_run(
    tmp_path: Path,
) -> None:
    target_file = REPO_ROOT / "README.md"
    ledger = (
        Path(".entroping")
        / "factory-metrics"
        / "tests"
        / f"deepseek-dry-run-{uuid.uuid4().hex}.jsonl"
    )
    full_ledger = REPO_ROOT / ledger

    try:
        result = run_worker(
            "--mode",
            "review",
            "--file",
            str(target_file),
            "--issue",
            "654",
            "--artifact-root",
            str(tmp_path / "reviews"),
            "--record-factory-metrics",
            "--factory-role",
            "code_review_agent",
            "--factory-metrics-ledger",
            ledger.as_posix(),
            "--dry-run",
            "--json",
            env={"DEEPSEEK_API_KEY": ""},
        )

        assert result.returncode == 0, result.stderr
        events = read_metrics_events(full_ledger)
        assert len(events) == 1
        event = events[0]
        metrics = cast(dict[str, object], event["metrics"])
        assert event["event_type"] == "worker_job"
        assert event["role"] == "code_review_agent"
        assert event["agent"] == "DeepSeek"
        assert event["tool"] == "scripts/deepseek_worker.py"
        assert event["provider"] == "deepseek"
        assert event["model"] == "deepseek-v4-pro"
        assert event["issue"] == "654"
        assert event["outcome"] == "success"
        assert event["decision"] == "not_applicable"
        assert metrics["context_bytes"] == target_file.stat().st_size
        assert metrics["estimated_tokens"] == max(1, (target_file.stat().st_size + 3) // 4)
        assert metrics["candidate_files"] == 1
        assert metrics["files_read"] == 1
        assert "## Bounded File Contents" not in full_ledger.read_text(encoding="utf-8")
    finally:
        full_ledger.unlink(missing_ok=True)


def test_deepseek_worker_rejects_missing_api_key_before_artifact_write(
    tmp_path: Path,
) -> None:
    result = run_worker(
        "--mode",
        "review",
        "--file",
        "README.md",
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--api-key-env",
        "ENTROPING_TEST_MISSING_DEEPSEEK_KEY",
        env={"ENTROPING_TEST_MISSING_DEEPSEEK_KEY": ""},
    )

    assert result.returncode == 2
    assert "missing DeepSeek API key env var" in result.stderr
    assert not (tmp_path / "reviews").exists()


def test_deepseek_worker_rejects_base_url_with_credentials_before_model_call(
    tmp_path: Path,
) -> None:
    result = run_worker(
        "--mode",
        "review",
        "--file",
        "README.md",
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--base-url",
        "https://user:secret@api.deepseek.com",
        "--api-key-env",
        "ENTROPING_TEST_DEEPSEEK_KEY",
        env={"ENTROPING_TEST_DEEPSEEK_KEY": "test-secret-token"},
    )

    assert result.returncode == 2
    assert "--base-url must not include credentials, query, or fragment" in result.stderr
    assert not (tmp_path / "reviews").exists()


def test_deepseek_worker_posts_openai_compatible_request_and_writes_artifacts(
    tmp_path: Path,
) -> None:
    DeepSeekStubHandler.requests = []
    server = HTTPServer(("127.0.0.1", 0), DeepSeekStubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        result = run_worker(
            "--mode",
            "review",
            "--file",
            "README.md",
            "--artifact-root",
            str(tmp_path / "reviews"),
            "--base-url",
            base_url,
            "--api-key-env",
            "ENTROPING_TEST_DEEPSEEK_KEY",
            "--json",
            env={"ENTROPING_TEST_DEEPSEEK_KEY": "test-secret-token"},
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    artifact_dir = Path(str(payload["artifact_dir"]))
    metadata = read_metadata(artifact_dir)
    request = DeepSeekStubHandler.requests[0]
    body = cast(dict[str, object], request["body"])

    assert request["path"] == "/chat/completions"
    assert request["authorization"] == "Bearer test-secret-token"
    assert body["model"] == "deepseek-v4-pro"
    assert body["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in body
    assert "messages" in body
    messages = cast(list[dict[str, str]], body["messages"])
    assert "## Factory Capability Context" in messages[1]["content"]
    assert "Direct DeepSeek API workers do not have live MCP" in messages[1]["content"]
    assert "scripts/context_pack.sh --mode implementation" in messages[1]["content"]
    assert "## Bounded File Contents" in messages[1]["content"]
    assert "# Entroping" in messages[1]["content"]
    assert (
        metadata["capability_context_version"]
        == "entroping.deepseek-capability-context.v1"
    )
    assert metadata["status"] == "completed"
    assert metadata["usage"] == {
        "completion_tokens": 7,
        "prompt_tokens": 11,
        "total_tokens": 18,
    }
    assert "Concrete finding" in (artifact_dir / "stdout.txt").read_text(
        encoding="utf-8"
    )
    assert "test-secret-token" not in (artifact_dir / "metadata.json").read_text(
        encoding="utf-8"
    )


def test_deepseek_worker_withholds_secret_like_assistant_output(
    tmp_path: Path,
) -> None:
    DeepSeekStubHandler.requests = []
    DeepSeekStubHandler.response_payload = {
        "id": "chatcmpl-test",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": 'api_key = "abcdefghijklmnopqrstuvwxyz123456"',
                }
            }
        ],
        "usage": {
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "total_tokens": 18,
        },
    }
    server = HTTPServer(("127.0.0.1", 0), DeepSeekStubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        result = run_worker(
            "--mode",
            "review",
            "--file",
            "README.md",
            "--artifact-root",
            str(tmp_path / "reviews"),
            "--base-url",
            base_url,
            "--api-key-env",
            "ENTROPING_TEST_DEEPSEEK_KEY",
            "--json",
            env={"ENTROPING_TEST_DEEPSEEK_KEY": "test-secret-token"},
        )
    finally:
        DeepSeekStubHandler.response_payload = None
        server.shutdown()
        thread.join(timeout=2)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    artifact_dir = Path(str(payload["artifact_dir"]))
    metadata = read_metadata(artifact_dir)
    persisted_stdout = (artifact_dir / "stdout.txt").read_text(encoding="utf-8")
    persisted_stderr = (artifact_dir / "stderr.txt").read_text(encoding="utf-8")
    persisted_metadata = (artifact_dir / "metadata.json").read_text(encoding="utf-8")

    assert metadata["status"] == "failed"
    assert "DeepSeek stdout withheld because it contained secret-like content" in (
        persisted_stdout
    )
    assert persisted_stderr == ""
    assert not (artifact_dir / "response.json").exists()
    assert "abcdefghijklmnopqrstuvwxyz123456" not in persisted_stdout
    assert "abcdefghijklmnopqrstuvwxyz123456" not in persisted_stderr
    assert "abcdefghijklmnopqrstuvwxyz123456" not in persisted_metadata


def test_deepseek_worker_withholds_secret_like_error_response(
    tmp_path: Path,
) -> None:
    class SecretErrorHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            body = b'{"error": "token=abcdefghijklmnopqrstuvwxyz123456"}'
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), SecretErrorHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        result = run_worker(
            "--mode",
            "review",
            "--file",
            "README.md",
            "--artifact-root",
            str(tmp_path / "reviews"),
            "--base-url",
            base_url,
            "--api-key-env",
            "ENTROPING_TEST_DEEPSEEK_KEY",
            "--json",
            env={"ENTROPING_TEST_DEEPSEEK_KEY": "test-secret-token"},
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    artifact_dir = Path(str(payload["artifact_dir"]))
    metadata = read_metadata(artifact_dir)
    persisted_stdout = (artifact_dir / "stdout.txt").read_text(encoding="utf-8")
    persisted_stderr = (artifact_dir / "stderr.txt").read_text(encoding="utf-8")
    persisted_metadata = (artifact_dir / "metadata.json").read_text(encoding="utf-8")

    assert metadata["status"] == "failed"
    assert persisted_stdout == ""
    assert "DeepSeek stderr withheld because it contained secret-like content" in (
        persisted_stderr
    )
    assert not (artifact_dir / "response.json").exists()
    assert "abcdefghijklmnopqrstuvwxyz123456" not in persisted_stdout
    assert "abcdefghijklmnopqrstuvwxyz123456" not in persisted_stderr
    assert "abcdefghijklmnopqrstuvwxyz123456" not in persisted_metadata


def test_deepseek_worker_patch_mode_writes_proposal_for_safe_diff(
    tmp_path: Path,
) -> None:
    DeepSeekStubHandler.requests = []
    DeepSeekStubHandler.response_payload = {
        "id": "chatcmpl-test",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": (
                        "Implementation proposal:\n"
                        "```diff\n"
                        "diff --git a/example.py b/example.py\n"
                        "--- a/example.py\n"
                        "+++ b/example.py\n"
                        "@@ -1 +1 @@\n"
                        "-old\n"
                        "+new\n"
                        "```\n"
                    ),
                }
            }
        ],
    }
    server = HTTPServer(("127.0.0.1", 0), DeepSeekStubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        result = run_worker(
            "--mode",
            "patch",
            "--file",
            "README.md",
            "--artifact-root",
            str(tmp_path / "reviews"),
            "--base-url",
            base_url,
            "--api-key-env",
            "ENTROPING_TEST_DEEPSEEK_KEY",
            "--json",
            env={"ENTROPING_TEST_DEEPSEEK_KEY": "test-secret-token"},
        )
    finally:
        DeepSeekStubHandler.response_payload = None
        server.shutdown()
        thread.join(timeout=2)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    artifact_dir = Path(str(payload["artifact_dir"]))
    metadata = read_metadata(artifact_dir)
    raw_output = (artifact_dir / "stdout.txt").read_text(encoding="utf-8")
    proposal = (artifact_dir / "proposal.diff").read_text(encoding="utf-8")

    assert metadata["status"] == "patch-proposed"
    assert "Implementation proposal" in raw_output
    assert proposal.startswith("diff --git a/example.py b/example.py\n")
    assert "```" not in proposal


def test_deepseek_worker_withholds_secret_like_response_payload_without_proposal(
    tmp_path: Path,
) -> None:
    DeepSeekStubHandler.requests = []
    DeepSeekStubHandler.response_payload = {
        "id": "chatcmpl-test",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": (
                        "diff --git a/example.py b/example.py\n"
                        "--- a/example.py\n"
                        "+++ b/example.py\n"
                        "@@ -1 +1 @@\n"
                        "-old\n"
                        "+new\n"
                    ),
                }
            }
        ],
        "provider_debug": {"api_key": "sk-proj-abcdefghijklmnopqrstuvwxyz123456"},
        "usage": {
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "total_tokens": 18,
        },
    }
    server = HTTPServer(("127.0.0.1", 0), DeepSeekStubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        result = run_worker(
            "--mode",
            "patch",
            "--file",
            "README.md",
            "--artifact-root",
            str(tmp_path / "reviews"),
            "--base-url",
            base_url,
            "--api-key-env",
            "ENTROPING_TEST_DEEPSEEK_KEY",
            "--json",
            env={"ENTROPING_TEST_DEEPSEEK_KEY": "test-secret-token"},
        )
    finally:
        DeepSeekStubHandler.response_payload = None
        server.shutdown()
        thread.join(timeout=2)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    artifact_dir = Path(str(payload["artifact_dir"]))
    metadata = read_metadata(artifact_dir)
    persisted_stdout = (artifact_dir / "stdout.txt").read_text(encoding="utf-8")
    persisted_stderr = (artifact_dir / "stderr.txt").read_text(encoding="utf-8")
    persisted_metadata = (artifact_dir / "metadata.json").read_text(encoding="utf-8")

    assert metadata["status"] == "failed"
    assert "DeepSeek response payload withheld because it contained secret-like content" in (
        persisted_stderr
    )
    assert "diff --git a/example.py b/example.py" in persisted_stdout
    assert not (artifact_dir / "proposal.diff").exists()
    assert not (artifact_dir / "response.json").exists()
    assert "sk-proj-abcdefghijklmnopqrstuvwxyz123456" not in persisted_stdout
    assert "sk-proj-abcdefghijklmnopqrstuvwxyz123456" not in persisted_stderr
    assert "sk-proj-abcdefghijklmnopqrstuvwxyz123456" not in persisted_metadata


def test_deepseek_worker_withholds_secret_like_patch_output_without_proposal(
    tmp_path: Path,
) -> None:
    DeepSeekStubHandler.requests = []
    DeepSeekStubHandler.response_payload = {
        "id": "chatcmpl-test",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": (
                        "diff --git a/example.py b/example.py\n"
                        "--- a/example.py\n"
                        "+++ b/example.py\n"
                        "@@ -1 +1 @@\n"
                        '-old = "value"\n'
                        '+api_key = "abcdefghijklmnopqrstuvwxyz123456"\n'
                    ),
                }
            }
        ],
    }
    server = HTTPServer(("127.0.0.1", 0), DeepSeekStubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        result = run_worker(
            "--mode",
            "patch",
            "--file",
            "README.md",
            "--artifact-root",
            str(tmp_path / "reviews"),
            "--base-url",
            base_url,
            "--api-key-env",
            "ENTROPING_TEST_DEEPSEEK_KEY",
            "--json",
            env={"ENTROPING_TEST_DEEPSEEK_KEY": "test-secret-token"},
        )
    finally:
        DeepSeekStubHandler.response_payload = None
        server.shutdown()
        thread.join(timeout=2)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    artifact_dir = Path(str(payload["artifact_dir"]))
    metadata = read_metadata(artifact_dir)
    persisted_stdout = (artifact_dir / "stdout.txt").read_text(encoding="utf-8")
    persisted_metadata = (artifact_dir / "metadata.json").read_text(encoding="utf-8")

    assert metadata["status"] == "failed"
    assert "DeepSeek stdout withheld because it contained secret-like content" in (
        persisted_stdout
    )
    assert not (artifact_dir / "proposal.diff").exists()
    assert not (artifact_dir / "response.json").exists()
    assert "abcdefghijklmnopqrstuvwxyz123456" not in persisted_stdout
    assert "abcdefghijklmnopqrstuvwxyz123456" not in persisted_metadata


def test_deepseek_worker_records_usage_tokens_when_available(
    tmp_path: Path,
) -> None:
    DeepSeekStubHandler.requests = []
    server = HTTPServer(("127.0.0.1", 0), DeepSeekStubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    ledger = (
        Path(".entroping")
        / "factory-metrics"
        / "tests"
        / f"deepseek-live-{uuid.uuid4().hex}.jsonl"
    )
    full_ledger = REPO_ROOT / ledger

    try:
        result = run_worker(
            "--mode",
            "review",
            "--file",
            "README.md",
            "--artifact-root",
            str(tmp_path / "reviews"),
            "--base-url",
            base_url,
            "--api-key-env",
            "ENTROPING_TEST_DEEPSEEK_KEY",
            "--record-factory-metrics",
            "--factory-role",
            "code_review_agent",
            "--factory-metrics-ledger",
            ledger.as_posix(),
            "--json",
            env={"ENTROPING_TEST_DEEPSEEK_KEY": "test-secret-token"},
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    try:
        assert result.returncode == 0, result.stderr
        events = read_metrics_events(full_ledger)
        assert len(events) == 1
        event = events[0]
        metrics = cast(dict[str, object], event["metrics"])
        assert event["event_type"] == "worker_job"
        assert event["outcome"] == "success"
        assert event["decision"] == "needs_review"
        assert metrics["estimated_tokens"] == 18
        ledger_text = full_ledger.read_text(encoding="utf-8")
        assert "Concrete finding" not in ledger_text
        assert "test-secret-token" not in ledger_text
    finally:
        full_ledger.unlink(missing_ok=True)


def test_deepseek_worker_thinking_enabled_adds_reasoning_effort(
    tmp_path: Path,
) -> None:
    DeepSeekStubHandler.requests = []
    server = HTTPServer(("127.0.0.1", 0), DeepSeekStubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        result = run_worker(
            "--mode",
            "review",
            "--file",
            "README.md",
            "--artifact-root",
            str(tmp_path / "reviews"),
            "--base-url",
            base_url,
            "--api-key-env",
            "ENTROPING_TEST_DEEPSEEK_KEY",
            "--thinking",
            "enabled",
            "--reasoning-effort",
            "max",
            "--json",
            env={"ENTROPING_TEST_DEEPSEEK_KEY": "test-secret-token"},
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert result.returncode == 0, result.stderr
    request = DeepSeekStubHandler.requests[0]
    body = cast(dict[str, object], request["body"])

    assert body["thinking"] == {"type": "enabled"}
    assert body["reasoning_effort"] == "max"


def test_deepseek_worker_rejects_file_outside_repo_before_model_call(
    tmp_path: Path,
) -> None:
    outside_file = tmp_path / "outside.py"
    outside_file.write_text("print('secret')\n", encoding="utf-8")

    result = run_worker(
        "--mode",
        "review",
        "--file",
        str(outside_file),
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--api-key-env",
        "ENTROPING_TEST_DEEPSEEK_KEY",
        env={"ENTROPING_TEST_DEEPSEEK_KEY": "test-secret-token"},
    )

    assert result.returncode == 2
    assert "input file must be inside repository" in result.stderr
    assert not (tmp_path / "reviews").exists()


def test_deepseek_worker_rejects_symlink_before_artifact_or_model_call(
    tmp_path: Path,
) -> None:
    repo = make_worker_repo(tmp_path)
    target_file = repo / "target.md"
    target_file.write_text("safe content\n", encoding="utf-8")
    symlink_file = repo / "linked.md"
    try:
        symlink_file.symlink_to(target_file)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    DeepSeekStubHandler.requests = []
    server = HTTPServer(("127.0.0.1", 0), DeepSeekStubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        result = run_worker(
            "--mode",
            "review",
            "--file",
            "linked.md",
            "--artifact-root",
            str(tmp_path / "reviews"),
            "--base-url",
            f"http://127.0.0.1:{server.server_port}",
            "--api-key-env",
            "ENTROPING_TEST_DEEPSEEK_KEY",
            env={"ENTROPING_TEST_DEEPSEEK_KEY": "test-secret-token"},
            cwd=repo,
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert result.returncode == 2
    assert "input path must be a regular non-symlink file" in result.stderr
    assert not (tmp_path / "reviews").exists()
    assert DeepSeekStubHandler.requests == []


@pytest.mark.parametrize(
    "content",
    (
        "OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz123456\n",
        '{"client_secret": "xoxb-abcdefghijklmnopqrstuvwxyz123456"}\n',
    ),
)
def test_deepseek_worker_rejects_secret_like_file_before_artifact_or_model_call(
    tmp_path: Path,
    content: str,
) -> None:
    repo = make_worker_repo(tmp_path)
    secret_file = repo / "notes.md"
    secret_file.write_text(content, encoding="utf-8")
    DeepSeekStubHandler.requests = []
    server = HTTPServer(("127.0.0.1", 0), DeepSeekStubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        result = run_worker(
            "--mode",
            "review",
            "--file",
            "notes.md",
            "--artifact-root",
            str(tmp_path / "reviews"),
            "--base-url",
            f"http://127.0.0.1:{server.server_port}",
            "--api-key-env",
            "ENTROPING_TEST_DEEPSEEK_KEY",
            env={"ENTROPING_TEST_DEEPSEEK_KEY": "test-secret-token"},
            cwd=repo,
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert result.returncode == 2
    assert "refusing to send selected file to DeepSeek" in result.stderr
    assert "secret-like content" in result.stderr
    assert "abcdefghijklmnopqrstuvwxyz123456" not in result.stderr
    assert not (tmp_path / "reviews").exists()
    assert DeepSeekStubHandler.requests == []


@pytest.mark.parametrize(
    "relative_path",
    (
        ".env.backup",
        "secret.env.prod",
        "config/client.key.bak",
        "certs/internal.pem.old",
        "credentials.backup",
    ),
)
def test_deepseek_worker_rejects_sensitive_path_variants_before_model_call(
    tmp_path: Path,
    relative_path: str,
) -> None:
    repo = make_worker_repo(tmp_path)
    sensitive_file = repo / relative_path
    sensitive_file.parent.mkdir(parents=True, exist_ok=True)
    sensitive_file.write_text("placeholder only\n", encoding="utf-8")
    DeepSeekStubHandler.requests = []
    server = HTTPServer(("127.0.0.1", 0), DeepSeekStubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        result = run_worker(
            "--mode",
            "review",
            "--file",
            relative_path,
            "--artifact-root",
            str(tmp_path / "reviews"),
            "--base-url",
            f"http://127.0.0.1:{server.server_port}",
            "--api-key-env",
            "ENTROPING_TEST_DEEPSEEK_KEY",
            env={"ENTROPING_TEST_DEEPSEEK_KEY": "test-secret-token"},
            cwd=repo,
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert result.returncode == 2
    assert "refusing to send selected file to DeepSeek" in result.stderr
    assert "sensitive credential file" in result.stderr
    assert not (tmp_path / "reviews").exists()
    assert DeepSeekStubHandler.requests == []


def test_deepseek_worker_rejects_binary_file_before_artifact_write(
    tmp_path: Path,
) -> None:
    repo = make_worker_repo(tmp_path)
    binary_file = repo / "payload.bin"
    binary_file.write_bytes(b"not-text\x00payload")

    result = run_worker(
        "--mode",
        "review",
        "--file",
        "payload.bin",
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--dry-run",
        cwd=repo,
    )

    assert result.returncode == 2
    assert "binary content" in result.stderr
    assert not (tmp_path / "reviews").exists()


def test_deepseek_worker_rejects_oversized_file_before_artifact_write(
    tmp_path: Path,
) -> None:
    repo = make_worker_repo(tmp_path)
    oversized_file = repo / "large.md"
    oversized_file.write_text("x" * 12, encoding="utf-8")

    result = run_worker(
        "--mode",
        "review",
        "--file",
        "large.md",
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--max-file-bytes",
        "10",
        "--dry-run",
        cwd=repo,
    )

    assert result.returncode == 2
    assert "exceeds --max-file-bytes" in result.stderr
    assert not (tmp_path / "reviews").exists()
