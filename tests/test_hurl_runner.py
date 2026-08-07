"""Adapter tests for the deterministic Hurl subprocess runner."""

import base64
import json
import subprocess
import threading
import time
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pytest

from entroping.core import hurl_runner
from entroping.core.hurl_runner import (
    HurlAssertionEvidence,
    HurlAssertionPolicy,
    HurlBinaryNotFoundError,
    HurlRunnerError,
    HurlRunOptions,
    HurlStructuredReportError,
    discover_hurl,
    run_hurl_file,
    run_hurl_files,
    validate_hurl_path,
)


def _write_hurl(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("GET {{base_url}}/health\nHTTP 200\n", encoding="utf-8")
    return path


def _write_structured_json(
    stdout: BinaryIO,
    *,
    filename: str,
    success: bool,
    assertions: list[dict[str, object]],
    capture_name: str = "__entroping_response_body_0",
    body: bytes = b"response body\n",
    captures: list[dict[str, str]] | None = None,
) -> None:
    response_captures = captures if captures is not None else [
        {"name": capture_name, "value": base64.b64encode(body).decode("ascii")},
    ]
    stdout.write(
        json.dumps(
            {
                "filename": filename,
                "success": success,
                "entries": [
                    {
                        "asserts": assertions,
                        "calls": [
                            {
                                "response": {
                                    "status": 200,
                                    "headers": [
                                        {"name": "Content-Type", "value": "text/plain"},
                                    ],
                                },
                            },
                        ],
                        "captures": response_captures,
                    },
                ],
            },
    ).encode("utf-8"),
    )


_RESPONSE_CAPTURE_NAME = "__entroping_response_body_0"


def _structured_entry(
    *,
    asserts: object = (),
    calls: object = (
        {
            "response": {
                "status": 200,
                "headers": [],
            },
        },
    ),
    captures: object = (
        {"name": _RESPONSE_CAPTURE_NAME, "value": "aGVsbG8="},
    ),
) -> dict[str, object]:
    return {"asserts": asserts, "calls": calls, "captures": captures}


def _structured_root(entries: object) -> dict[str, object]:
    return {
        "filename": "/tmp/health.hurl",
        "success": True,
        "entries": entries,
    }


def _read_structured_payload(
    payload: object,
    *,
    capture_names: tuple[str, ...] = (_RESPONSE_CAPTURE_NAME,),
) -> hurl_runner._StructuredHurlReport:
    return hurl_runner._read_hurl_json_output(
        BytesIO(json.dumps(payload).encode("utf-8")),
        hurl_path=Path("/tmp/health.hurl"),
        expected_success=True,
        capture_names=capture_names,
    )


def _write_executable(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o111)
    return path


def _host_symlink_anchor_alias(path: Path) -> Path | None:
    resolved = path.resolve()
    for anchor in (Path("/var"), Path("/tmp")):
        if not anchor.is_symlink():
            continue
        try:
            relative = resolved.relative_to(anchor.resolve())
        except ValueError:
            continue
        return anchor / relative
    return None


def test_discover_hurl_reports_binary_availability(monkeypatch: pytest.MonkeyPatch) -> None:
    def resolve_binary(binary: str) -> str:
        return f"/opt/bin/{binary}"

    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", resolve_binary)

    assert discover_hurl("custom-hurl").available
    assert discover_hurl("custom-hurl").path == "/opt/bin/custom-hurl"

    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: None)

    assert not discover_hurl("missing-hurl").available
    assert discover_hurl("missing-hurl").path is None


def test_discover_hurl_trusts_parent_path_precedence_for_bare_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    earlier_bin = tmp_path / "earlier-bin"
    later_bin = tmp_path / "later-bin"
    _write_executable(earlier_bin / "hurl", "#!/bin/sh\necho 'hurl 8.0.1 earlier'\n")
    _write_executable(later_bin / "hurl", "#!/bin/sh\necho 'hurl 8.0.1 later'\n")
    monkeypatch.setenv("PATH", f"{earlier_bin}:{later_bin}")

    status = discover_hurl("hurl")

    assert status.available is True
    assert status.path == str(earlier_bin / "hurl")
    assert status.version_checked is True
    assert status.version == "8.0.1"
    assert status.version_output == "hurl 8.0.1 earlier"


def test_discover_hurl_resolves_path_selected_binary_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bin_dir = tmp_path / "bin"
    real_hurl = _write_executable(
        tmp_path / "Cellar" / "hurl" / "8.0.1" / "bin" / "hurl",
        "#!/bin/sh\necho 'hurl 8.0.1 cellar'\n",
    )
    bin_dir.mkdir()
    (bin_dir / "hurl").symlink_to(real_hurl)
    monkeypatch.setenv("PATH", str(bin_dir))

    status = discover_hurl("hurl")

    assert status.available is True
    assert status.path == str(real_hurl)
    assert status.version_checked is True
    assert status.version == "8.0.1"


def test_discover_hurl_missing_default_binary_does_not_claim_version_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: None)

    status = discover_hurl("hurl")

    assert status.available is False
    assert status.path is None
    assert status.version_checked is False
    assert status.version is None
    assert status.version_parts is None
    assert status.version_error is None


def test_discover_hurl_reports_compatible_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str],
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(
            {
                "args": args,
                "timeout": timeout,
                "check": check,
                "env": env,
                "shell": shell,
            }
        )
        stdout.write(b"hurl 8.0.1 (x86_64-apple-darwin)\n")
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/opt/bin/hurl")
    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr(Path, "is_dir", lambda path: False)

    status = discover_hurl("hurl")

    assert status.available is True
    assert status.path == "/opt/bin/hurl"
    assert status.version_checked is True
    assert status.version == "8.0.1"
    assert status.version_parts == (8, 0, 1)
    assert status.version_output == "hurl 8.0.1 (x86_64-apple-darwin)"
    assert status.version_error is None
    assert calls == [
        {
            "args": ["/opt/bin/hurl", "--version"],
            "timeout": 2.0,
            "check": False,
            "env": {"PATH": "/opt/bin:/usr/bin:/bin"},
            "shell": False,
        }
    ]


def test_discover_hurl_reports_unparsable_version_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str],
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stderr, timeout, check, env, shell)
        stdout.write(b"hurl dev-build\n")
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/opt/bin/hurl")
    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)

    status = discover_hurl("hurl")

    assert status.version_checked is True
    assert status.version is None
    assert status.version_parts is None
    assert status.version_output == "hurl dev-build"
    assert status.version_error is None


