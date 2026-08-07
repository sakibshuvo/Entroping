from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_issue_selector_models import GitHubSnapshot, SnapshotMetadata  # noqa: E402
from scripts.factory_issue_selector_parser import parse_issue  # noqa: E402
from scripts.factory_policy_import_closure import policy_import_closure  # noqa: E402

_AUTHORITY_SOURCES = {
    path.relative_to(REPO_ROOT).as_posix(): path.read_bytes()
    for parent in (REPO_ROOT / "scripts", REPO_ROOT / "src/entroping")
    for path in parent.rglob("*.py")
}
POLICY_FILES = policy_import_closure(
    roots=("scripts/factory_scheduler_delivery.py",),
    sources=_AUTHORITY_SOURCES,
)


def git(repo: Path, *args: str, input_bytes: bytes | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        input=input_bytes,
    )
    return result.stdout.decode().strip()


def repository(tmp_path: Path) -> tuple[Path, Path, str]:
    main = tmp_path / "Entroping"
    main.mkdir(parents=True)
    git(main, "init", "-b", "main")
    git(main, "config", "user.email", "test@example.invalid")
    git(main, "config", "user.name", "Test Maintainer")
    guide = main / "docs" / "user" / "guide.md"
    guide.parent.mkdir(parents=True)
    guide.write_text("Version one.\n", encoding="utf-8")
    gate = main / "scripts" / "doc_governance_check.sh"
    gate.parent.mkdir(parents=True)
    gate.write_text(
        "#!/bin/bash\nset -euo pipefail\n"
        "git diff --name-only --diff-filter=ACMR HEAD -- | "
        "awk 'BEGIN{ok=1} !/^docs\\/(product|user)\\//{ok=0} END{exit !ok}'\n",
        encoding="utf-8",
    )
    gate.chmod(0o755)
    for relative in POLICY_FILES:
        destination = main / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((REPO_ROOT / relative).read_bytes())
    (main / ".gitignore").write_text(".entroping/\n", encoding="utf-8")
    git(main, "add", ".")
    git(main, "commit", "-m", "initial")
    base = git(main, "rev-parse", "HEAD")
    worktree = tmp_path / "Entroping-issue-1574"
    git(main, "worktree", "add", "-b", "feat/example", str(worktree), base)
    return main, worktree, base


def admission_repository(tmp_path: Path) -> Path:
    main = tmp_path / "Entroping"
    main.mkdir(parents=True)
    git(main, "init", "-b", "main")
    git(main, "config", "user.email", "test@example.invalid")
    git(main, "config", "user.name", "Test Maintainer")
    guide = main / "docs/user/guide.md"
    guide.parent.mkdir(parents=True)
    guide.write_text("Version one.\n", encoding="utf-8")
    gate = main / "scripts/doc_governance_check.sh"
    gate.parent.mkdir(parents=True)
    gate.write_text(
        "#!/bin/bash\nset -euo pipefail\n"
        "git diff --name-only --diff-filter=ACMR HEAD -- | "
        "awk 'BEGIN{ok=1} !/^docs\\/(product|user)\\//{ok=0} END{exit !ok}'\n",
        encoding="utf-8",
    )
    gate.chmod(0o755)
    for relative in POLICY_FILES:
        destination = main / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((REPO_ROOT / relative).read_bytes())
    for relative in ("scripts/start_issue.sh", "scripts/_project_board_lib.sh"):
        destination = main / relative
        destination.write_bytes((REPO_ROOT / relative).read_bytes())
        destination.chmod(0o755)
    (main / ".gitignore").write_text(".entroping/\n", encoding="utf-8")
    git(main, "add", ".")
    git(main, "commit", "-m", "initial")
    return main


def selection_snapshot(*, scope: str = "docs/user/guide.md") -> GitHubSnapshot:
    now = datetime.now(UTC)
    body = (
        "## Outcome\n\nShip docs.\n\n## Scope\n\nStatic docs.\n\n"
        "## Non-goals\n\nNo runtime.\n\n## Acceptance criteria\n\nGate passes.\n\n"
        "## Verification\n\nVerification lane: `tiny-docs`.\n\n"
        "## Autonomy\n\nTier A autonomous lane.\n\n"
        f"## Allowed files\n\n- {scope}\n"
    )
    issue = parse_issue(
        {
            "number": 1574,
            "title": "Ship static docs",
            "state": "open",
            "html_url": "https://github.com/sakibshuvo/Entroping/issues/1574",
            "body": body,
            "labels": [
                {"name": "type:docs"},
                {"name": "priority:p1"},
                {"name": "status:ready"},
                {"name": "autonomy:tier-a"},
            ],
            "assignees": [],
            "milestone": {"title": "Factory"},
        }
    )
    return GitHubSnapshot(
        metadata=SnapshotMetadata(
            repo="sakibshuvo/Entroping",
            fetched_at=now - timedelta(seconds=1),
            expires_at=now + timedelta(seconds=59),
            complete=True,
        ),
        issues=(issue,),
        open_pr_issue_numbers=frozenset(),
    )


def request_payload(main: Path, worktree: Path, base: str) -> dict[str, object]:
    scopes = ("docs/user/guide.md",)
    if worktree.exists():
        common = Path(git(worktree, "rev-parse", "--git-common-dir"))
        if not common.is_absolute():
            common = (worktree / common).resolve()
    else:
        common = (main / ".git").resolve()
    return {
        "schema_version": "entroping.factory-orchestration-request.v1",
        "request_id": "orchestrate-1574-1",
        "issue_number": 1574,
        "job_id": "implementation-1574-1",
        "assignment_id": f"assign_{'1' * 64}",
        "scheduler_owner_id": "factory-owner-1",
        "scheduler_owner_pid": 10001,
        "scheduler_owner_start_token": f"proc_{1:064x}",
        "scheduler_owner_epoch": 7,
        "selector_digest": "3" * 64,
        "selection_digest": "4" * 64,
        "worktree_id": f"wt_{'2' * 64}",
        "autonomy_tier": "tier-a",
        "verification_lane": "tiny-docs",
        "allowed_scopes": scopes,
        "allowed_scope_digest": hashlib.sha256(
            json.dumps(list(scopes), separators=(",", ":")).encode()
        ).hexdigest(),
        "worktree_path": str(worktree.resolve()),
        "branch": "feat/example",
        "common_git_dir": str(common),
        "base_commit": base,
        "proposal_path": str(main.parent / "private" / "proposal.diff"),
        "proposal_sha256": "b" * 64,
    }


def update_patch() -> bytes:
    return (
        b"diff --git a/docs/user/guide.md b/docs/user/guide.md\n"
        b"index fdd56dd..2d192db 100644\n"
        b"--- a/docs/user/guide.md\n"
        b"+++ b/docs/user/guide.md\n"
        b"@@ -1 +1 @@\n"
        b"-Version one.\n"
        b"+Version two.\n"
    )


def private_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    _ = path.write_bytes(content)
    os.chmod(path, 0o600)
