#!/usr/bin/env python3
"""Install the built Entroping wheel into a fresh venv and run public CLI smoke."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

SCHEMA_VERSION = "entroping.local-wheel-install-smoke.v1"
EVIDENCE_NAME = "local-wheel-install-smoke-evidence.json"
OUTPUT_LIMIT = 4000
DEMO_FIXTURE_ID: Final = "checkout-api"
DEMO_PORT_ENV: Final = "ENTROPING_DEMO_PORT"
DEFAULT_DEMO_PORT: Final = 18080
COPY_DEMO_FIXTURE_CODE: Final = """
from pathlib import Path
import sys
from entroping.core.demo_fixtures import copy_demo_fixture

destination = Path(sys.argv[1])
source_examples_root = Path(sys.argv[2])
fixture_id = sys.argv[3]
copy_demo_fixture(
    fixture_id,
    destination,
    source_examples_root=source_examples_root,
)
print(f"Copied {fixture_id} demo fixture to {destination}")
"""


@dataclass(frozen=True)
class CommandEvidence:
    name: str
    command: str
    cwd: str
    exit_code: int | None
    stdout: str
    stderr: str


class SmokeError(Exception):
    """Local wheel smoke failure with command evidence."""

    def __init__(
        self,
        message: str,
        commands: Sequence[CommandEvidence] = (),
    ) -> None:
        super().__init__(message)
        self.commands = tuple(commands)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install the built wheel in a temporary venv and run public CLI smoke."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Entroping repository root.",
    )
    parser.add_argument(
        "--wheel",
        type=Path,
        default=None,
        help="Wheel artifact to install. Defaults to dist/<name>-<version>-py3-none-any.whl.",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=None,
        help="Optional directory where machine-readable smoke evidence is written.",
    )
    parser.add_argument(
        "--format",
        choices=("md", "json"),
        default="md",
        help="Output format.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned evidence without building, installing, or creating temp files.",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Reuse existing dist/ artifacts instead of running scripts/package_check.sh first.",
    )
    parser.add_argument(
        "--keep-workdir",
        action="store_true",
        help="Keep the temporary venv and project directory for inspection.",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python interpreter used to create the temporary virtual environment.",
    )
    parser.add_argument(
        "--uv-bin",
        default="uv",
        help="uv executable used for offline wheel installation into the temporary venv.",
    )
    args = parser.parse_args()

    repo_root = args.root.expanduser().resolve()
    if args.dry_run:
        planned_payload = _planned_payload(skip_build=args.skip_build)
        _print_payload(planned_payload, args.format)
        return 0

    temp_root: Path | None = None
    commands: list[CommandEvidence] = []
    payload: dict[str, object]
    try:
        if not repo_root.is_dir():
            msg = f"Repository root not found: {repo_root}"
            raise SmokeError(msg)
        python_bin = _resolve_executable(args.python)
        uv_bin = _resolve_executable(args.uv_bin)
        if not args.skip_build:
            _run_and_record(
                commands,
                name="build package artifacts",
                argv=(str(repo_root / "scripts" / "package_check.sh"),),
                cwd=repo_root,
                display="scripts/package_check.sh",
                timeout=180,
            )
        wheel = _resolve_wheel(repo_root, args.wheel)
        temp_root = Path(tempfile.mkdtemp(prefix="entroping-local-wheel-smoke-")).resolve()
        venv_dir = temp_root / "venv"
        project_dir = temp_root / "project"
        project_dir.mkdir()
        venv_python = _venv_python(venv_dir)
        entroping_bin = _venv_executable(venv_dir, "entroping")

        _run_and_record(
            commands,
            name="create virtual environment",
            argv=(python_bin, "-m", "venv", str(venv_dir)),
            cwd=temp_root,
            display="<python> -m venv <temp-root>/venv",
            timeout=90,
        )
        _run_and_record(
            commands,
            name="install wheel offline",
            argv=(
                uv_bin,
                "pip",
                "install",
                "--offline",
                "--python",
                str(venv_python),
                str(wheel),
            ),
            cwd=temp_root,
            display="uv pip install --offline --python <venv-python> <wheel>",
            timeout=180,
        )
        _run_and_record(
            commands,
            name="entroping --version",
            argv=(str(entroping_bin), "--version"),
            cwd=project_dir,
            display="entroping --version",
        )
        _run_and_record(
            commands,
            name="entroping init --minimal",
            argv=(str(entroping_bin), "init", "--minimal"),
            cwd=project_dir,
            display="entroping init --minimal",
        )
        _run_and_record(
            commands,
            name="entroping doctor",
            argv=(str(entroping_bin), "doctor"),
            cwd=project_dir,
            display="entroping doctor",
        )
        _run_installed_demo_smoke(
            commands,
            repo_root=repo_root,
            temp_root=temp_root,
            venv_python=venv_python,
            entroping_bin=entroping_bin,
        )
        payload = _result_payload(
            status="pass",
            wheel=wheel,
            temp_root=temp_root,
            project_dir=project_dir,
            commands=commands,
            workdir_preserved=args.keep_workdir,
            artifact_dir=args.artifact_dir,
            failure="",
        )
        _write_evidence(payload, args.artifact_dir)
    except (OSError, SmokeError, subprocess.TimeoutExpired, ValueError) as exc:
        if isinstance(exc, SmokeError):
            commands = list(exc.commands) if exc.commands else commands
        payload = _error_payload(str(exc), commands)
        _write_evidence(payload, args.artifact_dir)
        _print_payload(payload, args.format)
        print(f"local wheel install smoke failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if temp_root is not None and not args.keep_workdir:
            shutil.rmtree(temp_root, ignore_errors=True)

    _print_payload(payload, args.format)
    return 0


def _planned_payload(*, skip_build: bool) -> dict[str, object]:
    commands = []
    if not skip_build:
        commands.append(_planned_command("build package artifacts", "scripts/package_check.sh"))
    commands.extend(
        [
            _planned_command("create virtual environment", "<python> -m venv <temp-root>/venv"),
            _planned_command(
                "install wheel offline",
                "uv pip install --offline --python <venv-python> <wheel>",
            ),
            _planned_command("entroping --version", "entroping --version"),
            _planned_command("entroping init --minimal", "entroping init --minimal"),
            _planned_command("entroping doctor", "entroping doctor"),
            _planned_command(
                "copy demo fixture",
                "copy demo fixture through installed package",
            ),
            _planned_command(
                "entroping architect build demo",
                "entroping architect build --new --tag smoke",
            ),
            _planned_command(
                "entroping run demo",
                "entroping run --env local --tag smoke --report json",
            ),
        ]
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "planned",
        "stable_core_ready": False,
        "uses_public_cli": True,
        "requires_package_index": False,
        "wheel": "",
        "temporary_root": "",
        "project_path": "",
        "workdir_preserved": False,
        "commands": commands,
        "artifacts": [],
        "failure": "",
    }


def _planned_command(name: str, command: str) -> dict[str, object]:
    return {
        "name": name,
        "command": command,
        "cwd": "",
        "exit_code": None,
        "stdout": "",
        "stderr": "",
    }


def _result_payload(
    *,
    status: str,
    wheel: Path,
    temp_root: Path,
    project_dir: Path,
    commands: Sequence[CommandEvidence],
    workdir_preserved: bool,
    artifact_dir: Path | None,
    failure: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "stable_core_ready": False,
        "uses_public_cli": True,
        "requires_package_index": False,
        "wheel": str(wheel),
        "temporary_root": str(temp_root),
        "project_path": str(project_dir),
        "workdir_preserved": workdir_preserved,
        "commands": [asdict(command) for command in commands],
        "artifacts": [EVIDENCE_NAME] if artifact_dir is not None else [],
        "failure": failure,
    }


def _error_payload(failure: str, commands: Sequence[CommandEvidence]) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "fail",
        "stable_core_ready": False,
        "uses_public_cli": True,
        "requires_package_index": False,
        "wheel": "",
        "temporary_root": "",
        "project_path": "",
        "workdir_preserved": False,
        "commands": [asdict(command) for command in commands],
        "artifacts": [],
        "failure": _bounded(failure),
    }


def _resolve_executable(value: str) -> str:
    candidate = Path(value).expanduser()
    if candidate.is_absolute() or os.sep in value:
        resolved = candidate.resolve()
        if not resolved.is_file():
            msg = f"Executable not found: {value}"
            raise SmokeError(msg)
        return str(resolved)
    found = shutil.which(value)
    if found is None:
        msg = f"Executable not found on PATH: {value}"
        raise SmokeError(msg)
    return found


def _resolve_wheel(repo_root: Path, requested: Path | None) -> Path:
    candidate = requested.expanduser() if requested is not None else _expected_wheel(repo_root)
    if requested is not None and not candidate.is_absolute():
        candidate = repo_root / candidate
    if candidate.suffix != ".whl":
        msg = f"Expected a .whl artifact, got: {candidate}"
        raise SmokeError(msg)
    if not candidate.is_file():
        msg = f"Wheel artifact not found: {candidate}"
        raise SmokeError(msg)
    return candidate.resolve(strict=True)


def _expected_wheel(repo_root: Path) -> Path:
    pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]
    name = str(project["name"])
    version = str(project["version"])
    return repo_root / "dist" / f"{name}-{version}-py3-none-any.whl"


def _venv_bin_dir(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts" if os.name == "nt" else "bin")


def _venv_python(venv_dir: Path) -> Path:
    return _venv_bin_dir(venv_dir) / ("python.exe" if os.name == "nt" else "python")


def _venv_executable(venv_dir: Path, name: str) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    return _venv_bin_dir(venv_dir) / f"{name}{suffix}"


def _run_installed_demo_smoke(
    commands: list[CommandEvidence],
    *,
    repo_root: Path,
    temp_root: Path,
    venv_python: Path,
    entroping_bin: Path,
) -> None:
    if shutil.which("hurl") is None:
        commands.append(
            CommandEvidence(
                name="installed demo smoke skipped",
                command="entroping demo fixture smoke",
                cwd=str(temp_root),
                exit_code=None,
                stdout=(
                    "Skipped installed demo smoke because Hurl is not available on PATH. "
                    "Install Hurl, then rerun this smoke to execute the demo path."
                ),
                stderr="",
            )
        )
        return

    demo_port = _demo_port_from_env()
    demo_dir = temp_root / "demo"
    _run_and_record(
        commands,
        name="copy demo fixture",
        argv=(
            str(venv_python),
            "-c",
            COPY_DEMO_FIXTURE_CODE,
            str(demo_dir),
            str(repo_root / "examples"),
            DEMO_FIXTURE_ID,
        ),
        cwd=temp_root,
        display="copy demo fixture through installed package",
    )

    server = subprocess.Popen(
        [str(venv_python), str(demo_dir / "demo_server.py"), "--port", str(demo_port)],
        cwd=demo_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        _wait_for_demo_server(server, demo_port)
        _run_and_record(
            commands,
            name="entroping architect build demo",
            argv=(str(entroping_bin), "architect", "build", "--new", "--tag", "smoke"),
            cwd=demo_dir,
            display="entroping architect build --new --tag smoke",
            timeout=120,
        )
        env_dir = demo_dir / "envs"
        env_dir.mkdir(exist_ok=True)
        (env_dir / "local.env").write_text(
            f"base_url=http://127.0.0.1:{demo_port}\ncart_id=demo-cart-001\n",
            encoding="utf-8",
        )
        _run_and_record(
            commands,
            name="entroping run demo",
            argv=(
                str(entroping_bin),
                "run",
                "--env",
                "local",
                "--tag",
                "smoke",
                "--report",
                "json",
            ),
            cwd=demo_dir,
            display="entroping run --env local --tag smoke --report json",
            timeout=120,
        )
    finally:
        _stop_process(server)


def _demo_port_from_env() -> int:
    raw = os.environ.get(DEMO_PORT_ENV, str(DEFAULT_DEMO_PORT))
    try:
        port = int(raw)
    except ValueError as exc:
        msg = f"{DEMO_PORT_ENV} must be an integer port, got: {raw}"
        raise SmokeError(msg) from exc
    if port < 1 or port > 65535:
        msg = f"{DEMO_PORT_ENV} must be between 1 and 65535, got: {port}"
        raise SmokeError(msg)
    return port


def _wait_for_demo_server(server: subprocess.Popen[str], port: int) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if server.poll() is not None:
            msg = f"Demo server exited before readiness on port {port}"
            raise SmokeError(msg)
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    msg = f"Demo server did not become ready on port {port}"
    raise SmokeError(msg)


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _run_and_record(
    commands: list[CommandEvidence],
    *,
    name: str,
    argv: Sequence[str],
    cwd: Path,
    display: str,
    timeout: int = 60,
) -> None:
    try:
        commands.append(
            _run_step(
                name=name,
                argv=argv,
                cwd=cwd,
                display=display,
                timeout=timeout,
            )
        )
    except SmokeError as exc:
        commands.extend(exc.commands)
        raise SmokeError(str(exc), tuple(commands)) from exc


def _run_step(
    *,
    name: str,
    argv: Sequence[str],
    cwd: Path,
    display: str,
    timeout: int,
) -> CommandEvidence:
    try:
        result = subprocess.run(  # nosec B603
            list(argv),
            check=False,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        evidence = CommandEvidence(
            name=name,
            command=display,
            cwd=str(cwd),
            exit_code=None,
            stdout=_bounded(_expired_output(exc.stdout)),
            stderr=_bounded(_expired_output(exc.stderr)),
        )
        msg = f"{name} timed out after {timeout} seconds"
        raise SmokeError(msg, (evidence,)) from exc

    evidence = CommandEvidence(
        name=name,
        command=display,
        cwd=str(cwd),
        exit_code=result.returncode,
        stdout=_bounded(result.stdout),
        stderr=_bounded(result.stderr),
    )
    if result.returncode != 0:
        msg = f"{name} failed with exit code {result.returncode}: {_failure_summary(evidence)}"
        raise SmokeError(msg, (evidence,))
    return evidence


def _expired_output(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _failure_summary(evidence: CommandEvidence) -> str:
    combined = "\n".join(
        part for part in (evidence.stderr.strip(), evidence.stdout.strip()) if part
    )
    return _bounded(combined or "command failed without output")


def _bounded(value: str) -> str:
    if len(value) <= OUTPUT_LIMIT:
        return value
    return f"{value[:OUTPUT_LIMIT]}... [truncated]"


def _write_evidence(payload: dict[str, object], artifact_dir: Path | None) -> None:
    if artifact_dir is None:
        return
    target_dir = artifact_dir.expanduser()
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / EVIDENCE_NAME).write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _print_payload(payload: dict[str, object], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    lines = [
        "# Local Wheel Install Smoke Evidence",
        "",
        f"- Schema: `{payload['schema_version']}`",
        f"- Status: `{payload['status']}`",
        f"- Stable-core ready: `{str(payload['stable_core_ready']).lower()}`",
        f"- Uses public CLI: `{str(payload['uses_public_cli']).lower()}`",
        f"- Requires package index: `{str(payload['requires_package_index']).lower()}`",
    ]
    if payload["wheel"]:
        lines.append(f"- Wheel: `{payload['wheel']}`")
    if payload["project_path"]:
        lines.append(f"- Temporary project: `{payload['project_path']}`")
    artifacts = payload["artifacts"]
    if isinstance(artifacts, list) and artifacts:
        lines.extend(["", "## Artifacts", ""])
        lines.extend(f"- `{artifact}`" for artifact in artifacts)
    lines.extend(["", "## Commands", ""])
    commands = payload["commands"]
    command_items = commands if isinstance(commands, list) else []
    for command in command_items:
        command_data = command if isinstance(command, dict) else {}
        lines.append(
            "- "
            f"`{command_data.get('name', '')}`: "
            f"`{command_data.get('command', '')}` "
            f"(exit `{command_data.get('exit_code')}`)"
        )
    if payload["failure"]:
        lines.extend(["", "## Failure", "", str(payload["failure"])])
    print("\n".join(lines))


if __name__ == "__main__":
    raise SystemExit(main())
