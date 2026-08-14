"""Shared CLI presentation helpers."""

from pathlib import Path

from rich.console import Console

from entroping.brain import ArchitectAuditReviewParseError, ArchitectOutputParseError
from entroping.brain.safety import redact_secret_like_values
from entroping.core.hurl_validator import HurlValidationError

console = Console()


def display_cli_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def safe_cli_text(value: object) -> str:
    redacted = redact_secret_like_values(str(value))
    return "".join(
        character
        if (ord_character := ord(character)) in {9, 10}
        else "�"
        if (ord_character < 32 or ord_character == 127 or 128 <= ord_character <= 159)
        else character
        for character in redacted
    )


def print_cli_error(exc: BaseException) -> None:
    console.print(safe_cli_text(exc), style="red", markup=False)


def print_architect_error(exc: BaseException) -> None:
    print_cli_error(exc)
    if isinstance(exc, ArchitectOutputParseError):
        console.print("Architect output validation failed before write.", style="yellow")
        console.print(
            "Expected JSON object with summary, optional warnings, and edits[].",
            style="yellow",
        )
        console.print(
            "Retry guidance: return only the Architect JSON object. "
            "Do not wrap the response in Markdown fences.",
            style="yellow",
            markup=False,
            soft_wrap=True,
        )
        console.print("No Architect files were written.", style="yellow")
    if isinstance(exc, ArchitectAuditReviewParseError):
        console.print("Auditor output validation failed before display.", style="yellow")
        console.print(
            "Expected JSON object with summary, findings[], and optional warnings[].",
            style="yellow",
        )
        console.print(
            "Retry guidance: return only the Auditor JSON object. "
            "Do not wrap the response in Markdown fences.",
            style="yellow",
            markup=False,
            soft_wrap=True,
        )
        console.print("No files were written.", style="yellow")
    if isinstance(exc, HurlValidationError):
        console.print("Architect Hurl validation failed before write.", style="yellow")
        console.print(
            "Retry guidance: return syntactically valid Hurl. "
            "Keep generated content in the selected Hurl file only.",
            style="yellow",
            markup=False,
            soft_wrap=True,
        )
        console.print("No Architect files were written.", style="yellow")
