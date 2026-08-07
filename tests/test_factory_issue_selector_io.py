from __future__ import annotations

import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import factory_issue_selector_github as github  # noqa: E402
from scripts import factory_issue_selector_local as local  # noqa: E402
from scripts import factory_issue_selector_service as service  # noqa: E402
from scripts.bounded_process import BoundedProcessResult  # noqa: E402
from scripts.factory_issue_selector import build_parser  # noqa: E402
from scripts.factory_issue_selector_github import GitHubStateError  # noqa: E402
from scripts.factory_issue_selector_models import (  # noqa: E402
    ActiveState,
    GitHubSnapshot,
    JsonObject,
    JsonValue,
    SnapshotMetadata,
)
from scripts.factory_issue_selector_parser import parse_issue  # noqa: E402

AS_OF = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _trusted_gh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(github, "trusted_executable", lambda _name: Path("/usr/bin/false"))


def _issue(number: int, *, state: str = "open") -> JsonObject:
    return {
        "number": number,
        "title": f"Issue {number}",
        "state": state,
        "html_url": f"https://github.com/sakibshuvo/Entroping/issues/{number}",
        "body": (
            "## Outcome\n\nSelect.\n\n## Scope\n\nRead.\n\n"
            "## Non-goals\n\nNo dispatch.\n\n"
            "## Acceptance criteria\n\n- Deterministic.\n\n"
            "## Verification\n\nVerification lane: `normal-code`.\n\n"
            "## Autonomy\n\nTier A.\n\n"
            f"## Allowed files\n\n- scripts/issue_{number}.py"
        ),
        "labels": [
            {"name": "type:feature"},
            {"name": "priority:p1"},
            {"name": "status:ready"},
            {"name": "autonomy:tier-a"},
        ],
        "assignees": [],
        "milestone": {"title": "Factory"},
    }


def _completed(
    payload: JsonValue, *, returncode: int = 0, stderr: str = ""
) -> BoundedProcessResult:
    return BoundedProcessResult(
        args=("gh",),
        returncode=returncode,
        stdout=json.dumps(payload),
        stderr=stderr,
        timed_out=False,
        output_limit_exceeded=False,
    )


def _git_runner(
    worktree_output: str, branch_output: str = ""
) -> Callable[..., tuple[str, bool]]:
    def run(repo_root: Path, *arguments: str) -> tuple[str, bool]:
        del repo_root
        return (
            (worktree_output, True)
            if arguments[:2] == ("worktree", "list")
            else (branch_output, True)
        )

    return run


def test_github_refresh_builds_complete_sanitized_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        (
            _completed([[_issue(90), _issue(89, state="closed")]]),
            _completed(
                [
                    {
                        "number": 10,
                        "author": {"is_bot": False},
                        "closingIssuesReferences": [{"number": 90}],
                        "files": [{"path": "scripts/issue_90.py"}],
                    }
                ]
            ),
        )
    )
    monkeypatch.setattr(github, "run_subprocess", lambda *args, **kwargs: next(responses))

    snapshot = github.refresh_snapshot(
        repo="sakibshuvo/Entroping", as_of=AS_OF, ttl_seconds=60
    )

    assert snapshot.metadata.complete is True
    assert snapshot.open_pr_issue_numbers == frozenset({90})
    assert snapshot.open_pr_scopes == ("scripts/issue_90.py",)
    assert tuple(issue.number for issue in snapshot.issues) == (89, 90)
    assert "body" not in repr(snapshot).lower()


def test_github_refresh_fails_closed_on_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        github,
        "run_subprocess",
        lambda *args, **kwargs: _completed(
            [], returncode=1, stderr="API rate limit exceeded"
        ),
    )

    with pytest.raises(GitHubStateError, match="github-rate-limited"):
        github.refresh_snapshot(
            repo="sakibshuvo/Entroping", as_of=AS_OF, ttl_seconds=60
        )


