from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from shutil import copy2

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from factory_pr_delivery_test_support import (  # noqa: E402
    accepted_artifacts,
    write_delivery_request,
)

from scripts.bounded_process import (  # noqa: E402
    BoundedProcessError,
    BoundedProcessResult,
)
from scripts.factory_orchestration_errors import OrchestrationServiceError  # noqa: E402
from scripts.factory_pr_delivery_cleanup import (  # noqa: E402
    _FILE_OPEN_FLAGS,
    DeliveryCleanupError,
    run_strict_finish_issue,
)
from scripts.factory_pr_delivery_github import REPOSITORY  # noqa: E402
from scripts.factory_pr_delivery_github_io import GitHubTransportError  # noqa: E402
from scripts.factory_pr_delivery_io import load_delivery_envelope  # noqa: E402
from scripts.factory_pr_delivery_journal import DeliveryJournal  # noqa: E402
from scripts.factory_pr_delivery_journal_records import (  # noqa: E402
    DeliveryJournalRecord,
    read_terminal_receipt,
)
from scripts.factory_pr_delivery_models import CommitResult, DeliveryEnvelope  # noqa: E402
from scripts.factory_pr_delivery_receipts import encode_delivery_receipt  # noqa: E402

_FINISH_AUTHORITY_FILES = (
    "finish_issue.sh",
    "_project_board_lib.sh",
    "factory_metrics_archive.py",
    "finish_issue_replay_evidence.py",
)


def _accepted_envelope(tmp_path: Path) -> tuple[Path, DeliveryEnvelope]:
    main, _worktree, payload = accepted_artifacts(tmp_path)
    request_path = tmp_path / "private/delivery-request.json"
    write_delivery_request(request_path, payload)
    return main, load_delivery_envelope(request_path)


def _ensure_finish_script(main: Path) -> None:
    destination = main / "scripts"
    destination.mkdir(parents=True, exist_ok=True)
    for name in _FINISH_AUTHORITY_FILES:
        copy2(REPO_ROOT / "scripts" / name, destination / name)


def _commit_result(base: str) -> CommitResult:
    return CommitResult(
        accepted_local_head=base,
        committed_head="b" * 40,
        commit_parent=base,
        commit_tree="c" * 40,
        accepted_diff_sha256="1" * 64,
        committed_diff_sha256="1" * 64,
        accepted_manifest_sha256="2" * 64,
        committed_manifest_sha256="2" * 64,
        approved_path_sha256="3" * 64,
    )


def _seed_merged_record(main: Path, envelope: DeliveryEnvelope) -> DeliveryJournalRecord:
    journal = DeliveryJournal(main)
    result = _commit_result(envelope.orchestration_request.base_commit)
    _ = journal.prepare(envelope)
    _ = journal.commit_intent(
        envelope,
        committed_head=result.committed_head,
        commit_parent=result.commit_parent,
        commit_tree=result.commit_tree,
    )
    _ = journal.committed(envelope)
    _ = journal.push_intent(envelope)
    _ = journal.pushed(envelope, remote_head=result.committed_head)
    _ = journal.merge_intent(
        envelope,
        pr_number=42,
        merge_head=result.committed_head,
        ci_digest="d" * 64,
    )
    return journal.merged(envelope, merged_head=result.committed_head)


def _seed_pushed_record(
    _main: Path,
    _envelope: DeliveryEnvelope,
    base_record: DeliveryJournalRecord,
) -> DeliveryJournalRecord:
    return replace(base_record, lifecycle="pushed", reason="pushed")


def _replace_with_completed_terminal(
    _main: Path,
    _envelope: DeliveryEnvelope,
    record: DeliveryJournalRecord,
) -> DeliveryJournalRecord:
    terminal = read_terminal_receipt(record)
    if terminal is None:
        raise AssertionError("record must have terminal")
    completed = terminal.model_copy(update={"lifecycle": "completed", "reason": "completed"})
    raw, digest = encode_delivery_receipt(completed)
    return replace(
        record,
        terminal_receipt_json=raw,
        terminal_receipt_sha256=digest,
    )


def _replace_with_non_authoritative_terminal(
    _main: Path,
    _envelope: DeliveryEnvelope,
    record: DeliveryJournalRecord,
) -> DeliveryJournalRecord:
    terminal = read_terminal_receipt(record)
    if terminal is None:
        raise AssertionError("record must have terminal")
    non_authoritative = terminal.model_copy(update={"authoritative": False})
    raw, digest = encode_delivery_receipt(non_authoritative)
    return replace(
        record,
        terminal_receipt_json=raw,
        terminal_receipt_sha256=digest,
    )


