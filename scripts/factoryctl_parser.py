from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run bounded maintainer factory scheduler operations."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    status = subparsers.add_parser(
        "status",
        description="Read a bounded, maintainer-only factory status projection.",
        help="Read factory state without creating state, dispatching, or calling providers.",
    )
    _ = status.add_argument("--json", action="store_true")
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
    _ = tick.add_argument("--authorization-id")
    recover = subparsers.add_parser(
        "recover",
        description=(
            "Plan or commit one fenced scheduler recovery decision. Recovery never "
            "dispatches providers and never releases uncertain holds."
        ),
        help="Plan or commit one scheduler recovery decision without provider dispatch.",
    )
    _ = recover.add_argument(
        "--apply",
        action="store_true",
        help="Commit the recovery decision; otherwise remain plan-only.",
    )
    _ = recover.add_argument("--json", action="store_true")
    _ = recover.add_argument("--lease-seconds", type=int, default=30)
    _ = recover.add_argument("--owner-id")
    _ = recover.add_argument("--request-id", required=True)
    _ = recover.add_argument("--assignment-id", required=True)
    _ = recover.add_argument("--expected-epoch", type=int, required=True)
    _ = recover.add_argument(
        "--dispatch-state",
        choices=("not-dispatched", "dispatched", "completed", "unknown"),
        required=True,
    )
    _ = recover.add_argument(
        "--settlement-state",
        choices=("not-required", "settled", "uncertain", "unknown"),
        required=True,
    )
    _ = recover.add_argument(
        "--failure-class",
        choices=("none", "transient", "rate-limited", "terminal", "unknown"),
        required=True,
    )
    _ = recover.add_argument("--failure-code", required=True)
    _ = recover.add_argument("--retry-after-seconds", type=int)
    _ = recover.add_argument(
        "--snapshot",
        action="append",
        default=[],
        metavar="SOURCE,OBSERVED,EXPIRES,DIGEST",
    )
    _ = recover.add_argument("--retry-base-seconds", type=int, default=30)
    _ = recover.add_argument("--retry-max-seconds", type=int, default=3600)
    _ = recover.add_argument("--max-attempts", type=int, default=5)
    _ = recover.add_argument("--max-elapsed-seconds", type=int, default=86400)
    _ = recover.add_argument("--jitter-percent", type=int, default=20)
    _ = recover.add_argument("--retry-after-ceiling-seconds", type=int, default=86400)
    return parser
