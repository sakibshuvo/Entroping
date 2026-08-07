"""Regression coverage for aggregate-PR finish evidence."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Final, TypedDict, cast

import pytest

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
FINISH_SCRIPT: Final = REPO_ROOT / "scripts" / "finish_issue.sh"


class ManifestEntryPayload(TypedDict):
    issue_number: int
    source_branch: str
    source_commit: str
    integrated_commit: str
    patch_id: str


class ManifestPayload(TypedDict):
    schema_version: str
    repository: str
    aggregate_pr_number: int
    aggregate_merge_commit: str
    entries: list[ManifestEntryPayload]


class Fixture(TypedDict):
    repo: Path
    worktree: Path
    manifest: Path
    source_commit: str
    integrated_commit: str
    merge_commit: str
    patch_id: str
    base: str


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result


def _branch_exists(repo: Path) -> bool:
    return (
        _git(
            repo,
            "show-ref",
            "--verify",
            "--quiet",
            "refs/heads/feat/aggregate-source",
            check=False,
        ).returncode
        == 0
    )


def _patch_id(cwd: Path, commit: str) -> str:
    patch = subprocess.run(
        ["git", "diff-tree", "--root", "--no-commit-id", "-p", "--binary", commit],
        cwd=cwd,
        check=True,
        capture_output=True,
    ).stdout
    result = subprocess.run(
        ["git", "patch-id", "--stable"],
        input=patch,
        check=True,
        capture_output=True,
    )
    return result.stdout.decode().split()[0]


def _write_fake_gh(
    tmp_path: Path,
    *,
    issue_json: dict[str, object],
    pr_json: dict[str, object],
) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "gh-calls.log"
    fake = bin_dir / "gh"
    issue_payload = shlex.quote(json.dumps(issue_json, separators=(",", ":")))
    pr_payload = shlex.quote(json.dumps(pr_json, separators=(",", ":")))
    calls_path = shlex.quote(str(calls))
    fields_payload = shlex.quote(
        '{"fields":[{"name":"Status","id":"field-id",'
        '"options":[{"name":"Done","id":"done-id"}]}]}'
    )
    items_payload = shlex.quote(
        '{"items":[{"id":"item-id","content":{"number":99}}]}'
    )
    fake.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        f"printf '%s\\n' \"$*\" >> {calls_path}\n"
        'case "$1 $2" in\n'
        f"  'issue view') printf '%s' {issue_payload} ;;\n"
        f"  'pr view') printf '%s' {pr_payload} ;;\n"
        "  'api') printf '%s\\n' '999' ;;\n"
        "  'issue edit'|'project item-edit') : ;;\n"
        "  'project view') printf '%s\\n' '{\"id\":\"project-id\"}' ;;\n"
        f"  'project field-list') printf '%s\\n' {fields_payload} ;;\n"
        f"  'project item-list') printf '%s\\n' {items_payload} ;;\n"
        '  *) echo "unexpected gh command" >&2; exit 2 ;;\n'
        "esac\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    return bin_dir


def _fixture(tmp_path: Path) -> Fixture:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "remote", "add", "origin", "git@github.com:sakibshuvo/Entroping.git")
    (repo / ".gitignore").write_text(".entroping/\n", encoding="utf-8")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", ".gitignore", "README.md")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()

    worktree = tmp_path / "Entroping-issue-99"
    _git(repo, "worktree", "add", str(worktree), "-b", "feat/aggregate-source")
    (worktree / "README.md").write_text("aggregate\n", encoding="utf-8")
    _git(worktree, "add", "README.md")
    _git(worktree, "commit", "-m", "source change")
    source_commit = _git(worktree, "rev-parse", "HEAD").stdout.strip()

    _git(repo, "switch", "-c", "aggregate-pr")
    _git(repo, "cherry-pick", "--no-commit", source_commit)
    _git(repo, "commit", "-m", "integrated aggregate change")
    integrated_commit = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "switch", "main")
    _git(repo, "merge", "--no-ff", "aggregate-pr", "-m", "merge aggregate PR")
    merge_commit = _git(repo, "rev-parse", "HEAD").stdout.strip()
    patch_id = _patch_id(repo, source_commit)
    assert patch_id == _patch_id(repo, integrated_commit)

    manifest = repo / "aggregate-evidence.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "entroping.aggregate-pr-finish-evidence.v1",
                "repository": "sakibshuvo/Entroping",
                "aggregate_pr_number": 1537,
                "aggregate_merge_commit": merge_commit,
                "entries": [
                    {
                        "issue_number": 99,
                        "source_branch": "feat/aggregate-source",
                        "source_commit": source_commit,
                        "integrated_commit": integrated_commit,
                        "patch_id": patch_id,
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _git(repo, "add", "aggregate-evidence.json")
    _git(repo, "commit", "-m", "record aggregate evidence")
    return {
        "repo": repo,
        "worktree": worktree,
        "manifest": manifest,
        "source_commit": source_commit,
        "integrated_commit": integrated_commit,
        "merge_commit": merge_commit,
        "patch_id": patch_id,
        "base": base,
    }


def _write_fake_remote_python(
    fake_bin: Path,
    responses: tuple[tuple[str, int], ...],
) -> Path:
    real_uv = shutil.which("uv")
    assert real_uv is not None
    calls = fake_bin.parent / "remote-helper-calls"
    cases = "\n".join(
        f"  {index}) printf '%s\\n' {shlex.quote(response)}; exit {code} ;;"
        for index, (response, code) in enumerate(responses)
    )
    wrapper = fake_bin / "uv"
    wrapper.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "if [ \"$1\" = run ] && [ \"$2\" = python ]; then\n"
        "  case \"$3\" in */finish_issue_remote_branch.py) ;; *) "
        f"exec {shlex.quote(real_uv)} \"$@\" ;; esac\n"
        "else\n"
        f"  exec {shlex.quote(real_uv)} \"$@\"\n"
        "fi\n"
        f"count_file={shlex.quote(str(calls))}\n"
        "count=$(cat \"$count_file\" 2>/dev/null || printf '0')\n"
        "printf '%s' $((count + 1)) > \"$count_file\"\n"
        "case \"$count\" in\n"
        f"{cases}\n"
        "  *) exit 2 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    ambient_python = fake_bin / "python3"
    ambient_python.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "case \"$1\" in\n"
        "  */finish_issue_remote_branch.py) exit 91 ;;\n"
        f"  *) exec {shlex.quote(sys.executable)} \"$@\" ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    ambient_python.chmod(0o755)
    return calls


def _gh_payloads(fixture: Fixture) -> tuple[dict[str, object], dict[str, object]]:
    issue: dict[str, object] = {
        "title": "aggregate fixture",
        "url": "https://github.com/sakibshuvo/Entroping/issues/99",
        "state": "CLOSED",
        "closedByPullRequestsReferences": [{"number": 1537}],
    }
    pr: dict[str, object] = {
        "number": 1537,
        "url": "https://github.com/sakibshuvo/Entroping/pull/1537",
        "state": "MERGED",
        "headRefName": "aggregate-pr",
        "headRefOid": fixture["integrated_commit"],
        "mergedAt": "2026-08-07T12:00:00Z",
        "mergeCommit": {"oid": fixture["merge_commit"]},
        "commits": [{"oid": fixture["integrated_commit"]}],
        "statusCheckRollup": [
            {
                "__typename": "CheckRun",
                "name": "checks",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
            }
        ],
    }
    return issue, pr


def _run_finish(
    fixture: Fixture,
    fake_bin: Path,
    *args: str,
    remote_responses: tuple[tuple[str, int], ...] | None = None,
) -> subprocess.CompletedProcess[str]:
    repo = fixture["repo"]
    if remote_responses is not None:
        _write_fake_remote_python(fake_bin, remote_responses)
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
    environment["ENTROPING_WORKTREE_PARENT"] = str(repo.parent)
    return subprocess.run(
        ["/bin/bash", str(FINISH_SCRIPT), *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def _rewrite_manifest(fixture: Fixture, payload: ManifestPayload) -> None:
    manifest = fixture["manifest"]
    manifest.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
    _git(fixture["repo"], "add", manifest.name)
    _git(fixture["repo"], "commit", "-m", "mutate fixture evidence")


def test_aggregate_dry_run_verifies_mapping_without_mutation(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    issue, pr = _gh_payloads(fixture)
    fake_bin = _write_fake_gh(tmp_path, issue_json=issue, pr_json=pr)
    manifest = fixture["manifest"]

    result = _run_finish(
        fixture,
        fake_bin,
        "99",
        "--dry-run",
        "--aggregate-evidence",
        str(manifest),
        remote_responses=(("absent", 0),),
    )

    assert result.returncode == 0, result.stderr
    assert "Aggregate PR: #1537" in result.stdout
    assert f"Integrated commit: {fixture['integrated_commit']}" in result.stdout
    assert f"Stable patch ID: {fixture['patch_id']}" in result.stdout
    assert fixture["worktree"].exists()
    assert (
        _git(
            fixture["repo"],
            "show-ref",
            "--verify",
            "--quiet",
            "refs/heads/feat/aggregate-source",
            check=False,
        ).returncode
        == 0
    )
    assert not (fixture["repo"] / ".entroping" / "finish-issue-replay").exists()
    gh_calls = (tmp_path / "gh-calls.log").read_text(encoding="utf-8")
    assert "issue edit" not in gh_calls
    assert "project " not in gh_calls


def test_aggregate_real_cleanup_removes_only_mapped_source_branch(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    issue, pr = _gh_payloads(fixture)
    fake_bin = _write_fake_gh(tmp_path, issue_json=issue, pr_json=pr)
    manifest = fixture["manifest"]

    result = _run_finish(
        fixture,
        fake_bin,
        "99",
        "--aggregate-evidence",
        str(manifest),
        remote_responses=(
            (f"present:{fixture['source_commit']}", 0),
            ("deleted", 0),
            ("absent", 0),
        ),
    )

    assert result.returncode == 0, result.stderr
    assert not fixture["worktree"].exists()
    assert (
        _git(
            fixture["repo"],
            "show-ref",
            "--verify",
            "--quiet",
            "refs/heads/feat/aggregate-source",
            check=False,
        ).returncode
        == 1
    )
    assert (
        _git(
            fixture["repo"],
            "show-ref",
            "--verify",
            "--quiet",
            "refs/heads/aggregate-pr",
            check=False,
        ).returncode
        == 0
    )
    assert "Finish workflow complete." in result.stdout
    assert (tmp_path / "remote-helper-calls").read_text(encoding="utf-8") == "3"


def _aggregate_replay_stage(fixture: Fixture) -> str:
    proof = fixture["repo"] / ".entroping" / "finish-issue-replay" / "issue-99.json"
    payload = cast(dict[str, str], json.loads(proof.read_text(encoding="utf-8")))
    return payload["stage"]


def test_aggregate_real_cleanup_accepts_already_absent_remote_branch(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    issue, pr = _gh_payloads(fixture)
    fake_bin = _write_fake_gh(tmp_path, issue_json=issue, pr_json=pr)
    manifest = fixture["manifest"]

    result = _run_finish(
        fixture,
        fake_bin,
        "99",
        "--aggregate-evidence",
        str(manifest),
        remote_responses=(("absent", 0), ("absent", 0)),
    )

    assert result.returncode == 0, result.stderr
    assert not fixture["worktree"].exists()
    assert not _branch_exists(fixture["repo"])
    assert _aggregate_replay_stage(fixture) == "branch-deletion-attempted"
    assert (tmp_path / "remote-helper-calls").read_text(encoding="utf-8") == "2"


def test_aggregate_rejects_mismatched_remote_head_before_local_cleanup(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    issue, pr = _gh_payloads(fixture)
    fake_bin = _write_fake_gh(tmp_path, issue_json=issue, pr_json=pr)
    manifest = fixture["manifest"]

    result = _run_finish(
        fixture,
        fake_bin,
        "99",
        "--aggregate-evidence",
        str(manifest),
        remote_responses=((f"present:{'b' * 40}", 0),),
    )

    assert result.returncode == 1
    assert "remote source branch head does not match" in result.stderr
    assert fixture["worktree"].exists()
    assert _branch_exists(fixture["repo"])
    assert not (fixture["repo"] / ".entroping" / "finish-issue-replay").exists()


@pytest.mark.parametrize(
    "responses",
    [
        (("present:{head}", 0), ("", 1)),
        (("present:{head}", 0), ("deleted", 0), ("", 1)),
    ],
    ids=("delete-failure", "absence-query-failure"),
)
def test_aggregate_remote_failure_stops_before_labels_and_projects(
    tmp_path: Path,
    responses: tuple[tuple[str, int], ...],
) -> None:
    fixture = _fixture(tmp_path)
    issue, pr = _gh_payloads(fixture)
    fake_bin = _write_fake_gh(tmp_path, issue_json=issue, pr_json=pr)
    manifest = fixture["manifest"]
    resolved = tuple(
        (response.format(head=fixture["source_commit"]), code) for response, code in responses
    )

    result = _run_finish(
        fixture,
        fake_bin,
        "99",
        "--aggregate-evidence",
        str(manifest),
        remote_responses=resolved,
    )

    assert result.returncode == 1
    assert "remote source branch" in result.stderr
    assert not fixture["worktree"].exists()
    assert not _branch_exists(fixture["repo"])
    assert _aggregate_replay_stage(fixture) == "remote-branch-deletion-attempted"
    gh_calls = (tmp_path / "gh-calls.log").read_text(encoding="utf-8")
    assert "issue edit" not in gh_calls
    assert "project " not in gh_calls


@pytest.mark.parametrize(
    "responses",
    [
        (
            ("present:{head}", 0),
            ("", 1),
            ("present:{head}", 0),
            ("deleted", 0),
            ("absent", 0),
        ),
        (
            ("present:{head}", 0),
            ("deleted", 0),
            ("", 1),
            ("present:{head}", 0),
            ("deleted", 0),
            ("absent", 0),
        ),
    ],
    ids=("delete-failure-replay", "absence-query-failure-replay"),
)
def test_aggregate_replay_after_remote_failure_finishes_once(
    tmp_path: Path,
    responses: tuple[tuple[str, int], ...],
) -> None:
    fixture = _fixture(tmp_path)
    issue, pr = _gh_payloads(fixture)
    fake_bin = _write_fake_gh(tmp_path, issue_json=issue, pr_json=pr)
    manifest = fixture["manifest"]
    resolved = tuple(
        (response.format(head=fixture["source_commit"]), code) for response, code in responses
    )

    first = _run_finish(
        fixture,
        fake_bin,
        "99",
        "--aggregate-evidence",
        str(manifest),
        remote_responses=resolved,
    )

    assert first.returncode == 1
    assert _aggregate_replay_stage(fixture) == "remote-branch-deletion-attempted"
    assert not fixture["worktree"].exists()
    assert not _branch_exists(fixture["repo"])

    second = _run_finish(
        fixture,
        fake_bin,
        "99",
        "--aggregate-evidence",
        str(manifest),
    )

    assert second.returncode == 0, second.stderr
    assert "Verified remote source branch absent" in second.stdout
    assert "Finish workflow complete." in second.stdout
    assert _aggregate_replay_stage(fixture) == "remote-branch-deletion-attempted"
    assert (tmp_path / "remote-helper-calls").read_text(encoding="utf-8") == str(len(resolved))
    gh_calls = (tmp_path / "gh-calls.log").read_text(encoding="utf-8").splitlines()
    assert sum(call.startswith("issue edit ") for call in gh_calls) == 2
    assert sum(call.startswith("project item-edit ") for call in gh_calls) == 1
    assert (
        _git(
            fixture["repo"],
            "show-ref",
            "--verify",
            "--quiet",
            "refs/heads/aggregate-pr",
            check=False,
        ).returncode
        == 0
    )


@pytest.mark.parametrize(
    ("name", "mutator"),
    [
        (
            "unmapped",
            lambda payload: payload["entries"][0].__setitem__("issue_number", 100),
        ),
        (
            "wrong-source",
            lambda payload: payload["entries"][0].__setitem__("source_commit", "f" * 40),
        ),
        (
            "wrong-branch",
            lambda payload: payload["entries"][0].__setitem__(
                "source_branch", "feat/other-source"
            ),
        ),
        (
            "wrong-repository",
            lambda payload: payload.__setitem__("repository", "attacker/other"),
        ),
        (
            "patch-mismatch",
            lambda payload: payload["entries"][0].__setitem__("patch_id", "0" * 40),
        ),
    ],
)
def test_aggregate_invalid_mapping_fails_before_cleanup(
    tmp_path: Path,
    name: str,
    mutator: Callable[[ManifestPayload], None],
) -> None:
    del name
    fixture = _fixture(tmp_path)
    manifest = fixture["manifest"]
    payload = cast(ManifestPayload, json.loads(manifest.read_text(encoding="utf-8")))
    mutator(payload)
    _rewrite_manifest(fixture, payload)
    issue, pr = _gh_payloads(fixture)
    fake_bin = _write_fake_gh(tmp_path, issue_json=issue, pr_json=pr)

    result = _run_finish(fixture, fake_bin, "99", "--aggregate-evidence", str(manifest))

    assert result.returncode == 1
    assert "aggregate evidence is invalid or unsafe" in result.stderr
    assert fixture["worktree"].exists()
    assert (
        _git(
            fixture["repo"],
            "show-ref",
            "--verify",
            "--quiet",
            "refs/heads/feat/aggregate-source",
            check=False,
        ).returncode
        == 0
    )


def test_aggregate_rejects_dirty_worktree(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    fixture["worktree"].joinpath("README.md").write_text("dirty\n", encoding="utf-8")
    issue, pr = _gh_payloads(fixture)
    fake_bin = _write_fake_gh(tmp_path, issue_json=issue, pr_json=pr)
    manifest = fixture["manifest"]

    result = _run_finish(fixture, fake_bin, "99", "--aggregate-evidence", str(manifest))

    assert result.returncode == 1
    assert "aggregate evidence is invalid or unsafe" in result.stderr
    assert fixture["worktree"].exists()


def test_aggregate_rejects_duplicate_manifest_mapping(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    manifest = fixture["manifest"]
    payload = cast(ManifestPayload, json.loads(manifest.read_text(encoding="utf-8")))
    payload["entries"].append(payload["entries"][0])
    _rewrite_manifest(fixture, payload)
    issue, pr = _gh_payloads(fixture)
    fake_bin = _write_fake_gh(tmp_path, issue_json=issue, pr_json=pr)

    result = _run_finish(fixture, fake_bin, "99", "--aggregate-evidence", str(manifest))

    assert result.returncode == 1
    assert "aggregate evidence is invalid or unsafe" in result.stderr
    assert fixture["worktree"].exists()


def test_aggregate_rejects_malformed_tracked_manifest(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    manifest = fixture["manifest"]
    manifest.write_text('{"schema_version":"wrong"}\n', encoding="utf-8")
    _git(fixture["repo"], "add", manifest.name)
    _git(fixture["repo"], "commit", "-m", "malform fixture evidence")
    issue, pr = _gh_payloads(fixture)
    fake_bin = _write_fake_gh(tmp_path, issue_json=issue, pr_json=pr)

    result = _run_finish(
        fixture, fake_bin, "99", "--dry-run", "--aggregate-evidence", str(manifest)
    )

    assert result.returncode == 1
    assert "aggregate evidence is invalid or unsafe" in result.stderr
    assert fixture["worktree"].exists()


@pytest.mark.parametrize(
    "name",
    ("wrong-pr", "wrong-merge", "integrated-not-in-pr", "missing-object", "not-reachable"),
)
def test_aggregate_rejects_incomplete_live_integration(tmp_path: Path, name: str) -> None:
    fixture = _fixture(tmp_path)
    issue, pr = _gh_payloads(fixture)
    manifest = fixture["manifest"]
    if name == "wrong-pr":
        pr["number"] = 1538
    elif name == "wrong-merge":
        pr["mergeCommit"] = {"oid": "0" * 40}
    elif name == "integrated-not-in-pr":
        pr["commits"] = [{"oid": fixture["source_commit"]}]
    elif name in {"missing-object", "not-reachable"}:
        payload = cast(ManifestPayload, json.loads(manifest.read_text(encoding="utf-8")))
        replacement = "0" * 40 if name == "missing-object" else fixture["base"]
        payload["aggregate_merge_commit"] = replacement
        _rewrite_manifest(fixture, payload)
        pr["mergeCommit"] = {"oid": replacement}

    fake_bin = _write_fake_gh(tmp_path, issue_json=issue, pr_json=pr)
    result = _run_finish(
        fixture, fake_bin, "99", "--dry-run", "--aggregate-evidence", str(manifest)
    )

    assert result.returncode == 1
    assert "aggregate evidence is invalid or unsafe" in result.stderr
    assert fixture["worktree"].exists()
