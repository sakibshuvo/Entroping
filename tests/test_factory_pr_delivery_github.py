from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.bounded_process import BoundedProcessResult  # noqa: E402
from scripts.factory_pr_delivery_github import (  # noqa: E402
    GhGitHubDeliveryPort,
    GitHubDeliveryError,
    ScriptedGitHubDeliveryPort,
)
from scripts.factory_pr_delivery_github_io import (  # noqa: E402
    GitHubTransportError,
    run_gh_json,
)
from scripts.factory_pr_delivery_github_models import (  # noqa: E402
    CheckObservation,
    CiObservation,
    IssueObservation,
    MergeResult,
    ProtectionObservation,
    PullRequestObservation,
    RequiredCheck,
    evaluate_ci,
)

REPO = "sakibshuvo/Entroping"
BASE = "a" * 40
HEAD = "b" * 40


def _issue() -> IssueObservation:
    return IssueObservation(
        repo=REPO,
        number=1574,
        state="open",
        title="Ship static docs",
        labels=("autonomy:tier-a", "priority:p1"),
        body_sha256="1" * 64,
    )


def _pr(*, number: int = 42, state: str = "open") -> PullRequestObservation:
    return PullRequestObservation(
        repo=REPO,
        number=number,
        title="Ship static docs",
        body_sha256="2" * 64,
        state=state,
        draft=False,
        head_branch="feat/example",
        head_sha=HEAD,
        base_ref="main",
        base_sha=BASE,
        mergeable="MERGEABLE",
        merge_state_status="CLEAN",
        changed_files=("docs/user/guide.md",),
        closing_issue_numbers=(1574,),
        merged_head=HEAD if state == "merged" else None,
    )


def _protection() -> ProtectionObservation:
    return ProtectionObservation(
        repo=REPO,
        base_ref="main",
        base_sha=BASE,
        required_checks=(RequiredCheck(context="quality", app_id=1),),
        complete=True,
    )


def _ci(protection: ProtectionObservation, status: str = "success") -> CiObservation:
    return CiObservation(
        repo=REPO,
        base_ref="main",
        base_sha=BASE,
        head_sha=HEAD,
        protection_digest=protection.digest,
        checks=(CheckObservation(context="quality", app_id=1, status=status, head_sha=HEAD),),
        mergeable="MERGEABLE",
        merge_state_status="CLEAN",
        complete=True,
    )


def test_scripted_port_records_typed_calls_without_body_text() -> None:
    protection = _protection()
    body = "## Documentation Impact Declaration\n"
    port = ScriptedGitHubDeliveryPort(
        issue=_issue(),
        created=_pr(),
        protection=protection,
        ci=_ci(protection),
        merge=MergeResult(
            repo=REPO,
            pr_number=42,
            requested_head=HEAD,
            state="merged",
            merged_head=HEAD,
        ),
    )

    created = port.create_pull_request(
        REPO,
        title="Ship static docs",
        body=body,
        head_branch="feat/example",
        base_ref="main",
    )
    result = port.merge_pull_request(REPO, pr_number=created.number, head_sha=HEAD)

    assert result.state == "merged"
    assert port.calls[0].operation == "create-pr"
    assert port.calls[0].body_sha256 is not None
    assert body not in repr(port.calls)


@pytest.mark.parametrize(
    ("status", "expected"),
    [("success", (True, "ready")), ("pending", (False, "visible-check-not-terminal")),
     ("failure", (False, "visible-check-not-terminal"))],
)
def test_ci_classifier_requires_exact_terminal_required_context(
    status: str, expected: tuple[bool, str]
) -> None:
    protection = _protection()
    assert evaluate_ci(protection, _ci(protection, status)) == expected


def test_ci_classifier_rejects_missing_duplicate_and_stale_contexts() -> None:
    protection = _protection()
    missing = _ci(protection).model_copy(update={"checks": ()})
    assert evaluate_ci(protection, missing) == (False, "required-check-absent")
    duplicate = _ci(protection).model_copy(
        update={"checks": _ci(protection).checks + _ci(protection).checks}
    )
    assert evaluate_ci(protection, duplicate) == (False, "duplicate-check")
    stale = _ci(protection).model_copy(
        update={
            "checks": (
                CheckObservation(context="quality", app_id=1, status="success", head_sha=BASE),
            )
        }
    )
    assert evaluate_ci(protection, stale) == (False, "stale-check")


def test_protection_requires_nonempty_complete_required_checks() -> None:
    with pytest.raises(ValidationError):
        ProtectionObservation(
            repo=REPO,
            base_ref="main",
            base_sha=BASE,
            required_checks=(),
            complete=False,
        )


def test_gh_adapter_uses_fixed_arrays_and_rejects_bound_incomplete_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    issue_payload = {
        "number": 1574,
        "state": "OPEN",
        "title": "Ship static docs",
        "body": "body",
        "labels": [{"name": "autonomy:tier-a"}],
    }

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_github.trusted_gh_contract",
        lambda: (Path("/usr/bin/gh"), {"PATH": "/usr/bin:/bin"}),
    )

    def fake_json(_executable: Path, _env: object, args: tuple[str, ...], *, cwd: Path) -> object:
        calls.append(args)
        if args[:2] == ("api", "repos/sakibshuvo/Entroping/issues/1574"):
            return issue_payload
        return [{"number": index} for index in range(100)]

    monkeypatch.setattr("scripts.factory_pr_delivery_github.run_gh_json", fake_json)
    port = GhGitHubDeliveryPort(cwd=REPO_ROOT)
    assert port.observe_issue(REPO, 1574).state == "open"
    with pytest.raises(GitHubDeliveryError) as exc_info:
        port.observe_pull_requests(REPO, 1574, "feat/example")
    assert exc_info.value.code == "pr-list-incomplete"
    assert calls[0] == ("api", "repos/sakibshuvo/Entroping/issues/1574")


def test_gh_adapter_sanitizes_transport_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_github.trusted_gh_contract",
        lambda: (Path("/usr/bin/gh"), {"PATH": "/usr/bin:/bin"}),
    )

    def fail(*_args: object, **_kwargs: object) -> object:
        raise GitHubTransportError("github-output-exceeded")

    monkeypatch.setattr("scripts.factory_pr_delivery_github.run_gh_json", fail)
    port = GhGitHubDeliveryPort(cwd=REPO_ROOT)
    with pytest.raises(GitHubDeliveryError) as exc_info:
        port.observe_issue(REPO, 1574)
    assert str(exc_info.value) == "github-output-exceeded"
    assert "secret" not in str(exc_info.value)


def test_gh_transport_uses_exact_command_and_scrubbed_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_process(command: object, **kwargs: object) -> BoundedProcessResult:
        captured["command"] = command
        captured.update(kwargs)
        return BoundedProcessResult(
            args=("/usr/bin/gh", "api"),
            returncode=0,
            stdout="{\"ok\":true}",
            stderr="",
            timed_out=False,
            output_limit_exceeded=False,
        )

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_github_io.run_bounded_process", fake_process
    )
    assert run_gh_json(
        Path("/usr/bin/gh"),
        {"PATH": "/usr/bin:/bin", "HOME": "/tmp/home"},
        ("api", "repos/sakibshuvo/Entroping/issues/1574"),
        cwd=REPO_ROOT,
    ) == {"ok": True}
    assert captured["command"] == [
        Path("/usr/bin/gh"),
        "api",
        "repos/sakibshuvo/Entroping/issues/1574",
    ]
    assert captured["env"] == {"PATH": "/usr/bin:/bin", "HOME": "/tmp/home"}
