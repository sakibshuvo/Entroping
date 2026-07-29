from __future__ import annotations

import json
import stat
import sys
import time
from collections.abc import Mapping
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.opencode_unattended_preflight as preflight_module  # noqa: E402
from scripts.opencode_unattended_preflight import (  # noqa: E402
    preflight_unattended_profile,
    verify_execution_binding,
)
from scripts.opencode_unattended_profile import (  # noqa: E402
    UnattendedProfileError,
    build_unattended_profile,
)


def _write_fake_opencode(
    path: Path,
    *,
    help_text: str | None = None,
    version: str = "1.18.4",
) -> Path:
    help_output = help_text or (
        "--pure --agent --dir --format json --model --file --auto --attach "
        "--continue --session --share --interactive dangerous"
    )
    path.write_text(
        "#!/bin/sh\n"
        f"if [ \"${{1:-}}\" = '--version' ]; then echo {json.dumps(version)}; exit 0; fi\n"
        "if [ \"${1:-} ${2:-}\" = 'run --help' ]; then\n"
        f"  echo {json.dumps(help_output)}\n"
        "  exit 0\n"
        "fi\n"
        "if [ \"${1:-} ${2:-} ${3:-}\" = '--pure debug config' ]; then\n"
        "  printf '%s\\n' \"$OPENCODE_CONFIG_CONTENT\"\n"
        "  exit 0\n"
        "fi\n"
        "exit 91\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _assert_scrubbed_environment(
    environment: Mapping[str, str], *, isolated_root: Path
) -> None:
    expected = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(isolated_root / "home"),
        "TMPDIR": str(isolated_root / "tmp"),
        "OPENCODE_DISABLE_PROJECT_CONFIG": "1",
        "OPENCODE_DISABLE_CLAUDE_CODE": "1",
        "OPENCODE_DISABLE_EXTERNAL_SKILLS": "1",
        "OPENCODE_DISABLE_DEFAULT_PLUGINS": "1",
        "OPENCODE_DISABLE_MODELS_FETCH": "1",
        "OPENCODE_DISABLE_AUTOUPDATE": "1",
        "OPENCODE_DISABLE_AUTOCOMPACT": "1",
    }
    forbidden = {
        "HTTPS_PROXY",
        "OPENCODE_ENABLE_EXA",
        "BASH_ENV",
        "NODE_OPTIONS",
        "NODE_EXTRA_CA_CERTS",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "UNRELATED_SECRET",
    }

    assert {key: environment.get(key) for key in expected} == expected
    assert forbidden.isdisjoint(environment)


def _assert_tool_free_config(config: dict[str, object], *, agent: str) -> None:
    expected = {
        "plugin": [],
        "mcp": {},
        "instructions": [],
        "snapshot": False,
        "share": "disabled",
        "lsp": False,
        "subagent_depth": 0,
    }
    permissions = config["permission"]
    tools = config["tools"]

    assert {key: config.get(key) for key in expected} == expected
    assert isinstance(permissions, dict)
    assert set(permissions) >= {
        "*",
        "bash",
        "edit",
        "task",
        "skill",
        "webfetch",
        "websearch",
        "external_directory",
        "read",
        "glob",
        "grep",
    }
    assert set(permissions.values()) == {"deny"}
    assert isinstance(tools, dict)
    assert set(tools) >= {"*", "read", "glob", "grep"}
    assert set(tools.values()) == {False}
    agents = config["agent"]
    assert isinstance(agents, dict)
    assert agents[agent]["steps"] == 1


