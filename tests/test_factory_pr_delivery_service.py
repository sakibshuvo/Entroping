from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from factory_pr_delivery_test_support import accepted_artifacts, write_delivery_request

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_pr_delivery_github import (  # noqa: E402
    CheckObservation,
    CiObservation,
    IssueObservation,
    MergeResult,
    ProtectionObservation,
    PullRequestObservation,
    RequiredCheck,
    ScriptedGitHubDeliveryPort,
)
from scripts.factory_pr_delivery_io import load_delivery_envelope  # noqa: E402
from scripts.factory_pr_delivery_models import CommitResult  # noqa: E402
from scripts.factory_pr_delivery_receipts import DeliveryReceipt  # noqa: E402
from scripts.factory_pr_delivery_service import DeliveryService  # noqa: E402
from scripts.factory_pr_delivery_ssh import PushResult  # noqa: E402

REPO = "sakibshuvo/Entroping"
HEAD = "b" * 40


class _Journal:
    def __init__(self, _repo_root: Path) -> None:
        pass

    def push_intent(self, _envelope):
        return None

    def pushed(self, _envelope, *, remote_head: str):
        return None


def _setup(tmp_path: Path):
    main, _worktree, payload = accepted_artifacts(tmp_path)
    request_path = tmp_path / "private/delivery-request.json"
    write_delivery_request(request_path, payload)
    base = load_delivery_envelope(request_path).orchestration_request.base_commit
    return main, request_path, base, str(payload["pr_body_sha256"])


def _port(
    base: str,
    body_sha: str,
    *,
    existing: bool = False,
    ci_status: str = "success",
):
    issue = IssueObservation(
        repo=REPO,
        number=1574,
        state="open",
        title="Ship static docs",
        labels=("autonomy:tier-a",),
        body_sha256="1" * 64,
    )


    protection = ProtectionObservation(
        repo=REPO,
        base_ref="main",
        base_sha=base,
        required_checks=(RequiredCheck(context="quality", app_id=1),),
        complete=True,
    )
    pull = PullRequestObservation(
        repo=REPO,
        number=42,
        title="Ship static docs",
        body_sha256=body_sha,
        state="open",
        draft=False,
        head_branch="feat/example",
        head_sha=HEAD,
        base_ref="main",
        base_sha=base,
        mergeable="MERGEABLE",
        merge_state_status="CLEAN",
        changed_files=("docs/user/guide.md",),
        closing_issue_numbers=(1574,),
    )
    ci = CiObservation(
        repo=REPO,
        base_ref="main",
        base_sha=base,
        head_sha=HEAD,
        protection_digest=protection.digest,
        checks=(CheckObservation(context="quality", app_id=1, status=ci_status, head_sha=HEAD),),
        mergeable="MERGEABLE",
        merge_state_status="CLEAN",
        complete=True,
    )
    return ScriptedGitHubDeliveryPort(
        issue=issue,
        pull_requests=(pull,) if existing else (),
        created=pull,
        protection=protection,
        ci=ci,
        merge=MergeResult(
            repo=REPO,
            pr_number=42,
            requested_head=HEAD,
            state="merged",
            merged_head=HEAD,
        ),
    )


def _commit_result(base: str) -> CommitResult:
    return CommitResult(
        accepted_local_head=base,
        committed_head=HEAD,
        commit_parent=base,
        commit_tree="c" * 40,
        accepted_diff_sha256="d" * 64,
        committed_diff_sha256="d" * 64,
        accepted_manifest_sha256="e" * 64,
        committed_manifest_sha256="e" * 64,
        approved_path_sha256="f" * 64,
    )


def test_plan_mode_reads_authority_without_mutating_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main, request_path, base, body_sha = _setup(tmp_path)
    port = _port(base, body_sha)
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service_support.validate_body", lambda *_args, **_kwargs: []
    )

    receipt = DeliveryService(
        main,
        github=port,
        now=lambda: datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
    ).deliver(request_path, apply=False)

    assert receipt.lifecycle == "planned"
    assert receipt.reason == "plan-only"
    assert receipt.authoritative is False
    assert [call.operation for call in port.calls] == [
        "observe-issue",
        "observe-protection",
        "observe-prs",
    ]


def test_apply_reaches_merged_receipt_once_gates_are_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main, request_path, base, body_sha = _setup(tmp_path)
    port = _port(base, body_sha)
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service_support.validate_body", lambda *_args, **_kwargs: []
    )
    monkeypatch.setattr("scripts.factory_pr_delivery_service.DeliveryJournal", _Journal)
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service.commit_exact_diff",
        lambda *_args, **_kwargs: _commit_result(base),
    )
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service.push_exact_commit",
        lambda *_args, **_kwargs: PushResult("pushed", "c" * 40),
    )

    receipt = DeliveryService(
        main,
        github=port,
        now=lambda: datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
    ).deliver(request_path, apply=True)

    assert receipt.lifecycle == "merged"
    assert receipt.reason == "cleanup-pending"
    assert receipt.committed_head == HEAD
    assert receipt.remote_head == "c" * 40
    assert receipt.pr_number == 42
    assert [call.operation for call in port.calls].count("create-pr") == 1
    assert [call.operation for call in port.calls].count("merge-pr") == 1


def test_apply_stops_after_push_when_required_ci_is_not_green(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main, request_path, base, body_sha = _setup(tmp_path)
    port = _port(base, body_sha, ci_status="pending")
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service_support.validate_body", lambda *_args, **_kwargs: []
    )
    monkeypatch.setattr("scripts.factory_pr_delivery_service.DeliveryJournal", _Journal)
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service.commit_exact_diff",
        lambda *_args, **_kwargs: _commit_result(base),
    )
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service.push_exact_commit",
        lambda *_args, **_kwargs: PushResult("pushed", "c" * 40),
    )

    receipt = DeliveryService(main, github=port).deliver(request_path, apply=True)

    assert receipt.lifecycle == "pushed"
    assert receipt.reason == "ci-pending"
    assert not any(call.operation == "merge-pr" for call in port.calls)


def test_delivery_receipt_rejects_incomplete_merged_projection() -> None:
    with pytest.raises(ValueError):
        DeliveryReceipt(
            request_id="delivery_" + "1" * 64,
            lifecycle="merged",
            reason="cleanup-pending",
            authoritative=True,
            accepted_local_head="a" * 40,
            created_at=datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
            updated_at=datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
        )
