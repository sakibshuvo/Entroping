from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from factory_orchestration_test_support import (  # noqa: E402
    private_file,
    repository,
    request_payload,
    update_patch,
)

from scripts.factory_orchestration_git import apply_exact_patch  # noqa: E402
from scripts.factory_orchestration_models import (  # noqa: E402
    GateExitState,
    OrchestrationRequest,
)
from scripts.factory_orchestration_receipts import build_receipt  # noqa: E402
from scripts.factory_scheduler import FactoryScheduler  # noqa: E402
from scripts.factory_scheduler_assignment_transaction import insert_assignment  # noqa: E402
from scripts.factory_scheduler_execution_models import ExecutionPhase  # noqa: E402
from scripts.factory_scheduler_lease_transaction import store_lease  # noqa: E402
from scripts.factory_scheduler_models import (  # noqa: E402
    AssignmentRequest,
    DeliveryAuthorityEnvelope,
    LeaseOwner,
)
from scripts.factory_scheduler_receipts import (  # noqa: E402
    make_decision_id,
    request_digest,
)
from scripts.factory_scheduler_storage import writable_connection  # noqa: E402
from scripts.factory_scheduler_transaction_control import update_clock  # noqa: E402


def accepted_artifacts(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    main, worktree, base = repository(tmp_path)
    orchestration = OrchestrationRequest.model_validate(
        request_payload(main, worktree, base), strict=True
    )
    _seed_scheduler_authority(main, orchestration)
    truth = apply_exact_patch(main, orchestration, update_patch())
    now = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    gate = GateExitState.model_validate(
        {
            "name": "docs-gate",
            "command_id": "docs-gate-v1",
            "exit_code": 0,
            "signal_number": None,
            "state": "passed",
            "stdout_sha256": "1" * 64,
            "stderr_sha256": "2" * 64,
            "started_at": now,
            "finished_at": now,
        },
        strict=True,
    )
    receipt = build_receipt(
        orchestration,
        lifecycle="accepted",
        reason="accepted",
        authoritative=True,
        paths=truth.paths,
        additions=1,
        deletions=1,
        truth=truth,
        gates=(gate,),
    )
    private = tmp_path / "private"
    orchestration_path = private / "orchestration-request.json"
    receipt_path = private / "orchestration-receipt.json"
    body_path = private / "pr-body.md"
    private_file(orchestration_path, orchestration.model_dump_json().encode())
    private_file(receipt_path, receipt.model_dump_json().encode())
    private_file(body_path, b"## Summary\n\nExact docs delivery.\n")
    payload: dict[str, object] = {
        "schema_version": "entroping.factory-pr-delivery-request.v1",
        "request_id": "pending",
        "orchestration_request_path": str(orchestration_path.resolve()),
        "orchestration_request_sha256": _sha(orchestration_path.read_bytes()),
        "orchestration_receipt_path": str(receipt_path.resolve()),
        "orchestration_receipt_sha256": _sha(receipt_path.read_bytes()),
        "pr_body_path": str(body_path.resolve()),
        "pr_body_sha256": _sha(body_path.read_bytes()),
    }
    from scripts.factory_pr_delivery_models import delivery_request_id_for_payload

    payload["request_id"] = delivery_request_id_for_payload(payload)
    return main, worktree, payload


def _seed_scheduler_authority(main: Path, orchestration: OrchestrationRequest) -> None:
    now = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    owner = LeaseOwner(
        owner_id=orchestration.scheduler_owner_id,
        pid=orchestration.scheduler_owner_pid,
        process_start_token=orchestration.scheduler_owner_start_token,
    )
    authority = DeliveryAuthorityEnvelope(
        selector_digest=orchestration.selector_digest,
        selection_digest=orchestration.selection_digest,
        autonomy_tier=orchestration.autonomy_tier,
        verification_lane="tiny-docs",
        allowed_scopes=orchestration.allowed_scopes,
        allowed_scope_digest=orchestration.allowed_scope_digest,
    )
    request = AssignmentRequest(
        request_id=orchestration.request_id,
        job_id=orchestration.job_id,
        issue_number=orchestration.issue_number,
        worktree_id=orchestration.worktree_id,
        worker_class="free-local",
        access_mode="write",
        delivery_authority=authority,
    )
    digest = request_digest(request)
    decision = make_decision_id(
        request_digest_value=digest,
        epoch=orchestration.scheduler_owner_epoch,
        observed_at=now,
        decision="assigned",
        reason="capacity-reserved",
    )
    with writable_connection(main, initialized_at=now.isoformat()) as connection:
        update_clock(connection, now, epoch=orchestration.scheduler_owner_epoch)
        store_lease(
            connection,
            owner,
            orchestration.scheduler_owner_epoch,
            now,
            now.replace(hour=13),
        )
        insert_assignment(
            connection,
            request=request,
            request_digest=digest,
            assignment_id=orchestration.assignment_id,
            decision_id=decision,
            owner=owner,
            epoch=orchestration.scheduler_owner_epoch,
            created_at=now,
            lease_expires_at=now.replace(hour=13),
        )
    scheduler = FactoryScheduler(main, settlement_authority=lambda _assignment: "not-required")
    phases: tuple[ExecutionPhase, ...] = (
        "dispatch-intent",
        "dispatched",
        "completed-unsettled",
    )
    for version, phase in enumerate(phases, 1):
        scheduler.transition_execution(
            assignment_id=orchestration.assignment_id,
            owner=owner,
            epoch=orchestration.scheduler_owner_epoch,
            expected_phase_version=version,
            target_phase=phase,
            observed_at=now.replace(microsecond=version),
            evidence_digest=(
                orchestration.proposal_sha256
                if phase == "completed-unsettled"
                else f"{version:x}" * 64
            ),
        )


def write_delivery_request(path: Path, payload: dict[str, object]) -> None:
    private_file(
        path,
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
    )


def raw_git(repo: Path, *args: str) -> bytes:
    return subprocess.run(
        ["/usr/bin/git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LANG": "C"},
    ).stdout


def private_ssh_home(root: Path) -> Path:
    home = root / "home"
    ssh = home / ".ssh"
    ssh.mkdir(mode=0o700, parents=True)
    os.chmod(home, 0o700)
    private_file(ssh / "id_ed25519", b"not-a-real-private-key")
    private_file(ssh / "known_hosts", b"github.com ssh-ed25519 test-key")
    return home


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
