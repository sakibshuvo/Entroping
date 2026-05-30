"""Parser for untrusted Architect provider output."""

import json
from collections.abc import Mapping

from pydantic import ValidationError

from entroping.brain.safety import redact_secret_like_values
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
        msg = f"Invalid Architect edit set: {_format_validation_error(exc)}"
        raise ArchitectOutputParseError(msg) from exc


def _format_validation_error(exc: ValidationError) -> str:
    messages: list[str] = []
    for error in exc.errors(include_input=False, include_url=False):
        location = ".".join(str(part) for part in error.get("loc", ()))
        detail = str(error.get("msg", "invalid value"))
        if location:
            messages.append(f"{location}: {detail}")
        else:
            messages.append(detail)
    return redact_secret_like_values("; ".join(messages))
