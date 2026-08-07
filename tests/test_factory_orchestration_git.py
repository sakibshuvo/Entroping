from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from factory_orchestration_test_support import git, repository, request_payload, update_patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

git_boundary = importlib.import_module("scripts.factory_orchestration_git")
models = importlib.import_module("scripts.factory_orchestration_models")


def _request(main: Path, worktree: Path, base: str) -> object:
    return models.OrchestrationRequest.model_validate(
        request_payload(main, worktree, base), strict=True
    )


def test_reuses_exact_registered_clean_issue_worktree(tmp_path: Path) -> None:
    # Given: exactly one registered clean non-main worktree at the expected base.
    main, worktree, base = repository(tmp_path)

    # When: reuse is validated against shared Git authority.
    snapshot = git_boundary.validate_reusable_worktree(main, _request(main, worktree, base))

    # Then: the canonical identity is returned unchanged.
    assert snapshot.path == worktree.resolve()
    assert snapshot.branch == "feat/example"
    assert snapshot.head == base
    assert snapshot.tree == git(worktree, "rev-parse", "HEAD^{tree}")


@pytest.mark.parametrize("dirty_kind", ["tracked", "staged", "untracked"])
def test_reuse_rejects_every_dirty_state(tmp_path: Path, dirty_kind: str) -> None:
    # Given: a registered issue worktree with one dirty state.
    main, worktree, base = repository(tmp_path)
    if dirty_kind == "untracked":
        (worktree / "untracked.txt").write_text("dirty", encoding="utf-8")
    else:
        (worktree / "docs/user/guide.md").write_text("dirty\n", encoding="utf-8")
        if dirty_kind == "staged":
            git(worktree, "add", "docs/user/guide.md")

    # When/Then: reuse refuses to reset or repair it.
    with pytest.raises(git_boundary.OrchestrationGitError) as exc_info:
        git_boundary.validate_reusable_worktree(main, _request(main, worktree, base))
    assert exc_info.value.code == "worktree-dirty"


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("base_commit", "f" * 40, "stale-base"),
        ("branch", "feat/foreign", "worktree-mismatch"),
        ("common_git_dir", "/tmp/foreign.git", "worktree-mismatch"),
        ("worktree_path", "/tmp/foreign-worktree", "worktree-mismatch"),
    ],
)
def test_reuse_rejects_stale_or_foreign_identity(
    tmp_path: Path,
    field: str,
    value: str,
    reason: str,
) -> None:
    # Given: a request whose Git identity differs from the registered worktree.
    main, worktree, base = repository(tmp_path)
    payload = request_payload(main, worktree, base)
    payload[field] = value
    request = models.OrchestrationRequest.model_validate(payload, strict=True)

    # When/Then: identity validation fails closed with a fixed reason code.
    with pytest.raises(git_boundary.OrchestrationGitError) as exc_info:
        git_boundary.validate_reusable_worktree(main, request)
    assert exc_info.value.code == reason


def test_reuse_rejects_symlink_alias_of_registered_worktree(tmp_path: Path) -> None:
    main, worktree, base = repository(tmp_path)
    alias = tmp_path / "worktree-alias"
    alias.symlink_to(worktree, target_is_directory=True)
    payload = request_payload(main, worktree, base)
    payload["worktree_path"] = str(alias)
    request = models.OrchestrationRequest.model_validate(payload, strict=True)

    with pytest.raises(git_boundary.OrchestrationGitError) as exc_info:
        git_boundary.validate_reusable_worktree(main, request)

    assert exc_info.value.code == "worktree-mismatch"


def test_reuse_rejects_detached_head_and_active_git_operation(tmp_path: Path) -> None:
    # Given: a detached issue worktree.
    main, worktree, base = repository(tmp_path)
    git(worktree, "checkout", "--detach", base)

    # When/Then: detached reuse is foreign.
    with pytest.raises(git_boundary.OrchestrationGitError) as detached:
        git_boundary.validate_reusable_worktree(main, _request(main, worktree, base))
    assert detached.value.code == "worktree-mismatch"

    # Given: the expected branch is restored but a merge operation is active.
    git(worktree, "checkout", "feat/example")
    git_dir = Path(git(worktree, "rev-parse", "--git-dir"))
    if not git_dir.is_absolute():
        git_dir = (worktree / git_dir).resolve()
    (git_dir / "MERGE_HEAD").write_text(base, encoding="ascii")

    # When/Then: active repository operations block reuse.
    with pytest.raises(git_boundary.OrchestrationGitError) as active:
        git_boundary.validate_reusable_worktree(main, _request(main, worktree, base))
    assert active.value.code == "worktree-mismatch"


