from __future__ import annotations

import importlib
import os
import shutil
import sys
from pathlib import Path

import pytest
from factory_orchestration_test_support import repository, request_payload

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

models = importlib.import_module("scripts.factory_orchestration_models")
bounded = importlib.import_module("scripts.bounded_process")
runtime = importlib.import_module("scripts.factory_orchestration_runtime")
tools = importlib.import_module("scripts.factory_orchestration_tools")


def test_start_issue_uses_only_canonical_script_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: an authorized worktree request and a cancellation callback.
    main, worktree, base = repository(tmp_path)
    request = models.OrchestrationRequest.model_validate(
        request_payload(main, worktree, base), strict=True
    )
    observed: dict[str, object] = {}

    def callback() -> bool:
        return False

    def fake_run(argv: tuple[str, ...], **kwargs: object) -> object:
        observed.update({"argv": argv, **kwargs})
        return bounded.BoundedProcessResult(
            args=tuple(argv),
            returncode=0,
            stdout="",
            stderr="",
            timed_out=False,
            output_limit_exceeded=False,
            cancelled=False,
        )

    monkeypatch.setattr(runtime, "run_bounded_process", fake_run)
    monkeypatch.setattr(
        runtime,
        "trusted_tool_path",
        lambda _required: "/test/trusted/bin",
    )

    # When: production worktree creation is invoked.
    runtime.start_issue(main, request, cancelled=callback)

    # Then: the exact repository script/issue/branch contract is the sole mutation seam.
    assert observed["argv"] == (
        "/bin/bash",
        str(main / "scripts" / "start_issue.sh"),
        "1574",
        "feat/example",
        "--base-commit",
        base,
    )
    assert observed["cwd"] == main
    assert observed["cancelled"] is callback
    assert observed["env"] == {
        "PATH": "/test/trusted/bin",
        "LC_ALL": "C",
        "LANG": "C",
    }


def test_start_issue_rejects_noncanonical_target_before_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a request attempting creation at a noncanonical absolute path.
    main, worktree, base = repository(tmp_path)
    request = models.OrchestrationRequest.model_validate(
        request_payload(main, worktree, base), strict=True
    ).model_copy(update={"worktree_path": str(tmp_path / "unexpected")})
    called = False

    def fake_run(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(runtime, "run_bounded_process", fake_run)

    # When/Then: no launcher or unexpected worktree mutation can occur.
    with pytest.raises(runtime.OrchestrationServiceError) as rejected:
        runtime.start_issue(main, request, cancelled=lambda: False)
    assert rejected.value.code == "worktree-mismatch"
    assert called is False
    assert not (tmp_path / "unexpected").exists()


def test_trusted_tool_path_includes_valid_resolved_non_system_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: uv installed in a private directory outside the fixed system paths.
    executable = tmp_path / "private-tools" / "uv"
    executable.parent.mkdir(mode=0o700)
    executable.write_bytes(b"#!/bin/sh\nexit 0\n")
    executable.chmod(0o700)

    def resolved_tool(_name: str, path: str | None = None) -> str:
        return str(executable)

    monkeypatch.setattr(tools.shutil, "which", resolved_tool)

    # When/Then: system tools lead PATH and the private required tool remains available.
    path = tools.trusted_tool_path(("uv",)).split(os.pathsep)
    assert path[:2] == ["/usr/bin", "/bin"]
    assert path[-1] == str(executable.parent.resolve())


def test_trusted_tool_path_rejects_uv_in_world_writable_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "unsafe-tools"
    parent.mkdir(mode=0o700)
    executable = parent / "uv"
    executable.write_bytes(b"#!/bin/sh\nexit 0\n")
    executable.chmod(0o700)
    parent.chmod(0o777)
    real_which = shutil.which

    def resolve_uv(
        name: str,
        mode: int = os.F_OK | os.X_OK,
        path: str | None = None,
    ) -> str | None:
        if name == "uv" and path is None:
            return str(executable)
        return real_which(name, mode=mode, path=path)

    monkeypatch.setattr(tools.shutil, "which", resolve_uv)

    with pytest.raises(tools.OrchestrationServiceError) as rejected:
        tools.trusted_tool_path(("uv",))
    assert rejected.value.code == "tool-unavailable"


def test_trusted_tool_path_rejects_world_writable_uv_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "private-tools"
    parent.mkdir(mode=0o700)
    executable = parent / "uv"
    executable.write_bytes(b"#!/bin/sh\nexit 0\n")
    executable.chmod(0o777)
    real_which = shutil.which

    def resolve_uv(
        name: str,
        mode: int = os.F_OK | os.X_OK,
        path: str | None = None,
    ) -> str | None:
        if name == "uv" and path is None:
            return str(executable)
        return real_which(name, mode=mode, path=path)

    monkeypatch.setattr(tools.shutil, "which", resolve_uv)

    with pytest.raises(tools.OrchestrationServiceError) as rejected:
        tools.trusted_tool_path(("uv",))
    assert rejected.value.code == "tool-unavailable"


def test_private_uv_directory_cannot_shadow_system_bash_or_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private = tmp_path / "private-tools"
    private.mkdir(mode=0o700)
    for name in ("uv", "bash", "git"):
        executable = private / name
        executable.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
        executable.chmod(0o700)
    real_which = tools.shutil.which

    def select_uv(name: str, path: str | None = None) -> object:
        if name == "uv":
            return str(private / "uv")
        return real_which(name, path=path)

    monkeypatch.setattr(tools.shutil, "which", select_uv)

    trusted = tools.trusted_tool_path(("uv",))

    selected_bash = real_which("bash", path=trusted)
    assert selected_bash is not None
    assert Path(selected_bash).resolve(strict=True) == tools.trusted_executable("bash")
    assert real_which("git", path=trusted) == "/usr/bin/git"
    assert trusted.split(os.pathsep)[-1] == str(private)