def test_profile_scrubs_host_environment_and_builds_isolated_deny_first_config(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "isolated" / "snapshots" / "notes.md"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text("safe snapshot\n", encoding="utf-8")
    executable = _write_fake_opencode(tmp_path / "opencode")
    inherited = {
        "PATH": "/trusted/runtime",
        "LANG": "C.UTF-8",
        "HOME": "/hostile/home",
        "XDG_CONFIG_HOME": "/hostile/config",
        "OPENCODE_CONFIG": "/hostile/config.json",
        "OPENCODE_CONFIG_CONTENT": '{"plugin":["poison"]}',
        "HTTPS_PROXY": "http://poison.invalid",
        "OPENCODE_ENABLE_EXA": "1",
        "BASH_ENV": "/hostile/bashrc",
        "NODE_OPTIONS": "--require=/hostile/inject.js",
        "NODE_EXTRA_CA_CERTS": "/hostile/ca.pem",
        "SSL_CERT_DIR": "/hostile/certs",
        "SSL_CERT_FILE": "/hostile/ca-bundle.pem",
        "UNRELATED_SECRET": "must-not-pass",
    }

    profile = build_unattended_profile(
        mode="review",
        model="deepseek/deepseek-v4-pro",
        executable=executable,
        isolated_root=tmp_path / "isolated",
        snapshot_paths=(snapshot,),
        inherited_environment=inherited,
    )
    config = json.loads(profile.environment["OPENCODE_CONFIG_CONTENT"])

    _assert_scrubbed_environment(
        profile.environment, isolated_root=tmp_path / "isolated"
    )
    _assert_tool_free_config(config, agent=profile.agent)


def test_review_and_patch_profiles_have_distinct_ids_and_output_contracts(
    tmp_path: Path,
) -> None:
    executable = _write_fake_opencode(tmp_path / "opencode")
    snapshot = tmp_path / "isolated" / "snapshots" / "notes.md"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text("safe snapshot\n", encoding="utf-8")

    review = build_unattended_profile(
        mode="review",
        model="deepseek/deepseek-v4-pro",
        executable=executable,
        isolated_root=tmp_path / "review-root",
        snapshot_paths=(snapshot,),
        inherited_environment={"PATH": "/usr/bin"},
    )
    patch = build_unattended_profile(
        mode="patch",
        model="deepseek/deepseek-v4-pro",
        executable=executable,
        isolated_root=tmp_path / "patch-root",
        snapshot_paths=(snapshot,),
        inherited_environment={"PATH": "/usr/bin"},
    )

    assert review.profile_id == "entroping.opencode-unattended-review.v1"
    assert patch.profile_id == "entroping.opencode-unattended-patch-proposal.v1"
    assert review.output_contract == "structured-review-findings"
    assert patch.output_contract == "textual-unified-diff-proposal"
    assert review.profile_digest != patch.profile_digest
    assert json.loads(patch.environment["OPENCODE_CONFIG_CONTENT"])["tools"]["edit"] is False


def test_preflight_requires_exact_run_capabilities_before_dispatch(tmp_path: Path) -> None:
    executable = _write_fake_opencode(
        tmp_path / "opencode",
        help_text="--agent --dir --format json --model --file --auto",
    )
    profile = build_unattended_profile(
        mode="review",
        model="deepseek/deepseek-v4-pro",
        executable=executable,
        isolated_root=tmp_path / "isolated",
        snapshot_paths=(),
        inherited_environment={"PATH": "/usr/bin"},
    )

    with pytest.raises(UnattendedProfileError, match="--pure"):
        preflight_unattended_profile(profile)


def test_preflight_rejects_unsupported_opencode_version(tmp_path: Path) -> None:
    executable = _write_fake_opencode(
        tmp_path / "opencode",
        version="1.18.5",
    )
    profile = build_unattended_profile(
        mode="review",
        model="deepseek/deepseek-v4-pro",
        executable=executable,
        isolated_root=tmp_path / "isolated",
        snapshot_paths=(),
        inherited_environment={},
    )

    with pytest.raises(UnattendedProfileError, match="unsupported OpenCode version"):
        preflight_unattended_profile(profile)


def test_preflight_rejects_probe_output_flood(tmp_path: Path) -> None:
    executable = tmp_path / "opencode"
    executable.write_text(
        "#!/usr/bin/python3\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "if sys.argv[1:] == ['--version']:\n"
        "    print('x' * 40000)\n"
        "    raise SystemExit(0)\n"
        "if sys.argv[1:] == ['run', '--help']:\n"
        "    print('--pure --agent --dir --format json --model --file --auto dangerous')\n"
        "    raise SystemExit(0)\n"
        "if sys.argv[1:] == ['--pure', 'debug', 'config']:\n"
        "    print(os.environ['OPENCODE_CONFIG_CONTENT'])\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(91)\n",
        encoding="utf-8",
    )
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    profile = build_unattended_profile(
        mode="review",
        model="deepseek/deepseek-v4-pro",
        executable=executable,
        isolated_root=tmp_path / "isolated",
        snapshot_paths=(),
        inherited_environment={},
    )

    with pytest.raises(UnattendedProfileError, match="output limit"):
        preflight_unattended_profile(profile)


def test_preflight_timeout_kills_descendant_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = tmp_path / "descendant-survived"
    executable = tmp_path / "opencode"
    executable.write_text(
        "#!/bin/bash\n"
        "if [[ \"${1:-}\" == '--version' ]]; then\n"
        f"  (/bin/sleep 0.4; /usr/bin/touch {str(sentinel)!r}) &\n"
        "  /bin/sleep 5\n"
        "fi\n"
        "exit 91\n",
        encoding="utf-8",
    )
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    profile = build_unattended_profile(
        mode="review",
        model="deepseek/deepseek-v4-pro",
        executable=executable,
        isolated_root=tmp_path / "isolated",
        snapshot_paths=(),
        inherited_environment={},
    )
    monkeypatch.setattr(preflight_module, "PREFLIGHT_PROBE_TIMEOUT_SECONDS", 0.1)

    with pytest.raises(UnattendedProfileError, match="timed out"):
        preflight_unattended_profile(profile)
    time.sleep(0.5)
    assert not sentinel.exists()


def test_execution_binding_detects_executable_mutation(tmp_path: Path) -> None:
    executable = _write_fake_opencode(tmp_path / "opencode")
    profile = build_unattended_profile(
        mode="review",
        model="deepseek/deepseek-v4-pro",
        executable=executable,
        isolated_root=tmp_path / "isolated",
        snapshot_paths=(),
        inherited_environment={"PATH": "/usr/bin"},
    )
    attestation = preflight_unattended_profile(profile)
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)

    with pytest.raises(UnattendedProfileError, match="digest changed"):
        verify_execution_binding(attestation)


