"""Resolved QAnstitution provenance models."""

from dataclasses import dataclass
from pathlib import Path

from entroping.models.qanstitution import GateRule, Qanstitution


@dataclass(frozen=True, slots=True)
class EffectiveGateEvidence:
    """One effective gate plus the QAnstitution file that supplied it."""

    rule: GateRule
    source_path: Path
    group: str | None = None


@dataclass(frozen=True, slots=True)
class QanstitutionEvidence:
    """Resolved local QAnstitution with import and gate provenance."""

    policy: Qanstitution
    root_path: Path
    import_paths: tuple[Path, ...]
    gates: tuple[EffectiveGateEvidence, ...]