def _seed_invalid_request_record(
    _main: Path,
    _envelope: DeliveryEnvelope,
    record: DeliveryJournalRecord,
) -> DeliveryJournalRecord:
    return replace(
        record,
        request_id="delivery_invalid" + "a" * 55,
    )


def _fake_success_result(command: tuple[str, ...], **_kwargs: object) -> BoundedProcessResult:
    return BoundedProcessResult(
        args=command,
        returncode=0,
        stdout="",
        stderr="",
        timed_out=False,
        output_limit_exceeded=False,
        cancelled=False,
    )


def _patch_trusted_cleanup_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    trusted_home = tmp_path / "trusted-home"
    trusted_home.mkdir(exist_ok=True)
    trusted_env = {
        "HOME": str(trusted_home),
        "PATH": "/opt/missing",
        "LC_ALL": "C.UTF-8",
        "LANG": "en_US.UTF-8",
        "GH_PAGER": "cat",
        "GH_FORCE_TTY": "0",
        "NO_COLOR": "1",
    }
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_cleanup.trusted_gh_contract",
        lambda: (trusted_home, trusted_env),
    )
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_cleanup.trusted_tool_path",
        lambda _required: "/usr/local/bin:/usr/bin:/bin",
    )


def test_strict_finish_issue_invokes_fixed_finish_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope = _accepted_envelope(tmp_path)
    _ensure_finish_script(main)
    record = _seed_merged_record(main, envelope)
    captured: dict[str, object] = {}

    _patch_trusted_cleanup_environment(monkeypatch, tmp_path)
    trusted_home = tmp_path / "trusted-home"

    def fake_run(command: tuple[str, ...], **kwargs: object) -> BoundedProcessResult:
        pass_fds = kwargs.get("pass_fds")
        if (
            not isinstance(pass_fds, tuple)
            or len(pass_fds) != 4
            or not all(isinstance(descriptor, int) for descriptor in pass_fds)
        ):
            raise AssertionError("missing trusted finish descriptors")
        script_fd, project_lib_fd, metrics_fd, replay_fd = pass_fds
        captured["command"] = command
        captured["cwd"] = kwargs["cwd"]
        captured["timeout_seconds"] = kwargs["timeout_seconds"]
        captured["max_output_bytes"] = kwargs["max_output_bytes"]
        captured["env"] = kwargs["env"]
        captured["kwargs"] = kwargs
        captured["pass_fds"] = pass_fds
        captured["script_fd"] = script_fd
        captured["project_lib_fd"] = project_lib_fd
        captured["metrics_fd"] = metrics_fd
        captured["replay_fd"] = replay_fd
        captured["authority_bytes"] = tuple(
            os.pread(descriptor, 1_048_576, 0) for descriptor in pass_fds
        )
        return _fake_success_result(command)

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_cleanup.run_bounded_process",
        fake_run,
    )

    run_strict_finish_issue(main, envelope, record)

    script_fd = captured["script_fd"]
    project_lib_fd = captured["project_lib_fd"]
    metrics_fd = captured["metrics_fd"]
    replay_fd = captured["replay_fd"]
    assert isinstance(script_fd, int)
    assert isinstance(project_lib_fd, int)
    assert isinstance(metrics_fd, int)
    assert isinstance(replay_fd, int)
    assert captured["command"] == (
        "/bin/bash",
        f"/dev/fd/{script_fd}",
        str(envelope.orchestration_request.issue_number),
        "--worktree",
        str(envelope.worktree_path),
        "--expected-pr",
        str(record.merge_pr_number),
        "--expected-head",
        record.merge_head,
        "--expected-branch",
        envelope.orchestration_request.branch,
    )
    assert captured["cwd"] == main
    assert captured["timeout_seconds"] == 300.0
    assert captured["max_output_bytes"] == 1_048_576
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    capture_stdout = kwargs.get("capture_stdout")
    input_bytes = kwargs.get("input_bytes")
    assert capture_stdout is False
    assert input_bytes is None
    pass_fds = (script_fd, project_lib_fd, metrics_fd, replay_fd)
    assert captured["pass_fds"] == pass_fds
    assert captured["authority_bytes"] == tuple(
        (main / "scripts" / name).read_bytes() for name in _FINISH_AUTHORITY_FILES
    )
    assert captured["env"] == {
        "HOME": str(trusted_home),
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LC_ALL": "C.UTF-8",
        "LANG": "en_US.UTF-8",
        "GIT_PAGER": "cat",
        "GH_PAGER": "cat",
        "GH_FORCE_TTY": "0",
        "NO_COLOR": "1",
        "ENTROPING_REPO": REPOSITORY,
        "ENTROPING_PROJECT_OWNER": REPOSITORY.split("/")[0],
        "ENTROPING_PROJECT_NUMBER": "1",
        "ENTROPING_FINISH_PROJECT_LIB": f"/dev/fd/{project_lib_fd}",
        "ENTROPING_FINISH_METRICS_HELPER": f"/dev/fd/{metrics_fd}",
        "ENTROPING_FINISH_REPLAY_HELPER": f"/dev/fd/{replay_fd}",
    }
    for descriptor in pass_fds:
        with pytest.raises(OSError):
            os.fstat(descriptor)


