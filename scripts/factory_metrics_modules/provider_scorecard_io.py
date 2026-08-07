"""Bounded no-follow provider-scorecard evidence loading."""
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Never, cast

from pydantic import ValidationError

from entroping.core.owner_only_evidence import (
    read_owner_only_local_evidence_artifact_bytes,
)
from scripts.ai_worker_file_safety import secret_like_content_reason

from .errors import FactoryMetricsError
from .provider_scorecard_schema import ProviderScorecardEvidence

PROVIDER_SCORECARD_MAX_BYTES = 1024 * 1024
SCORECARD_EVIDENCE_KEY_ENV = "ENTROPING_FACTORY_SCORECARD_EVIDENCE_HMAC_KEY_V1"
SCORECARD_EVIDENCE_KEY_BYTES = 32


def load_provider_scorecard(path: Path) -> ProviderScorecardEvidence:
    """Load one strict local scorecard without following artifact symlinks."""

    raw, read_error = read_owner_only_local_evidence_artifact_bytes(
        path, max_bytes=PROVIDER_SCORECARD_MAX_BYTES
    )
    if raw is None:
        if read_error.startswith("authorization"):
            raise FactoryMetricsError("provider scorecard authentication failed")
        raise FactoryMetricsError(f"provider scorecard could not be safely read ({read_error})")
    try:
        document = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise FactoryMetricsError("provider scorecard must be valid UTF-8") from None
    _reject_secret_like(document)
    try:
        parsed_value = cast(
            object,
            json.loads(
                document,
                object_pairs_hook=_reject_duplicate_pairs,
                parse_constant=_reject_non_finite,
                parse_float=_parse_finite_float,
            ),
        )
    except (json.JSONDecodeError, RecursionError) as exc:
        detail = exc.msg if isinstance(exc, json.JSONDecodeError) else "nesting is too deep"
        raise FactoryMetricsError(f"provider scorecard JSON is invalid ({detail})") from None
    if not isinstance(parsed_value, dict):
        raise FactoryMetricsError("provider scorecard JSON must be an object")
    parsed = cast(dict[str, object], parsed_value)
    _reject_secret_like(json.dumps(parsed, ensure_ascii=False, sort_keys=True))
    _verify_authentication(parsed)
    try:
        return ProviderScorecardEvidence.model_validate_json(document, strict=True)
    except ValidationError as exc:
        first = exc.errors(include_url=False, include_context=False, include_input=False)[0]
        location = ".".join(str(value) for value in first["loc"])
        prefix = f"{location}: " if location else ""
        raise FactoryMetricsError(
            f"provider scorecard schema is invalid ({prefix}{first['msg']})"
        ) from None


def canonical_provider_scorecard_payload(document: Mapping[str, object]) -> bytes:
    """Serialize the signed scorecard envelope without its authentication block."""

    unsigned = dict(document)
    _ = unsigned.pop("authentication", None)
    return json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _verify_authentication(document: Mapping[str, object]) -> None:
    authentication = document.get("authentication")
    if not isinstance(authentication, dict):
        raise FactoryMetricsError("provider scorecard authentication failed")
    authentication_mapping = cast(dict[str, object], authentication)
    scheme = authentication_mapping.get("scheme")
    key_id = authentication_mapping.get("key_id")
    signature = authentication_mapping.get("signature")
    if (
        scheme != "hmac-sha256"
        or key_id != "maintainer-local-v1"
        or not isinstance(signature, str)
        or len(signature) != 64
    ):
        raise FactoryMetricsError("provider scorecard authentication failed")
    key = _authentication_key()
    expected = hmac.new(
        key, canonical_provider_scorecard_payload(document), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise FactoryMetricsError("provider scorecard authentication failed")


def _authentication_key() -> bytes:
    raw = os.environ.get(SCORECARD_EVIDENCE_KEY_ENV)
    if raw is None or raw != raw.casefold():
        raise FactoryMetricsError("provider scorecard authentication failed")
    try:
        key = bytes.fromhex(raw)
    except ValueError:
        raise FactoryMetricsError("provider scorecard authentication failed") from None
    if len(key) != SCORECARD_EVIDENCE_KEY_BYTES:
        raise FactoryMetricsError("provider scorecard authentication failed")
    return key


def _reject_secret_like(value: str) -> None:
    reason = secret_like_content_reason(value)
    if reason is not None:
        raise FactoryMetricsError(f"provider scorecard contains secret-like content ({reason})")


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise FactoryMetricsError("duplicate JSON key is forbidden")
        result[key] = value
    return result


def _parse_finite_float(raw: str) -> float:
    value = float(raw)
    if not math.isfinite(value):
        _reject_non_finite(raw)
    return value


def _reject_non_finite(raw: str) -> Never:
    raise FactoryMetricsError(f"non-finite JSON number is forbidden: {raw}")