def test_github_refresh_fails_closed_on_bounded_output_overflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    overflow = BoundedProcessResult(
        args=("gh",),
        returncode=-9,
        stdout="",
        stderr="",
        timed_out=False,
        output_limit_exceeded=True,
    )
    monkeypatch.setattr(github, "run_subprocess", lambda *args, **kwargs: overflow)

    with pytest.raises(GitHubStateError, match="github-snapshot-incomplete"):
        github.refresh_snapshot(
            repo="sakibshuvo/Entroping", as_of=AS_OF, ttl_seconds=60
        )


def test_github_refresh_marks_unassociated_open_pr_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        (
            _completed([[_issue(91)]]),
            _completed(
                [
                    {
                        "number": 11,
                        "author": {"is_bot": False},
                        "closingIssuesReferences": [],
                        "files": [{"path": "scripts/unassociated.py"}],
                    }
                ]
            ),
        )
    )
    monkeypatch.setattr(github, "run_subprocess", lambda *args, **kwargs: next(responses))

    snapshot = github.refresh_snapshot(
        repo="sakibshuvo/Entroping", as_of=AS_OF, ttl_seconds=60
    )

    assert snapshot.metadata.complete is False


def test_github_refresh_tracks_scoped_bot_pr_without_issue_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        (
            _completed([[_issue(91)]]),
            _completed(
                [
                    {
                        "number": 11,
                        "author": {"is_bot": True},
                        "closingIssuesReferences": [],
                        "files": [{"path": ".github/dependabot.yml"}],
                    }
                ]
            ),
        )
    )
    monkeypatch.setattr(github, "run_subprocess", lambda *args, **kwargs: next(responses))

    snapshot = github.refresh_snapshot(
        repo="sakibshuvo/Entroping", as_of=AS_OF, ttl_seconds=60
    )

    assert snapshot.metadata.complete is True
    assert snapshot.open_pr_issue_numbers == frozenset()
    assert snapshot.open_pr_scopes == (".github/dependabot.yml",)


