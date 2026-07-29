#!/usr/bin/env python3
"""Build compact review packets from bounded AI worker artifacts."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.factory_review_packet_model import (  # noqa: E402
    PacketError,
    build_packet,
)
from scripts.factory_review_packet_validation import (  # noqa: E402
    enforce_tier_a_proposal_policy,
    safe_packet_json,
    validate_packet,
)
from scripts.script_safety import (  # noqa: E402
    ScriptSafetyError,
    run_subprocess,
)

DEFAULT_JOB_ROOT = Path(".entroping") / "ai-jobs"
DEFAULT_ARTIFACT_ROOT = Path(".entroping") / "ai-reviews"


def main() -> int:
    try:
        args = _parse_args()
        repo_root = _repo_root()
        job_root = _resolve_root(repo_root, args.job_root, "job root")
        artifact_root = _resolve_root(repo_root, args.artifact_root, "artifact root")
        packet = build_packet(
            job_id=args.job_id,
            raw_artifact_dir=args.artifact_dir,
            job_root=job_root,
            artifact_root=artifact_root,
        )
        enforce_tier_a_proposal_policy(packet, repo_root=repo_root)
        validate_packet(packet)
        serialized_packet = safe_packet_json(packet)
    except PacketError as exc:
        print(f"factory_review_packet: {exc}", file=sys.stderr)
        return 2

    _print_packet(
        packet,
        json_output=args.json,
        serialized_packet=serialized_packet,
    )
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Print compact, transcript-free evidence for Codex review of AI worker artifacts."
        )
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--job-id", help="AI job id to find under the job root.")
    source.add_argument("--artifact-dir", type=Path, help="Worker artifact directory.")
    parser.add_argument(
        "--job-root",
        type=Path,
        default=DEFAULT_JOB_ROOT,
        help="AI job queue root. Default: .entroping/ai-jobs",
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_ARTIFACT_ROOT,
        help="Worker artifact root. Default: .entroping/ai-reviews",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable output.")
    return parser.parse_args()


def _repo_root() -> Path:
    try:
        completed = run_subprocess(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            timeout=5,
            max_output_bytes=2048,
        )
    except ScriptSafetyError as exc:
        msg = "run this from inside the Entroping git repository"
        raise PacketError(msg) from exc
    return Path(completed.stdout.strip()).resolve()


def _resolve_root(repo_root: Path, raw_root: Path, purpose: str) -> Path:
    root = raw_root.expanduser()
    relative_root = not root.is_absolute()
    if relative_root:
        root = repo_root / root
    if _has_symlink_component(root):
        msg = f"{purpose} must not use symlink components"
        raise PacketError(msg)
    resolved = root.resolve()
    if relative_root:
        try:
            resolved.relative_to(repo_root)
        except ValueError as exc:
            msg = f"{purpose} must stay inside repository"
            raise PacketError(msg) from exc
    elif not (
        _path_is_relative_to(resolved, repo_root)
        or _path_is_relative_to(resolved, _system_temp_root())
    ):
        msg = f"{purpose} must stay inside repository or system temp directory"
        raise PacketError(msg)
    return resolved


def _path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _system_temp_root() -> Path:
    return Path(tempfile.gettempdir()).resolve()


def _has_symlink_component(path: Path) -> bool:
    return any(candidate.is_symlink() for candidate in (path, *path.parents))


def _print_packet(
    packet: dict[str, Any],
    *,
    json_output: bool,
    serialized_packet: str,
) -> None:
    if json_output:
        print(serialized_packet)
        return

    job = packet.get("job")
    artifact = packet.get("artifact")
    print(f"Factory review packet: {packet['schema_version']}")
    if isinstance(job, dict):
        print(f"Job: {job.get('job_id')} issue={job.get('issue')} model={job.get('model')}")
        print(f"Worker status: {job.get('worker_status')}")
    if isinstance(artifact, dict):
        print(f"Artifact: {artifact.get('artifact_dir')}")
        if "metadata_path" in artifact:
            print(f"Metadata: {artifact['metadata_path']}")
        if "result_summary_path" in artifact:
            print(f"Result summary: {artifact['result_summary_path']}")
        if "tests_path" in artifact:
            print(f"Tests: {artifact['tests_path']}")
        proposal = artifact.get("proposal_diff")
        if isinstance(proposal, dict):
            print(
                "Proposal diff: "
                + f"{proposal.get('files_changed', 0)} files, "
                + f"+{proposal.get('additions', 0)} "
                + f"-{proposal.get('deletions', 0)}"
            )


if __name__ == "__main__":
    raise SystemExit(main())
