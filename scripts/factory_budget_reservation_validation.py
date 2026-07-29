from __future__ import annotations

import hashlib
import json
import re

from .factory_budget_ledger_models import SIGNED_64_BIT_MAX, FactoryBudgetLedgerError

EVIDENCE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


def public_reservation_id(idempotency_key: str) -> str:
    return f"res-{hashlib.sha256(idempotency_key.encode('utf-8')).hexdigest()[:32]}"


def require_sha256(value: str, label: str) -> None:
    if SHA256_PATTERN.fullmatch(value) is None:
        raise FactoryBudgetLedgerError("evidence", f"{label} must be a SHA-256 digest")


def canonical_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def require_identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or EVIDENCE_IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise FactoryBudgetLedgerError("identifier", f"{label} is invalid")


def require_positive_int(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FactoryBudgetLedgerError("integer", f"{label} must be a positive integer")
    if value > SIGNED_64_BIT_MAX:
        raise FactoryBudgetLedgerError("integer", f"{label} exceeds the signed 64-bit boundary")


def require_non_negative_int(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FactoryBudgetLedgerError("integer", f"{label} must be a non-negative integer")
    if value > SIGNED_64_BIT_MAX:
        raise FactoryBudgetLedgerError("integer", f"{label} exceeds the signed 64-bit boundary")
