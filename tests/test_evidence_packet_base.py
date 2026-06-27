from __future__ import annotations

import pytest
from pydantic import BaseModel

from entroping.core.evidence_packet_base import render_packet_content


class _Packet(BaseModel):
    value: str


def test_render_packet_content_rejects_unsupported_output() -> None:
    packet = _Packet(value="evidence")

    with pytest.raises(ValueError, match="unsupported packet output: yaml"):
        render_packet_content(
            packet,
            output="yaml",
            render_markdown=lambda _: "unused",
        )