def test_local_state_combines_worktree_queue_pr_and_lease_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = github_snapshot(owned_issue=92)
    queue = tmp_path / ".entroping" / "ai-jobs" / "running"
    queue.mkdir(parents=True)
    (queue / "job.json").write_text(
        json.dumps({"issue": "93", "files": ["scripts/queued-receipt.py"]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        local,
        "_run_git",
        _git_runner(
            (
                f"worktree {tmp_path}\nHEAD abc\nbranch refs/heads/main\n\n"
                f"worktree {tmp_path.parent / 'Entroping-issue-94'}\nHEAD def\n"
                "branch refs/heads/feat/example\n"
            ),
            f"feat/example\t{tmp_path.parent / 'Entroping-issue-94'}\n",
        ),
    )

    state = local.collect_active_state(
        repo_root=tmp_path,
        snapshot=snapshot,
        lease_state_complete=True,
        lease_issue_numbers=frozenset({95}),
        lease_scopes=("scripts/lease.py",),
    )

    assert state.complete is True
    assert state.owned_issue_numbers == frozenset({92, 93, 94, 95})
    assert "scripts/lease.py" in state.occupied_scopes
    assert "scripts/queued-receipt.py" in state.occupied_scopes


def test_local_state_fails_closed_for_unassociated_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        local,
        "_run_git",
        _git_runner(
            (
                f"worktree {tmp_path}\nHEAD abc\nbranch refs/heads/main\n\n"
                f"worktree {tmp_path.parent / 'mystery-worktree'}\nHEAD def\n"
            ),
        ),
    )

    state = local.collect_active_state(
        repo_root=tmp_path,
        snapshot=github_snapshot(),
        lease_state_complete=True,
        lease_issue_numbers=frozenset(),
        lease_scopes=(),
    )

    assert state.complete is False


def test_local_state_owns_current_issue_worktree_and_skips_primary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path / "Entroping-issue-1567"
    monkeypatch.setattr(
        local,
        "_run_git",
        _git_runner(
            (
                f"worktree {tmp_path / 'Entroping'}\nHEAD abc\n"
                "branch refs/heads/main\n\n"
                f"worktree {repo_root}\nHEAD def\n"
                "branch refs/heads/feat/selector\n\n"
                f"worktree {tmp_path / 'Entroping-issue-94'}\nHEAD ghi\n"
                "branch refs/heads/feat/other\n"
            ),
            (
                f"feat/selector\t{repo_root}\n"
                f"feat/other\t{tmp_path / 'Entroping-issue-94'}\n"
            ),
        ),
    )

    state = local.collect_active_state(
        repo_root=repo_root,
        snapshot=github_snapshot(extra_issue_numbers=(1567,)),
        lease_state_complete=True,
        lease_issue_numbers=frozenset(),
        lease_scopes=(),
    )

    assert state.complete is True
    assert state.owned_issue_numbers == frozenset({94, 1567})


def test_local_state_fails_closed_for_unassociated_current_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path / "Entroping-issue-1567"
    monkeypatch.setattr(
        local,
        "_run_git",
        _git_runner(
            f"worktree {tmp_path / 'Entroping'}\nHEAD abc\nbranch refs/heads/main\n",
            f"feat/unassociated\t{repo_root}\n",
        ),
    )

    state = local.collect_active_state(
        repo_root=repo_root,
        snapshot=github_snapshot(),
        lease_state_complete=True,
        lease_issue_numbers=frozenset(),
        lease_scopes=(),
    )

    assert state.complete is False


def test_local_state_owns_current_issue_worktree_after_branch_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path / "Entroping-issue-1567"
    monkeypatch.setattr(
        local,
        "_run_git",
        _git_runner(
            (
                f"worktree {tmp_path / 'Entroping'}\nHEAD abc\n"
                "branch refs/heads/main\n\n"
                f"worktree {repo_root}\nHEAD def\n"
                "branch refs/heads/feat/selector\n"
            ),
        ),
    )

    state = local.collect_active_state(
        repo_root=repo_root,
        snapshot=github_snapshot(extra_issue_numbers=(1567,)),
        lease_state_complete=True,
        lease_issue_numbers=frozenset(),
        lease_scopes=(),
    )

    assert state.complete is True
    assert 1567 in state.owned_issue_numbers


def test_local_state_fails_closed_for_detached_current_issue_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path / "Entroping-issue-1567"
    monkeypatch.setattr(
        local,
        "_run_git",
        _git_runner(
            (
                f"worktree {tmp_path / 'Entroping'}\nHEAD abc\n"
                "branch refs/heads/main\n\n"
                f"worktree {repo_root}\nHEAD def\ndetached\n"
            ),
        ),
    )

    state = local.collect_active_state(
        repo_root=repo_root,
        snapshot=github_snapshot(extra_issue_numbers=(1567,)),
        lease_state_complete=True,
        lease_issue_numbers=frozenset(),
        lease_scopes=(),
    )

    assert state.complete is False
    assert 1567 in state.owned_issue_numbers


def test_local_state_owns_standalone_issue_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        local,
        "_run_git",
        _git_runner(
            f"worktree {tmp_path}\nHEAD abc\nbranch refs/heads/main\n",
            "feat/issue-96-selector\t\n",
        ),
    )

    state = local.collect_active_state(
        repo_root=tmp_path,
        snapshot=github_snapshot(extra_issue_numbers=(96,)),
        lease_state_complete=True,
        lease_issue_numbers=frozenset(),
        lease_scopes=(),
    )

    assert state.complete is True
    assert 96 in state.owned_issue_numbers


def test_local_state_fails_closed_for_unassociated_unmerged_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        local,
        "_run_git",
        _git_runner(
            f"worktree {tmp_path}\nHEAD abc\nbranch refs/heads/main\n",
            "feat/unassociated\t\n",
        ),
    )

    state = local.collect_active_state(
        repo_root=tmp_path,
        snapshot=github_snapshot(),
        lease_state_complete=True,
        lease_issue_numbers=frozenset(),
        lease_scopes=(),
    )

    assert state.complete is False