def test_strict_finish_issue_rejects_symlinked_scripts_directory_before_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope = _accepted_envelope(tmp_path)
    _ensure_finish_script(main)
    record = _seed_merged_record(main, envelope)
    outside_scripts = tmp_path / "outside-scripts"
    (main / "scripts").rename(outside_scripts)
    (main / "scripts").symlink_to(outside_scripts, target_is_directory=True)
    launched = False

    def fail_if_called(*_args: object, **_kwargs: object) -> BoundedProcessResult:
        nonlocal launched
        launched = True
        raise AssertionError("symlinked scripts directory must not launch")

    _patch_trusted_cleanup_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_cleanup.run_bounded_process",
        fail_if_called,
    )

    with pytest.raises(DeliveryCleanupError) as exc_info:
        run_strict_finish_issue(main, envelope, record)

    assert exc_info.value.code == "cleanup-invalid"
    assert not launched


def test_strict_finish_issue_pins_open_script_across_path_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope = _accepted_envelope(tmp_path)
    _ensure_finish_script(main)
    record = _seed_merged_record(main, envelope)
    authority_paths = tuple(main / "scripts" / name for name in _FINISH_AUTHORITY_FILES)
    original = tuple(path.read_bytes() for path in authority_paths)
    replacement = b"replacement authority bytes\n"
    captured_fds: tuple[int, int, int, int] | None = None

    def fake_run(command: tuple[str, ...], **kwargs: object) -> BoundedProcessResult:
        nonlocal captured_fds
        pass_fds = kwargs.get("pass_fds")
        if not isinstance(pass_fds, tuple) or len(pass_fds) != 4:
            raise AssertionError("missing trusted finish descriptors")
        if not all(isinstance(descriptor, int) for descriptor in pass_fds):
            raise AssertionError("invalid trusted finish descriptors")
        captured_fds = pass_fds
        environment = kwargs.get("env")
        if not isinstance(environment, dict):
            raise AssertionError("missing fixed finish environment")
        capability_paths = (
            command[1],
            environment.get("ENTROPING_FINISH_PROJECT_LIB"),
            environment.get("ENTROPING_FINISH_METRICS_HELPER"),
            environment.get("ENTROPING_FINISH_REPLAY_HELPER"),
        )
        for path in authority_paths:
            path.unlink()
            path.write_bytes(replacement)
            path.chmod(0o755)
        for descriptor, capability, expected in zip(
            pass_fds, capability_paths, original, strict=True
        ):
            assert capability == f"/dev/fd/{descriptor}"
            assert os.pread(descriptor, len(expected) + 1, 0) == expected
        return _fake_success_result(command)

    _patch_trusted_cleanup_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_cleanup.run_bounded_process",
        fake_run,
    )

    run_strict_finish_issue(main, envelope, record)

    assert all(path.read_bytes() == replacement for path in authority_paths)
    assert captured_fds is not None
    for descriptor in captured_fds:
        with pytest.raises(OSError):
            os.fstat(descriptor)


def test_strict_finish_issue_closes_descriptors_after_launch_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope = _accepted_envelope(tmp_path)
    _ensure_finish_script(main)
    record = _seed_merged_record(main, envelope)
    captured_fds: tuple[int, int, int, int] | None = None

    def fake_run(_command: tuple[str, ...], **kwargs: object) -> BoundedProcessResult:
        nonlocal captured_fds
        pass_fds = kwargs.get("pass_fds")
        if not isinstance(pass_fds, tuple) or len(pass_fds) != 4:
            raise AssertionError("missing trusted finish descriptors")
        if not all(isinstance(descriptor, int) for descriptor in pass_fds):
            raise AssertionError("invalid trusted finish descriptors")
        captured_fds = pass_fds
        raise BoundedProcessError("simulated launch failure")

    _patch_trusted_cleanup_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_cleanup.run_bounded_process",
        fake_run,
    )

    with pytest.raises(DeliveryCleanupError) as exc_info:
        run_strict_finish_issue(main, envelope, record)

    assert exc_info.value.code == "cleanup-uncertain"
    assert captured_fds is not None
    for descriptor in captured_fds:
        with pytest.raises(OSError):
            os.fstat(descriptor)


