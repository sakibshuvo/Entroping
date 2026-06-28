from pathlib import Path


class BoundedReadError(ValueError):
    pass


def read_text_bounded(path: Path, *, max_bytes: int, label: str) -> str:
    if max_bytes < 1:
        msg = f"{label} byte limit must be positive"
        raise BoundedReadError(msg)
    try:
        with path.open("rb") as handle:
            raw_bytes = handle.read(max_bytes + 1)
    except OSError as exc:
        msg = f"Could not read {label} {path}: {exc}"
        raise BoundedReadError(msg) from exc
    if len(raw_bytes) > max_bytes:
        msg = f"{label} {path} exceeds {max_bytes} bytes"
        raise BoundedReadError(msg)
    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        msg = f"Could not decode {label} {path} as UTF-8: {exc}"
        raise BoundedReadError(msg) from exc
