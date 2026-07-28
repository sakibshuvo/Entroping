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

_CUSTOM_VALIDATION_ERRORS = frozenset(
    {
        "ambiguous_price_unit",
        "cash_reserve",
        "cash_reserve_threshold",
        "duplicate_identifier",
        "duplicate_reference",
        "lane_model_provider",
        "policy_window",
        "price_model",
        "price_model_provider",
        "price_provider",
        "price_reference",
        "price_window",
        "quota_provider",
        "quota_reference",
        "quota_subscription_provider",
        "quota_subscription_reference",
        "subscription_provider",
        "subscription_reference",
    }
)


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


def _validation_error_detail(exc: ValidationError) -> str:
    details: list[str] = []
    for error in exc.errors(
        include_url=False,
        include_context=False,
        include_input=False,
    ):
        error_type = str(error["type"])
        if error_type in _CUSTOM_VALIDATION_ERRORS:
            detail = str(error["msg"])
        else:
            location = tuple(str(part) for part in error.get("loc", ()))
            detail = _builtin_validation_error_detail(error_type, location)
        if detail not in details:
            details.append(detail)
        if len(details) == 8:
            break
    return "; ".join(details) if details else "policy declaration is invalid"


def _builtin_validation_error_detail(
    error_type: str,
    location: tuple[str, ...],
) -> str:
    if error_type in {"union_tag_invalid", "union_tag_not_found"}:
        return "unsupported tagged policy variant"
    if error_type == "literal_error":
        if "automatic_top_up" in location:
            return "automatic top-up must remain disabled"
        if "currency" in location:
            return "currency must be USD"
        if "timezone" in location or "calendar_month_timezone" in location:
            return "timezone must be UTC"
        return "policy field contains an unsupported literal"
    builtin_details = {
        "datetime_parsing": "timestamp must be a valid datetime",
        "datetime_type": "timestamp must be a valid datetime",
        "extra_forbidden": "unknown policy field is forbidden",
        "finite_number": "number must be finite",
        "greater_than": "value must be greater than 0",
        "greater_than_equal": "value is below the supported minimum",
        "int_type": "value must be a valid integer",
        "less_than_equal": "value exceeds the supported maximum",
        "missing": "required policy field is missing",
        "string_pattern_mismatch": "identifier has an unsupported format",
        "timezone_aware": "timestamp must include a timezone offset",
        "too_long": "policy collection exceeds its supported size",
        "too_short": "policy collection is missing required entries",
        "tuple_type": "policy collection must be an array",
    }
    return builtin_details.get(error_type, "policy declaration is invalid")


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
    except ValidationError as exc:
        print(
            f"factory_cost_policy: validation: {_validation_error_detail(exc)}",
            file=sys.stderr,
        )
        return 2
    except (FactoryCostPolicyError, OSError, ValueError) as exc:
        print(f"factory_cost_policy: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summarize_policy(policy), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
