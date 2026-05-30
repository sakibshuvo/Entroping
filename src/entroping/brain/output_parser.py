"""Parser for untrusted Architect provider output."""

import json
from collections.abc import Mapping

from pydantic import ValidationError

from entroping.models import ArchitectEditSet


class ArchitectOutputParseError(ValueError):
    """Raised when provider output cannot become validated Architect edits."""


def parse_architect_edit_set(content: str) -> ArchitectEditSet:
    """Parse provider JSON content into a strict ``ArchitectEditSet``."""

    if not content.strip():
        msg = "Architect output must not be empty"
        raise ArchitectOutputParseError(msg)

    try:
        payload: object = json.loads(content)
    except json.JSONDecodeError as exc:
        msg = f"Architect output must be a valid JSON object: {exc.msg}"
        raise ArchitectOutputParseError(msg) from exc
    if not isinstance(payload, Mapping):
        msg = "Architect output must be a valid JSON object"
        raise ArchitectOutputParseError(msg)

    try:
        return ArchitectEditSet.model_validate(payload)
    except ValidationError as exc:
        msg = f"Invalid Architect edit set: {exc}"
        raise ArchitectOutputParseError(msg) from exc
