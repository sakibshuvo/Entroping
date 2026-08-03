from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

REPO_ROOT = Path(__file__).resolve().parents[1]
RECEIPT_SCHEMA_VERSION: Final[int] = 1
MAX_RECEIPT_BYTES: Final[int] = 4_096
MAX_FIELD_LENGTH: Final[int] = 96
MAX_LIST_ITEMS: Final[int] = 16
MAX_SUMMARIZED_FILES: Final[int] = 512
MAX_SUMMARIZED_BYTES: Final[int] = 2_000_000
_SCENARIO = re.compile(r"^[a-z0-9-]{1,80}$")
_ALLOWED_PATHS: Final[frozenset[str]] = frozenset({".entroping", "fake-worker"})
_FORBIDDEN_TEXT: Final[tuple[str, ...]] = (
    "secret",
    "token",
    "credential",
    "password",
    "api-key",
    "provider-output",
)
type InvariantClass = Literal[
    "authority-fail-closed",
    "bounded-pressure",
    "durable-reopen",
    "exact-settlement",
    "fail-closed",
    "no-provider",
    "no-source-mutation",
    "no-worker",
    "offline",
    "one-capacity-winner",
    "replay-safe",
    "restart-each-boundary",
    "settlement-hold-retained",
]
type ReturnClass = Literal[
    "assigned",
    "blocked",
    "bounded-complete",
    "exit-1",
    "fail-closed",
    "input-invalid",
    "one-capacity-winner",
    "recovered",
    "replay-conflict",
    "retry-scheduled",
    "settled-replay",
    "uncertain",
    "would-assign",
    "would-recover",
]
_ALLOWED_INVARIANTS: Final[frozenset[str]] = frozenset(
    {
        "authority-fail-closed",
        "bounded-pressure",
        "durable-reopen",
        "exact-settlement",
        "fail-closed",
        "no-provider",
        "no-source-mutation",
        "no-worker",
        "offline",
        "one-capacity-winner",
        "replay-safe",
        "restart-each-boundary",
        "settlement-hold-retained",
    }
)
_ALLOWED_RETURNS: Final[frozenset[str]] = frozenset(
    {
        "assigned",
        "blocked",
        "bounded-complete",
        "exit-1",
        "fail-closed",
        "input-invalid",
        "one-capacity-winner",
        "recovered",
        "replay-conflict",
        "retry-scheduled",
        "settled-replay",
        "uncertain",
        "would-assign",
        "would-recover",
    }
)


@dataclass(frozen=True, slots=True)
class StateSummary:
    digest: str
    file_total: int
    byte_total: int
    category_digests: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class ScenarioReceipt:
    scenario: str
    crash_point: str
    return_class: ReturnClass
    state_digest: str
    fake_call_count: int
    changed_paths: tuple[str, ...]
    file_total: int
    byte_total: int
    invariants: tuple[InvariantClass, ...]
    path: Path


class CountedFakeWorker:
    """Bounded test-only worker that persists one digest per observed dispatch."""

    def __init__(self, root: Path) -> None:
        self._path = root / "fake-worker-events.json"

    def dispatch(self, assignment_id: str) -> None:
        events = self._events()
        events.append(hashlib.sha256(assignment_id.encode("utf-8")).hexdigest())
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


@dataclass(frozen=True, slots=True)
class ScenarioObservation:
    root: Path
    scenario: str
    before: StateSummary
    worker: CountedFakeWorker

    @classmethod
    def begin(cls, root: Path, scenario: str) -> ScenarioObservation:
        if not _SCENARIO.fullmatch(scenario):
            raise AssertionError("scenario identifier is invalid")
        root.mkdir(parents=True, exist_ok=True)
        return cls(root, scenario, state_summary(root), CountedFakeWorker(root))

    def receipt(
        self,
        *,
        return_class: ReturnClass,
        crash_point: str = "none",
        checks: Mapping[InvariantClass, bool],
    ) -> ScenarioReceipt:
        return record_receipt(
            self, return_class=return_class, crash_point=crash_point, checks=checks
        )


def state_summary(root: Path) -> StateSummary:
    """Summarize only declared durable state, never scaffolding or receipts."""

    digest = hashlib.sha256()
    files = 0
    bytes_total = 0
    categories: list[tuple[str, str]] = []
    for durable_root in (root / ".entroping", root / "fake-worker-events.json"):
        if not durable_root.exists() and not durable_root.is_symlink():
            continue
        category = ".entroping" if durable_root.name == ".entroping" else "fake-worker"
        item_digest = hashlib.sha256()
        paths = (
            (durable_root,)
            if durable_root.is_file() or durable_root.is_symlink()
            else tuple(sorted(durable_root.rglob("*")))
        )
        for path in paths:
            stat = path.stat(follow_symlinks=False)
            relative = path.relative_to(root).as_posix().encode("utf-8")
            for current in (digest, item_digest):
                current.update(relative)
                current.update(str(stat.st_mode).encode("ascii"))
                current.update(str(stat.st_size).encode("ascii"))
            if path.is_symlink():
                digest.update(b"symlink")
                item_digest.update(b"symlink")
            elif path.is_file():
                files += 1
                bytes_total += stat.st_size
                content = hashlib.sha256(path.read_bytes()).digest()
                digest.update(content)
                item_digest.update(content)
        categories.append((category, item_digest.hexdigest()))
    if files > MAX_SUMMARIZED_FILES or bytes_total > MAX_SUMMARIZED_BYTES:
        raise AssertionError("scenario durable state exceeds receipt summary bounds")
    return StateSummary(digest.hexdigest(), files, bytes_total, tuple(sorted(categories)))