def test_discover_hurl_reports_version_command_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str],
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stdout, timeout, check, env, shell)
        stderr.write(b"unexpected option\n")
        return subprocess.CompletedProcess(args=args, returncode=2)

    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/opt/bin/hurl")
    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)

    status = discover_hurl("hurl")

    assert status.version_checked is True
    assert status.version is None
    assert status.version_error == "hurl --version exited with code 2: unexpected option"


def test_discover_hurl_reports_version_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str],
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stdout, stderr, check, env, shell)
        raise subprocess.TimeoutExpired(cmd=args, timeout=timeout)

    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/opt/bin/hurl")
    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)

    status = discover_hurl("hurl")

    assert status.version_checked is True
    assert status.version is None
    assert status.version_error == "hurl --version timed out after 2 seconds"


def test_discover_hurl_reports_version_os_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str],
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (args, stdout, stderr, timeout, check, env, shell)
        raise OSError("permission denied")

    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/opt/bin/hurl")
    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)

    status = discover_hurl("hurl")

    assert status.version_checked is True
    assert status.version is None
    assert status.version_error == "hurl --version failed: permission denied"


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: HurlRunOptions(binary="  "), "Hurl binary must not be empty"),
        (lambda: HurlRunOptions(timeout_ms=0), "Hurl timeout must be greater than zero"),
        (
            lambda: HurlRunOptions(output_limit_bytes=0),
            "Hurl output limit must be greater than zero",
        ),
        (lambda: HurlRunOptions(retry=-1), "Hurl retry count must not be negative"),
        (lambda: HurlRunOptions(variables={"bad-name": "value"}), "Invalid Hurl variable name"),
        (lambda: HurlRunOptions(variables={"token": "line1\nline2"}), "must be single-line"),
    ],
)
def test_hurl_run_options_reject_invalid_runtime_options(
    factory: Callable[[], HurlRunOptions],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        factory()


def test_run_hurl_file_invokes_hurl_with_argument_array_and_redacts_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "health.hurl")
    calls: list[dict[str, object]] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(
            {
                "args": args,
                "timeout": timeout,
                "check": check,
                "shell": shell,
            }
        )
        stdout.write(b"Authorization: Bearer live-secret\nbody ok\n")
        stderr.write(b"token=live-secret\n")
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(
        hurl_file,
        HurlRunOptions(
            binary="hurl",
            timeout_ms=1500,
            output_limit_bytes=4096,
            redacted_values=("live-secret",),
        ),
    )

    assert calls == [
        {
            "args": [str(Path("/bin/hurl").resolve()), str(hurl_file.resolve())],
            "timeout": 1.5,
            "check": False,
            "shell": False,
        }
    ]
    assert result.passed
    assert result.status == "passed"
    assert result.exit_code == 0
    assert "live-secret" not in result.stdout
    assert "live-secret" not in result.stderr
    assert "Authorization: [REDACTED]" in result.stdout
    assert "token=[REDACTED]" in result.stderr


def test_run_hurl_file_classifies_structured_nonblocking_assertion_without_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "health.hurl")
    calls: list[list[str]] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stderr, timeout, check, env, shell)
        calls.append(args)
        _write_structured_json(
            stdout,
            filename=args[-1],
            success=False,
            assertions=[{"line": 2, "success": False}],
        )
        return subprocess.CompletedProcess(args=args, returncode=4)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(
        hurl_file,
        HurlRunOptions(
            binary="hurl",
            capture_assertions=True,
            assertion_policies={
                hurl_file.resolve(): (HurlAssertionPolicy(line=2, blocking=False),),
            },
            response_capture_names={hurl_file.resolve(): ("__entroping_response_body_0",)},
        ),
    )

    assert len(calls) == 1
    assert "--continue-on-error" in calls[0]
    assert "--json" in calls[0]
    assert "--report-json" not in calls[0]
    assert result.passed
    assert result.exit_code == 0
    assert result.assertion_evidence == (HurlAssertionEvidence(line=2, success=False),)


def test_run_hurl_files_scopes_structured_execution_to_gated_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gated_path = _write_hurl(tmp_path / "tests" / "gated.hurl")
    normal_path = _write_hurl(tmp_path / "tests" / "normal.hurl")
    calls: dict[Path, list[str]] = {}

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stderr, timeout, check, env, shell)
        path = Path(args[-1]).resolve()
        calls[path] = args
        if path == gated_path.resolve():
            _write_structured_json(
                stdout,
                filename=args[-1],
                success=True,
                assertions=[{"line": 2, "success": True}],
            )
        else:
            stdout.write(b"normal stdout\n")
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_files(
        (gated_path, normal_path),
        HurlRunOptions(
            binary="hurl",
            capture_assertions=True,
            assertion_policies={
                gated_path.resolve(): (HurlAssertionPolicy(line=2, blocking=True),),
            },
            response_capture_names={gated_path.resolve(): (_RESPONSE_CAPTURE_NAME,)},
        ),
    )

    gated_result, normal_result = result.results
    assert "--json" in calls[gated_path.resolve()]
    assert "--continue-on-error" in calls[gated_path.resolve()]
    assert "--json" not in calls[normal_path.resolve()]
    assert "--continue-on-error" not in calls[normal_path.resolve()]
    assert gated_result.assertion_evidence == (HurlAssertionEvidence(line=2, success=True),)
    assert "HTTP/1.1 200" in gated_result.stdout
    assert normal_result.assertion_evidence is None
    assert normal_result.stdout == "normal stdout\n"


def test_run_hurl_file_unscoped_capture_assertions_remains_structured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "unscoped.hurl")
    calls: list[list[str]] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stderr, timeout, check, env, shell)
        calls.append(args)
        _write_structured_json(
            stdout,
            filename=args[-1],
            success=True,
            assertions=[],
        )
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(hurl_file, HurlRunOptions(binary="hurl", capture_assertions=True))

    assert "--json" in calls[0]
    assert result.assertion_evidence == ()
    assert "HTTP/1.1 200" in result.stdout


def test_run_hurl_file_reconstructs_response_without_policy_classification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "response-only.hurl")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stderr, timeout, check, env, shell)
        _write_structured_json(
            stdout,
            filename=args[-1],
            success=True,
            assertions=[],
        )
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(
        hurl_file,
        HurlRunOptions(
            binary="hurl",
            capture_assertions=True,
            response_capture_names={hurl_file.resolve(): (_RESPONSE_CAPTURE_NAME,)},
        ),
    )

    assert result.passed
    assert "HTTP/1.1 200" in result.stdout
    assert "response body" in result.stdout