def test_strict_finish_issue_rejects_trusted_environment_failures_before_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope = _accepted_envelope(tmp_path)
    record = _seed_merged_record(main, envelope)
    called = False

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True
        raise AssertionError("launch must not happen")

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_cleanup.trusted_gh_contract",
        lambda: (_ for _ in ()).throw(GitHubTransportError("transport-failed")),
    )
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_cleanup.run_bounded_process",
        fail_if_called,
    )

    with pytest.raises(DeliveryCleanupError) as exc:
        run_strict_finish_issue(main, envelope, record)
    assert exc.value.code == "cleanup-invalid"
    assert not called


def test_strict_finish_issue_propagates_trust_helper_bug_before_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope = _accepted_envelope(tmp_path)
    _ensure_finish_script(main)
    record = _seed_merged_record(main, envelope)
    called = False

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True
        raise AssertionError("launch should not happen")

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_cleanup.trusted_gh_contract",
        lambda: (_ for _ in ()).throw(AssertionError("developer bug")),
    )
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_cleanup.run_bounded_process",
        fail_if_called,
    )

    with pytest.raises(AssertionError):
        run_strict_finish_issue(main, envelope, record)
    assert not called

    trusted_home = tmp_path / "trusted-home-2"
    trusted_home.mkdir()
    trusted_env = {
        "HOME": str(trusted_home),
        "PATH": "/opt/homebrew/bin",
        "LC_ALL": "C.UTF-8",
        "LANG": "en_US.UTF-8",
    }
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_cleanup.trusted_gh_contract",
        lambda: (trusted_home, trusted_env),
    )
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_cleanup.trusted_tool_path",
        lambda _required: (_ for _ in ()).throw(
            OrchestrationServiceError("tool-unavailable")
        ),
    )
    with pytest.raises(DeliveryCleanupError) as exc:
        run_strict_finish_issue(main, envelope, record)
    assert exc.value.code == "cleanup-invalid"
    assert not called


def test_strict_finish_issue_allows_missing_worktree_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope = _accepted_envelope(tmp_path)
    _ensure_finish_script(main)
    record = _seed_merged_record(main, envelope)
    envelope = envelope.model_copy(update={"worktree_path": main / "missing-worktree"})
    captured: dict[str, object] = {}

    def fake_run(command: tuple[str, ...], **kwargs: object) -> BoundedProcessResult:
        captured["command"] = command
        return _fake_success_result(command)

    _patch_trusted_cleanup_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_cleanup.run_bounded_process",
        fake_run,
    )

    run_strict_finish_issue(main, envelope, record)

    command = captured["command"]
    assert isinstance(command, tuple)
    assert command[3] == "--worktree"
    assert command[4] == str(main / "missing-worktree")


@pytest.mark.parametrize(
    "record_factory",
    [
        _seed_pushed_record,
        _replace_with_completed_terminal,
        _replace_with_non_authoritative_terminal,
        _seed_invalid_request_record,
    ],
    ids=["nonterminal", "completed", "non_authoritative", "invalid_record"],
)
def test_strict_finish_issue_rejects_non_strict_or_invalid_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    record_factory: Callable[
        [Path, DeliveryEnvelope, DeliveryJournalRecord],
        DeliveryJournalRecord,
    ],
) -> None:
    main, envelope = _accepted_envelope(tmp_path)
    base_record = _seed_merged_record(main, envelope)
    record = record_factory(main, envelope, base_record)

    def fail_if_called(*_args: object, **_kwargs: object) -> BoundedProcessResult:
        raise AssertionError("process launch must not happen")

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_cleanup.run_bounded_process",
        fail_if_called,
    )

    with pytest.raises(DeliveryCleanupError) as exc:
        run_strict_finish_issue(main, envelope, record)
    assert exc.value.code == "cleanup-invalid"


