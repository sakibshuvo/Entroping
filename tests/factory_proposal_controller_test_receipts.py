from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeGuard, assert_never

from factory_proposal_controller_test_receipt_contracts import (
    CRASH_POINTS,
    FORBIDDEN_TEXT,
    MAX_PROVIDER_CALLS,
    MAX_RECEIPT_BYTES,
    RECEIPT_SCHEMA_VERSION,
    CompositionOutcome,
    CrashPoint,
    InvariantClass,
    ReceiptPayload,
    ReturnClass,
    ScenarioReceipt,
    StateSummary,
)
from factory_proposal_controller_test_receipt_state import (
    receipt_path as _receipt_path,
)
from factory_proposal_controller_test_receipt_state import (
    state_summary,
)
from factory_proposal_controller_test_receipt_state import (
    write_new_receipt as _write_new_receipt,
)
from factory_proposal_controller_test_source_manifest import SourceManifest
from pydantic import ValidationError

_SCENARIO = re.compile(r"^[a-z0-9-]{1,80}$")


class CountedFakeWorker:
    def __init__(self, root: Path) -> None:
        self._path = root / "fake-worker-events.json"

    def dispatch(self, assignment_id: str) -> None:
        events = self._events()
        events.append(hashlib.sha256(assignment_id.encode()).hexdigest())
        self._path.write_text(json.dumps(events), encoding="utf-8")

    @property
    def call_count(self) -> int:
        return len(self._events())

    def _events(self) -> list[str]:
        if not self._path.exists():
            return []
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(raw, list) or not all(isinstance(value, str) for value in raw):
            raise AssertionError("fake worker evidence is malformed")
        return raw


class CountedProviderBoundary:
    def __init__(self, root: Path) -> None:
        self._path = root / "provider-model-events.json"

    def invoke(self, call_id: str) -> None:
        events = self._events()
        if len(events) >= MAX_PROVIDER_CALLS:
            raise AssertionError("provider/model call counter exceeds its bound")
        events.append(hashlib.sha256(call_id.encode()).hexdigest())
        self._path.write_text(json.dumps(events), encoding="utf-8")

    @property
    def call_count(self) -> int:
        return len(self._events())

    def _events(self) -> list[str]:
        if not self._path.exists():
            return []
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(raw, list) or not all(isinstance(value, str) for value in raw):
            raise AssertionError("provider/model call evidence is malformed")
        if len(raw) > MAX_PROVIDER_CALLS:
            raise AssertionError("provider/model call evidence exceeds its bound")
        return raw


class ProviderDispatchPort(Protocol):
    def invoke(self, call_id: str) -> None: ...


@dataclass(frozen=True, slots=True)
class PendingReceipt:
    observation: ScenarioObservation
    return_class: ReturnClass
    crash_point: CrashPoint
    after: StateSummary
    worker_call_count: int
    provider_call_count: int


@dataclass(frozen=True, slots=True)
class ScenarioObservation:
    root: Path
    scenario: str
    before: StateSummary
    worker: CountedFakeWorker
    provider: CountedProviderBoundary

    @classmethod
    def begin(cls, root: Path, scenario: str) -> ScenarioObservation:
        if not _SCENARIO.fullmatch(scenario):
            raise AssertionError("scenario identifier is invalid")
        root.mkdir(parents=True, exist_ok=True)
        return cls(
            root,
            scenario,
            state_summary(root),
            CountedFakeWorker(root),
            CountedProviderBoundary(root),
        )

    def receipt(self, *, return_class: ReturnClass, crash_point: str = "none") -> PendingReceipt:
        if not _is_crash_point(crash_point):
            raise AssertionError("receipt crash point is not categorical")
        return PendingReceipt(
            self,
            return_class,
            crash_point,
            state_summary(self.root),
            self.worker.call_count,
            self.provider.call_count,
        )