def test_run_hurl_file_rejects_missing_structured_report_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "health.hurl")
    calls: list[list[str]] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stdout, stderr, timeout, check, env, shell)
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(
        hurl_file,
        HurlRunOptions(
            binary="hurl",
            capture_assertions=True,
            response_capture_names={hurl_file.resolve(): ("__entroping_response_body_0",)},
        ),
    )

    assert result.status == "error"
    assert result.exit_code == 126
    assert result.assertion_evidence is None
    assert result.stderr == "Hurl structured assertion report invalid"
    assert calls and "--report-json" not in calls[0]


@pytest.mark.parametrize(
    "payload",
    [
        b"{",
        b"{}",
        b"{}" + b"x" * (hurl_runner._STRUCTURED_JSON_LIMIT_BYTES + 1),
    ],
)
def test_run_hurl_file_rejects_malformed_or_oversized_4_3_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "malformed-json.hurl")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stderr, timeout, check, env, shell)
        stdout.write(payload)
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(
        hurl_file,
        HurlRunOptions(
            binary="hurl",
            capture_assertions=True,
            response_capture_names={hurl_file.resolve(): ("__entroping_response_body_0",)},
        ),
    )

    assert result.status == "error"
    assert result.exit_code == 126
    assert result.stdout == ""
    assert result.stderr == "Hurl structured assertion report invalid"


@pytest.mark.parametrize(
    "payload",
    [
        [],
        _structured_root({}),
        _structured_root([None]),
        _structured_root([_structured_entry(asserts="invalid")]),
        _structured_root([_structured_entry(asserts=[None])]),
        _structured_root([_structured_entry(asserts=[{"line": 0, "success": True}])]),
        _structured_root([_structured_entry(calls="invalid")]),
        _structured_root([_structured_entry(calls=[None])]),
        _structured_root([_structured_entry(calls=[{"response": None}])]),
        _structured_root(
            [
                _structured_entry(
                    calls=[{"response": {"status": 99, "headers": []}}],
                ),
            ],
        ),
        _structured_root(
            [
                _structured_entry(
                    calls=[{"response": {"status": "200", "headers": []}}],
                ),
            ],
        ),
        _structured_root(
            [
                _structured_entry(
                    calls=[{"response": {"status": 200, "headers": None}}],
                ),
            ],
        ),
        _structured_root(
            [
                _structured_entry(
                    calls=[{"response": {"status": 200, "headers": [None]}}],
                ),
            ],
        ),
        _structured_root(
            [
                _structured_entry(
                    calls=[
                        {
                            "response": {
                                "status": 200,
                                "headers": [{"name": "X-Test", "value": "bad\n"}],
                            },
                        },
                    ],
                ),
            ],
        ),
        _structured_root(
            [
                _structured_entry(
                    asserts=[{"line": 1, "success": "true"}],
                ),
            ],
        ),
        _structured_root(
            [
                _structured_entry(
                    calls=[
                        {
                            "response": {
                                "status": 200,
                                "headers": [{"name": 1, "value": "bad"}],
                            },
                        },
                    ],
                ),
            ],
        ),
        _structured_root([_structured_entry(captures="invalid")]),
        _structured_root([_structured_entry(captures=[None])]),
        _structured_root(
            [_structured_entry(captures=[{"name": 1, "value": "value"}])],
        ),
        _structured_root(
            [
                _structured_entry(
                    captures=[{"name": _RESPONSE_CAPTURE_NAME, "value": 200}],
                ),
            ],
        ),
    ],
)
def test_read_hurl_json_rejects_malformed_4_3_shapes(payload: object) -> None:
    with pytest.raises(HurlStructuredReportError):
        _read_structured_payload(payload)


def test_read_hurl_json_ignores_non_reserved_captures() -> None:
    payload = _structured_root(
        [
            _structured_entry(
                captures=[
                    {"name": "unrelated", "value": "not surfaced"},
                    {"name": _RESPONSE_CAPTURE_NAME, "value": "aGVsbG8="},
                ],
            ),
        ],
    )

    report = _read_structured_payload(payload)

    assert report.response_output is not None
    assert report.response_output.endswith(b"hello")


def test_read_hurl_json_allows_numeric_non_reserved_captures() -> None:
    payload = _structured_root(
        [
            _structured_entry(
                captures=[
                    {"name": "status", "value": 200},
                    {"name": _RESPONSE_CAPTURE_NAME, "value": "aGVsbG8="},
                ],
            ),
        ],
    )

    report = _read_structured_payload(payload)

    assert report.response_output is not None
    assert report.response_output.endswith(b"hello")


def test_read_hurl_json_rejects_capture_without_response_status() -> None:
    payload = _structured_root(
        [_structured_entry(calls=[], captures=[{"name": _RESPONSE_CAPTURE_NAME, "value": "aA=="}])],
    )

    with pytest.raises(HurlStructuredReportError):
        _read_structured_payload(payload)


def test_read_hurl_json_without_capture_returns_no_response_output() -> None:
    payload = _structured_root([_structured_entry(calls=[], captures=[])])

    report = _read_structured_payload(payload, capture_names=())

    assert report.response_output is None


@pytest.mark.parametrize(
    "capture_value",
    [
        "not-base64",
        base64.b64encode(
            b"x" * (hurl_runner._STRUCTURED_RESPONSE_BODY_LIMIT_BYTES + 1),
        ).decode("ascii"),
    ],
)
def test_read_hurl_json_rejects_invalid_or_oversized_capture(
    capture_value: str,
) -> None:
    payload = _structured_root(
        [
            _structured_entry(
                captures=[{"name": _RESPONSE_CAPTURE_NAME, "value": capture_value}],
            ),
        ],
    )

    with pytest.raises(HurlStructuredReportError):
        _read_structured_payload(payload)


def test_classify_structured_result_rejects_duplicate_policy_lines() -> None:
    result = hurl_runner._classify_structured_result(
        status="passed",
        exit_code=0,
        assertions=(),
        policies=(
            HurlAssertionPolicy(line=2, blocking=False),
            HurlAssertionPolicy(line=2, blocking=False),
        ),
    )

    assert result == ("error", 126)


def test_classify_structured_result_keeps_nonpassed_block_failure_status() -> None:
    result = hurl_runner._classify_structured_result(
        status="failed",
        exit_code=4,
        assertions=(HurlAssertionEvidence(line=2, success=False),),
        policies=(HurlAssertionPolicy(line=2, blocking=True),),
    )

    assert result == ("failed", 4)

    assert hurl_runner._classify_structured_result(
        status="passed",
        exit_code=0,
        assertions=(HurlAssertionEvidence(line=2, success=False),),
        policies=(HurlAssertionPolicy(line=2, blocking=True),),
    ) == ("failed", 1)
    assert hurl_runner._classify_structured_result(
        status="passed",
        exit_code=0,
        assertions=(HurlAssertionEvidence(line=2, success=True),),
        policies=(HurlAssertionPolicy(line=2, blocking=True),),
    ) == ("passed", 0)


