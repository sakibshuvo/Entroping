"""Local wheel install smoke evidence harness."""

import json
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "local_wheel_install_smoke.py"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _write_fake_python(path: Path) -> None:
    _write_executable(
        path,
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            from __future__ import annotations

            import sys
            from pathlib import Path


            ENTROPING_SCRIPT = '''#!/usr/bin/env python3
            from __future__ import annotations

            import sys
            from pathlib import Path

            args = sys.argv[1:]
            if args == ["--version"]:
                print("entroping 0.1.1")
                raise SystemExit(0)
            if args == ["init", "--minimal"]:
                Path("tests").mkdir(exist_ok=True)
                Path("envs").mkdir(exist_ok=True)
                Path(".entroping").mkdir(exist_ok=True)
                Path("qanstitution.yaml").write_text(
                    "project: fake\\\\nversion: '4.1'\\\\ngates: []\\\\n",
                    encoding="utf-8",
                )
                print("Initialized Entroping project structure.")
                raise SystemExit(0)
            if args == ["doctor"]:
                if not Path("qanstitution.yaml").is_file():
                    print("QAnstitution: not found", file=sys.stderr)
                    raise SystemExit(1)
                print("QAnstitution: valid")
                raise SystemExit(0)
            print(f"unexpected entroping args: {args}", file=sys.stderr)
            raise SystemExit(2)
            '''


            args = sys.argv[1:]
            if len(args) == 3 and args[:2] == ["-m", "venv"]:
                venv = Path(args[2])
                bin_dir = venv / "bin"
                bin_dir.mkdir(parents=True, exist_ok=True)
                python_path = bin_dir / "python"
                python_path.write_text(Path(__file__).read_text(encoding="utf-8"), encoding="utf-8")
                python_path.chmod(python_path.stat().st_mode | 0o100)
                entroping_path = bin_dir / "entroping"
                entroping_path.write_text(ENTROPING_SCRIPT, encoding="utf-8")
                entroping_path.chmod(entroping_path.stat().st_mode | 0o100)
                raise SystemExit(0)
            print(f"unexpected fake python args: {args}", file=sys.stderr)
            raise SystemExit(2)
            """
        ),
    )


def _write_fake_uv(path: Path) -> None:
    _write_executable(
        path,
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            from __future__ import annotations

            import sys

            args = sys.argv[1:]
            if args[:2] == ["pip", "install"] and "--offline" in args:
                print("fake uv installed wheel offline")
                raise SystemExit(0)
            print(f"unexpected fake uv args: {args}", file=sys.stderr)
            raise SystemExit(2)
            """
        ),
    )


def run_local_wheel_smoke(
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )


def test_local_wheel_install_smoke_json_dry_run_describes_public_cli() -> None:
    result = run_local_wheel_smoke("--dry-run", "--format", "json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    commands = "\n".join(command["command"] for command in payload["commands"])
    assert payload["schema_version"] == "entroping.local-wheel-install-smoke.v1"
    assert payload["status"] == "planned"
    assert payload["stable_core_ready"] is False
    assert payload["uses_public_cli"] is True
    assert payload["requires_package_index"] is False
    assert "scripts/package_check.sh" in commands
    assert "entroping --version" in commands
    assert "entroping init --minimal" in commands
    assert "entroping doctor" in commands


def test_local_wheel_install_smoke_runs_with_fake_installer(tmp_path: Path) -> None:
    fake_python = tmp_path / "python"
    fake_uv = tmp_path / "uv"
    _write_fake_python(fake_python)
    _write_fake_uv(fake_uv)
    fake_wheel = tmp_path / "entroping-0.1.1-py3-none-any.whl"
    fake_wheel.write_text("fake wheel", encoding="utf-8")
    artifact_dir = tmp_path / "artifacts"

    result = run_local_wheel_smoke(
        "--format",
        "json",
        "--skip-build",
        "--wheel",
        str(fake_wheel),
        "--python",
        str(fake_python),
        "--uv-bin",
        str(fake_uv),
        "--artifact-dir",
        str(artifact_dir),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    assert payload["stable_core_ready"] is False
    assert payload["uses_public_cli"] is True
    assert payload["requires_package_index"] is False
    assert payload["wheel"] == str(fake_wheel)
    assert payload["workdir_preserved"] is False
    assert [command["name"] for command in payload["commands"]] == [
        "create virtual environment",
        "install wheel offline",
        "entroping --version",
        "entroping init --minimal",
        "entroping doctor",
    ]
    evidence_path = artifact_dir / "local-wheel-install-smoke-evidence.json"
    assert evidence_path.is_file()
    assert json.loads(evidence_path.read_text(encoding="utf-8"))["status"] == "pass"


def test_local_wheel_install_smoke_reports_missing_wheel(tmp_path: Path) -> None:
    fake_python = tmp_path / "python"
    fake_uv = tmp_path / "uv"
    _write_fake_python(fake_python)
    _write_fake_uv(fake_uv)
    missing_wheel = tmp_path / "missing.whl"

    result = run_local_wheel_smoke(
        "--format",
        "json",
        "--skip-build",
        "--wheel",
        str(missing_wheel),
        "--python",
        str(fake_python),
        "--uv-bin",
        str(fake_uv),
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "fail"
    assert "Wheel artifact not found" in payload["failure"]
    assert "local wheel install smoke failed" in result.stderr
