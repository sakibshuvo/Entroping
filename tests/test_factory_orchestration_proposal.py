from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

factory_patch_inspection = importlib.import_module("scripts.factory_patch_inspection")


def _patch(path: str = "src/example.py") -> bytes:
    return (
        f"diff --git a/{path} b/{path}\n"
        "new file mode 100644\n"
        "index 0000000..ce01362\n"
        "--- /dev/null\n"
        f"+++ b/{path}\n"
        "@@ -0,0 +1 @@\n"
        "+safe = True\n"
    ).encode()


def test_proposal_bytes_are_inspected_without_reopening_a_path() -> None:
    # Given: one bounded UTF-8 unified diff already read from its trusted descriptor.
    proposal = _patch()

    # When: the exact bytes cross the patch-inspection boundary.
    inspected = factory_patch_inspection.inspect_proposal_bytes(proposal)

    # Then: inspection reports only Git-derived metadata, never the patch body.
    assert inspected == {
        "changed_files": ["src/example.py"],
        "files_changed": 1,
        "additions": 1,
        "deletions": 0,
        "new_files": ["src/example.py"],
    }


@pytest.mark.parametrize(
    "proposal",
    [
        b"\xff",
        _patch() + b"\x00",
        b"diff --git a/link b/link\nnew file mode 120000\n",
        b"diff --git a/mod b/mod\nnew file mode 160000\n",
        b"diff --git a/a b/b\nsimilarity index 100%\nrename from a\nrename to b\n",
        b"diff --git a/a b/b\nsimilarity index 100%\ncopy from a\ncopy to b\n",
        b"diff --git a/a b/a\nold mode 100644\nnew mode 100755\n",
    ],
)
def test_proposal_bytes_reject_unsafe_encodings_and_git_shapes(proposal: bytes) -> None:
    # Given: a proposal using a forbidden encoding or Git object transition.
    # When/Then: the boundary rejects it before any worktree mutation.
    with pytest.raises(factory_patch_inspection.PatchInspectionError):
        factory_patch_inspection.inspect_proposal_bytes(proposal)


@pytest.mark.parametrize(
    "path",
    [
        "../escape.py",
        "/absolute.py",
        "src/../../escape.py",
        "src/\u202ealias.py",
        ".git/config",
        "scripts/factoryctl.py",
    ],
)
def test_proposal_policy_rejects_path_aliases_and_protected_surfaces(
    tmp_path: Path,
    path: str,
) -> None:
    # Given: a syntactically valid patch naming an unsafe path.
    inspected = factory_patch_inspection.inspect_proposal_bytes(_patch(path))

    # When: the existing control-plane policy checks the parsed Git paths.
    violations = factory_patch_inspection.proposal_control_plane_violations(
        inspected,
        repo_root=tmp_path,
    )

    # Then: the unsafe path is denied.
    assert violations
