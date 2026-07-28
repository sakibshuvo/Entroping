from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import cast

from pydantic import ValidationError

from scripts.factory_inbox_io import repo_root as discover_repo_root
from scripts.factory_retention_apply import ApplyResult, RetentionApplyError, apply_retention_plan
from scripts.factory_retention_fs import (
    RetentionFsError,
    open_relative_directory,
    path_exists,
    read_bounded_regular,
)
from scripts.factory_retention_inventory import RetentionInventory, inventory_factory
from scripts.factory_retention_models import RetentionPlanReport, RetentionPolicy
from scripts.factory_retention_plan import plan_retention

DEFAULT_LOCAL_POLICY = Path(".entroping/factory-retention-policy.json")
DEFAULT_EXAMPLE_POLICY = Path("docs/meta/factory-retention-policy.example.json")


class RetentionCliError(ValueError):
    pass


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
        repo_root = _repo_root(cast(Path | None, args.repo_root))
        policy = _load_policy(repo_root, cast(Path | None, args.policy))
        as_of = _as_of(cast(str | None, args.as_of))
        inventory = inventory_factory(repo_root)
        plan = plan_retention(policy, inventory.candidates, as_of)
        apply_result = None
        apply_requested = bool(getattr(args, "apply", False))
        command = cast(str, args.command)
        if command == "prune" and apply_requested:
            apply_result = apply_retention_plan(repo_root, plan, inventory)
        payload = _payload(command, apply_requested, inventory, plan, apply_result)
        if cast(bool, args.json):
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            _print_human(payload)
        return 0
    except (
        OSError,
        RetentionApplyError,
        RetentionCliError,
        RetentionFsError,
        ValidationError,
        ValueError,
    ) as exc:
        print(f"factory_retention: {exc}", file=sys.stderr)
        return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan or explicitly apply bounded local factory retention."
    )
    common = argparse.ArgumentParser(add_help=False)
    _ = common.add_argument("--repo-root", type=Path)
    _ = common.add_argument("--policy", type=Path)
    _ = common.add_argument("--as-of", help="UTC ISO-8601 planning instant. Default: now.")
    _ = common.add_argument("--json", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _ = subparsers.add_parser("plan", parents=[common], help="Print a read-only prune plan.")
    prune = subparsers.add_parser(
        "prune",
        parents=[common],
        help="Print a plan, or apply it only with --apply.",
    )
    _ = prune.add_argument(
        "--apply",
        action="store_true",
        help="Apply the fresh validated plan.",
    )
    return parser


def _repo_root(raw_root: Path | None) -> Path:
    if raw_root is None:
        return discover_repo_root()
    if raw_root.is_symlink():
        raise RetentionCliError("repository root must not be a symlink")
    root = raw_root.expanduser().resolve()
    if not root.is_dir():
        raise RetentionCliError("repository root must be a directory")
    return root


def _load_policy(repo_root: Path, raw_policy: Path | None) -> RetentionPolicy:
    policy = raw_policy
    if policy is None:
        local_policy_exists = path_exists(repo_root, DEFAULT_LOCAL_POLICY.parts)
        policy = DEFAULT_LOCAL_POLICY if local_policy_exists else DEFAULT_EXAMPLE_POLICY
    relative = _repo_relative_path(repo_root, policy)
    with open_relative_directory(repo_root, relative.parts[:-1]) as directory_fd:
        payload = read_bounded_regular(directory_fd, relative.parts[-1])
    return RetentionPolicy.model_validate_json(payload, strict=True)


def _repo_relative_path(repo_root: Path, raw_path: Path) -> PurePosixPath:
    expanded = raw_path.expanduser()
    if expanded.is_absolute():
        try:
            relative = expanded.relative_to(repo_root)
        except ValueError as exc:
            raise RetentionCliError("policy must stay inside the repository") from exc
    else:
        relative = expanded
    pure = PurePosixPath(relative.as_posix())
    if not pure.parts or any(part in {".", ".."} for part in pure.parts):
        raise RetentionCliError("policy path must be canonical and repository-relative")
    return pure


def _as_of(raw_value: str | None) -> datetime:
    if raw_value is None:
        return datetime.now(UTC)
    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RetentionCliError("as-of must be a valid UTC ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise RetentionCliError("as-of must be UTC")
    return parsed.astimezone(UTC)


def _payload(
    command: str,
    apply_requested: bool,
    inventory: RetentionInventory,
    plan: RetentionPlanReport,
    apply_result: ApplyResult | None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "schema_version": "entroping.factory-retention-command.v1",
        "command": command,
        "mode": "apply" if apply_requested else "plan-only",
        "blocked": bool(inventory.errors),
        "inventory_errors": list(inventory.errors),
        "plan": plan.model_dump(mode="json"),
    }
    if apply_result is not None:
        result["apply"] = asdict(apply_result)
    return result


def _print_human(payload: dict[str, object]) -> None:
    plan_value = payload["plan"]
    if not isinstance(plan_value, dict):
        raise RetentionCliError("retention plan output is invalid")
    plan = cast(dict[str, object], plan_value)
    print(f"Mode: {payload['mode']}")
    print(f"Delete: {plan['total_delete_count']} entries / {plan['total_delete_bytes']} bytes")
    print(f"Retain: {plan['total_retain_count']} entries / {plan['total_retain_bytes']} bytes")
    errors = payload["inventory_errors"]
    if isinstance(errors, list) and errors:
        error_items = cast(list[object], errors)
        print(f"Blocked: {len(error_items)} inventory error(s)")
        for error in error_items:
            print(f"- {error}")
    elif payload["mode"] == "plan-only":
        print("No files changed. Use `prune --apply` for explicit deletion.")
    else:
        print("Prune completed; the durable journal receipt remains under .entroping/.")


if __name__ == "__main__":
    raise SystemExit(main())