def test_read_hurl_json_rejects_stdout_handle_errors() -> None:
    class BrokenStdout(BytesIO):
        def seek(self, offset: int, whence: int = 0) -> int:
            _ = offset, whence
            raise OSError("seek failed")

    with pytest.raises(HurlStructuredReportError):
        hurl_runner._read_hurl_json_output(
            BrokenStdout(),
            hurl_path=Path("/tmp/health.hurl"),
            expected_success=True,
            capture_names=(_RESPONSE_CAPTURE_NAME,),
        )


def test_read_hurl_json_rejects_oversized_entry_list() -> None:
    payload = _structured_root(
        [_structured_entry() for _ in range(hurl_runner._STRUCTURED_REPORT_ENTRY_LIMIT + 1)],
    )

    with pytest.raises(HurlStructuredReportError):
        _read_structured_payload(payload)


@pytest.mark.parametrize("field", ["filename", "success"])
def test_run_hurl_file_rejects_4_3_json_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "identity-mismatch.hurl")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stderr, timeout, check, env, shell)
        _write_structured_json(
            stdout,
            filename=args[-1] if field != "filename" else "other.hurl",
            success=field != "success",
            assertions=[{"line": 2, "success": True}],
        )
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(
        hurl_file,
        HurlRunOptions(
            binary="hurl",
            capture_assertions=True,
            response_capture_names={hurl_file.resolve(): ("__entroping_response_body_0",)},
        ),
    )

    assert result.status == "error"
    assert result.exit_code == 126
    assert result.assertion_evidence is None


@pytest.mark.parametrize(
    "assertions",
    [
        [{"line": 9, "success": False}],
        [{"line": 2, "success": False}, {"line": 2, "success": False}],
    ],
)
def test_run_hurl_file_rejects_missing_or_duplicate_policy_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    assertions: list[dict[str, object]],
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "policy-evidence.hurl")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stderr, timeout, check, env, shell)
        _write_structured_json(
            stdout,
            filename=args[-1],
            success=False,
            assertions=assertions,
        )
        return subprocess.CompletedProcess(args=args, returncode=1)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(
        hurl_file,
        HurlRunOptions(
            binary="hurl",
            capture_assertions=True,
            assertion_policies={
                hurl_file.resolve(): (HurlAssertionPolicy(line=2, blocking=False),),
            },
            response_capture_names={hurl_file.resolve(): ("__entroping_response_body_0",)},
        ),
    )

    assert result.status == "error"
    assert result.exit_code == 126


def test_run_hurl_file_keeps_original_assertion_failure_blocking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "source-assertion.hurl")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stderr, timeout, check, env, shell)
        _write_structured_json(
            stdout,
            filename=args[-1],
            success=False,
            assertions=[{"line": 2, "success": False}, {"line": 4, "success": False}],
        )
        return subprocess.CompletedProcess(args=args, returncode=1)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(
        hurl_file,
        HurlRunOptions(
            binary="hurl",
            capture_assertions=True,
            assertion_policies={
                hurl_file.resolve(): (HurlAssertionPolicy(line=2, blocking=False),),
            },
            response_capture_names={hurl_file.resolve(): ("__entroping_response_body_0",)},
        ),
    )

    assert result.status == "failed"
    assert result.exit_code == 1


@pytest.mark.parametrize(
    "captures",
    [
        [],
        [
            {"name": "__entroping_response_body_0", "value": "not-base64"},
            {"name": "__entroping_response_body_0", "value": "aGVsbG8="},
        ],
    ],
)
def test_run_hurl_file_rejects_missing_or_invalid_reserved_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    captures: list[dict[str, str]],
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "reserved-capture.hurl")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stderr, timeout, check, env, shell)
        _write_structured_json(
            stdout,
            filename=args[-1],
            success=True,
            assertions=[{"line": 2, "success": True}],
            captures=captures,
        )
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(
        hurl_file,
        HurlRunOptions(
            binary="hurl",
            capture_assertions=True,
            response_capture_names={hurl_file.resolve(): ("__entroping_response_body_0",)},
        ),
    )

    assert result.status == "error"
    assert result.exit_code == 126


def test_run_hurl_file_uses_minimal_subprocess_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "health.hurl")
    calls: list[dict[str, str]] = []
    monkeypatch.setenv("DB_URL", "postgres://user:secret-host/db")
    monkeypatch.setattr(Path, "is_dir", lambda path: False)

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str],
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (args, stderr, timeout, check, shell)
        calls.append(env)
        stdout.write(f"DB_URL={env.get('DB_URL', '')}\n".encode())
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(hurl_file, HurlRunOptions(binary="hurl"))

    expected_path = ":".join(
        dict.fromkeys(
            [
                str(Path("/bin/hurl").resolve().parent),
                "/usr/bin",
                "/bin",
            ]
        )
    )
    assert calls == [{"PATH": expected_path}]
    assert "secret-host" not in result.stdout


def test_minimal_subprocess_environment_includes_existing_non_fhs_runtime_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binary_path = tmp_path / "nix-store" / "bin" / "hurl"
    non_fhs_paths = {
        Path("/opt/homebrew/bin"),
        Path("/run/current-system/sw/bin"),
    }

    def fake_is_dir(path: Path) -> bool:
        return path in non_fhs_paths

    monkeypatch.setattr(Path, "is_dir", fake_is_dir)
    monkeypatch.setenv("PATH", "/untrusted/bin")

    env = hurl_runner._minimal_subprocess_env(str(binary_path))

    path_entries = env["PATH"].split(":")
    assert path_entries[:3] == [
        str(binary_path.resolve().parent),
        "/opt/homebrew/bin",
        "/run/current-system/sw/bin",
    ]
    assert "/untrusted/bin" not in path_entries


