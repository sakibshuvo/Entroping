#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts import ai_jobs  # noqa: E402
from scripts.ai_job_quarantine_modules.quarantine import quarantine_jobs  # noqa: E402
from scripts.ai_job_quarantine_modules.requeue import requeue_job  # noqa: E402


def main() -> int:
    try:
        args = _parse_args()
        payload = _dispatch(args)
    except ImportError:
        print(
            "ai_job_quarantine: project dependencies are unavailable; run "
            "`uv run python scripts/ai_job_quarantine.py ...`.",
            file=sys.stderr,
        )
        return 2
    except ai_jobs.AiJobError as exc:
        print(f"ai_job_quarantine: {exc}", file=sys.stderr)
        return 2
    _print_payload(payload, json_output=bool(args.json))
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan or apply fail-closed quarantine for queued AI jobs.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    quarantine = subparsers.add_parser(
        "quarantine",
        help="Plan quarantine for malformed or routing-invalid queued jobs.",
    )
    quarantine.add_argument(
        "--job-root",
        type=Path,
        default=ai_jobs.DEFAULT_JOB_ROOT,
    )
    quarantine.add_argument("--apply", action="store_true")
    quarantine.add_argument("--json", action="store_true")
    requeue = subparsers.add_parser(
        "requeue",
        help="Revalidate a quarantined job and explicitly plan a safe requeue.",
    )
    requeue.add_argument(
        "--job-root",
        type=Path,
        default=ai_jobs.DEFAULT_JOB_ROOT,
    )
    requeue.add_argument("--job-id", required=True)
    requeue.add_argument(
        "--engine",
        choices=("opencode", "deepseek-api"),
        required=True,
    )
    requeue.add_argument("--profile", required=True)
    requeue.add_argument("--model")
    requeue.add_argument("--apply", action="store_true")
    requeue.add_argument("--json", action="store_true")
    return parser.parse_args()


def _dispatch(args: argparse.Namespace) -> dict[str, object]:
    repo_root = ai_jobs._repo_root()
    job_root = ai_jobs._resolve_root(repo_root, args.job_root, "job root")
    if args.command == "quarantine":
        return quarantine_jobs(repo_root, job_root, apply=bool(args.apply))
    if args.command == "requeue":
        return requeue_job(
            repo_root,
            job_root,
            job_id=str(args.job_id),
            engine=args.engine,
            profile=str(args.profile),
            model=args.model,
            apply=bool(args.apply),
        )
    msg = f"unknown command: {args.command}"
    raise ai_jobs.AiJobError(msg)


def _print_payload(payload: dict[str, object], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(f"AI job quarantine status: {payload['status']}")
    if "candidate_count" in payload:
        print(f"Candidates: {payload['candidate_count']}")
    if "job_path" in payload:
        print(f"Queued job: {payload['job_path']}")


if __name__ == "__main__":
    raise SystemExit(main())
