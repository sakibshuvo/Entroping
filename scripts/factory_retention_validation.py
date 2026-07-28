from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import PurePosixPath

from pydantic_core import PydanticCustomError

from scripts.factory_retention_types import MAX_PATH_LENGTH, ArtifactClass

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def require_utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise PydanticCustomError("timestamp", "timestamp must be UTC")


def require_clean_text(value: str) -> None:
    if value != value.strip() or _CONTROL_CHARS.search(value):
        raise PydanticCustomError("text", "text must be canonical and control-free")


def require_managed_path(artifact_class: ArtifactClass, raw_path: str) -> None:
    require_clean_text(raw_path)
    if len(raw_path) > MAX_PATH_LENGTH or raw_path.startswith("/") or "\\" in raw_path:
        raise PydanticCustomError("relative_path", "path must be repository-relative")
    path = PurePosixPath(raw_path)
    if raw_path == "." or path.as_posix() != raw_path or any(
        part in {".", ".."} for part in path.parts
    ):
        raise PydanticCustomError("relative_path", "path must be canonical")
    parts = path.parts
    valid = (
        artifact_class == "ai_job"
        and len(parts) == 4
        and parts[:2] == (".entroping", "ai-jobs")
        and parts[2] in {"completed", "failed"}
        and parts[3].endswith(".json")
    ) or (
        artifact_class == "ai_review"
        and len(parts) == 3
        and parts[:2] == (".entroping", "ai-reviews")
    ) or (
        artifact_class == "factory_log"
        and len(parts) == 3
        and parts[:2] == (".entroping", "factory-logs")
        and re.fullmatch(r"factory-tick\.(?:out|err)\.log(?:\.\d+)?", parts[2]) is not None
    ) or (
        artifact_class == "factory_metrics_archive"
        and len(parts) == 4
        and parts[:3] == (".entroping", "factory-metrics", "finished-issues")
        and re.fullmatch(r"issue-[1-9][0-9]*", parts[3]) is not None
    ) or (
        artifact_class == "retention_journal"
        and len(parts) == 3
        and parts[:2] == (".entroping", "retention-journal")
        and re.fullmatch(r"[0-9a-f]{32}\.json", parts[2]) is not None
    )
    if not valid:
        raise PydanticCustomError("managed_path", "path is outside its managed class root")