def test_run_hurl_file_passes_variables_as_argument_array_and_redacts_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "health.hurl")
    calls: list[list[str]] = []
    variables_files: list[Path] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stderr, timeout, check, shell)
        calls.append(args)
        variables_file = Path(args[args.index("--variables-file") + 1])
        variables_files.append(variables_file)
        assert variables_file.is_file()
        assert variables_file.read_text(encoding="utf-8") == (
            "base_url=http://localhost:18080\ncart_id=demo-cart-001\n"
        )
        stdout.write(b"base_url=http://localhost:18080\n")
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(
        hurl_file,
        HurlRunOptions(
            binary="hurl",
            variables={"base_url": "http://localhost:18080", "cart_id": "demo-cart-001"},
        ),
    )

    assert calls == [
        [
            str(Path("/bin/hurl").resolve()),
            "--variables-file",
            str(variables_files[0]),
            str(hurl_file.resolve()),
        ]
    ]
    assert "http://localhost:18080" not in " ".join(calls[0])
    assert not variables_files[0].exists()
    assert "http://localhost:18080" not in result.stdout
    assert "base_url=[REDACTED]" in result.stdout


def test_variables_file_is_removed_when_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    variables_file = tmp_path / "entroping-hurl-vars.env"
    variables_file.write_text("partial\n", encoding="utf-8")

    class FailingVariablesFile:
        name = str(variables_file)

        def __enter__(self) -> "FailingVariablesFile":
            return self

        def __exit__(self, *exc_info: object) -> None:
            return None

        def write(self, content: str) -> int:
            _ = content
            raise OSError("disk full")

    def fail_named_temporary_file(*args: object, **kwargs: object) -> FailingVariablesFile:
        _ = args, kwargs
        return FailingVariablesFile()

    monkeypatch.setattr(
        "entroping.core.hurl_runner.tempfile.NamedTemporaryFile",
        fail_named_temporary_file,
    )

    with pytest.raises(OSError, match="disk full"):
        hurl_runner._write_variables_file({"base_url": "http://localhost:8080"})

    assert not variables_file.exists()


@pytest.mark.security
def test_run_hurl_file_removes_variables_file_when_setup_after_write_interrupts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "setup-interrupt.hurl")
    variables_file = tmp_path / "entroping-hurl-vars.env"

    def write_variables_file(variables: dict[str, str]) -> Path:
        assert variables == {"token": "live-secret"}
        variables_file.write_text("token=live-secret\n", encoding="utf-8")
        return variables_file

    def interrupt_minimal_env(binary_path: str) -> dict[str, str]:
        _ = binary_path
        raise KeyboardInterrupt

    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")
    monkeypatch.setattr("entroping.core.hurl_runner._write_variables_file", write_variables_file)
    monkeypatch.setattr("entroping.core.hurl_runner._minimal_subprocess_env", interrupt_minimal_env)

    with pytest.raises(KeyboardInterrupt):
        run_hurl_file(
            hurl_file,
            HurlRunOptions(binary="hurl", variables={"token": "live-secret"}),
        )

    assert not variables_file.exists()


def test_run_hurl_file_returns_failed_result_for_non_zero_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "failing.hurl")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (timeout, check, shell)
        stderr.write(b"Assert status < 500 failed\n")
        return subprocess.CompletedProcess(args=args, returncode=42)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(hurl_file, HurlRunOptions(binary="hurl"))

    assert not result.passed
    assert result.status == "failed"
    assert result.exit_code == 42
    assert "Assert status < 500 failed" in result.stderr
    assert result.retry_count == 0
    assert not result.unstable
    assert [attempt.status for attempt in result.attempts] == ["failed"]


def test_run_hurl_file_retries_until_pass_and_marks_unstable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "eventual.hurl")
    return_codes = [7, 0]
    calls: list[list[str]] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (timeout, check, env, shell)
        calls.append(args)
        return_code = return_codes.pop(0)
        stdout.write(f"attempt={len(calls)} secret=live-secret\n".encode())
        stderr.write(f"stderr attempt={len(calls)}\n".encode())
        return subprocess.CompletedProcess(args=args, returncode=return_code)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(
        hurl_file,
        HurlRunOptions(binary="hurl", retry=2, redacted_values=("live-secret",)),
    )

    assert len(calls) == 2
    assert result.passed
    assert result.status == "passed"
    assert result.exit_code == 0
    assert result.retry_count == 1
    assert result.unstable
    assert [attempt.attempt for attempt in result.attempts] == [1, 2]
    assert [attempt.status for attempt in result.attempts] == ["failed", "passed"]
    assert [attempt.exit_code for attempt in result.attempts] == [7, 0]
    assert result.stdout == "attempt=2 secret=[REDACTED]\n"
    assert "live-secret" not in result.stdout


def test_run_hurl_file_exhausts_retry_budget_without_hiding_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "always-fails.hurl")
    calls = 0

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        _ = (stdout, timeout, check, env, shell)
        calls += 1
        stderr.write(f"failed attempt {calls}\n".encode())
        return subprocess.CompletedProcess(args=args, returncode=42)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(hurl_file, HurlRunOptions(binary="hurl", retry=2))

    assert calls == 3
    assert not result.passed
    assert result.status == "failed"
    assert result.exit_code == 42
    assert result.retry_count == 2
    assert not result.unstable
    assert [attempt.status for attempt in result.attempts] == ["failed", "failed", "failed"]
    assert result.stderr == "failed attempt 3\n"


def test_run_hurl_file_returns_error_result_for_subprocess_oserror(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "error.hurl")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (args, stdout, timeout, check, env, shell)
        stderr.write(b"stderr before failure\n")
        raise OSError("permission denied")

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(hurl_file, HurlRunOptions(binary="hurl"))

    assert not result.passed
    assert result.status == "error"
    assert result.exit_code == 126
    assert "stderr before failure" in result.stderr
    assert "Hurl subprocess failed: permission denied" in result.stderr


@pytest.mark.security
def test_run_hurl_file_returns_timeout_result_with_redacted_partial_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "slow.hurl")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (check, shell)
        stdout.write(b"Cookie: session=live-secret\n")
        raise subprocess.TimeoutExpired(cmd=args, timeout=timeout)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(
        hurl_file,
        HurlRunOptions(binary="hurl", timeout_ms=250, redacted_values=("live-secret",)),
    )

    assert not result.passed
    assert result.status == "timeout"
    assert result.exit_code == 124
    assert result.timeout_ms == 250
    assert "live-secret" not in result.stdout
    assert "Cookie: [REDACTED]" in result.stdout
    assert "timed out after 250 ms" in result.stderr


@pytest.mark.security
def test_run_hurl_file_removes_variables_file_after_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "slow.hurl")
    variables_files: list[Path] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stdout, stderr, check, shell)
        variables_file = Path(args[args.index("--variables-file") + 1])
        variables_files.append(variables_file)
        assert variables_file.is_file()
        raise subprocess.TimeoutExpired(cmd=args, timeout=timeout)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(
        hurl_file,
        HurlRunOptions(binary="hurl", variables={"base_url": "http://localhost:18080"}),
    )

    assert result.status == "timeout"
    assert variables_files and not variables_files[0].exists()