def test_exact_patch_applies_only_in_issue_worktree_and_binds_git_truth(tmp_path: Path) -> None:
    # Given: clean main and issue checkouts sharing one base.
    main, worktree, base = repository(tmp_path)
    request = _request(main, worktree, base)
    main_status = git(main, "status", "--porcelain=v1", "-z")

    # When: the exact proposal bytes pass check and apply inside the issue worktree.
    truth = git_boundary.apply_exact_patch(main, request, update_patch())

    # Then: Git truth binds the resulting diff while main remains byte-identical.
    assert (worktree / "docs/user/guide.md").read_text(encoding="utf-8") == "Version two.\n"
    assert (main / "docs/user/guide.md").read_text(encoding="utf-8") == "Version one.\n"
    assert git(main, "rev-parse", "HEAD") == base
    assert git(main, "status", "--porcelain=v1", "-z") == main_status
    assert truth.paths == ("docs/user/guide.md",)
    assert len(truth.diff_sha256) == 64
    assert truth.head == base


def test_exact_patch_binds_new_regular_file_content_in_git_diff(tmp_path: Path) -> None:
    # Given: a valid proposal that adds one in-scope regular file.
    main, worktree, base = repository(tmp_path)
    payload = request_payload(main, worktree, base)
    payload["allowed_scopes"] = ("docs/user/new.md",)
    payload["allowed_scope_digest"] = hashlib.sha256(b'["docs/user/new.md"]').hexdigest()
    request = models.OrchestrationRequest.model_validate(payload, strict=True)
    proposal = (
        b"diff --git a/docs/user/new.md b/docs/user/new.md\n"
        b"new file mode 100644\n"
        b"index 0000000..3b18e51\n"
        b"--- /dev/null\n"
        b"+++ b/docs/user/new.md\n"
        b"@@ -0,0 +1 @@\n"
        b"+hello world\n"
    )

    # When: exact apply accepts the new regular file.
    truth = git_boundary.apply_exact_patch(main, request, proposal)
    raw_diff = subprocess.run(
        ["git", "diff", "--binary", "--full-index", "--no-ext-diff", "--no-renames", base, "--"],
        cwd=worktree,
        check=True,
        capture_output=True,
    ).stdout

    # Then: path and content are present in the canonical revision-bound diff.
    assert (worktree / "docs/user/new.md").read_bytes() == b"hello world\n"
    assert truth.paths == ("docs/user/new.md",)
    assert truth.diff_sha256 == hashlib.sha256(raw_diff).hexdigest()
    assert truth.manifest_sha256 == hashlib.sha256(base.encode() + b"\0" + raw_diff).hexdigest()
    assert b"+hello world" in raw_diff


@pytest.mark.parametrize(
    ("path", "lane"),
    (
        ("src/entroping/generated.py", "tiny-docs"),
        ("tests/test_generated.py", "tiny-docs"),
        ("scripts/generated.sh", "tiny-docs"),
        ("docs/user/generated.py", "tiny-docs"),
        ("docs/meta/generated.md", "tiny-docs"),
        ("docs/user/guide.md", "tests-only"),
    ),
)
def test_scope_rejects_non_static_tier_a_envelope(
    tmp_path: Path,
    path: str,
    lane: str,
) -> None:
    main, worktree, base = repository(tmp_path)
    payload = request_payload(main, worktree, base)
    payload["verification_lane"] = lane
    payload["allowed_scopes"] = (path,)
    payload["allowed_scope_digest"] = hashlib.sha256(
        json.dumps([path], separators=(",", ":")).encode()
    ).hexdigest()
    request = models.OrchestrationRequest.model_validate(payload, strict=True)

    with pytest.raises(git_boundary.OrchestrationGitError) as exc_info:
        git_boundary.validate_inspected_scope(
            request,
            {"changed_files": [path]},
            repo_root=main,
        )

    assert exc_info.value.code == "scope-denied"
