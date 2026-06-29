from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "script_safety.py"


def _script_safety_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("script_safety", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCRIPT_SAFETY = _script_safety_module()
ScriptSafetyError = SCRIPT_SAFETY.ScriptSafetyError
read_json_file = SCRIPT_SAFETY.read_json_file
read_text_file = SCRIPT_SAFETY.read_text_file
run_subprocess = SCRIPT_SAFETY.run_subprocess
write_json_file = SCRIPT_SAFETY.write_json_file
write_text_file = SCRIPT_SAFETY.write_text_file


def test_run_subprocess_bounds_command_output() -> None:
    completed = run_subprocess(
        [
            sys.executable,
            "-c",
            "import sys; print('stdout' * 2000); print('stderr' * 2000, file=sys.stderr)",
        ],
        max_output_bytes=40,
    )

    assert completed.returncode == 0
    assert len(completed.stdout) <= 40
    assert len(completed.stderr) <= 40


def test_run_subprocess_rejects_non_positive_output_limit() -> None:
    with pytest.raises(ScriptSafetyError, match="max_output_bytes must be positive"):
        run_subprocess([sys.executable, "-c", "print('ok')"], max_output_bytes=0)


def test_run_subprocess_can_use_explicit_environment_only() -> None:
    completed = run_subprocess(
        [
            sys.executable,
            "-c",
            "import os; print(os.environ.get('SCRIPT_SAFETY_TEST', 'missing'))",
        ],
        inherit_env=False,
        env={"SCRIPT_SAFETY_TEST": "present"},
    )

    assert completed.stdout.strip() == "present"


def test_run_subprocess_raises_when_check_enabled_for_failure() -> None:
    with pytest.raises(ScriptSafetyError, match="command failed with exit code 5"):
        run_subprocess(
            [sys.executable, "-c", "import sys; sys.exit(5)"],
            check=True,
        )


def test_run_subprocess_treats_timeout_as_safety_error() -> None:
    with pytest.raises(
        ScriptSafetyError,
        match="command timed out after 0.05 seconds",
    ):
        run_subprocess(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            timeout=0.05,
        )


def test_read_and_write_text_files_are_bounded_and_safe(tmp_path: Path) -> None:
    json_path = write_json_file(
        Path("reports") / "report.json",
        {"status": "ok"},
        artifact="quality hotspot report",
        root=tmp_path,
    )
    assert json_path == (tmp_path / "reports" / "report.json").resolve()
    assert json.loads(json_path.read_text(encoding="utf-8")) == {"status": "ok"}

    text = read_text_file(json_path)
    assert text.startswith("{")

    payload = read_json_file(json_path)
    assert payload == {"status": "ok"}


def test_read_text_file_rejects_invalid_utf8(tmp_path: Path) -> None:
    bad = tmp_path / "bad.txt"
    bad.write_bytes(b"\xff\xfe")

    with pytest.raises(ScriptSafetyError, match="not valid UTF-8"):
        read_text_file(bad)


def test_read_text_file_can_replace_invalid_utf8(tmp_path: Path) -> None:
    bad = tmp_path / "bad.txt"
    bad.write_bytes(b"\xff\xfe")

    assert read_text_file(bad, errors="replace") == "\ufffd\ufffd"


def test_write_text_file_rejects_forbidden_artifact_path(tmp_path: Path) -> None:
    with pytest.raises(ScriptSafetyError, match="must not be written into .entroping"):
        write_text_file(
            Path(".entroping/report.txt"),
            "value",
            artifact="unsafe artifact",
            root=tmp_path,
        )


def test_write_json_file_wraps_serialization_errors(tmp_path: Path) -> None:
    with pytest.raises(ScriptSafetyError, match="could not serialize report JSON"):
        write_json_file(
            Path("reports") / "report.json",
            {"bad": object()},
            artifact="report",
            root=tmp_path,
        )