def record_receipt(
    observation: ScenarioObservation,
    *,
    return_class: ReturnClass,
    crash_point: str,
    checks: Mapping[InvariantClass, bool],
) -> ScenarioReceipt:
    after = state_summary(observation.root)
    changed = tuple(sorted(_changed_categories(observation.before, after)))
    invariants = tuple(sorted(_checked_invariants(checks)))
    payload = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "scenario": observation.scenario,
        "crash_point": crash_point,
        "return_class": return_class,
        "state_digest": after.digest,
        "fake_call_count": observation.worker.call_count,
        "changed_paths": changed,
        "file_total": after.file_total,
        "byte_total": after.byte_total,
        "durations_ms": {"compose": 0, "verify": 0},
        "invariants": invariants,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    _validate_payload(payload, encoded)
    path = _receipt_path(observation.root, observation.scenario)
    path.write_text(encoded, encoding="utf-8")
    return ScenarioReceipt(
        observation.scenario,
        crash_point,
        return_class,
        after.digest,
        observation.worker.call_count,
        changed,
        after.file_total,
        after.byte_total,
        invariants,
        path,
    )


def _changed_categories(before: StateSummary, after: StateSummary) -> frozenset[str]:
    prior, current = dict(before.category_digests), dict(after.category_digests)
    return frozenset(
        category
        for category in set(prior) | set(current)
        if prior.get(category) != current.get(category)
    )


def _checked_invariants(checks: Mapping[InvariantClass, bool]) -> frozenset[InvariantClass]:
    if not checks or set(checks) - _ALLOWED_INVARIANTS or not all(checks.values()):
        raise AssertionError("receipt invariant checks are incomplete or failed")
    return frozenset(checks)


def _receipt_path(root: Path, scenario: str) -> Path:
    candidate = Path(os.environ.get("ENTROPING_PROPOSAL_RECEIPTS_DIR", root / "receipts"))
    allowed = (REPO_ROOT / ".omo" / "evidence").resolve()
    if candidate.is_symlink() or not (
        _within(candidate.resolve(), allowed) or _within(candidate.resolve(), root.resolve())
    ):
        raise AssertionError("receipt destination escapes the approved fixture or evidence root")
    candidate.mkdir(parents=True, exist_ok=True)
    if candidate.is_symlink():
        raise AssertionError("receipt destination is a symlink")
    return candidate / f"{scenario}.json"


def _validate_payload(payload: Mapping[str, object], encoded: str) -> None:
    expected = {
        "schema_version",
        "scenario",
        "crash_point",
        "return_class",
        "state_digest",
        "fake_call_count",
        "changed_paths",
        "file_total",
        "byte_total",
        "durations_ms",
        "invariants",
    }
    changed_paths = payload["changed_paths"]
    invariants = payload["invariants"]
    file_total = payload["file_total"]
    byte_total = payload["byte_total"]
    if (
        set(payload) != expected
        or len(encoded.encode()) > MAX_RECEIPT_BYTES
        or not _SCENARIO.fullmatch(str(payload["scenario"]))
        or str(payload["return_class"]) not in _ALLOWED_RETURNS
        or len(str(payload["crash_point"])) > MAX_FIELD_LENGTH
        or len(str(payload["state_digest"])) != 64
    ):
        raise AssertionError("receipt schema or scalar bound failed")
    if not isinstance(changed_paths, tuple) or not isinstance(invariants, tuple):
        raise AssertionError("receipt lists are invalid")
    if not all(isinstance(value, str) for value in (*changed_paths, *invariants)):
        raise AssertionError("receipt lists leak non-categorical values")
    if (
        len(changed_paths) > MAX_LIST_ITEMS
        or len(invariants) > MAX_LIST_ITEMS
        or any(len(value) > MAX_FIELD_LENGTH for value in (*changed_paths, *invariants))
    ):
        raise AssertionError("receipt list bound failed")
    if not isinstance(file_total, int) or not isinstance(byte_total, int):
        raise AssertionError("receipt totals are invalid")
    if (
        set(changed_paths) - _ALLOWED_PATHS
        or set(invariants) - _ALLOWED_INVARIANTS
        or any(marker in encoded.lower() for marker in _FORBIDDEN_TEXT)
        or file_total > MAX_SUMMARIZED_FILES
        or byte_total > MAX_SUMMARIZED_BYTES
    ):
        raise AssertionError("receipt value class or summary bound failed")


def _within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