@pytest.mark.parametrize(
    ("label", "outcome"),
    [
        (
            "nonzero",
            lambda _command: BoundedProcessResult(
                args=(),
                returncode=1,
                stdout="",
                stderr="",
                timed_out=False,
                output_limit_exceeded=False,
                cancelled=False,
            ),
        ),
        (
            "timed_out",
            lambda _command: BoundedProcessResult(
                args=(),
                returncode=0,
                stdout="",
                stderr="",
                timed_out=True,
                output_limit_exceeded=False,
                cancelled=False,
            ),
        ),
        (
            "output_limit",
            lambda _command: BoundedProcessResult(
                args=(),
                returncode=0,
                stdout="",
                stderr="",
                timed_out=False,
                output_limit_exceeded=True,
                cancelled=False,
            ),
        ),
        (
            "cancelled",
            lambda _command: BoundedProcessResult(
                args=(),
                returncode=0,
                stdout="",
                stderr="",
                timed_out=False,
                output_limit_exceeded=False,
                cancelled=True,
            ),
        ),
        (
            "launch_error",
            lambda _command: (_ for _ in ()).throw(BoundedProcessError("boom")),
        ),
    ],
)
def test_strict_finish_issue_ambiguous_launch_outcomes_are_uncertain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    outcome: Callable[[tuple[str, ...]], BoundedProcessResult | BoundedProcessError],
) -> None:
    main, envelope = _accepted_envelope(tmp_path)
    _ensure_finish_script(main)
    record = _seed_merged_record(main, envelope)

    def fake_run(command: tuple[str, ...], **_kwargs: object) -> BoundedProcessResult:
        result = outcome(command)
        if isinstance(result, BoundedProcessResult):
            return result
        raise result
    _patch_trusted_cleanup_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_cleanup.run_bounded_process",
        fake_run,
    )

    with pytest.raises(DeliveryCleanupError) as exc:
        run_strict_finish_issue(main, envelope, record)
    assert exc.value.code == "cleanup-uncertain"
    _ = label


@pytest.mark.parametrize("kind", ["missing-script", "symlink-script"])
def test_strict_finish_issue_rejects_invalid_finish_script(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    main, envelope = _accepted_envelope(tmp_path)
    record = _seed_merged_record(main, envelope)
    bad_root = tmp_path / f"bad-script-{kind}"
    bad_scripts = bad_root / "scripts"
    bad_scripts.mkdir(parents=True)

    if kind == "symlink-script":
        (bad_scripts / "finish_issue.sh").symlink_to(
            main / "scripts" / "finish_issue.sh"
        )

    envelope = envelope.model_copy(update={"main_root": bad_root})
    _patch_trusted_cleanup_environment(monkeypatch, tmp_path)

    def fail_if_called(*_args: object, **_kwargs: object) -> BoundedProcessResult:
        raise AssertionError("launch must not happen")

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_cleanup.run_bounded_process",
        fail_if_called,
    )

    with pytest.raises(DeliveryCleanupError) as exc:
        run_strict_finish_issue(bad_root, envelope, record)
    assert exc.value.code == "cleanup-invalid"
    assert exc.value.__cause__ is None


@pytest.mark.parametrize(
    "damage",
    ["root-mode", "scripts-mode", "script-mode", "script-hardlink"],
)
def test_strict_finish_issue_rejects_unsafe_finish_authority_before_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    damage: str,
) -> None:
    main, envelope = _accepted_envelope(tmp_path)
    _ensure_finish_script(main)
    record = _seed_merged_record(main, envelope)
    script = main / "scripts" / "finish_issue.sh"
    if damage == "root-mode":
        main.chmod(0o775)
    elif damage == "scripts-mode":
        script.parent.chmod(0o775)
    elif damage == "script-mode":
        script.chmod(0o775)
    else:
        os.link(script, tmp_path / "finish-issue-hardlink")
    launched = False

    def fail_if_called(*_args: object, **_kwargs: object) -> BoundedProcessResult:
        nonlocal launched
        launched = True
        raise AssertionError("unsafe finish authority must not launch")

    _patch_trusted_cleanup_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_cleanup.run_bounded_process",
        fail_if_called,
    )

    with pytest.raises(DeliveryCleanupError) as exc_info:
        run_strict_finish_issue(main, envelope, record)

    assert exc_info.value.code == "cleanup-invalid"
    assert not launched


