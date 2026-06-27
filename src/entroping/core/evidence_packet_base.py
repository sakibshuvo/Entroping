"""Shared helpers for deterministic local evidence packet reports."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from entroping.core.safe_write import SafeWriteError, safe_write_text


@dataclass(frozen=True, slots=True)
class EvidencePacketResult[PacketType: BaseModel]:
    """Result of writing one local evidence packet artifact."""

    output_path: Path
    packet: PacketType


def render_packet_content[PacketType: BaseModel](
    packet: PacketType,
    *,
    output: str,
    render_markdown: Callable[[PacketType], str],
) -> str:
    """Render packet content in JSON or markdown form."""

    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    if output == "md":
        return render_markdown(packet)
    msg = f"unsupported packet output: {output}"
    raise ValueError(msg)


def write_evidence_packet_report[PacketType: BaseModel](
    *,
    project_root: Path,
    output: str,
    output_path: Path,
    packet: PacketType,
    render_markdown: Callable[[PacketType], str],
    has_secret_content: Callable[[str], bool],
    secret_error_message: str,
    artifact: str,
    error_type: type[Exception],
    safe_write: Callable[..., Path] = safe_write_text,
) -> EvidencePacketResult[PacketType]:
    """Write a local evidence packet with shared safety and formatting checks."""

    content = render_packet_content(
        packet,
        output=output,
        render_markdown=render_markdown,
    )
    if has_secret_content(content):
        raise error_type(secret_error_message)

    try:
        written = safe_write(
            output_path,
            content,
            artifact=artifact,
            root=project_root,
        )
    except SafeWriteError as exc:
        raise error_type(str(exc)) from exc

    return EvidencePacketResult(output_path=written, packet=packet)
