#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import ValidationError

from scripts.factory_retry_policy import RecoverySnapshot, RetryPolicy
from scripts.factory_scheduler import FactoryScheduler, FactorySchedulerError
from scripts.factory_scheduler_execution_models import RecoveryReceipt, RecoveryRequest
from scripts.factory_scheduler_models import AssignmentRequest, DecisionReceipt, LeaseOwner
from scripts.factory_scheduler_process import current_lease_owner
from scripts.factoryctl_parser import build_parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "tick":
            return _tick(args)
        if args.command == "recover":
            return _recover(args)
    except (FactorySchedulerError, ValidationError, ValueError) as exc:
        print(f"factoryctl: {_safe_error(exc)}", file=sys.stderr)
        return 2
    print("factoryctl: unsupported command", file=sys.stderr)
    return 2


def _tick(args: argparse.Namespace) -> int:
    request = _request(args)
    apply = bool(args.apply)
    owner = _owner(args, apply=apply)
    receipt = FactoryScheduler(Path.cwd()).tick(
        request=request,
        owner=owner,
        as_of=None,
        lease_seconds=cast(int, args.lease_seconds),
        plan_only=not apply,
    )
    _print_receipt(receipt, json_output=bool(args.json))
    return 1 if receipt.decision == "blocked" else 0


def _recover(args: argparse.Namespace) -> int:
    apply = bool(args.apply)
    receipt = FactoryScheduler(Path.cwd()).recover(
        _recovery_request(args),
        owner=_owner(args, apply=apply),
        as_of=datetime.now(UTC),
        lease_seconds=cast(int, args.lease_seconds),
        retry_policy=RetryPolicy.model_validate(
            {
                "base_delay_seconds": args.retry_base_seconds,
                "max_delay_seconds": args.retry_max_seconds,
                "max_attempts": args.max_attempts,
                "max_elapsed_seconds": args.max_elapsed_seconds,
                "jitter_percent": args.jitter_percent,
                "retry_after_ceiling_seconds": args.retry_after_ceiling_seconds,
            },
            strict=True,
        ),
        plan_only=not apply,
    )
    _print_recovery_receipt(receipt, json_output=bool(args.json))
    return 1 if receipt.decision == "blocked" else 0


def _request(args: argparse.Namespace) -> AssignmentRequest | None:
    raw = {
        "request_id": args.request_id,
        "job_id": args.job_id,
        "issue_number": args.issue,
        "worktree_id": args.worktree_id,
        "worker_class": args.worker_class,
        "access_mode": args.access_mode,
    }
    present = [value is not None for value in raw.values()]
    if not any(present):
        if args.reservation_id is not None or args.authorization_id is not None:
            raise ValueError("candidate fields must be supplied together")
        return None
    if not all(present):
        raise ValueError("candidate fields must be supplied together")
    return AssignmentRequest.model_validate(
        {
            **raw,
            "reservation_id": args.reservation_id,
            "authorization_id": args.authorization_id,
        },
        strict=True,
    )


def _recovery_request(args: argparse.Namespace) -> RecoveryRequest:
    return RecoveryRequest.model_validate(
        {
            "request_id": args.request_id,
            "assignment_id": args.assignment_id,
            "expected_epoch": args.expected_epoch,
            "dispatch_state": args.dispatch_state,
            "settlement_state": args.settlement_state,
            "failure_class": args.failure_class,
            "failure_code": args.failure_code,
            "retry_after_seconds": args.retry_after_seconds,
            "snapshots": tuple(_snapshot(value) for value in args.snapshot),
        },
        strict=True,
    )


def _snapshot(value: str) -> RecoverySnapshot:
    if len(value.encode("utf-8")) > 512:
        raise ValueError("recovery snapshot exceeds input bound")
    parts = value.split(",")
    if len(parts) != 4:
        raise ValueError("recovery snapshot must be SOURCE,OBSERVED,EXPIRES,DIGEST")
    source, observed, expires, digest = parts
    try:
        observed_at = datetime.fromisoformat(observed.replace("Z", "+00:00"))
        expires_at = datetime.fromisoformat(expires.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("recovery snapshot timestamp is invalid") from exc
    return RecoverySnapshot.model_validate(
        {
            "source": source,
            "observed_at": observed_at,
            "expires_at": expires_at,
            "digest": digest,
        },
        strict=True,
    )


def _owner(args: argparse.Namespace, *, apply: bool) -> LeaseOwner:
    if apply and args.owner_id is None:
        raise ValueError("--apply requires --owner-id")
    if apply:
        return current_lease_owner(cast(str, args.owner_id))
    return LeaseOwner.model_validate(
        {
            "owner_id": args.owner_id or "plan-only",
            "pid": 1,
            "process_start_token": f"proc_{0:064x}",
        },
        strict=True,
    )


def _print_receipt(receipt: DecisionReceipt, *, json_output: bool) -> None:
    if json_output:
        payload = receipt.model_dump(mode="json")
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        return
    mode = "authoritative" if receipt.authoritative else "plan-only"
    print(f"Factory tick: {receipt.decision} ({receipt.reason})")
    print(f"Mode: {mode}")
    if receipt.assignment_id is not None:
        print(f"Assignment: {receipt.assignment_id}")


def _print_recovery_receipt(
    receipt: RecoveryReceipt,
    *,
    json_output: bool,
) -> None:
    if json_output:
        print(
            json.dumps(
                receipt.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return
    mode = "authoritative" if receipt.authoritative else "plan-only"
    print(f"Factory recovery: {receipt.decision} ({receipt.reason})")
    print(f"Mode: {mode}")
    print(f"Assignment: {receipt.assignment_id}")
    print(f"Phase: {receipt.phase}")


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        for error in exc.errors(include_input=False, include_url=False):
            message = error.get("msg")
            if isinstance(message, str) and message:
                return message.removeprefix("Value error, ")
        return "input validation failed"
    return str(exc)


if __name__ == "__main__":
    raise SystemExit(main())