@pytest.mark.security
def test_run_hurl_file_bounds_stdout_and_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "noisy.hurl")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (timeout, check, shell)
        stdout.write(b"a" * 128)
        stderr.write(b"b" * 128)
        return subprocess.CompletedProcess(args=args, returncode=1)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(
        hurl_file,
        HurlRunOptions(binary="hurl", output_limit_bytes=32),
    )

    assert result.stdout == ("a" * 32) + "\n[entroping: stdout truncated]\n"
    assert result.stderr == ("b" * 32) + "\n[entroping: stderr truncated]\n"
    assert result.stdout_truncated
    assert result.stderr_truncated


def test_run_hurl_file_preserves_empty_output_without_truncation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "quiet.hurl")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stdout, stderr, timeout, check, env, shell)
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(hurl_file, HurlRunOptions(binary="hurl"))

    assert result.passed
    assert result.stdout == ""
    assert result.stderr == ""
    assert result.stdout_truncated is False
    assert result.stderr_truncated is False


@pytest.mark.parametrize("return_code", [-9, -15])
def test_run_hurl_file_preserves_signal_like_exit_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    return_code: int,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "signal.hurl")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (timeout, check, env, shell)
        stdout.write(b"partial stdout\n")
        stderr.write(b"partial stderr\n")
        return subprocess.CompletedProcess(args=args, returncode=return_code)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(hurl_file, HurlRunOptions(binary="hurl"))

    assert not result.passed
    assert result.status == "failed"
    assert result.exit_code == return_code
    assert result.stdout == "partial stdout\n"
    assert result.stderr == "partial stderr\n"
    assert [(attempt.status, attempt.exit_code) for attempt in result.attempts] == [
        ("failed", return_code)
    ]


@pytest.mark.security
def test_run_hurl_file_decodes_binary_output_and_still_redacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "binary-output.hurl")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (timeout, check, env, shell)
        stdout.write(b"\xff\xfe\x00secret-value\x80stdout")
        stderr.write(b"\xf0\x28\x8c\x28secret-value stderr")
        return subprocess.CompletedProcess(args=args, returncode=1)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(
        hurl_file,
        HurlRunOptions(binary="hurl", redacted_values=("secret-value",)),
    )

    assert result.status == "failed"
    assert "secret-value" not in result.stdout
    assert "secret-value" not in result.stderr
    assert "[REDACTED]" in result.stdout
    assert "[REDACTED]" in result.stderr
    assert "\ufffd" in result.stdout
    assert "\ufffd" in result.stderr


@pytest.mark.parametrize(
    ("payload", "expected", "truncated"),
    [
        (b"12345678", "12345678", False),
        (b"123456789", "12345678\n[entroping: stdout truncated]\n", True),
    ],
)
def test_run_hurl_file_handles_stdout_truncation_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
    expected: str,
    truncated: bool,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "boundary.hurl")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stderr, timeout, check, env, shell)
        stdout.write(payload)
        return subprocess.CompletedProcess(args=args, returncode=1)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(
        hurl_file,
        HurlRunOptions(binary="hurl", output_limit_bytes=8),
    )

    assert result.stdout == expected
    assert result.stdout_truncated is truncated
    assert result.stderr == ""
    assert result.stderr_truncated is False


@pytest.mark.security
def test_run_hurl_file_redacts_truncated_output_before_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "redacted-truncated.hurl")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stderr, timeout, check, env, shell)
        stdout.write(b"abc live-secret def")
        return subprocess.CompletedProcess(args=args, returncode=1)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(
        hurl_file,
        HurlRunOptions(
            binary="hurl",
            output_limit_bytes=len("abc live-secret"),
            redacted_values=("live-secret",),
        ),
    )

    assert result.stdout == "abc [REDACTED]\n[entroping: stdout truncated]\n"
    assert "live-secret" not in result.stdout
    assert result.stdout_truncated is True


@pytest.mark.security
def test_run_hurl_file_captures_partial_streams_and_cleans_variables_after_oserror(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "partial-error.hurl")
    variables_files: list[Path] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (timeout, check, env, shell)
        variables_file = Path(args[args.index("--variables-file") + 1])
        variables_files.append(variables_file)
        stdout.write(b"partial stdout live-secret\n")
        stderr.write(b"partial stderr live-secret\n")
        raise OSError("broken pipe")

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(
        hurl_file,
        HurlRunOptions(
            binary="hurl",
            variables={"token": "live-secret"},
            redacted_values=("live-secret",),
        ),
    )

    assert result.status == "error"
    assert result.exit_code == 126
    assert result.stdout == "partial stdout [REDACTED]\n"
    assert "partial stderr [REDACTED]" in result.stderr
    assert "Hurl subprocess failed: broken pipe" in result.stderr
    assert "live-secret" not in result.stdout
    assert "live-secret" not in result.stderr
    assert variables_files and not variables_files[0].exists()


def test_run_hurl_file_marks_signal_retry_as_unstable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "signal-retry.hurl")
    return_codes = [-9, 0]

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stdout, stderr, timeout, check, env, shell)
        return subprocess.CompletedProcess(args=args, returncode=return_codes.pop(0))

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    result = run_hurl_file(hurl_file, HurlRunOptions(binary="hurl", retry=1))

    assert result.passed
    assert result.unstable
    assert [(attempt.status, attempt.exit_code) for attempt in result.attempts] == [
        ("failed", -9),
        ("passed", 0),
    ]


def test_run_hurl_file_reports_missing_binary_before_subprocess(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "health.hurl")
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: None)

    with pytest.raises(HurlBinaryNotFoundError, match="Hurl binary not found"):
        run_hurl_file(hurl_file, HurlRunOptions(binary="missing-hurl"))


def test_run_hurl_file_explicit_absolute_binary_bypasses_parent_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "health.hurl")
    malicious_bin = tmp_path / "malicious-bin"
    trusted_hurl = _write_executable(
        tmp_path / "trusted-bin" / "hurl",
        "#!/bin/sh\necho trusted\n",
    )
    _write_executable(malicious_bin / "hurl", "#!/bin/sh\necho malicious\n")
    monkeypatch.setenv("PATH", str(malicious_bin))
    monkeypatch.setattr(Path, "is_dir", lambda path: False)
    calls: list[dict[str, object]] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stderr, timeout, check)
        calls.append({"args": args, "env": env, "shell": shell})
        stdout.write(b"trusted\n")
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)

    result = run_hurl_file(hurl_file, HurlRunOptions(binary=str(trusted_hurl)))

    assert result.passed
    assert calls == [
        {
            "args": [str(trusted_hurl.resolve()), str(hurl_file.resolve())],
            "env": {"PATH": f"{trusted_hurl.parent.resolve()}:/usr/bin:/bin"},
            "shell": False,
        }
    ]


