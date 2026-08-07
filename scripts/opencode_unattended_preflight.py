from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import ClassVar, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from scripts.bounded_process import BoundedProcessError, run_bounded_process
from scripts.opencode_unattended_profile import (
    UnattendedAttestation,
    UnattendedProfile,
    UnattendedProfileError,
    build_unattended_profile,
)

type PermissionDecision = Literal["allow", "ask", "deny"]
type PermissionRule = PermissionDecision | dict[str, PermissionDecision]
type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]

SUPPORTED_OPENCODE_VERSIONS: Final = frozenset({"1.18.4"})
PREFLIGHT_PROBE_TIMEOUT_SECONDS: Final = 5.0
PREFLIGHT_MAX_SECONDS: Final = 20.0
PREFLIGHT_OUTPUT_LIMIT_BYTES: Final = 32_768
_VERSION_PATTERN: Final = re.compile(
    r"(?:opencode\s+)?(?P<version>\d+\.\d+\.\d+)"
)
_REQUIRED_HELP_TOKENS: Final = (
    "--pure",
    "--agent",
    "--dir",
    "--format",
    "json",
    "--model",
    "--file",
    "--auto",
    "dangerous",
)


class _StrictConfigModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        strict=True,
    )


class _CompactionConfig(_StrictConfigModel):
    auto: bool = False


class _AgentConfig(_StrictConfigModel):
    mode: str
    model: str
    options: dict[str, JsonValue] = Field(default_factory=dict)
    permission: dict[str, PermissionRule]
    steps: int
    tools: dict[str, bool]


class _EffectiveConfig(_StrictConfigModel):
    schema_url: str = Field(alias="$schema")
    agent: dict[str, _AgentConfig]
    command: dict[str, JsonValue] = Field(default_factory=dict)
    compaction: _CompactionConfig = Field(default_factory=_CompactionConfig)
    default_agent: str
    formatter: bool
    instructions: tuple[str, ...]
    lsp: bool
    mcp: dict[str, JsonValue]
    mode: dict[str, JsonValue] = Field(default_factory=dict)
    model: str
    permission: dict[str, PermissionRule]
    plugin: tuple[str, ...]
    provider: dict[str, JsonValue] = Field(default_factory=dict)
    reference: dict[str, JsonValue] = Field(default_factory=dict)
    share: Literal["disabled"]
    skills: dict[str, JsonValue] = Field(default_factory=dict)
    snapshot: bool
    subagent_depth: int
    tools: dict[str, bool]
    username: str | None = None

    def capability_contract(self) -> Self:
        return self.model_copy(update={"username": None})


def preflight_unattended_profile(profile: UnattendedProfile) -> UnattendedAttestation:
    deadline = time.monotonic() + PREFLIGHT_MAX_SECONDS

    def probe(command: tuple[str, ...]) -> str:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise UnattendedProfileError("OpenCode preflight exceeded its total deadline")
        return _profile_probe(
            profile,
            command,
            timeout_seconds=min(PREFLIGHT_PROBE_TIMEOUT_SECONDS, remaining),
        )

    initial_digest = _file_digest(profile.executable)
    version_text = probe((str(profile.executable), "--version"))
    version = _supported_version(version_text)
    help_text = probe((str(profile.executable), "run", "--help"))
    missing = [token for token in _REQUIRED_HELP_TOKENS if token not in help_text]
    if missing:
        raise UnattendedProfileError(
            "OpenCode run --help cannot prove the unattended contract; missing: "
            + ", ".join(missing)
        )
    resolved_text = probe(
        (str(profile.executable), "--pure", "debug", "config"),
    )
    resolved = _parse_effective_config(resolved_text)
    expected = _parse_effective_config(
        profile.environment["OPENCODE_CONFIG_CONTENT"]
    )
    if resolved.capability_contract() != expected.capability_contract():
        raise UnattendedProfileError(
            "OpenCode resolved config does not honor the deny-first unattended profile"
        )
    final_version = _supported_version(probe((str(profile.executable), "--version")))
    if final_version != version:
        raise UnattendedProfileError("OpenCode version changed during preflight")
    if _file_digest(profile.executable) != initial_digest:
        raise UnattendedProfileError("OpenCode executable digest changed during preflight")
    return UnattendedAttestation(
        profile=profile,
        executable_version=version,
        executable_digest=initial_digest,
    )


def verify_execution_binding(attestation: UnattendedAttestation) -> None:
    profile = attestation.profile
    if _file_digest(profile.executable) != attestation.executable_digest:
        raise UnattendedProfileError("OpenCode executable digest changed after preflight")
    expected = build_unattended_profile(
        mode=profile.mode,
        model=profile.model,
        executable=profile.executable,
        isolated_root=profile.isolated_root,
        snapshot_paths=profile.snapshot_paths,
        inherited_environment=profile.environment,
    )
    if expected.profile_digest != profile.profile_digest:
        raise UnattendedProfileError("OpenCode unattended profile digest changed")


def _parse_effective_config(payload: str) -> _EffectiveConfig:
    try:
        return _EffectiveConfig.model_validate_json(payload)
    except (ValidationError, ValueError) as exc:
        raise UnattendedProfileError(
            "OpenCode debug config returned invalid or unsupported JSON"
        ) from exc


def _supported_version(output: str) -> str:
    match = _VERSION_PATTERN.fullmatch(output.strip())
    if match is None or match.group("version") not in SUPPORTED_OPENCODE_VERSIONS:
        supported = ", ".join(sorted(SUPPORTED_OPENCODE_VERSIONS))
        raise UnattendedProfileError(
            f"unsupported OpenCode version; reviewed versions: {supported}"
        )
    return match.group("version")


def _profile_probe(
    profile: UnattendedProfile,
    command: tuple[str, ...],
    *,
    timeout_seconds: float,
) -> str:
    try:
        completed = run_bounded_process(
            command,
            cwd=profile.worker_directory,
            env=profile.probe_environment,
            timeout_seconds=timeout_seconds,
            max_output_bytes=PREFLIGHT_OUTPUT_LIMIT_BYTES,
        )
    except BoundedProcessError as exc:
        raise UnattendedProfileError("OpenCode preflight could not run safely") from exc
    if completed.timed_out:
        raise UnattendedProfileError("OpenCode preflight command timed out")
    if completed.output_limit_exceeded:
        raise UnattendedProfileError("OpenCode preflight command exceeded output limit")
    if completed.returncode != 0:
        raise UnattendedProfileError(
            f"OpenCode preflight command failed with exit {completed.returncode}"
        )
    outputs = tuple(
        output.strip()
        for output in (completed.stdout, completed.stderr)
        if output.strip()
    )
    if not outputs:
        raise UnattendedProfileError("OpenCode preflight command returned empty output")
    if len(outputs) != 1:
        raise UnattendedProfileError(
            "OpenCode preflight command returned ambiguous output streams"
        )
    return outputs[0]


def _file_digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise UnattendedProfileError(
            "OpenCode executable must remain a regular non-symlink file"
        )
    digest = hashlib.sha256()
    try:
        with path.open("rb") as executable_file:
            for chunk in iter(lambda: executable_file.read(65_536), b""):
                digest.update(chunk)
    except OSError as exc:
        raise UnattendedProfileError("OpenCode executable is not readable") from exc
    return digest.hexdigest()
