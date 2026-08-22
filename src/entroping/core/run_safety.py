"""Protected-environment safety preflight for deterministic runs."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from entroping.models.hurl import HurlTest
from entroping.models.report import RunSafetyEvidence

READ_ONLY_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS"})
MUTATING_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})
ALLOWED_PROTECTED_SAFETY: frozenset[str] = frozenset({"read-only", "idempotent", "teardown-backed"})
ALL_SAFETY_VALUES: frozenset[str] = ALLOWED_PROTECTED_SAFETY | frozenset({"destructive"})


class RunSafetyError(ValueError):
    """Raised when run safety metadata is malformed."""


@dataclass(frozen=True, slots=True)
class RunSafetyBlock:
    """One selected Hurl test blocked before Hurl execution."""

    path: Path
    evidence: RunSafetyEvidence


@dataclass(frozen=True, slots=True)
class RunSafetyEvaluation:
    """Safety evidence for a selected deterministic run."""

    protected_environment: bool
    evidence_by_path: dict[Path, RunSafetyEvidence]
    blocks: tuple[RunSafetyBlock, ...]


def evaluate_run_safety(
    tests: Sequence[HurlTest],
    *,
    environment: str | None,
    protected_run: bool,
    suite_safety: str | None,
    protected_environments: Sequence[str],
) -> RunSafetyEvaluation:
    """Evaluate selected Hurl tests before any subprocess execution."""

    protected_environment = protected_run or is_protected_environment(
        environment,
        protected_environments=protected_environments,
    )
    normalized_suite_safety = (
        _normalize_safety(suite_safety, source="suite metadata")
        if suite_safety is not None
        else None
    )
    evidence_by_path: dict[Path, RunSafetyEvidence] = {}
    blocks: list[RunSafetyBlock] = []

    for hurl_test in tests:
        safety, safety_source = _test_safety(hurl_test, suite_safety=normalized_suite_safety)
        mutating_methods = tuple(
            sorted(
                {
                    exchange.method.upper()
                    for exchange in hurl_test.exchanges
                    if _is_mutating(exchange.method)
                }
            )
        )
        if not protected_environment and safety is None:
            continue
        if not mutating_methods and safety is None:
            continue

        blocked_reason = _blocked_reason(
            protected_environment=protected_environment,
            safety=safety,
            mutating_methods=mutating_methods,
        )
        evidence = RunSafetyEvidence(
            protected_environment=protected_environment,
            safety=safety,
            safety_source=safety_source,
            methods=mutating_methods,
            blocked_reason=blocked_reason,
        )
        evidence_by_path[hurl_test.path.expanduser().resolve()] = evidence
        if blocked_reason is not None:
            blocks.append(
                RunSafetyBlock(path=hurl_test.path.expanduser().resolve(), evidence=evidence)
            )

    return RunSafetyEvaluation(
        protected_environment=protected_environment,
        evidence_by_path=evidence_by_path,
        blocks=tuple(blocks),
    )


def is_protected_environment(
    environment: str | None,
    *,
    protected_environments: Sequence[str],
) -> bool:
    """Return whether a run environment name is protected."""

    if environment is None:
        return False
    normalized = environment.strip().lower()
    protected = {_normalize_environment_name(item) for item in protected_environments}
    return normalized in protected


def _test_safety(
    hurl_test: HurlTest,
    *,
    suite_safety: str | None,
) -> tuple[str | None, str | None]:
    metadata_value = hurl_test.metadata.meta.get("safety")
    if metadata_value is not None:
        return _normalize_safety(metadata_value, source="test metadata"), "test metadata"

    safety_tags = sorted(
        {
            _normalize_safety(tag, source="test tag")
            for tag in hurl_test.metadata.tags
            if _looks_like_safety(tag)
        }
    )
    if len(safety_tags) > 1:
        msg = f"{hurl_test.path}: multiple safety tags are ambiguous: " + ", ".join(safety_tags)
        raise RunSafetyError(msg)
    if safety_tags:
        return safety_tags[0], "test tag"
    if suite_safety is not None:
        return suite_safety, "suite metadata"
    return None, None


def _blocked_reason(
    *,
    protected_environment: bool,
    safety: str | None,
    mutating_methods: tuple[str, ...],
) -> str | None:
    if not protected_environment:
        return None
    if safety == "destructive":
        return "destructive tests are blocked in protected environments"
    if not mutating_methods:
        return None
    if safety == "read-only":
        if len(mutating_methods) == 1:
            return (
                "read-only safety metadata conflicts with mutating method "
                f"{mutating_methods[0]} in protected environments"
            )
        return (
            "read-only safety metadata conflicts with mutating methods "
            + ", ".join(mutating_methods)
            + " in protected environments"
        )
    if safety in {"idempotent", "teardown-backed"}:
        return None
    if len(mutating_methods) == 1:
        return (
            f"mutating method {mutating_methods[0]} requires safety metadata "
            "in protected environments"
        )
    return (
        "mutating methods "
        + ", ".join(mutating_methods)
        + " require safety metadata in protected environments"
    )


def _is_mutating(method: str) -> bool:
    upper_method = method.upper()
    return upper_method in MUTATING_METHODS or upper_method not in READ_ONLY_METHODS


def _looks_like_safety(value: str) -> bool:
    return _canonical_safety(value) in ALL_SAFETY_VALUES


def _normalize_safety(value: str, *, source: str) -> str:
    normalized = _canonical_safety(value)
    if not normalized:
        msg = f"{source} safety value must not be empty"
        raise RunSafetyError(msg)
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        msg = f"{source} safety value must not contain control characters"
        raise RunSafetyError(msg)
    if normalized not in ALL_SAFETY_VALUES:
        msg = (
            f"Unsupported {source} safety value {value!r}; expected read-only, "
            "idempotent, teardown-backed, or destructive"
        )
        raise RunSafetyError(msg)
    return normalized


def _canonical_safety(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def _normalize_environment_name(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        msg = "protected environment names must not be empty"
        raise RunSafetyError(msg)
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        msg = "protected environment names must not contain control characters"
        raise RunSafetyError(msg)
    return normalized
