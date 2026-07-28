from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from .factory_cost_policy_io import read_policy_document
from .factory_cost_policy_models import FactoryCostPolicy, summarize_policy
from .factory_cost_policy_schema import factory_cost_policy_json_schema
from .factory_cost_policy_validation import FactoryCostPolicyError, validate_policy_at


@dataclass(frozen=True, slots=True)
class ValidateArguments:
    policy: Path
    as_of: str


@dataclass(frozen=True, slots=True)
class SchemaArguments:
    pass


type Arguments = ValidateArguments | SchemaArguments


class _ValidateNamespace(argparse.Namespace):
    def __init__(self) -> None:
        super().__init__()
        self.command: str = ""
        self.policy: Path = Path()
        self.as_of: str = ""


def _parse_args() -> Arguments:
    parser = argparse.ArgumentParser(
        description="Validate the local Entroping factory cost policy.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    _ = validate.add_argument("--policy", type=Path, required=True)
    _ = validate.add_argument("--as-of", required=True)
    _ = subparsers.add_parser("schema")
    namespace = _ValidateNamespace()
    _ = parser.parse_args(namespace=namespace)
    if namespace.command == "schema":
        return SchemaArguments()
    return ValidateArguments(policy=namespace.policy, as_of=namespace.as_of)


def _parse_as_of(raw: str) -> datetime:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise FactoryCostPolicyError(
            code="as_of",
            detail="as-of timestamp must use ISO 8601",
        ) from None


def main() -> int:
    args = _parse_args()
    if isinstance(args, SchemaArguments):
        print(json.dumps(factory_cost_policy_json_schema(), sort_keys=True))
        return 0
    try:
        as_of = _parse_as_of(args.as_of)
        document = read_policy_document(args.policy)
        policy = FactoryCostPolicy.model_validate_json(document)
        validate_policy_at(policy, as_of)
    except (FactoryCostPolicyError, OSError, ValueError, ValidationError) as exc:
        print(f"factory_cost_policy: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summarize_policy(policy), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
