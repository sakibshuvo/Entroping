"""Tests for the bounded direct DeepSeek API worker harness."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import ClassVar, cast

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


class DeepSeekStubHandler(BaseHTTPRequestHandler):
    """Tiny local OpenAI-compatible endpoint for direct-worker tests."""

    requests: ClassVar[list[dict[str, object]]] = []

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
        response = {
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
    prompt = (artifact_dir / "prompt.md").read_text(encoding="utf-8")
    assert "Codex remains the integrator" in prompt
    assert str(target_file.resolve()) in prompt
    assert not (artifact_dir / "stdout.txt").exists()
    assert "secret" not in (artifact_dir / "metadata.json").read_text(encoding="utf-8")


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
    assert body["thinking"] == {"type": "enabled"}
    assert body["reasoning_effort"] == "high"
    assert "messages" in body
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
