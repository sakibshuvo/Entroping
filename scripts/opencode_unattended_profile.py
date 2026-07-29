from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final, Literal

Mode = Literal["review", "patch"]

SCHEMA_VERSION: Final = "entroping.opencode-unattended-capability-receipt.v1"
_PROFILE_IDS: Final[dict[Mode, str]] = {
    "review": "entroping.opencode-unattended-review.v1",
    "patch": "entroping.opencode-unattended-patch-proposal.v1",
}
_OUTPUT_CONTRACTS: Final[dict[Mode, str]] = {
    "review": "structured-review-findings",
    "patch": "textual-unified-diff-proposal",
}
_AGENTS: Final[dict[Mode, str]] = {
    "review": "entroping-unattended-review",
    "patch": "entroping-unattended-patch-proposal",
}
_CANONICAL_PATH: Final = "/usr/bin:/bin:/usr/sbin:/sbin"
_FIXED_ENVIRONMENT: Final[dict[str, str]] = {
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "LC_CTYPE": "C.UTF-8",
}
_ISOLATION_FLAGS: Final[dict[str, str]] = {
    "OPENCODE_DISABLE_PROJECT_CONFIG": "1",
    "OPENCODE_DISABLE_CLAUDE_CODE": "1",
    "OPENCODE_DISABLE_EXTERNAL_SKILLS": "1",
    "OPENCODE_DISABLE_DEFAULT_PLUGINS": "1",
    "OPENCODE_DISABLE_MODELS_FETCH": "1",
    "OPENCODE_DISABLE_AUTOUPDATE": "1",
    "OPENCODE_DISABLE_AUTOCOMPACT": "1",
    "OPENCODE_PURE": "1",
}
_ALLOWED_CAPABILITIES: Final = ("explicit_file_attachment",)
_DENIED_CAPABILITIES: Final = (
    "apply_patch",
    "bash",
    "custom",
    "doom_loop",
    "edit",
    "external_directory",
    "glob",
    "grep",
    "mcp",
    "question",
    "read",
    "skill",
    "subagent",
    "task",
    "todowrite",
    "unknown",
    "webfetch",
    "websearch",
    "write",
)
_ISOLATED_ROOT_CATEGORIES: Final = (
    "home",
    "xdg_config",
    "xdg_data",
    "xdg_state",
    "xdg_cache",
    "tmp",
    "worker_directory",
)


class UnattendedProfileError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class UnattendedProfile:
    mode: Mode
    profile_id: str
    output_contract: str
    model: str
    agent: str
    executable: Path
    isolated_root: Path
    worker_directory: Path
    snapshot_paths: tuple[Path, ...]
    probe_environment: Mapping[str, str]
    environment: Mapping[str, str]
    profile_digest: str

    def command(self, prompt: str) -> list[str]:
        command = [
            str(self.executable),
            "run",
            "--pure",
            "--agent",
            self.agent,
            "--dir",
            str(self.worker_directory),
            "--format",
            "json",
            "--model",
            self.model,
        ]
        for snapshot_path in self.snapshot_paths:
            command.extend(("--file", str(snapshot_path)))
        command.append(prompt)
        return command


@dataclass(frozen=True, slots=True)
class UnattendedAttestation:
    profile: UnattendedProfile
    executable_version: str
    executable_digest: str

    def receipt_payload(self) -> dict[str, str | bool | list[str]]:
        return {
            "schema_version": SCHEMA_VERSION,
            "profile_id": self.profile.profile_id,
            "mode": self.profile.mode,
            "model": self.profile.model,
            "agent": self.profile.agent,
            "output_contract": self.profile.output_contract,
            "executable_version": self.executable_version,
            "executable_digest": self.executable_digest,
            "profile_digest": self.profile.profile_digest,
            "allowed_capabilities": list(_ALLOWED_CAPABILITIES),
            "denied_capabilities": list(_DENIED_CAPABILITIES),
            "isolated_root_categories": list(_ISOLATED_ROOT_CATEGORIES),
            "sanitized_environment_keys": list(
                sorted(self.profile.environment)
            ),
            "pure_mode": True,
            "project_config_disabled": True,
            "share_disabled": True,
            "snapshot_disabled": True,
            "lsp_disabled": True,
            "subagents_disabled": True,
            "raw_values_recorded": False,
        }


