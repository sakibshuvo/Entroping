"""Tests for committed AI artifact and sensitive-context hygiene."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "ai_artifact_hygiene.py"
DOC_GOVERNANCE_SCRIPT = REPO_ROOT / "scripts" / "doc_governance_check.sh"
REPO_HYGIENE_SCRIPT = REPO_ROOT / "scripts" / "repo_hygiene.sh"


def run_ai_artifact_hygiene(*args: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT), *args],
        check=False,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init"], check=True, cwd=path, capture_output=True, text=True)


def _track(path: Path, *relative_paths: str) -> None:
    subprocess.run(
        ["git", "add", *relative_paths],
        check=True,
        cwd=path,
        capture_output=True,
        text=True,
    )


def test_ai_artifact_hygiene_passes_current_repo() -> None:
    result = run_ai_artifact_hygiene()

    assert result.returncode == 0, result.stderr
    assert "AI artifact hygiene OK" in result.stdout


def test_ai_artifact_hygiene_rejects_tracked_generated_artifact_paths(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    artifact = tmp_path / ".entroping" / "ai-reviews" / "run-1" / "prompt.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("worker prompt\n", encoding="utf-8")
    _track(tmp_path, ".entroping/ai-reviews/run-1/prompt.md")

    result = run_ai_artifact_hygiene("--root", str(tmp_path))

    assert result.returncode == 1
    assert "AI artifact hygiene failed" in result.stderr
    assert ".entroping/ai-reviews/run-1/prompt.md" in result.stderr
    assert "tracked generated artifact path" in result.stderr


def test_ai_artifact_hygiene_rejects_docs_only_local_state_paths(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    ds_store = tmp_path / ".DS_Store"
    obsidian = tmp_path / ".obsidian" / "workspace.json"
    ds_store.write_text("machine state\n", encoding="utf-8")
    obsidian.parent.mkdir()
    obsidian.write_text('{"workspace":true}\n', encoding="utf-8")
    _track(tmp_path, ".DS_Store", ".obsidian/workspace.json")

    result = run_ai_artifact_hygiene("--root", str(tmp_path))

    assert result.returncode == 1
    assert ".DS_Store: tracked local machine state path" in result.stderr
    assert ".obsidian/workspace.json: tracked local machine state path" in result.stderr


def test_ai_artifact_hygiene_rejects_prompt_response_and_traffic_leaks(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Leak\n"
        "prompt: full provider request copied from the worker run\n"
        "stdout: Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456\n"
        "Cookie: sessionid=abcdef1234567890\n"
        "request_body: {\"password\":\"raw-secret-value\"}\n"
        "{\"choices\":[{\"message\":{\"content\":\"raw model output\"}}],"
        "\"usage\":{\"prompt_tokens\":123}}\n",
        encoding="utf-8",
    )
    _track(tmp_path, "README.md")

    result = run_ai_artifact_hygiene("--root", str(tmp_path))

    assert result.returncode == 1
    assert "raw prompt/stdout/stderr marker" in result.stderr
    assert "secret-like content" in result.stderr
    assert "cookie header" in result.stderr
    assert "raw request/response body marker" in result.stderr
    assert "provider response dump" in result.stderr


def test_ai_artifact_hygiene_rejects_non_openai_provider_dumps(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    anthropic = tmp_path / "docs" / "anthropic-response.json"
    gemini = tmp_path / "docs" / "gemini-response.json"
    anthropic.parent.mkdir(parents=True)
    anthropic.write_text(
        '{"model":"claude-example","content":[{"type":"text","text":"raw"}],'
        '"usage":{"input_tokens":1,"output_tokens":1}}\n',
        encoding="utf-8",
    )
    gemini.write_text(
        '{"candidates":[{"content":{"parts":[{"text":"raw"}]}}],'
        '"usageMetadata":{"promptTokenCount":1}}\n',
        encoding="utf-8",
    )
    _track(tmp_path, "docs/anthropic-response.json", "docs/gemini-response.json")

    result = run_ai_artifact_hygiene("--root", str(tmp_path))

    assert result.returncode == 1
    assert result.stderr.count("provider response dump") == 2


def test_ai_artifact_hygiene_scans_new_root_level_docs(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    contributing = tmp_path / "CONTRIBUTING.md"
    contributing.write_text(
        "# Contributing\n"
        "stdout: copied worker output should not be committed\n",
        encoding="utf-8",
    )
    _track(tmp_path, "CONTRIBUTING.md")

    result = run_ai_artifact_hygiene("--root", str(tmp_path))

    assert result.returncode == 1
    assert "CONTRIBUTING.md:2: raw prompt/stdout/stderr marker" in result.stderr


def test_ai_artifact_hygiene_scans_nested_text_bearing_files(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    source = tmp_path / "src" / "worker.py"
    source.parent.mkdir()
    provider_token = "".join(("sk-proj-", "abcdefghijklmnopqrstuvwxyz123456"))
    source.write_text(
        f"# {provider_token}\n",
        encoding="utf-8",
    )
    _track(tmp_path, "src/worker.py")

    result = run_ai_artifact_hygiene("--root", str(tmp_path))

    assert result.returncode == 1
    assert "src/worker.py:1: secret-like content (provider token)" in result.stderr


def test_ai_artifact_hygiene_allow_marker_does_not_hide_leaks(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Leak\n"
        "Cookie: sessionid=abcdef1234567890 <!-- ai-artifact-hygiene: allow -->\n",
        encoding="utf-8",
    )
    _track(tmp_path, "README.md")

    result = run_ai_artifact_hygiene("--root", str(tmp_path))

    assert result.returncode == 1
    assert "cookie header" in result.stderr


def test_ai_artifact_hygiene_allows_placeholder_credentials_but_not_same_line_secret(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Placeholder\n"
        'api_key="{{api_key}}"\n'
        'password="{{user_password}}"\n'
        "export ENTROPING_OMLX_API_KEY=\"local-placeholder\"\n"
        "token=<redacted>\n"
        'api_key="{{api_key}}" token=abcdefghijklmnopqrstuvwxyz123456\n',
        encoding="utf-8",
    )
    _track(tmp_path, "README.md")

    result = run_ai_artifact_hygiene("--root", str(tmp_path))

    assert result.returncode == 1
    assert "README.md:6: secret-like content" in result.stderr
    assert "README.md:2" not in result.stderr
    assert "README.md:3" not in result.stderr
    assert "README.md:4" not in result.stderr
    assert "README.md:5" not in result.stderr


def test_ai_artifact_hygiene_allows_placeholder_cookie_headers(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Placeholder cookies\n"
        "Set-Cookie: session=<PLACEHOLDER>\n"
        "Cookie: sessionid=<cookie_token_here>\n",
        encoding="utf-8",
    )
    _track(tmp_path, "README.md")

    result = run_ai_artifact_hygiene("--root", str(tmp_path))

    assert result.returncode == 0, result.stderr


def test_ai_artifact_hygiene_allows_guardrail_language_and_redacted_examples(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    docs = tmp_path / "docs" / "meta" / "AGENT_CONTROL_PLANE.md"
    docs.parent.mkdir(parents=True)
    docs.write_text(
        "# Guardrails\n"
        "Do not store prompt transcripts, provider responses, raw stdout/stderr, "
        "cookies, raw traffic, request bodies, or response bodies in Git.\n"
        "Safe examples use Authorization: Bearer {{token}}, "
        "Cookie: sessionid={{session_id}}, and token=<redacted>.\n",
        encoding="utf-8",
    )
    _track(tmp_path, "docs/meta/AGENT_CONTROL_PLANE.md")

    result = run_ai_artifact_hygiene("--root", str(tmp_path))

    assert result.returncode == 0, result.stderr
    assert "AI artifact hygiene OK" in result.stdout


def test_ai_artifact_hygiene_allows_test_fixture_boundaries(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    fixture = tmp_path / "tests" / "test_redaction_fixture.py"
    fixture.parent.mkdir()
    fixture.write_text(
        "def test_fixture() -> None:\n"
        "    assert 'Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456'\n"
        "    assert 'Cookie: sessionid=abcdef1234567890'\n"
        "    assert {'choices': [{'message': {'content': 'ok'}}]}\n",
        encoding="utf-8",
    )
    _track(tmp_path, "tests/test_redaction_fixture.py")

    result = run_ai_artifact_hygiene("--root", str(tmp_path))

    assert result.returncode == 0, result.stderr


def test_ai_artifact_hygiene_is_wired_into_repo_and_docs_gates() -> None:
    repo_hygiene = REPO_HYGIENE_SCRIPT.read_text(encoding="utf-8")
    doc_governance = DOC_GOVERNANCE_SCRIPT.read_text(encoding="utf-8")

    assert "scripts/ai_artifact_hygiene.py" in repo_hygiene
    assert "scripts/ai_artifact_hygiene.py" in doc_governance
