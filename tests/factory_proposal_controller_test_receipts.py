from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import TypeGuard, assert_never

from factory_proposal_controller_test_receipt_contracts import (
    ALLOWED_INVARIANTS,
    ALLOWED_PATHS,
    ALLOWED_RETURNS,
    CRASH_POINTS,
    FORBIDDEN_TEXT,
    MAX_FIELD_LENGTH,
    MAX_LIST_ITEMS,
    MAX_PROVIDER_CALLS,
    MAX_RECEIPT_BYTES,
    MAX_SUMMARIZED_BYTES,
    MAX_SUMMARIZED_FILES,
    RECEIPT_SCHEMA_VERSION,
    CompositionOutcome,
    CrashPoint,
    InvariantClass,
    ReturnClass,
    ScenarioReceipt,
    StateSummary,
)
from factory_proposal_controller_test_receipt_state import state_summary
from factory_proposal_controller_test_source_manifest import SourceManifest

REPO_ROOT = Path(__file__).resolve().parents[1]
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


@dataclass(frozen=True, slots=True)
class PendingReceipt:
    observation: ScenarioObservation
    return_class: ReturnClass
    crash_point: CrashPoint


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
        return PendingReceipt(self, return_class, crash_point)


def compose_counted_worker(observation: ScenarioObservation, outcome: CompositionOutcome) -> None:
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
    after = state_summary(observation.root)
    changed = tuple(sorted(_changed_categories(observation.before, after)))
    invariants: list[InvariantClass] = ["offline", "no-source-mutation"]
    if observation.provider.call_count == 0:
        invariants.append("no-provider")
    if observation.worker.call_count == 0:
        invariants.append("no-worker")
    payload = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "scenario": observation.scenario,
        "crash_point": pending.crash_point,
        "return_class": pending.return_class,
        "state_digest": after.digest,
        "fake_call_count": observation.worker.call_count,
        "provider_call_count": observation.provider.call_count,
        "changed_paths": changed,
        "file_total": after.file_total,
        "byte_total": after.byte_total,
        "durations_ms": {"compose": 0, "verify": 0},
        "invariants": tuple(sorted(invariants)),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    _validate_payload(payload, encoded)
    path = _receipt_path(observation.root, observation.scenario)
    _write_new_receipt(path, encoded)
    return ScenarioReceipt(
        observation.scenario,
        pending.crash_point,
        pending.return_class,
        after.digest,
        observation.worker.call_count,
        observation.provider.call_count,
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


def _receipt_path(root: Path, scenario: str) -> Path:
    candidate = Path(os.environ.get("ENTROPING_PROPOSAL_RECEIPTS_DIR", root / "receipts"))
    allowed = (REPO_ROOT / ".omo" / "evidence").resolve()
    resolved = candidate.resolve()
    if candidate.is_symlink() or not (
        _within(resolved, allowed) or _within(resolved, root.resolve())
    ):
        raise AssertionError("receipt destination escapes the approved fixture or evidence root")
    candidate.mkdir(parents=True, exist_ok=True)
    path = candidate / f"{scenario}.json"
    if path.exists() or path.is_symlink():
        raise AssertionError("receipt destination is reused or unsafe")
    return path


def _write_new_receipt(path: Path, encoded: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    committed = False
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise AssertionError("receipt destination is not an exclusive regular file")
        data = encoded.encode()
        if len(data) > MAX_RECEIPT_BYTES or os.write(descriptor, data) != len(data):
            raise AssertionError("receipt write was incomplete or exceeded its bound")
        committed = True
    finally:
        os.close(descriptor)
        if not committed:
            path.unlink(missing_ok=True)


def _validate_payload(payload: dict[str, object], encoded: str) -> None:
    expected = {
        "schema_version",
        "scenario",
        "crash_point",
        "return_class",
        "state_digest",
        "fake_call_count",
        "provider_call_count",
        "changed_paths",
        "file_total",
        "byte_total",
        "durations_ms",
        "invariants",
    }
    changed, invariants = payload["changed_paths"], payload["invariants"]
    if set(payload) != expected or len(encoded.encode()) > MAX_RECEIPT_BYTES:
        raise AssertionError("receipt schema or byte bound failed")
    if (
        not _SCENARIO.fullmatch(str(payload["scenario"]))
        or str(payload["return_class"]) not in ALLOWED_RETURNS
    ):
        raise AssertionError("receipt categorical scalar failed")
    if str(payload["crash_point"]) not in CRASH_POINTS or len(str(payload["state_digest"])) != 64:
        raise AssertionError("receipt crash point or digest failed")
    if not isinstance(changed, tuple) or not isinstance(invariants, tuple):
        raise AssertionError("receipt lists are invalid")
    values = (*changed, *invariants)
    values_are_bounded = all(
        isinstance(value, str) and len(value) <= MAX_FIELD_LENGTH for value in values
    )
    if len(changed) > MAX_LIST_ITEMS or len(invariants) > MAX_LIST_ITEMS or not values_are_bounded:
        raise AssertionError("receipt list bound failed")
    files, bytes_total = payload["file_total"], payload["byte_total"]
    provider_calls = payload["provider_call_count"]
    if (
        not isinstance(files, int)
        or not isinstance(bytes_total, int)
        or not isinstance(provider_calls, int)
        or not 0 <= provider_calls <= MAX_PROVIDER_CALLS
    ):
        raise AssertionError("receipt totals are invalid")
    if set(changed) - ALLOWED_PATHS or set(invariants) - ALLOWED_INVARIANTS:
        raise AssertionError("receipt categorical value leaked")
    if files > MAX_SUMMARIZED_FILES or bytes_total > MAX_SUMMARIZED_BYTES:
        raise AssertionError("receipt summary bound failed")
    if any(marker in encoded.lower() for marker in FORBIDDEN_TEXT):
        raise AssertionError("receipt contains a forbidden leakage class")


def _within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _is_crash_point(value: str) -> TypeGuard[CrashPoint]:
    return value in CRASH_POINTS
