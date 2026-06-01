"""Regression tests for the no-Hurl CLI smoke script."""

import os
import shlex
import shutil
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "cli_smoke.sh"
SYSTEM_SHELL_PATH = os.pathsep.join(("/usr/bin", "/bin", "/usr/sbin", "/sbin"))


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _write_uv_wrapper(path: Path) -> None:
    uv_path = shutil.which("uv")
    assert uv_path is not None, "uv must be installed to run the CLI smoke script"
    _write_executable(
        path,
        f"#!/usr/bin/env bash\nexec {shlex.quote(uv_path)} \"$@\"\n",
    )


def test_cli_smoke_script_runs_without_hurl_available(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_uv_wrapper(fake_bin / "uv")

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{SYSTEM_SHELL_PATH}"

    result = subprocess.run(
        ["/bin/bash", "scripts/cli_smoke.sh"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert "[entroping-cli-smoke] entroping --help" in result.stdout
    assert "[entroping-cli-smoke] entroping --version" in result.stdout
    assert "[entroping-cli-smoke] entroping init --minimal" in result.stdout
    assert "[entroping-cli-smoke] entroping doctor" in result.stdout
    assert "Hurl:" in result.stdout
    assert "not found" in result.stdout
    assert "Missing Hurl is acceptable for this no-Hurl smoke." in result.stdout
    assert "QAnstitution:" in result.stdout
    assert "valid" in result.stdout


def test_cli_smoke_script_does_not_confuse_traffic_state_with_missing_hurl(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_uv_wrapper(fake_bin / "uv")
    _write_executable(fake_bin / "hurl", "#!/usr/bin/env bash\nexit 99\n")
    _write_executable(fake_bin / "hurlfmt", "#!/usr/bin/env bash\nexit 99\n")

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{SYSTEM_SHELL_PATH}"

    result = subprocess.run(
        ["/bin/bash", "scripts/cli_smoke.sh"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Hurl: found" in result.stdout
    assert "Traffic state:" in result.stdout
    assert "not found" in result.stdout
    assert "Hurl is installed; smoke still avoided runtime execution." in result.stdout
    assert "Missing Hurl is acceptable for this no-Hurl smoke." not in result.stdout


def test_test_strategy_positions_cli_smoke_against_heavier_gates() -> None:
    strategy = (REPO_ROOT / "docs" / "meta" / "TEST_STRATEGY.md").read_text(
        encoding="utf-8"
    )

    assert "scripts/cli_smoke.sh" in strategy
    assert "without requiring Hurl" in strategy
    assert "scripts/check.sh" in strategy
    assert "scripts/feature_gate.sh" in strategy
    assert "scripts/live_demo_smoke.sh" in strategy