def build_unattended_profile(
    *,
    mode: Mode,
    model: str,
    executable: Path,
    isolated_root: Path,
    snapshot_paths: tuple[Path, ...],
    inherited_environment: Mapping[str, str],
) -> UnattendedProfile:
    if executable.is_symlink() or not executable.is_file():
        raise UnattendedProfileError(
            "OpenCode executable must be a regular non-symlink file"
        )
    if isolated_root.is_symlink():
        raise UnattendedProfileError("OpenCode isolated root must not be a symlink")
    for snapshot_path in snapshot_paths:
        if snapshot_path.is_symlink() or not snapshot_path.is_file():
            raise UnattendedProfileError(
                "OpenCode snapshots must be regular non-symlink files"
            )
    root = isolated_root.resolve()
    directories = {
        "HOME": root / "home",
        "XDG_CONFIG_HOME": root / "xdg-config",
        "XDG_DATA_HOME": root / "xdg-data",
        "XDG_STATE_HOME": root / "xdg-state",
        "XDG_CACHE_HOME": root / "xdg-cache",
        "TMPDIR": root / "tmp",
    }
    worker_directory = root / "worker"
    config_directory = directories["XDG_CONFIG_HOME"] / "opencode"
    for directory in (*directories.values(), worker_directory, config_directory):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)

    config = _profile_config(mode, model)
    config_content = json.dumps(config, sort_keys=True, separators=(",", ":"))
    environment = dict(_FIXED_ENVIRONMENT)
    environment["PATH"] = _CANONICAL_PATH
    environment.update({key: str(value) for key, value in directories.items()})
    environment.update(_ISOLATION_FLAGS)
    environment["OPENCODE_CONFIG_DIR"] = str(config_directory)
    environment["OPENCODE_CONFIG_CONTENT"] = config_content
    probe_environment = MappingProxyType(dict(environment))
    if model.startswith("deepseek/") and "DEEPSEEK_API_KEY" in inherited_environment:
        environment["DEEPSEEK_API_KEY"] = inherited_environment["DEEPSEEK_API_KEY"]
    digest_contract = {
        "agent": _AGENTS[mode],
        "allowed_capabilities": _ALLOWED_CAPABILITIES,
        "config": config,
        "denied_capabilities": _DENIED_CAPABILITIES,
        "dispatch_environment_keys": sorted(environment),
        "fixed_environment": _FIXED_ENVIRONMENT,
        "isolation_flags": _ISOLATION_FLAGS,
        "model": model,
        "output_contract": _OUTPUT_CONTRACTS[mode],
        "probe_environment_keys": sorted(probe_environment),
        "profile_id": _PROFILE_IDS[mode],
    }
    profile_digest = hashlib.sha256(
        json.dumps(digest_contract, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return UnattendedProfile(
        mode=mode,
        profile_id=_PROFILE_IDS[mode],
        output_contract=_OUTPUT_CONTRACTS[mode],
        model=model,
        agent=_AGENTS[mode],
        executable=executable.resolve(),
        isolated_root=root,
        worker_directory=worker_directory,
        snapshot_paths=tuple(path.resolve() for path in snapshot_paths),
        probe_environment=probe_environment,
        environment=MappingProxyType(environment),
        profile_digest=profile_digest,
    )


def _profile_config(
    mode: Mode,
    model: str,
) -> dict[str, object]:
    permissions: dict[str, object] = {
        "*": "deny",
        **dict.fromkeys(_DENIED_CAPABILITIES, "deny"),
    }
    tools: dict[str, bool] = {
        "*": False,
        **dict.fromkeys(_DENIED_CAPABILITIES, False),
    }
    agent = _AGENTS[mode]
    return {
        "$schema": "https://opencode.ai/config.json",
        "agent": {
            agent: {
                "mode": "primary",
                "model": model,
                "steps": 1,
                "permission": permissions,
                "tools": tools,
            }
        },
        "default_agent": agent,
        "formatter": False,
        "instructions": [],
        "lsp": False,
        "mcp": {},
        "model": model,
        "permission": permissions,
        "plugin": [],
        "share": "disabled",
        "snapshot": False,
        "subagent_depth": 0,
        "tools": tools,
    }
