"""Local wheel install smoke evidence harness."""

import json
import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "local_wheel_install_smoke.py"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content.lstrip(), encoding="utf-8")
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
            if len(args) == 3 and args[:2] == ["demo", "--project"]:
                project = Path(args[2])
                project.mkdir(parents=True, exist_ok=True)
                (project / "reports").mkdir(exist_ok=True)
                (project / "reports" / "run-latest.json").write_text(
                    '{"schema_version":"entroping.run-report.v1","status":"passed"}',
                    encoding="utf-8",
                )
                (project / "reports" / "junit.xml").write_text(
                    "<testsuite />\\\\n",
                    encoding="utf-8",
                )
                (project / "reports" / "run-latest.html").write_text(
                    "<html></html>\\\\n",
                    encoding="utf-8",
                )
                print("Entroping demo: passed")
                print("Commands: 2 total, 2 passed, 0 failed, 0 errors, 0 blocked")
                raise SystemExit(0)
            if args == ["architect", "build", "--new", "--tag", "smoke"]:
                Path("tests/generated").mkdir(parents=True, exist_ok=True)
                Path("tests/generated/checkout_smoke.hurl").write_text(
                    "# generated smoke\\\\nGET {{base_url}}/health\\\\nHTTP 200\\\\n",
                    encoding="utf-8",
                )
                print("Generated demo Hurl tests.")
                raise SystemExit(0)
            if args == ["run", "--env", "local", "--tag", "smoke", "--report", "json"]:
                Path("reports").mkdir(exist_ok=True)
                Path("reports/run-latest.json").write_text(
                    '{"schema_version":"entroping.run-report.v1","status":"passed"}',
                    encoding="utf-8",
                )
                print("Hurl run: 1 passed, 0 failed")
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
            if len(args) >= 4 and args[0] == "-c":
                destination = Path(args[2])
                (destination / "tests").mkdir(parents=True, exist_ok=True)
                (destination / "envs").mkdir(parents=True, exist_ok=True)
                (destination / "README.md").write_text("# fake checkout demo\\n", encoding="utf-8")
                (destination / "demo_server.py").write_text(
                    "print('fake demo server should be handled by fake python')\\n",
                    encoding="utf-8",
                )
                (destination / "openapi.yaml").write_text("openapi: 3.1.0\\n", encoding="utf-8")
                (destination / "qanstitution.yaml").write_text(
                    "project: fake\\nversion: '4.1'\\ngates: []\\n",
                    encoding="utf-8",
                )
                (destination / "tests" / "checkout_smoke.hurl").write_text(
                    "GET http://127.0.0.1:18080/health\\nHTTP 200\\n",
                    encoding="utf-8",
                )
                print(f"Copied fixture to {destination}")
                raise SystemExit(0)
            if args and args[0].endswith("demo_server.py"):
                from http.server import BaseHTTPRequestHandler, HTTPServer

                port = int(args[args.index("--port") + 1])

                class Handler(BaseHTTPRequestHandler):
                    def do_GET(self) -> None:
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(b'{"status":"ok"}')

                    def do_POST(self) -> None:
                        self.send_response(201)
                        self.end_headers()
                        self.wfile.write(b'{"id":"demo","status":"accepted"}')

                    def log_message(self, *_: object) -> None:
                        return

                HTTPServer(("127.0.0.1", port), Handler).serve_forever()
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


def _python_only_path() -> str:
    return os.pathsep.join((str(Path(sys.executable).parent), "/usr/bin", "/bin"))


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
    assert "entroping demo --project <temp-root>/demo" in commands


def test_local_wheel_install_smoke_runs_with_fake_installer(tmp_path: Path) -> None:
    fake_python = tmp_path / "python"
    fake_uv = tmp_path / "uv"
    _write_fake_python(fake_python)
    _write_fake_uv(fake_uv)
    fake_wheel = tmp_path / "entroping-0.1.1-py3-none-any.whl"
    fake_wheel.write_text("fake wheel", encoding="utf-8")
    artifact_dir = tmp_path / "artifacts"
    env = os.environ.copy()
    env["PATH"] = _python_only_path()

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
        env=env,
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
        "installed demo smoke skipped",
    ]
    assert "Hurl is not available on PATH" in payload["commands"][-1]["stdout"]
    evidence_path = artifact_dir / "local-wheel-install-smoke-evidence.json"
    assert evidence_path.is_file()
    assert json.loads(evidence_path.read_text(encoding="utf-8"))["status"] == "pass"


def test_local_wheel_install_smoke_runs_demo_path_with_installed_cli(
    tmp_path: Path,
) -> None:
    fake_python = tmp_path / "python"
    fake_uv = tmp_path / "uv"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_fake_python(fake_python)
    _write_fake_uv(fake_uv)
    _write_executable(fake_bin / "hurl", "#!/usr/bin/env bash\necho hurl 8.0.1\n")
    fake_wheel = tmp_path / "entroping-0.1.1-py3-none-any.whl"
    fake_wheel.write_text("fake wheel", encoding="utf-8")
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join((str(fake_bin), _python_only_path()))
    env["ENTROPING_DEMO_PORT"] = "18180"

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
        env=env,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    assert [command["name"] for command in payload["commands"]] == [
        "create virtual environment",
        "install wheel offline",
        "entroping --version",
        "entroping init --minimal",
        "entroping doctor",
        "entroping demo",
    ]
    assert "Entroping demo: passed" in payload["commands"][-1]["stdout"]


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
