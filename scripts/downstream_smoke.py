#!/usr/bin/env python3
"""Run Entroping against a temporary downstream project outside this repository."""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

SCHEMA_VERSION = "entroping.downstream-smoke.v1"
REPORT_ARTIFACTS = (
    "run-latest.json",
    "run-latest.html",
    "junit.xml",
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prove Entroping can run from an external downstream project."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Entroping repository root.",
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=None,
        help="Empty downstream project directory to create/use. Defaults to a temp dir.",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=None,
        help="Optional directory where evidence and run reports are copied.",
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
        help="Print planned evidence without creating a project or running Hurl.",
    )
    parser.add_argument(
        "--keep-workdir",
        action="store_true",
        help="Keep an auto-created temporary downstream project for inspection.",
    )
    args = parser.parse_args()

    repo_root = args.root.expanduser().resolve()
    command_display = _command_display()
    if args.dry_run:
        payload = _planned_payload(command_display)
        _print_payload(payload, args.format)
        return 0

    own_workdir = False
    server: subprocess.Popen[str] | None = None
    try:
        workdir, own_workdir = _prepare_workdir(repo_root, args.workdir)
        port = _find_free_port()
        _write_downstream_project(workdir, port)
        server = _start_server(workdir, port)
        _wait_for_server(port)

        hurl_version = _hurl_version()
        command = _run_command(repo_root)
        result = subprocess.run(  # nosec B603
            command,
            cwd=workdir,
            text=True,
            capture_output=True,
            check=False,
            timeout=90,
        )
        payload = _result_payload(
            status="pass" if result.returncode == 0 else "fail",
            command_display=command_display,
            workdir=workdir,
            hurl_version=hurl_version,
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            artifact_dir=args.artifact_dir,
        )
        if args.artifact_dir is not None:
            _copy_artifacts(workdir, args.artifact_dir, payload)
    except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError) as exc:
        payload = _error_payload(command_display, str(exc))
        _print_payload(payload, args.format)
        print(f"downstream smoke failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
        if own_workdir and not args.keep_workdir:
            shutil.rmtree(workdir, ignore_errors=True)

    _print_payload(payload, args.format)
    if payload["status"] != "pass":
        print(
            f"downstream smoke failed: Entroping run failed with exit code {payload['exit_code']}",
            file=sys.stderr,
        )
    return 0 if payload["status"] == "pass" else 1


def _command_display() -> str:
    return (
        "uv run --project <repo-root> entroping run --ci --tag downstream-smoke "
        "--report json --report junit --report html"
    )


def _run_command(repo_root: Path) -> list[str]:
    return [
        "uv",
        "run",
        "--project",
        str(repo_root),
        "entroping",
        "run",
        "--ci",
        "--tag",
        "downstream-smoke",
        "--report",
        "json",
        "--report",
        "junit",
        "--report",
        "html",
    ]


def _planned_payload(command_display: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "planned",
        "stable_core_ready": False,
        "uses_public_cli": True,
        "requires_hurl": True,
        "command": command_display,
        "downstream_project_path": "",
        "artifacts": [],
        "hurl_version": "",
        "exit_code": None,
        "failure": "",
    }


def _result_payload(
    *,
    status: str,
    command_display: str,
    workdir: Path,
    hurl_version: str,
    exit_code: int,
    stdout: str,
    stderr: str,
    artifact_dir: Path | None,
) -> dict[str, Any]:
    artifacts = ["downstream-smoke-evidence.json", *REPORT_ARTIFACTS]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "stable_core_ready": False,
        "uses_public_cli": True,
        "requires_hurl": True,
        "command": command_display,
        "downstream_project_path": str(workdir),
        "artifacts": sorted(artifacts) if artifact_dir is not None else [],
        "hurl_version": hurl_version,
        "exit_code": exit_code,
        "failure": "" if status == "pass" else _failure_summary(stdout, stderr),
    }


def _error_payload(command_display: str, failure: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "fail",
        "stable_core_ready": False,
        "uses_public_cli": True,
        "requires_hurl": True,
        "command": command_display,
        "downstream_project_path": "",
        "artifacts": [],
        "hurl_version": "",
        "exit_code": 1,
        "failure": failure,
    }


def _prepare_workdir(repo_root: Path, requested: Path | None) -> tuple[Path, bool]:
    if requested is None:
        workdir = Path(tempfile.mkdtemp(prefix="entroping-downstream-smoke-")).resolve()
        return workdir, True

    candidate = requested.expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    _reject_symlink_components(candidate)
    candidate.mkdir(parents=True, exist_ok=True)
    workdir = candidate.resolve(strict=True)
    if workdir == Path("/") or workdir == repo_root or repo_root in workdir.parents:
        msg = f"Refusing unsafe downstream workdir: {workdir}"
        raise ValueError(msg)
    if any(workdir.iterdir()):
        msg = f"Refusing non-empty downstream workdir: {workdir}"
        raise ValueError(msg)
    return workdir, False