@pytest.mark.parametrize(
    ("helper_name", "damage"),
    [
        (helper_name, damage)
        for helper_name in _FINISH_AUTHORITY_FILES[1:]
        for damage in ("symlink", "hardlink", "mode")
    ],
)
def test_strict_finish_issue_rejects_unsafe_helper_before_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    helper_name: str,
    damage: str,
) -> None:
    main, envelope = _accepted_envelope(tmp_path)
    _ensure_finish_script(main)
    record = _seed_merged_record(main, envelope)
    helper = main / "scripts" / helper_name
    if damage == "symlink":
        outside = tmp_path / helper_name
        helper.replace(outside)
        helper.symlink_to(outside)
    elif damage == "hardlink":
        os.link(helper, tmp_path / helper_name)
    else:
        helper.chmod(0o775)
    launched = False

    def fail_if_called(*_args: object, **_kwargs: object) -> BoundedProcessResult:
        nonlocal launched
        launched = True
        raise AssertionError("unsafe finish helper must not launch")

    _patch_trusted_cleanup_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_cleanup.run_bounded_process",
        fail_if_called,
    )

    with pytest.raises(DeliveryCleanupError) as exc_info:
        run_strict_finish_issue(main, envelope, record)

    assert exc_info.value.code == "cleanup-invalid"
    assert not launched


@pytest.mark.parametrize("authority_name", _FINISH_AUTHORITY_FILES)
def test_strict_finish_issue_rejects_fifo_authority_without_blocking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    authority_name: str,
) -> None:
    nonblocking = getattr(os, "O_NONBLOCK", 0)
    assert nonblocking != 0
    assert _FILE_OPEN_FLAGS & nonblocking
    main, envelope = _accepted_envelope(tmp_path)
    _ensure_finish_script(main)
    record = _seed_merged_record(main, envelope)
    authority = main / "scripts" / authority_name
    authority.unlink()
    os.mkfifo(authority, mode=0o600)
    launched = False

    def fail_if_called(*_args: object, **_kwargs: object) -> BoundedProcessResult:
        nonlocal launched
        launched = True
        raise AssertionError("FIFO finish authority must not launch")

    _patch_trusted_cleanup_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_cleanup.run_bounded_process",
        fail_if_called,
    )

    with pytest.raises(DeliveryCleanupError) as exc_info:
        run_strict_finish_issue(main, envelope, record)

    assert exc_info.value.code == "cleanup-invalid"
    assert not launched
@pytest.mark.parametrize(
    ("label", "patch_target"),
    [
        (
            "resolve_os_error",
            lambda _self: (_ for _ in ()).throw(OSError("resolve-fail")),
        ),
        (
            "resolve_runtime_error",
            lambda _self: (_ for _ in ()).throw(RuntimeError("resolve-fail")),
        ),
        (
            "stat_os_error",
            lambda _self: (_ for _ in ()).throw(OSError("stat-fail")),
        ),
        (
            "stat_runtime_error",
            lambda _self: (_ for _ in ()).throw(RuntimeError("stat-fail")),
        ),
    ],
)
def test_strict_finish_issue_rejects_unresolvable_repo_root_without_launch(
    label: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    patch_target: Callable[[Path | int], object],
    ) -> None:
    _ = label
    main, envelope = _accepted_envelope(tmp_path)
    record = _seed_merged_record(main, envelope)

    def fail_if_called(*_args: object, **_kwargs: object) -> BoundedProcessResult:
        raise AssertionError("launch must not happen")

    if "resolve" in label:
        monkeypatch.setattr(
            "scripts.factory_pr_delivery_cleanup.Path.resolve",
            lambda *args, **kwargs: patch_target(*args),
        )
    else:
        monkeypatch.setattr(
            "scripts.factory_pr_delivery_cleanup._descriptor_metadata",
            lambda *args, **kwargs: patch_target(*args),
        )
    _patch_trusted_cleanup_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_cleanup.run_bounded_process",
        fail_if_called,
    )

    with pytest.raises(DeliveryCleanupError) as exc:
        run_strict_finish_issue(main, envelope, record)
    assert exc.value.code == "cleanup-invalid"
    assert exc.value.__cause__ is not None



def test_strict_finish_issue_rejects_root_mismatch_without_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope = _accepted_envelope(tmp_path)
    record = _seed_merged_record(main, envelope)

    def fail_if_called(*_args: object, **_kwargs: object) -> BoundedProcessResult:
        raise AssertionError("launch must not happen")

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_cleanup.run_bounded_process",
        fail_if_called,
    )

    with pytest.raises(DeliveryCleanupError) as exc:
        run_strict_finish_issue(main.parent, envelope, record)
    assert exc.value.code == "cleanup-invalid"
