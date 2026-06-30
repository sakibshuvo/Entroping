from pathlib import Path
from typing import Final

HURL_SOURCE_MAX_BYTES: Final = 10 * 1024 * 1024


class HurlSourceTooLargeError(ValueError):
    pass


def read_hurl_source_text(path: Path, *, label: str = "Hurl source") -> str:
    max_bytes = HURL_SOURCE_MAX_BYTES
    if max_bytes < 1:
        msg = "Hurl source byte limit must be positive"
        raise HurlSourceTooLargeError(msg)
    with path.open("rb") as handle:
        raw_bytes = handle.read(max_bytes + 1)
    if len(raw_bytes) > max_bytes:
        msg = f"{label} {path} exceeds {max_bytes} bytes"
        raise HurlSourceTooLargeError(msg)
    return raw_bytes.decode("utf-8")