def test_service_does_not_fall_back_to_stale_cache_after_failed_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stale = github_snapshot(
        fetched_at=AS_OF - timedelta(minutes=2),
        expires_at=AS_OF - timedelta(minutes=1),
    )
    monkeypatch.setattr(service, "read_snapshot", lambda *args, **kwargs: stale)
    monkeypatch.setattr(service, "_utc_now", lambda: AS_OF)
    monkeypatch.setattr(
        service,
        "refresh_snapshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            GitHubStateError("github-refresh-failed")
        ),
    )

    result = service.select_live(
        repo_root=tmp_path,
        repo="sakibshuvo/Entroping",
        ttl_seconds=60,
        force_refresh=False,
        autonomy_ceiling="tier-a",
        lease_state_complete=True,
        lease_issue_numbers=frozenset(),
        lease_scopes=(),
    )

    assert result.status == "blocked"
    assert result.selected is None
    assert result.errors == ("github-refresh-failed",)


def test_service_blocks_future_cache_without_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    future = github_snapshot(
        fetched_at=AS_OF + timedelta(seconds=10),
        expires_at=AS_OF + timedelta(seconds=70),
    )
    monkeypatch.setattr(service, "read_snapshot", lambda *args, **kwargs: future)
    monkeypatch.setattr(service, "_utc_now", lambda: AS_OF)

    def forbidden_refresh(**kwargs: JsonValue) -> GitHubSnapshot:
        _ = kwargs
        raise AssertionError("clock rollback must not refresh")

    monkeypatch.setattr(service, "refresh_snapshot", forbidden_refresh)

    result = service.select_live(
        repo_root=tmp_path,
        repo="sakibshuvo/Entroping",
        ttl_seconds=60,
        force_refresh=False,
        autonomy_ceiling="tier-a",
        lease_state_complete=True,
        lease_issue_numbers=frozenset(),
        lease_scopes=(),
    )

    assert result.errors == ("snapshot-clock-rollback",)


@pytest.mark.parametrize(
    ("post_refresh", "error"),
    (
        (AS_OF + timedelta(seconds=1), "snapshot-stale"),
        (AS_OF - timedelta(seconds=1), "snapshot-clock-rollback"),
    ),
)
def test_service_rechecks_freshness_after_refresh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    post_refresh: datetime,
    error: str,
) -> None:
    times = iter((AS_OF, post_refresh))
    snapshot = github_snapshot(fetched_at=AS_OF, expires_at=AS_OF + timedelta(seconds=1))
    monkeypatch.setattr(service, "_utc_now", lambda: next(times))
    monkeypatch.setattr(service, "refresh_snapshot", lambda **kwargs: snapshot)
    monkeypatch.setattr(service, "write_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        service,
        "collect_active_state",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("stale refresh must not inspect active state")
        ),
    )

    result = service.select_live(
        repo_root=tmp_path,
        repo="sakibshuvo/Entroping",
        ttl_seconds=1,
        force_refresh=True,
        autonomy_ceiling="tier-a",
        lease_state_complete=True,
        lease_issue_numbers=frozenset(),
        lease_scopes=(),
    )

    assert result.status == "blocked"
    assert result.errors == (error,)


def test_cli_does_not_expose_a_caller_controlled_freshness_clock() -> None:
    assert "--as-of" not in build_parser().format_help()


