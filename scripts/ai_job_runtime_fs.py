from __future__ import annotations

from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path

from scripts import ai_job_fs

QUEUE_STATES = ("queued", "running", "completed", "failed")


@dataclass(frozen=True)
class QueueStateHandles:
    job_root: Path
    directories: dict[str, int]

    def names(self, state: str) -> list[str]:
        return ai_job_fs.list_json_names(self._directory(state))

    def read_bytes(self, state: str, name: str) -> bytes:
        return ai_job_fs.read_regular_bytes(self._directory(state), name)

    def write_json(
        self,
        state: str,
        name: str,
        payload: dict[str, object],
    ) -> None:
        ai_job_fs.atomic_write_json(self._directory(state), name, payload)

    def move(self, source: str, target: str, name: str) -> None:
        ai_job_fs.rename_entry(
            self._directory(source),
            name,
            self._directory(target),
            name,
        )

    def unlink(self, state: str, name: str) -> None:
        ai_job_fs.unlink_entry(self._directory(state), name, missing_ok=True)

    def path(self, state: str, name: str) -> Path:
        self._directory(state)
        return self.job_root / state / name

    def _directory(self, state: str) -> int:
        try:
            return self.directories[state]
        except KeyError as exc:
            raise ai_job_fs.SafeStateError(f"unknown queue state: {state}") from exc


@contextmanager
def open_queue_state(job_root: Path) -> Generator[QueueStateHandles, None, None]:
    ai_job_fs.ensure_job_root(job_root)
    with ExitStack() as stack:
        directories = {
            state: stack.enter_context(ai_job_fs.open_state_directory(job_root, state))
            for state in QUEUE_STATES
        }
        yield QueueStateHandles(job_root=job_root, directories=directories)