def _reject_symlink_components(path: Path) -> None:
    current = Path(path.anchor or "/")
    for part in path.parts[1:]:
        current = current / part
        if (current.exists() or current.is_symlink()) and current.is_symlink():
            msg = f"Refusing symlinked downstream workdir component: {current}"
            raise ValueError(msg)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _write_downstream_project(workdir: Path, port: int) -> None:
    (workdir / "tests").mkdir()
    (workdir / "qanstitution.yaml").write_text(
        textwrap.dedent(
            """\
            project: "downstream-smoke"
            version: "4.1"
            description: "External downstream smoke fixture for stable-core evidence"

            gates:
              - id: "downstream.no_server_errors"
                description: "External smoke endpoints must not return server errors"
                condition: "true"
                gate: "status < 500"
                enforcement: "block"
              - id: "downstream.request_id"
                description: "External smoke responses must include a request ID"
                condition: "tags contains 'downstream-smoke'"
                gate: 'header "X-Request-Id" exists'
                enforcement: "block"

            settings:
              timeout: 30000
              parallel_workers: 1
              follow_redirects: true
              retry: 0
            """
        ),
        encoding="utf-8",
    )
    (workdir / "tests" / "downstream_smoke.hurl").write_text(
        textwrap.dedent(
            f"""\
            # entroping: tags=downstream-smoke,external-project
            # entroping: story_id=DOWNSTREAM-001
            # entroping: owner=stable-core

            GET http://127.0.0.1:{port}/health
            HTTP 200
            [Asserts]
            jsonpath "$.status" == "ok"
            """
        ),
        encoding="utf-8",
    )
    (workdir / "downstream_server.py").write_text(_server_source(), encoding="utf-8")


def _server_source() -> str:
    return textwrap.dedent(
        """\
        from __future__ import annotations

        import argparse
        import json
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path != "/health":
                    self.send_error(404)
                    return
                body = json.dumps({"status": "ok"}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("X-Request-Id", "downstream-smoke-001")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *args: object) -> None:
                return


        parser = argparse.ArgumentParser()
        parser.add_argument("--port", type=int, required=True)
        args = parser.parse_args()
        ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
        """
    )


def _start_server(workdir: Path, port: int) -> subprocess.Popen[str]:
    return subprocess.Popen(  # nosec B603
        [sys.executable, str(workdir / "downstream_server.py"), "--port", str(port)],
        cwd=workdir,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def _wait_for_server(port: int) -> None:
    deadline = time.monotonic() + 10
    url = f"http://127.0.0.1:{port}/health"
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=0.5) as response:  # nosec B310
                if response.status == 200:
                    return
        except (OSError, URLError):
            time.sleep(0.2)
    msg = f"Downstream smoke server did not become ready at {url}"
    raise RuntimeError(msg)


def _hurl_version() -> str:
    hurl_path = shutil.which("hurl")
    if hurl_path is None:
        msg = "Hurl is required for downstream smoke evidence."
        raise RuntimeError(msg)
    result = subprocess.run(  # nosec B603
        [hurl_path, "--version"],
        check=False,
        text=True,
        capture_output=True,
        timeout=10,
    )
    if result.returncode != 0:
        msg = "Unable to read Hurl version."
        raise RuntimeError(msg)
    return result.stdout.splitlines()[0] if result.stdout else hurl_path


def _copy_artifacts(workdir: Path, artifact_dir: Path, payload: dict[str, Any]) -> None:
    artifact_dir.expanduser().mkdir(parents=True, exist_ok=True)
    reports_dir = workdir / "reports"
    for name in REPORT_ARTIFACTS:
        source = reports_dir / name
        if not source.is_file():
            msg = f"Expected downstream report artifact was not written: {source}"
            raise RuntimeError(msg)
        shutil.copy2(source, artifact_dir / name)
    (artifact_dir / "downstream-smoke-evidence.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _failure_summary(stdout: str, stderr: str) -> str:
    combined = "\n".join(part for part in (stderr.strip(), stdout.strip()) if part)
    if not combined:
        return "downstream command failed without output"
    return combined[:4000]


def _print_payload(payload: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    lines = [
        "# Downstream Smoke Evidence",
        "",
        f"- Schema: `{payload['schema_version']}`",
        f"- Status: `{payload['status']}`",
        f"- Stable-core ready: `{str(payload['stable_core_ready']).lower()}`",
        f"- Uses public CLI: `{str(payload['uses_public_cli']).lower()}`",
        f"- Requires Hurl: `{str(payload['requires_hurl']).lower()}`",
        f"- Command: `{payload['command']}`",
    ]
    if payload["downstream_project_path"]:
        lines.append(f"- Downstream project: `{payload['downstream_project_path']}`")
    if payload["hurl_version"]:
        lines.append(f"- Hurl: `{payload['hurl_version']}`")
    if payload["artifacts"]:
        lines.extend(["", "## Artifacts", ""])
        lines.extend(f"- `{artifact}`" for artifact in payload["artifacts"])
    if payload["failure"]:
        lines.extend(["", "## Failure", "", str(payload["failure"])])
    print("\n".join(lines))


if __name__ == "__main__":
    raise SystemExit(main())
