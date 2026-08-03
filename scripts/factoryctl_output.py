"""Value-free factoryctl receipt rendering."""

from __future__ import annotations

import json

from scripts.factory_orchestration_models import OrchestrationReceipt
from scripts.factory_scheduler_execution_models import RecoveryReceipt
from scripts.factory_scheduler_models import DecisionReceipt


def print_decision(receipt: DecisionReceipt, *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(receipt.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))
        return
    mode = "authoritative" if receipt.authoritative else "plan-only"
    print(f"Factory tick: {receipt.decision} ({receipt.reason})")
    print(f"Mode: {mode}")
    if receipt.assignment_id is not None:
        print(f"Assignment: {receipt.assignment_id}")


def print_recovery(receipt: RecoveryReceipt, *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(receipt.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))
        return
    mode = "authoritative" if receipt.authoritative else "plan-only"
    print(f"Factory recovery: {receipt.decision} ({receipt.reason})")
    print(f"Mode: {mode}")
    print(f"Assignment: {receipt.assignment_id}")
    print(f"Phase: {receipt.phase}")


def print_orchestration(receipt: OrchestrationReceipt, *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(receipt.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))
        return
    mode = "authoritative" if receipt.authoritative else "plan-only"
    print(f"Factory orchestration: {receipt.lifecycle} ({receipt.reason})")
    print(f"Mode: {mode}")
    print(f"Issue: {receipt.issue_number}")
    print(f"Receipt: {receipt.receipt_id}")
