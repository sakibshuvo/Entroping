from __future__ import annotations

import json
import os
import stat
from typing import cast

from scripts.factory_metrics_archive_errors import FactoryMetricsArchiveError
from scripts.factory_retention_fs import RetentionFsError, read_bounded_regular

MAX_ARCHIVE_METADATA_BYTES = 65_536


def require_metadata_fits(payload: dict[str, object]) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(encoded) > MAX_ARCHIVE_METADATA_BYTES:
        raise FactoryMetricsArchiveError(
            "factory metrics archive metadata exceeds its byte limit"
        )


def read_archive_metadata(archive_fd: int) -> dict[str, object] | None:
    try:
        metadata = os.stat("metadata.json", dir_fd=archive_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(metadata.st_mode):
        raise FactoryMetricsArchiveError("factory metrics metadata must be a regular file")
    try:
        raw = cast(
            object,
            json.loads(
                read_bounded_regular(
                    archive_fd,
                    "metadata.json",
                    limit=MAX_ARCHIVE_METADATA_BYTES,
                )
            ),
        )
    except (json.JSONDecodeError, UnicodeDecodeError, RetentionFsError) as exc:
        raise FactoryMetricsArchiveError("factory metrics metadata is unreadable") from exc
    if not isinstance(raw, dict):
        raise FactoryMetricsArchiveError("factory metrics metadata must be a JSON object")
    return cast(dict[str, object], raw)