def compose_counted_worker(
    observation: ScenarioObservation,
    outcome: CompositionOutcome,
    provider_dispatch: ProviderDispatchPort,
    *,
    provider_call_id: str | None = None,
) -> None:
    if provider_call_id is not None:
        provider_dispatch.invoke(provider_call_id)
    match outcome.decision:
        case "assigned":
            if outcome.assignment_id is None or outcome.denial_reason is not None:
                raise AssertionError("assigned composition outcome is inconsistent")
            observation.worker.dispatch(outcome.assignment_id)
        case "blocked":
            if outcome.assignment_id is not None or outcome.denial_reason is None:
                raise AssertionError("blocked composition outcome is inconsistent")
        case unreachable:
            assert_never(unreachable)


def finalize_receipt(
    pending: PendingReceipt, source_before: SourceManifest, source_after: SourceManifest
) -> ScenarioReceipt:
    if source_before != source_after:
        raise AssertionError("scenario mutated tracked source or Git state")
    observation = pending.observation
    after = pending.after
    changed = tuple(sorted(_changed_categories(observation.before, after)))
    invariants: list[InvariantClass] = ["offline", "no-source-mutation"]
    if pending.provider_call_count == 0:
        invariants.append("no-provider")
    if pending.worker_call_count == 0:
        invariants.append("no-worker")
    payload = ReceiptPayload.model_validate(
        {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "scenario": observation.scenario,
            "crash_point": pending.crash_point,
            "return_class": pending.return_class,
            "state_digest": after.digest,
            "fake_call_count": pending.worker_call_count,
            "provider_call_count": pending.provider_call_count,
            "changed_paths": changed,
            "file_total": after.file_total,
            "byte_total": after.byte_total,
            "durations_ms": {"compose": 0, "verify": 0},
            "invariants": tuple(sorted(invariants)),
        },
        strict=True,
    )
    encoded = payload.model_dump_json()
    _validate_payload(payload.model_dump(mode="python"), encoded)
    path = _receipt_path(observation.root, observation.scenario)
    _write_new_receipt(path, encoded)
    return ScenarioReceipt(
        observation.scenario,
        pending.crash_point,
        pending.return_class,
        after.digest,
        pending.worker_call_count,
        pending.provider_call_count,
        changed,
        after.file_total,
        after.byte_total,
        tuple(sorted(invariants)),
        path,
    )


def _changed_categories(before: StateSummary, after: StateSummary) -> frozenset[str]:
    prior, current = dict(before.category_digests), dict(after.category_digests)
    return frozenset(
        category
        for category in set(prior) | set(current)
        if prior.get(category) != current.get(category)
    )


def _validate_payload(payload: dict[str, object], encoded: str) -> None:
    if len(encoded.encode()) > MAX_RECEIPT_BYTES:
        raise AssertionError("receipt byte bound failed")
    try:
        parsed_payload = ReceiptPayload.model_validate(payload, strict=True)
        parsed_encoded = ReceiptPayload.model_validate_json(encoded, strict=True)
    except ValidationError as exc:
        raise AssertionError("receipt schema validation failed") from exc
    if parsed_payload != parsed_encoded or encoded != parsed_payload.model_dump_json():
        raise AssertionError("receipt payload and encoding differ")
    if any(marker in encoded.lower() for marker in FORBIDDEN_TEXT):
        raise AssertionError("receipt contains a forbidden leakage class")


def scenario_receipt_from_path(path: Path) -> ScenarioReceipt:
    try:
        payload = ReceiptPayload.model_validate_json(path.read_bytes(), strict=True)
    except (OSError, ValidationError) as exc:
        raise AssertionError("scenario child receipt is invalid") from exc
    return ScenarioReceipt(
        payload.scenario,
        payload.crash_point,
        payload.return_class,
        payload.state_digest,
        payload.fake_call_count,
        payload.provider_call_count,
        payload.changed_paths,
        payload.file_total,
        payload.byte_total,
        payload.invariants,
        path,
    )


def _is_crash_point(value: str) -> TypeGuard[CrashPoint]:
    return value in CRASH_POINTS
