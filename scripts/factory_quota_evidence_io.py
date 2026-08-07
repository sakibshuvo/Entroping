from __future__ import annotations

import hashlib
import hmac
import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError

from entroping.core.evidence_common import read_local_evidence_artifact_bytes

from .ai_worker_file_safety import secret_like_content_reason
from .factory_quota_evidence_models import (
    AuthenticatedFactoryProviderEvidence as AuthenticatedFactoryProviderEvidence,
)
from .factory_quota_evidence_models import (
    FactoryProviderEvidence,
)
from .factory_quota_evidence_models import (
    FactoryProviderEvidenceError as FactoryProviderEvidenceError,
)

EVIDENCE_MAX_BYTES = 256 * 1024
PROVIDER_EVIDENCE_RELATIVE_PATH = Path(".entroping") / "factory-provider-evidence.json"
PROVIDER_EVIDENCE_KEY_ENV = "ENTROPING_FACTORY_PROVIDER_EVIDENCE_HMAC_KEY_V1"
PROVIDER_EVIDENCE_KEY_ID = "maintainer-local-v1"
PROVIDER_EVIDENCE_KEY_BYTES = 32


def read_provider_evidence(
    path: Path,
    *,
    authentication_key: bytes,
) -> AuthenticatedFactoryProviderEvidence:
    raw, read_error = read_local_evidence_artifact_bytes(path, max_bytes=EVIDENCE_MAX_BYTES)
    if raw is None:
        raise FactoryProviderEvidenceError(
            "evidence_file",
            f"could not safely read provider evidence ({read_error})",
        )
    try:
        document = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise FactoryProviderEvidenceError(
            "evidence_file",
            "provider evidence must be valid UTF-8",
        ) from None
    secret_reason = secret_like_content_reason(document)
    if secret_reason is not None:
        raise FactoryProviderEvidenceError(
            "evidence_secret",
            f"provider evidence contains secret-like content ({secret_reason})",
        )
    try:
        parsed = json.loads(document, object_pairs_hook=_reject_duplicate_pairs)
        evidence = FactoryProviderEvidence.model_validate_json(document, strict=True)
    except (json.JSONDecodeError, PydanticValidationError, RecursionError):
        raise FactoryProviderEvidenceError(
            "evidence_json",
            "provider evidence JSON is invalid",
        ) from None
    canonical = canonical_provider_evidence_payload(parsed)
    expected = hmac.new(authentication_key, canonical, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(evidence.authentication.signature, expected):
        raise FactoryProviderEvidenceError(
            "evidence_authentication",
            "provider evidence authentication failed",
        )
    return AuthenticatedFactoryProviderEvidence(
        evidence,
        hashlib.sha256(canonical).hexdigest(),
    )


def read_provider_evidence_for_dispatch(
    repo_root: Path,
    *,
    required: bool,
    test_path: Path | None = None,
) -> AuthenticatedFactoryProviderEvidence | None:
    if not required:
        return None
    path = _trusted_evidence_path(repo_root, test_path=test_path)
    key = _authentication_key()
    return read_provider_evidence(path, authentication_key=key)


def canonical_provider_evidence_payload(document: Mapping[str, object]) -> bytes:
    unsigned = dict(document)
    _ = unsigned.pop("authentication", None)
    return json.dumps(
        unsigned,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def provider_evidence_signature(document: Mapping[str, object], key: bytes) -> str:
    return hmac.new(
        key,
        canonical_provider_evidence_payload(document),
        hashlib.sha256,
    ).hexdigest()


def _authentication_key() -> bytes:
    raw = os.environ.get(PROVIDER_EVIDENCE_KEY_ENV)
    if raw is None:
        raise FactoryProviderEvidenceError(
            "evidence_authentication",
            "provider evidence authentication key is unavailable",
        )
    try:
        key = bytes.fromhex(raw)
    except ValueError:
        key = b""
    if len(key) != PROVIDER_EVIDENCE_KEY_BYTES or raw != raw.casefold():
        raise FactoryProviderEvidenceError(
            "evidence_authentication",
            "provider evidence authentication key is invalid",
        )
    return key


def _trusted_evidence_path(repo_root: Path, *, test_path: Path | None) -> Path:
    root = Path(os.path.abspath(repo_root.expanduser()))
    if test_path is None:
        path = root / PROVIDER_EVIDENCE_RELATIVE_PATH
    else:
        path = Path(os.path.abspath(test_path.expanduser()))
    if test_path is None and path != root / PROVIDER_EVIDENCE_RELATIVE_PATH:
        raise FactoryProviderEvidenceError(
            "evidence_path",
            "provider evidence must use the protected default path",
        )
    _require_owner_only_path(path)
    return path


def _require_owner_only_path(path: Path) -> None:
    try:
        parent_stat = path.parent.stat(follow_symlinks=False)
        file_stat = path.stat(follow_symlinks=False)
    except OSError:
        raise FactoryProviderEvidenceError(
            "evidence_file",
            "could not safely inspect provider evidence",
        ) from None
    if (
        not stat.S_ISDIR(parent_stat.st_mode)
        or not stat.S_ISREG(file_stat.st_mode)
        or parent_stat.st_uid != os.geteuid()
        or file_stat.st_uid != os.geteuid()
        or parent_stat.st_mode & 0o022
        or file_stat.st_mode & 0o022
    ):
        raise FactoryProviderEvidenceError(
            "evidence_permissions",
            "provider evidence ownership or permissions are unsafe",
        )


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise FactoryProviderEvidenceError(
                "evidence_json",
                "duplicate provider evidence JSON key is forbidden",
            )
        result[key] = value
    return result
