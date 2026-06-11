"""Guardrails for alpha install-reference synchronization."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Protocol, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "install_reference_sync.py"


class InstallReferenceSyncModule(Protocol):
    INSTALL_REFERENCE_PATHS: tuple[Path, ...]


def load_sync_module() -> InstallReferenceSyncModule:
    spec = importlib.util.spec_from_file_location("install_reference_sync", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load install_reference_sync.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return cast(InstallReferenceSyncModule, module)


SYNC_MODULE = load_sync_module()
INSTALL_REFERENCE_FILES = list(SYNC_MODULE.INSTALL_REFERENCE_PATHS)


def run_sync(*args: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT), *args],
        check=False,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def write_release_evidence(root: Path, tag: str) -> None:
    evidence_path = root / "docs/meta/release-evidence.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        json.dumps(
            {
                "schema_version": "entroping.release-evidence.v1",
                "stable_core_ready": False,
                "stable_core_blockers": [],
                "releases": [
                    {
                        "tag": tag,
                        "kind": "github-prerelease",
                        "published_at": "2026-06-01T00:00:00Z",
                        "commit": "0" * 40,
                        "url": f"https://github.com/sakibshuvo/Entroping/releases/tag/{tag}",
                        "evidence": {},
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def write_install_reference_files(root: Path, tag: str) -> None:
    install_spec = f"git+https://github.com/sakibshuvo/Entroping.git@{tag}"
    for relative_path in INSTALL_REFERENCE_FILES:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"Install with `{install_spec}`.\n", encoding="utf-8")


def latest_release_tag(root: Path = REPO_ROOT) -> str:
    release_evidence = json.loads(
        (root / "docs" / "meta" / "release-evidence.json").read_text(
            encoding="utf-8"
        )
    )
    return str(release_evidence["releases"][0]["tag"])


def test_install_reference_check_passes_for_current_repo() -> None:
    result = run_sync("--check")

    assert result.returncode == 0, result.stderr
    assert "Install references OK" in result.stdout
    assert latest_release_tag() in result.stdout


def test_install_reference_check_detects_stale_pins(tmp_path: Path) -> None:
    write_release_evidence(tmp_path, "v9.9.9-alpha")
    write_install_reference_files(tmp_path, "v9.9.9-alpha")
    stale_path = tmp_path / "docs/user/USER_GUIDE.md"
    stale_tag = "v1.2.3-alpha"
    stale_path.write_text(
        f"Install with `git+https://github.com/sakibshuvo/Entroping.git@{stale_tag}`.\n",
        encoding="utf-8",
    )

    result = run_sync("--root", str(tmp_path), "--check")

    assert result.returncode == 1
    assert "Install reference check failed" in result.stderr
    assert "docs/user/USER_GUIDE.md" in result.stderr
    assert "v9.9.9-alpha" in result.stderr
    assert stale_tag in result.stderr


def test_install_reference_sync_updates_stale_pins(tmp_path: Path) -> None:
    write_release_evidence(tmp_path, "v9.9.9-alpha")
    write_install_reference_files(tmp_path, "v1.2.3-alpha")

    result = run_sync("--root", str(tmp_path), "--write")

    assert result.returncode == 0, result.stderr
    assert "Updated 6 file(s)" in result.stdout

    expected = "git+https://github.com/sakibshuvo/Entroping.git@v9.9.9-alpha"
    for relative_path in INSTALL_REFERENCE_FILES:
        assert expected in (tmp_path / relative_path).read_text(encoding="utf-8")