def test_run_hurl_file_normalizes_explicit_binary_path_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "health.hurl")
    trusted_hurl = _write_executable(tmp_path / "bin" / "hurl", "#!/bin/sh\necho trusted\n")
    explicit_with_parent_ref = tmp_path / "bin" / ".." / "bin" / "hurl"
    calls: list[list[str]] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stdout, stderr, timeout, check, env, shell)
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)

    run_hurl_file(hurl_file, HurlRunOptions(binary=str(explicit_with_parent_ref)))

    assert calls == [[str(trusted_hurl.resolve()), str(hurl_file.resolve())]]


def test_run_hurl_file_rejects_relative_binary_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "health.hurl")
    relative_bin = tmp_path / "local-bin"
    _write_executable(relative_bin / "hurl", "#!/bin/sh\necho local\n")
    monkeypatch.chdir(relative_bin)

    with pytest.raises(ValueError, match="Hurl binary path must be absolute"):
        run_hurl_file(hurl_file, HurlRunOptions(binary="./hurl"))


def test_run_hurl_file_rejects_missing_explicit_binary_path(tmp_path: Path) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "health.hurl")

    with pytest.raises(HurlBinaryNotFoundError, match="Hurl binary not found"):
        run_hurl_file(hurl_file, HurlRunOptions(binary=str(tmp_path / "bin" / "missing-hurl")))


def test_run_hurl_file_rejects_non_executable_explicit_binary_path(tmp_path: Path) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "health.hurl")
    non_executable = tmp_path / "bin" / "hurl"
    non_executable.parent.mkdir(parents=True, exist_ok=True)
    non_executable.write_text("#!/bin/sh\necho hurl\n", encoding="utf-8")

    with pytest.raises(HurlBinaryNotFoundError, match="Hurl binary is not executable"):
        run_hurl_file(hurl_file, HurlRunOptions(binary=str(non_executable)))


def test_run_hurl_file_rejects_explicit_binary_under_symlinked_parent(
    tmp_path: Path,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "health.hurl")
    real_bin = tmp_path / "real-bin"
    linked_bin = tmp_path / "linked-bin"
    _write_executable(real_bin / "hurl", "#!/bin/sh\necho hurl\n")
    linked_bin.symlink_to(real_bin, target_is_directory=True)

    with pytest.raises(ValueError, match="symlinked Hurl binary path"):
        run_hurl_file(hurl_file, HurlRunOptions(binary=str(linked_bin / "hurl")))


def test_run_hurl_file_allows_explicit_binary_through_host_symlink_anchor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "health.hurl")
    real_binary = _write_executable(tmp_path / "bin" / "hurl", "#!/bin/sh\necho hurl\n")
    binary_alias = _host_symlink_anchor_alias(real_binary)
    if binary_alias is None:
        pytest.skip("host does not expose tmp path through a symlinked anchor")
    calls: list[list[str]] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stderr, timeout, check, env, shell)
        calls.append(args)
        stdout.write(b"ok\n")
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)

    result = run_hurl_file(hurl_file, HurlRunOptions(binary=str(binary_alias)))

    assert result.passed
    assert calls[0][0] == str(real_binary.resolve())


def test_validate_hurl_path_rejects_unsafe_or_invalid_paths(tmp_path: Path) -> None:
    target = _write_hurl(tmp_path / "real" / "health.hurl")
    symlink = tmp_path / "tests" / "linked.hurl"
    symlink.parent.mkdir(parents=True, exist_ok=True)
    symlink.symlink_to(target)

    with pytest.raises(ValueError, match="symlinked Hurl file"):
        validate_hurl_path(symlink)

    notes = tmp_path / "tests" / "notes.txt"
    notes.write_text("not hurl\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Expected a .hurl file"):
        validate_hurl_path(notes)

    with pytest.raises(ValueError, match="Hurl file not found"):
        validate_hurl_path(tmp_path / "tests" / "missing.hurl")


def test_validate_hurl_path_rejects_symlinked_parent_directory(tmp_path: Path) -> None:
    real_tests = tmp_path / "real-tests"
    linked_tests = tmp_path / "linked-tests"
    _write_hurl(real_tests / "health.hurl")
    linked_tests.symlink_to(real_tests, target_is_directory=True)

    with pytest.raises(ValueError, match="symlinked Hurl file path component"):
        validate_hurl_path(linked_tests / "health.hurl")


def test_validate_hurl_path_allows_host_symlink_anchor_for_real_file(
    tmp_path: Path,
) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "health.hurl")
    hurl_alias = _host_symlink_anchor_alias(hurl_file)
    if hurl_alias is None:
        pytest.skip("host does not expose tmp path through a symlinked anchor")

    assert validate_hurl_path(hurl_alias) == hurl_file.resolve()


def test_hurl_execution_symlink_anchor_allowlist_is_narrow() -> None:
    assert not hurl_runner._is_host_level_symlink_anchor(
        Path("/custom-symlink/tests/health.hurl"),
        Path("/custom-symlink"),
    )
    assert not hurl_runner._is_host_level_symlink_anchor(
        Path("relative/tests/health.hurl"),
        Path("relative"),
    )


def test_hurl_execution_symlink_component_rechecks_allowed_anchor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Path | None] = []

    def fake_first_symlink_path_component(
        path: Path,
        *,
        root: Path | None = None,
    ) -> Path | None:
        _ = path
        calls.append(root)
        return Path("/tmp") if root is None else None

    monkeypatch.setattr(
        hurl_runner,
        "first_symlink_path_component",
        fake_first_symlink_path_component,
    )

    assert hurl_runner._first_hurl_execution_symlink_component(
        Path("/tmp/tests/health.hurl")
    ) is None
    assert calls == [None, Path("/tmp")]


def test_run_hurl_files_aggregates_deterministic_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _write_hurl(tmp_path / "tests" / "first.hurl")
    second = _write_hurl(tmp_path / "tests" / "second.hurl")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stdout, stderr, timeout, check, shell)
        return subprocess.CompletedProcess(
            args=args,
            returncode=1 if args[-1].endswith("second.hurl") else 0,
        )

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    suite = run_hurl_files([first, second], HurlRunOptions(binary="hurl"))

    assert suite.total == 2
    assert suite.passed == 1
    assert suite.failed == 1
    assert suite.exit_code == 1


