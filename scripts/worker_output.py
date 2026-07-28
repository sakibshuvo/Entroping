from __future__ import annotations

import json
import os
import uuid
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

OUTPUT_LIMIT_MARKER = "[output truncated: byte limit exceeded]\n"
type ResponseReadError = Literal["invalid_utf8", "too_large"]


class BoundedReadable(Protocol):
    def read(self, n: int = -1) -> bytes: ...


@dataclass(frozen=True, slots=True)
class BoundedResponseRead:
    text: str | None
    error: ResponseReadError | None


def read_bounded_utf8(stream: BoundedReadable, limit: int) -> BoundedResponseRead:
    payload = stream.read(limit + 1)
    if len(payload) > limit:
        return BoundedResponseRead(text=None, error="too_large")
    try:
        return BoundedResponseRead(text=payload.decode("utf-8"), error=None)
    except UnicodeDecodeError:
        return BoundedResponseRead(text=None, error="invalid_utf8")


def bounded_persisted_text(text: str, limit: int) -> str:
    payload = text.encode("utf-8")
    if len(payload) <= limit:
        return text
    marker = OUTPUT_LIMIT_MARKER.encode("utf-8")
    if len(marker) >= limit:
        return marker[:limit].decode("utf-8", errors="ignore")
    head = payload[: limit - len(marker)].decode("utf-8", errors="ignore")
    return f"{head}{OUTPUT_LIMIT_MARKER}"


def serialized_json_payload(payload: dict[str, object], limit: int) -> str | None:
    response_json = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    serialized = f"{response_json}\n"
    return serialized if len(serialized.encode("utf-8")) <= limit else None


def atomic_write_text(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = -1
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary, flags, 0o600)
        payload = content.encode("utf-8")
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        _ = temporary.replace(path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        with suppress(FileNotFoundError):
            temporary.unlink()
