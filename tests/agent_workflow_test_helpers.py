"""Shared values for frozen agent-workflow documentation contracts."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def concat_text(*parts: str) -> str:
    """Join text fragments without implicit concatenation."""
    return "".join(parts)