def test_service_rejects_issue_scope_through_existing_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (tmp_path / "alias").symlink_to(target, target_is_directory=True)
    raw_issue = _issue(97)
    body = raw_issue["body"]
    assert isinstance(body, str)
    raw_issue["body"] = body.replace("scripts/issue_97.py", "alias/file.py")
    snapshot = GitHubSnapshot(
        metadata=SnapshotMetadata(
            repo="sakibshuvo/Entroping",
            fetched_at=AS_OF - timedelta(seconds=10),
            expires_at=AS_OF + timedelta(seconds=50),
            complete=True,
        ),
        issues=(parse_issue(raw_issue),),
        open_pr_issue_numbers=frozenset(),
    )
    monkeypatch.setattr(service, "read_snapshot", lambda *args, **kwargs: snapshot)
    monkeypatch.setattr(service, "_utc_now", lambda: AS_OF)
    monkeypatch.setattr(
        service,
        "collect_active_state",
        lambda **kwargs: ActiveState(True, frozenset(), ()),
    )

    result = service.select_live(
        repo_root=tmp_path,
        repo="sakibshuvo/Entroping",
        ttl_seconds=60,
        force_refresh=False,
        autonomy_ceiling="tier-a",
        lease_state_complete=True,
        lease_issue_numbers=frozenset(),
        lease_scopes=(),
    )

    assert result.status == "none"
    assert result.rejections[0].reason == "ambiguous-file-scope"


@pytest.mark.parametrize("scope", ("alias/*.py", "alias/**"))
def test_service_rejects_wildcard_scope_matching_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scope: str
) -> None:
    alias = tmp_path / "alias"
    alias.mkdir()
    target = tmp_path / "target.py"
    target.write_text("safe = True\n", encoding="utf-8")
    (alias / "linked.py").symlink_to(target)
    raw_issue = _issue(98)
    body = raw_issue["body"]
    assert isinstance(body, str)
    raw_issue["body"] = body.replace("scripts/issue_98.py", scope)
    snapshot = GitHubSnapshot(
        metadata=SnapshotMetadata(
            repo="sakibshuvo/Entroping",
            fetched_at=AS_OF - timedelta(seconds=10),
            expires_at=AS_OF + timedelta(seconds=50),
            complete=True,
        ),
        issues=(parse_issue(raw_issue),),
        open_pr_issue_numbers=frozenset(),
    )
    monkeypatch.setattr(service, "read_snapshot", lambda *args, **kwargs: snapshot)
    monkeypatch.setattr(service, "_utc_now", lambda: AS_OF)
    monkeypatch.setattr(
        service,
        "collect_active_state",
        lambda **kwargs: ActiveState(True, frozenset(), ()),
    )

    result = service.select_live(
        repo_root=tmp_path,
        repo="sakibshuvo/Entroping",
        ttl_seconds=60,
        force_refresh=False,
        autonomy_ceiling="tier-a",
        lease_state_complete=True,
        lease_issue_numbers=frozenset(),
        lease_scopes=(),
    )

    assert result.status == "none"
    assert result.rejections[0].reason == "ambiguous-file-scope"


def test_wildcard_scope_without_symlink_is_safe(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "selector.py").write_text("safe = True\n", encoding="utf-8")

    assert local.scope_has_symlink(tmp_path, "scripts/*.py") is False
    assert local.scope_has_symlink(tmp_path, "scripts/**") is False


def github_snapshot(
    *,
    owned_issue: int | None = None,
    fetched_at: datetime = AS_OF - timedelta(seconds=10),
    expires_at: datetime = AS_OF + timedelta(seconds=50),
    extra_issue_numbers: tuple[int, ...] = (),
) -> GitHubSnapshot:
    issue_numbers = {
        number
        for number in (owned_issue, 93, 94, 95, *extra_issue_numbers)
        if number is not None
    }
    issues = tuple(parse_issue(_issue(number)) for number in sorted(issue_numbers))
    return GitHubSnapshot(
        metadata=SnapshotMetadata(
            repo="sakibshuvo/Entroping",
            fetched_at=fetched_at,
            expires_at=expires_at,
            complete=True,
        ),
        issues=issues,
        open_pr_issue_numbers=frozenset({owned_issue}) if owned_issue else frozenset(),
    )
