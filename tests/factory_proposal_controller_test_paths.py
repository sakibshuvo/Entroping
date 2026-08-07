from __future__ import annotations

import hashlib
import os
from pathlib import Path
from unittest.mock import patch

from factory_proposal_controller_test_receipt_state import receipt_path as _receipt_path
from factory_proposal_controller_test_receipts import PendingReceipt, ScenarioObservation
from factory_proposal_controller_test_support import offline_scenario
from factory_scheduler_test_support import NOW, dead, owner, request

from scripts import factory_retention_apply
from scripts.factory_budget_ledger import FactoryBudgetLedger, FactoryBudgetLedgerError
from scripts.factory_retention_apply import RetentionApplyError, recover_incomplete
from scripts.factory_retention_fs import RetentionFsError
from scripts.factory_scheduler import FactoryScheduler
from scripts.factory_tick_runner import TickRunnerError, run_tick

REPO_ROOT = Path(__file__).resolve().parents[1]


@offline_scenario
def ignored_state_escapes(root: Path) -> PendingReceipt:
    observed = ScenarioObservation.begin(root, "ignored-state-escapes")
    external = root / "external-targets"
    external.mkdir()
    _scheduler_attack(root / "scheduler", external / "scheduler.sqlite3")
    _ledger_attack(root / "ledger", external / "ledger.alias")
    _log_attack(root / "logs", external / "logs-target")
    _journal_attack(root / "journal", external / "journal-target")
    _receipt_attacks(root / "receipts-case", external)
    _evidence_attack(root, external / "evidence-target")
    return observed.receipt(return_class="fail-closed")


def _scheduler_attack(root: Path, target: Path) -> None:
    root.mkdir()
    assigned = FactoryScheduler(root).tick(
        request=request(1, worker_class="free-local"),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    assert assigned.assignment_id is not None
    database = root / ".entroping" / "factory-scheduler" / "scheduler.sqlite3"
    database.rename(target)
    before = _target_digest(target)
    database.symlink_to(target)
    blocked = FactoryScheduler(root).tick(
        request=request(2, worker_class="free-local"),
        owner=owner(2),
        as_of=NOW,
        lease_seconds=30,
        plan_only=True,
        owner_health=dead,
    )
    assert blocked.reason == "state-invalid" and _target_digest(target) == before


def _ledger_attack(root: Path, target: Path) -> None:
    root.mkdir()
    ledger = FactoryBudgetLedger.open_project(root)
    os.link(ledger.db_path, target)
    before = _target_digest(target)
    try:
        FactoryBudgetLedger.open_project(root)
    except FactoryBudgetLedgerError:
        pass
    else:
        raise AssertionError("external hardlinked ledger was accepted")
    assert _target_digest(target) == before


def _log_attack(root: Path, target: Path) -> None:
    target.mkdir()
    (target / "sentinel").write_text("log-target-sentinel", encoding="utf-8")
    before = _target_digest(target)
    log_directory = root / ".entroping" / "factory-logs"
    log_directory.parent.mkdir(parents=True)
    log_directory.symlink_to(target, target_is_directory=True)
    executable = root / "offline-factoryctl"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o700)
    try:
        run_tick(
            repo_root=root,
            factoryctl=executable,
            log_directory=log_directory,
            timeout_seconds=1,
            max_output_bytes=64,
            max_log_bytes=64,
        )
    except TickRunnerError:
        pass
    else:
        raise AssertionError("symlinked log state was accepted")
    assert _target_digest(target) == before


def _journal_attack(root: Path, target: Path) -> None:
    target.mkdir()
    (target / "sentinel.json").write_text("{", encoding="utf-8")
    before = _target_digest(target)
    journal = root / ".entroping" / "retention-journal"
    journal.parent.mkdir(parents=True)
    journal.symlink_to(target, target_is_directory=True)
    with patch.object(factory_retention_apply, "_tracked_paths", return_value=frozenset()):
        try:
            recover_incomplete(root)
        except (RetentionApplyError, RetentionFsError):
            pass
        else:
            raise AssertionError("symlinked journal state was accepted")
    assert _target_digest(target) == before


def _receipt_attacks(root: Path, external: Path) -> None:
    root.mkdir()
    symlink_target = external / "receipt-target"
    symlink_target.mkdir()
    (symlink_target / "sentinel").write_text("receipt-target-sentinel", encoding="utf-8")
    before = _target_digest(symlink_target)
    destination = root / "receipts"
    destination.symlink_to(symlink_target, target_is_directory=True)
    with patch.dict(os.environ, {"ENTROPING_PROPOSAL_RECEIPTS_DIR": str(destination)}):
        try:
            _receipt_path(root, "receipt-symlink")
        except AssertionError:
            pass
        else:
            raise AssertionError("receipt directory symlink was accepted")
    assert _target_digest(symlink_target) == before
    destination.unlink()
    destination.mkdir()
    symlink_file_target = external / "receipt-symlink-file-target"
    symlink_file_target.write_text("receipt-file-symlink-sentinel", encoding="utf-8")
    (destination / "receipt-file-symlink.json").symlink_to(symlink_file_target)
    file_before = _target_digest(symlink_file_target)
    with patch.dict(os.environ, {"ENTROPING_PROPOSAL_RECEIPTS_DIR": str(destination)}):
        try:
            _receipt_path(root, "receipt-file-symlink")
        except AssertionError:
            pass
        else:
            raise AssertionError("receipt file symlink was accepted")
    assert _target_digest(symlink_file_target) == file_before
    hardlink_target = external / "receipt-hardlink-target"
    hardlink_target.write_text("receipt-hardlink-sentinel", encoding="utf-8")
    os.link(hardlink_target, destination / "receipt-hardlink.json")
    hardlink_before = _target_digest(hardlink_target)
    with patch.dict(os.environ, {"ENTROPING_PROPOSAL_RECEIPTS_DIR": str(destination)}):
        try:
            _receipt_path(root, "receipt-hardlink")
        except AssertionError:
            pass
        else:
            raise AssertionError("receipt hardlink destination was accepted")
    assert _target_digest(hardlink_target) == hardlink_before


def _evidence_attack(root: Path, target: Path) -> None:
    target.mkdir()
    (target / "sentinel").write_text("evidence-target-sentinel", encoding="utf-8")
    before = _target_digest(target)
    suffix = hashlib.sha256(str(root).encode()).hexdigest()[:16]
    link = REPO_ROOT / ".omo" / "evidence" / f"issue-1575-escape-{suffix}"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target, target_is_directory=True)
    try:
        with patch.dict(os.environ, {"ENTROPING_PROPOSAL_RECEIPTS_DIR": str(link)}):
            try:
                _receipt_path(root, "evidence-escape")
            except AssertionError:
                pass
            else:
                raise AssertionError("evidence destination escape was accepted")
    finally:
        link.unlink()
    assert _target_digest(target) == before


def _target_digest(root: Path) -> tuple[tuple[str, int, int, int, str], ...]:
    paths = (root,) if root.is_file() else tuple(sorted((root, *root.rglob("*"))))
    return tuple(
        (
            path.relative_to(root.parent).as_posix(),
            path.stat(follow_symlinks=False).st_mode,
            path.stat(follow_symlinks=False).st_nlink,
            path.stat(follow_symlinks=False).st_size,
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "directory",
        )
        for path in paths
    )
