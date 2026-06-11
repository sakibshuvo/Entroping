"""Changed Hurl test selection from Git diff."""

import subprocess
from pathlib import Path

import pytest

from entroping.core.git_changed_hurl import (
    GIT_DIFF_TIMEOUT_SECONDS,
    GitChangedHurlError,
    select_changed_hurl_tests,
)


def _git(project_root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(project_root), *args],
        capture_output=True,
        check=True,
        text=True,
    )


def _write_hurl(path: Path, *, body: str = "GET http://localhost/health\nHTTP 200\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _init_repo(project_root: Path) -> None:
    _git(project_root, "init", "-b", "main")
    _git(project_root, "config", "user.email", "entroping@example.test")
    _git(project_root, "config", "user.name", "Entroping Test")


def test_select_changed_hurl_tests_returns_modified_files(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_hurl(tmp_path / "tests" / "health.hurl")
    _write_hurl(tmp_path / "tests" / "checkout.hurl")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")
    (tmp_path / "tests" / "health.hurl").write_text(
        "GET http://localhost/ready\nHTTP 200\n",
        encoding="utf-8",
    )

    selected = select_changed_hurl_tests(project_root=tmp_path, base_ref="HEAD")

    assert selected == ((tmp_path / "tests" / "health.hurl").resolve(),)


def test_select_changed_hurl_tests_skips_deleted_files(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_hurl(tmp_path / "tests" / "health.hurl")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")
    (tmp_path / "tests" / "health.hurl").unlink()

    selected = select_changed_hurl_tests(project_root=tmp_path, base_ref="HEAD")

    assert selected == ()


def test_select_changed_hurl_tests_uses_rename_target(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_hurl(tmp_path / "tests" / "old.hurl")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")
    _git(tmp_path, "mv", "tests/old.hurl", "tests/new.hurl")

    selected = select_changed_hurl_tests(project_root=tmp_path, base_ref="HEAD")

    assert selected == ((tmp_path / "tests" / "new.hurl").resolve(),)


def test_select_changed_hurl_tests_rejects_outside_root_diff_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCompletedProcess:
        returncode = 0
        stdout = b"M\x00../escape.hurl\x00"
        stderr = b""

    monkeypatch.setattr(
        "entroping.core.git_changed_hurl.subprocess.run",
        lambda *args, **kwargs: FakeCompletedProcess(),
    )

    with pytest.raises(GitChangedHurlError, match="outside the project root"):
        select_changed_hurl_tests(project_root=tmp_path, base_ref="main")


def test_select_changed_hurl_tests_ignores_non_hurl_and_missing_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCompletedProcess:
        returncode = 0
        stdout = b"M\x00README.md\x00M\x00tests/missing.hurl\x00"
        stderr = b""

    monkeypatch.setattr(
        "entroping.core.git_changed_hurl.subprocess.run",
        lambda *args, **kwargs: FakeCompletedProcess(),
    )

    selected = select_changed_hurl_tests(project_root=tmp_path, base_ref="main")

    assert selected == ()


def test_select_changed_hurl_tests_runs_git_diff_with_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_timeout: object = None

    class FakeCompletedProcess:
        returncode = 0
        stdout = b""
        stderr = b""

    def fake_run(*args: object, **kwargs: object) -> FakeCompletedProcess:
        nonlocal recorded_timeout
        recorded_timeout = kwargs.get("timeout")
        return FakeCompletedProcess()

    monkeypatch.setattr("entroping.core.git_changed_hurl.subprocess.run", fake_run)

    selected = select_changed_hurl_tests(project_root=tmp_path, base_ref="main")

    assert selected == ()
    assert recorded_timeout == GIT_DIFF_TIMEOUT_SECONDS


def test_select_changed_hurl_tests_reports_git_diff_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired(cmd=["git", "diff"], timeout=GIT_DIFF_TIMEOUT_SECONDS)

    monkeypatch.setattr("entroping.core.git_changed_hurl.subprocess.run", fake_run)

    with pytest.raises(GitChangedHurlError, match="timed out after 30 seconds"):
        select_changed_hurl_tests(project_root=tmp_path, base_ref="main")


def test_select_changed_hurl_tests_rejects_malformed_rename_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCompletedProcess:
        returncode = 0
        stdout = b"R100\x00tests/old.hurl\x00"
        stderr = b""

    monkeypatch.setattr(
        "entroping.core.git_changed_hurl.subprocess.run",
        lambda *args, **kwargs: FakeCompletedProcess(),
    )

    with pytest.raises(GitChangedHurlError, match="Malformed git diff rename/copy record"):
        select_changed_hurl_tests(project_root=tmp_path, base_ref="main")


def test_select_changed_hurl_tests_rejects_malformed_name_status_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCompletedProcess:
        returncode = 0
        stdout = b"M\x00"
        stderr = b""

    monkeypatch.setattr(
        "entroping.core.git_changed_hurl.subprocess.run",
        lambda *args, **kwargs: FakeCompletedProcess(),
    )

    with pytest.raises(GitChangedHurlError, match="Malformed git diff name-status record"):
        select_changed_hurl_tests(project_root=tmp_path, base_ref="main")


def test_select_changed_hurl_tests_reports_no_git_workspace(tmp_path: Path) -> None:
    with pytest.raises(GitChangedHurlError, match="Could not inspect git diff"):
        select_changed_hurl_tests(project_root=tmp_path, base_ref="main")


def test_select_changed_hurl_tests_reports_missing_git_binary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("entroping.core.git_changed_hurl.shutil.which", lambda binary: None)

    with pytest.raises(GitChangedHurlError, match="git executable not found"):
        select_changed_hurl_tests(project_root=tmp_path, base_ref="main")
