#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import ValidationError

from scripts.factory_scheduler import FactoryScheduler, FactorySchedulerError
from scripts.factory_scheduler_models import AssignmentRequest, DecisionReceipt, LeaseOwner
from scripts.factory_scheduler_process import current_lease_owner


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "tick":
            return _tick(args)
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
        if args.reservation_id is not None:
            raise ValueError("candidate fields must be supplied together")
        return None
    if not all(present):
        raise ValueError("candidate fields must be supplied together")
    return AssignmentRequest.model_validate(
        {
            **raw,
            "reservation_id": args.reservation_id,
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


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        for error in exc.errors(include_input=False, include_url=False):
            message = error.get("msg")
            if isinstance(message, str) and message:
                return message.removeprefix("Value error, ")
        return "input validation failed"
    return str(exc)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run bounded maintainer factory scheduler operations."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    tick = subparsers.add_parser(
        "tick",
        description=(
            "Plan or commit one fenced scheduler assignment. The default is "
            "plan-only and does not dispatch providers."
        ),
        help="Plan or commit one scheduler decision without provider dispatch.",
    )
    _ = tick.add_argument(
        "--apply",
        action="store_true",
        help="Commit the lease and assignment; otherwise remain plan-only.",
    )
    _ = tick.add_argument("--json", action="store_true")
    _ = tick.add_argument("--lease-seconds", type=int, default=30)
    _ = tick.add_argument("--owner-id")
    _ = tick.add_argument("--request-id")
    _ = tick.add_argument("--job-id")
    _ = tick.add_argument("--issue", type=int)
    _ = tick.add_argument("--worktree-id")
    _ = tick.add_argument("--worker-class", choices=("paid", "free-local"))
    _ = tick.add_argument("--access-mode", choices=("read-only", "write"))
    _ = tick.add_argument("--reservation-id")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
