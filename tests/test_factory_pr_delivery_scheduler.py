from __future__ import annotations

from pathlib import Path

import pytest
from factory_pr_delivery_test_support import accepted_artifacts, write_delivery_request

from scripts.factory_pr_delivery_io import load_delivery_envelope
from scripts.factory_pr_delivery_models import DeliveryEnvelope, DeliveryGitError
from scripts.factory_pr_delivery_scheduler import (
    SchedulerCompletionAuthority,
    validate_scheduler_authority,
)
from scripts.factory_scheduler_queries import read_assignment, read_execution_for_job
from scripts.factory_scheduler_storage import readonly_connection, writable_connection


def _envelope(tmp_path: Path) -> tuple[Path, DeliveryEnvelope]:
    main, _worktree, payload = accepted_artifacts(tmp_path)
    request_path = tmp_path / "private/delivery-request.json"
    write_delivery_request(request_path, payload)
    return main, load_delivery_envelope(request_path)


def _load_snapshot(
    main: Path, job_id: str, assignment_id: str
) -> tuple[tuple[str, str, str, str], tuple[str, str, int, str]]:
    with readonly_connection(main) as connection:
        assignment = read_assignment(connection, job_id=job_id)
        execution = read_execution_for_job(connection, job_id=job_id)
        request_row = connection.execute(
            "SELECT request_id, assignment_id, state, lease_owner_id "
            "FROM scheduler_assignments WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        execution_row = connection.execute(
            "SELECT assignment_id, phase, phase_version, evidence_digest "
            "FROM scheduler_execution_state WHERE assignment_id = ?",
            (assignment_id,),
        ).fetchone()
    assert assignment is not None
    assert execution is not None
    assert request_row is not None
    assert execution_row is not None
    request_id, loaded_assignment_id, state, owner_id = request_row
    execution_assignment_id, phase, phase_version, evidence_digest = execution_row
    if not all(
        isinstance(value, str)
        for value in (
            request_id,
            loaded_assignment_id,
            state,
            owner_id,
            execution_assignment_id,
            phase,
            evidence_digest,
        )
    ) or not isinstance(phase_version, int):
        raise AssertionError("unexpected scheduler snapshot shape")
    return (
        (request_id, loaded_assignment_id, state, owner_id),
        (execution_assignment_id, phase, phase_version, evidence_digest),
    )


def test_validate_scheduler_authority_returns_completion_snapshot_and_phase_version(
    tmp_path: Path,
) -> None:
    main, envelope = _envelope(tmp_path)
    request = envelope.orchestration_request
    before = _load_snapshot(main, request.job_id, request.assignment_id)
    before_phase_version = before[1][2]
    snapshot = validate_scheduler_authority(main, envelope)
    assert snapshot == SchedulerCompletionAuthority(
        owner_id=request.scheduler_owner_id,
        owner_pid=request.scheduler_owner_pid,
        owner_start_token=request.scheduler_owner_start_token,
        epoch=request.scheduler_owner_epoch,
        phase_version=before_phase_version,
    )
    after = _load_snapshot(main, request.job_id, request.assignment_id)
    assert before == after


def test_validate_scheduler_authority_ignores_absent_live_lease(tmp_path: Path) -> None:
    main, envelope = _envelope(tmp_path)
    with writable_connection(main, initialized_at="2026-08-03T12:00:00+00:00") as connection:
        _ = connection.execute("DELETE FROM scheduler_lease WHERE id = 1")
    _ = validate_scheduler_authority(main, envelope)


def test_validate_scheduler_authority_returns_mutated_execution_phase_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    main, envelope = _envelope(tmp_path)
    request = envelope.orchestration_request
    with readonly_connection(main) as connection:
        assignment = read_assignment(connection, job_id=request.job_id)
        execution = read_execution_for_job(connection, job_id=request.job_id)
    assert assignment is not None
    assert execution is not None
    expected_phase_version = execution.phase_version + 1
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_scheduler.read_assignment",
        lambda *_args, **_kwargs: assignment,
    )
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_scheduler.read_execution_for_job",
        lambda *_args, **_kwargs: execution.model_copy(
            update={"phase_version": expected_phase_version}
        ),
    )
    snapshot = validate_scheduler_authority(main, envelope)
    assert snapshot.phase_version == expected_phase_version


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("lease_owner_id", "mismatched-owner"),
        ("lease_owner_pid", 20001),
        ("lease_owner_start_token", f"proc_{2:064x}"),
        ("lease_epoch", 99),
    ],
)
def test_validate_scheduler_authority_rejects_assignment_owner_tuple_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    field: str,
    bad_value: str | int,
) -> None:
    main, envelope = _envelope(tmp_path)
    request = envelope.orchestration_request
    with readonly_connection(main) as connection:
        assignment = read_assignment(connection, job_id=request.job_id)
        execution = read_execution_for_job(connection, job_id=request.job_id)
    assert assignment is not None
    assert execution is not None
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_scheduler.read_assignment",
        lambda *_args, **_kwargs: assignment.model_copy(update={field: bad_value}),
    )
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_scheduler.read_execution_for_job",
        lambda *_args, **_kwargs: execution,
    )
    with pytest.raises(DeliveryGitError) as exc:
        validate_scheduler_authority(main, envelope)
    assert exc.value.code == "authority-mismatch"


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("lease_owner_id", "mismatched-owner"),
        ("lease_owner_pid", 20001),
        ("lease_owner_start_token", f"proc_{3:064x}"),
        ("lease_epoch", 99),
    ],
)
def test_validate_scheduler_authority_rejects_execution_owner_tuple_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    field: str,
    bad_value: str | int,
) -> None:
    main, envelope = _envelope(tmp_path)
    request = envelope.orchestration_request
    with readonly_connection(main) as connection:
        assignment = read_assignment(connection, job_id=request.job_id)
        execution = read_execution_for_job(connection, job_id=request.job_id)
    assert assignment is not None
    assert execution is not None
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_scheduler.read_assignment",
        lambda *_args, **_kwargs: assignment,
    )
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_scheduler.read_execution_for_job",
        lambda *_args, **_kwargs: execution.model_copy(update={field: bad_value}),
    )
    with pytest.raises(DeliveryGitError) as exc:
        validate_scheduler_authority(main, envelope)
    assert exc.value.code == "authority-mismatch"


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("state", "completed"),
        ("phase", "dispatched"),
        ("evidence_digest", "e" * 64),
    ],
)
def test_validate_scheduler_authority_rejects_phase_state_and_evidence_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    field: str,
    bad_value: str,
) -> None:
    main, envelope = _envelope(tmp_path)
    request = envelope.orchestration_request
    with readonly_connection(main) as connection:
        assignment = read_assignment(connection, job_id=request.job_id)
        execution = read_execution_for_job(connection, job_id=request.job_id)
    assert assignment is not None
    assert execution is not None
    if field == "state":
        mutated_assignment = assignment.model_copy(update={field: bad_value, "completed_at": None})
        mutated_execution = execution
    elif field == "phase":
        mutated_assignment = assignment
        mutated_execution = execution.model_copy(update={field: bad_value})
    else:
        mutated_assignment = assignment
        mutated_execution = execution.model_copy(update={field: bad_value})
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_scheduler.read_assignment",
        lambda *_args, **_kwargs: mutated_assignment,
    )
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_scheduler.read_execution_for_job",
        lambda *_args, **_kwargs: mutated_execution,
    )
    with pytest.raises(DeliveryGitError) as exc:
        validate_scheduler_authority(main, envelope)
    assert exc.value.code == "authority-mismatch"