def test_preflight_rejects_unexpected_resolved_config_capability(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "opencode"
    executable.write_text(
        "#!/usr/bin/python3\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "if sys.argv[1:] == ['--version']:\n"
        "    print('1.18.4')\n"
        "    raise SystemExit(0)\n"
        "if sys.argv[1:] == ['run', '--help']:\n"
        "    print('--pure --agent --dir --format json --model --file --auto dangerous')\n"
        "    raise SystemExit(0)\n"
        "if sys.argv[1:] == ['--pure', 'debug', 'config']:\n"
        "    config = json.loads(os.environ['OPENCODE_CONFIG_CONTENT'])\n"
        "    config['future_capability'] = {'enabled': True}\n"
        "    print(json.dumps(config))\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(91)\n",
        encoding="utf-8",
    )
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    profile = build_unattended_profile(
        mode="review",
        model="deepseek/deepseek-v4-pro",
        executable=executable,
        isolated_root=tmp_path / "isolated",
        snapshot_paths=(),
        inherited_environment={},
    )

    with pytest.raises(UnattendedProfileError, match="invalid or unsupported"):
        preflight_unattended_profile(profile)


def test_preflight_never_forwards_provider_credentials_to_untrusted_probes(
    tmp_path: Path,
) -> None:
    credential_seen = tmp_path / "credential-seen"
    executable = tmp_path / "opencode"
    executable.write_text(
        "#!/bin/bash\n"
        f"if [[ -n \"${{DEEPSEEK_API_KEY:-}}\" ]]; then touch {str(credential_seen)!r}; fi\n"
        "if [[ \"${1:-}\" == '--version' ]]; then echo 1.18.4; exit 0; fi\n"
        "if [[ \"${1:-} ${2:-}\" == 'run --help' ]]; then\n"
        "  echo '--pure --agent --dir --format json --model --file --auto dangerous'\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"${1:-} ${2:-} ${3:-}\" == '--pure debug config' ]]; then\n"
        "  printf '%s\\n' \"$OPENCODE_CONFIG_CONTENT\"\n"
        "  exit 0\n"
        "fi\n"
        "exit 91\n",
        encoding="utf-8",
    )
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    profile = build_unattended_profile(
        mode="review",
        model="deepseek/deepseek-v4-pro",
        executable=executable,
        isolated_root=tmp_path / "isolated",
        snapshot_paths=(),
        inherited_environment={"DEEPSEEK_API_KEY": "must-not-reach-probes"},
    )

    preflight_unattended_profile(profile)

    assert "DEEPSEEK_API_KEY" in profile.environment
    assert not credential_seen.exists()