def test_run_hurl_files_fail_fast_stops_sequential_scheduling_after_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _write_hurl(tmp_path / "tests" / "first.hurl")
    second = _write_hurl(tmp_path / "tests" / "second.hurl")
    third = _write_hurl(tmp_path / "tests" / "third.hurl")
    calls: list[str] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stdout, stderr, timeout, check, env, shell)
        calls.append(Path(args[-1]).name)
        return subprocess.CompletedProcess(
            args=args,
            returncode=1 if args[-1].endswith("second.hurl") else 0,
        )

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    suite = run_hurl_files(
        [first, second, third],
        HurlRunOptions(binary="hurl"),
        fail_fast=True,
    )

    assert calls == ["first.hurl", "second.hurl"]
    assert [result.path for result in suite.results] == [first.resolve(), second.resolve()]
    assert suite.total == 2
    assert suite.selected_count == 3
    assert suite.not_scheduled == 1
    assert suite.fail_fast is True
    assert suite.exit_code == 1


def test_run_hurl_files_fail_fast_parallel_preserves_order_and_stops_new_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _write_hurl(tmp_path / "tests" / "first.hurl")
    second = _write_hurl(tmp_path / "tests" / "second.hurl")
    third = _write_hurl(tmp_path / "tests" / "third.hurl")
    calls: list[str] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stdout, stderr, timeout, check, env, shell)
        name = Path(args[-1]).name
        calls.append(name)
        time.sleep(0.01 if name == "first.hurl" else 0.03)
        return subprocess.CompletedProcess(
            args=args,
            returncode=1 if name == "first.hurl" else 0,
        )

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    suite = run_hurl_files(
        [first, second, third],
        HurlRunOptions(binary="hurl"),
        max_workers=2,
        fail_fast=True,
    )

    assert sorted(calls) == ["first.hurl", "second.hurl"]
    assert [result.path for result in suite.results] == [first.resolve(), second.resolve()]
    assert [result.status for result in suite.results] == ["failed", "passed"]
    assert suite.selected_count == 3
    assert suite.not_scheduled == 1
    assert suite.fail_fast is True


def test_run_hurl_files_fail_fast_parallel_stops_new_work_after_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _write_hurl(tmp_path / "tests" / "first.hurl")
    second = _write_hurl(tmp_path / "tests" / "second.hurl")
    third = _write_hurl(tmp_path / "tests" / "third.hurl")
    calls: list[str] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stderr, check, env, shell)
        name = Path(args[-1]).name
        calls.append(name)
        if name == "first.hurl":
            raise subprocess.TimeoutExpired(args, timeout)
        time.sleep(0.03 if name == "second.hurl" else 0.01)
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    suite = run_hurl_files(
        [first, second, third],
        HurlRunOptions(binary="hurl"),
        max_workers=2,
        fail_fast=True,
    )

    assert sorted(calls) == ["first.hurl", "second.hurl"]
    assert [result.path for result in suite.results] == [first.resolve(), second.resolve()]
    assert [result.status for result in suite.results] == ["timeout", "passed"]
    assert suite.selected_count == 3
    assert suite.not_scheduled == 1
    assert suite.fail_fast is True


def test_run_hurl_files_fail_fast_parallel_schedules_while_results_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _write_hurl(tmp_path / "tests" / "first.hurl")
    second = _write_hurl(tmp_path / "tests" / "second.hurl")
    third = _write_hurl(tmp_path / "tests" / "third.hurl")
    calls: list[str] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stdout, stderr, timeout, check, env, shell)
        name = Path(args[-1]).name
        calls.append(name)
        time.sleep(0.01 if name != "second.hurl" else 0.03)
        return subprocess.CompletedProcess(
            args=args,
            returncode=1 if name == "second.hurl" else 0,
        )

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    suite = run_hurl_files(
        [first, second, third],
        HurlRunOptions(binary="hurl"),
        max_workers=2,
        fail_fast=True,
    )

    assert sorted(calls) == ["first.hurl", "second.hurl", "third.hurl"]
    assert [result.path for result in suite.results] == [
        first.resolve(),
        second.resolve(),
        third.resolve(),
    ]
    assert [result.status for result in suite.results] == ["passed", "failed", "passed"]
    assert suite.selected_count == 3
    assert suite.not_scheduled == 0
    assert suite.fail_fast is True


def test_run_hurl_files_rejects_invalid_worker_count(tmp_path: Path) -> None:
    hurl_file = _write_hurl(tmp_path / "tests" / "health.hurl")

    with pytest.raises(ValueError, match="Hurl worker count must be greater than zero"):
        run_hurl_files([hurl_file], HurlRunOptions(binary="hurl"), max_workers=0)


def test_run_hurl_files_surfaces_missing_worker_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _write_hurl(tmp_path / "tests" / "first.hurl")
    second = _write_hurl(tmp_path / "tests" / "second.hurl")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stdout, stderr, timeout, check, env, shell)
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")
    monkeypatch.setattr("entroping.core.hurl_runner.as_completed", lambda futures: ())

    with pytest.raises(HurlRunnerError, match="Hurl worker did not produce a result"):
        run_hurl_files([first, second], HurlRunOptions(binary="hurl"), max_workers=2)


def test_run_hurl_files_bounds_parallel_workers_and_preserves_input_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _write_hurl(tmp_path / "tests" / "first.hurl")
    second = _write_hurl(tmp_path / "tests" / "second.hurl")
    third = _write_hurl(tmp_path / "tests" / "third.hurl")
    active = 0
    max_active = 0
    lock = threading.Lock()

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        nonlocal active, max_active
        _ = (stderr, timeout, check, shell)
        with lock:
            active += 1
            max_active = max(max_active, active)
        try:
            path_name = Path(args[-1]).name
            time.sleep(0.03 if path_name == "third.hurl" else 0.01)
            stdout.write(f"ran {path_name}\n".encode())
            return subprocess.CompletedProcess(
                args=args,
                returncode=1 if path_name == "second.hurl" else 0,
            )
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")

    suite = run_hurl_files(
        [third, first, second],
        HurlRunOptions(binary="hurl"),
        max_workers=2,
    )

    assert max_active == 2
    assert [result.path for result in suite.results] == [
        third.resolve(),
        first.resolve(),
        second.resolve(),
    ]
    assert [result.stdout for result in suite.results] == [
        "ran third.hurl\n",
        "ran first.hurl\n",
        "ran second.hurl\n",
    ]
    assert [result.status for result in suite.results] == ["passed", "passed", "failed"]
    assert suite.exit_code == 1