def test_validate_scheduler_authority_rejects_identity_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    main, envelope = _envelope(tmp_path)
    request = envelope.orchestration_request
    with readonly_connection(main) as connection:
        assignment = read_assignment(connection, job_id=request.job_id)
        execution = read_execution_for_job(connection, job_id=request.job_id)
    assert assignment is not None
    assert execution is not None
    mutated_request = assignment.request.model_copy(update={"request_id": "other-request"})
    mutated_assignment = assignment.model_copy(update={"request": mutated_request})
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_scheduler.read_assignment",
        lambda *_args, **_kwargs: mutated_assignment,
    )
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_scheduler.read_execution_for_job",
        lambda *_args, **_kwargs: execution,
    )
    with pytest.raises(DeliveryGitError) as exc:
        validate_scheduler_authority(main, envelope)
    assert exc.value.code == "authority-mismatch"


def test_validate_scheduler_authority_rejects_execution_identity_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    main, envelope = _envelope(tmp_path)
    request = envelope.orchestration_request
    with readonly_connection(main) as connection:
        assignment = read_assignment(connection, job_id=request.job_id)
        execution = read_execution_for_job(connection, job_id=request.job_id)
    assert assignment is not None
    assert execution is not None
    mutated_execution = execution.model_copy(
        update={"assignment_id": f"assign_{3:064x}"}
    )
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_scheduler.read_assignment",
        lambda *_args, **_kwargs: assignment,
    )
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_scheduler.read_execution_for_job",
        lambda *_args, **_kwargs: mutated_execution,
    )
    with pytest.raises(DeliveryGitError) as exc:
        validate_scheduler_authority(main, envelope)
    assert exc.value.code == "authority-mismatch"


def test_validate_scheduler_authority_rejects_malformed_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    main, envelope = _envelope(tmp_path)
    request = envelope.orchestration_request
    with readonly_connection(main) as connection:
        _ = read_execution_for_job(connection, job_id=request.job_id)
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_scheduler.read_assignment",
        lambda *_args, **_kwargs: object(),
    )
    with pytest.raises(DeliveryGitError) as exc:
        validate_scheduler_authority(main, envelope)
    assert exc.value.code == "authority-mismatch"


@pytest.mark.parametrize(
    "missing",
    ["assignment", "execution"],
)
def test_validate_scheduler_authority_rejects_missing_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    missing: str,
) -> None:
    main, envelope = _envelope(tmp_path)
    request = envelope.orchestration_request
    with readonly_connection(main) as connection:
        assignment = read_assignment(connection, job_id=request.job_id)
        execution = read_execution_for_job(connection, job_id=request.job_id)
    assert assignment is not None
    assert execution is not None
    if missing == "assignment":
        monkeypatch.setattr(
            "scripts.factory_pr_delivery_scheduler.read_assignment",
            lambda *_args, **_kwargs: None,
        )
        monkeypatch.setattr(
            "scripts.factory_pr_delivery_scheduler.read_execution_for_job",
            lambda *_args, **_kwargs: execution,
        )
    else:
        monkeypatch.setattr(
            "scripts.factory_pr_delivery_scheduler.read_assignment",
            lambda *_args, **_kwargs: assignment,
        )
        monkeypatch.setattr(
            "scripts.factory_pr_delivery_scheduler.read_execution_for_job",
            lambda *_args, **_kwargs: None,
        )
    with pytest.raises(DeliveryGitError) as exc:
        validate_scheduler_authority(main, envelope)
    assert exc.value.code == "authority-mismatch"
