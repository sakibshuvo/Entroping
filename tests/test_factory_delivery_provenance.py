from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest
from factory_orchestration_test_support import admission_repository, git

from entroping import models as entroping_models
from scripts import bounded_process, factory_issue_selector_evidence
from scripts import factory_delivery_admission as admission
from scripts.factory_delivery_admission import DeliveryAdmissionError
from scripts.factory_policy_import_closure import (
    PolicyImportError,
    committed_policy_sources,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("module", "relative"),
    (
        (bounded_process, "scripts/bounded_process.py"),
        (factory_issue_selector_evidence, "scripts/factory_issue_selector_evidence.py"),
    ),
)
def test_transitive_loaded_module_drift_rejects_policy_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    relative: str,
) -> None:
    root = admission_repository(tmp_path)
    sibling = tmp_path / "Entroping-issue-transitive-drift"
    git(root, "worktree", "add", "-b", "feat/transitive-drift", str(sibling), "main")
    drifted = sibling / relative
    drifted.parent.mkdir(parents=True, exist_ok=True)
    assert module.__file__ is not None
    source = Path(module.__file__)
    drifted.write_bytes(source.read_bytes() + b"\n# transitive drift\n")
    monkeypatch.setattr(module, "__file__", str(drifted))

    with pytest.raises(DeliveryAdmissionError):
        admission.selector_policy_digest(root)


def test_policy_import_closure_follows_new_internal_import_without_mirror() -> None:
    assert hasattr(admission, "_policy_import_closure")
    closure = admission._policy_import_closure(
        roots=("scripts/root.py",),
        sources={
            "scripts/root.py": b"from scripts.mid import value\n",
            "scripts/mid.py": b"from scripts.leaf import value\n",
            "scripts/leaf.py": b"value = 1\n",
        },
    )

    assert closure == (
        "scripts/leaf.py",
        "scripts/mid.py",
        "scripts/root.py",
    )


def test_policy_import_closure_rejects_missing_internal_import() -> None:
    with pytest.raises(PolicyImportError, match="policy-import-missing"):
        admission._policy_import_closure(
            roots=("scripts/root.py",),
            sources={"scripts/root.py": b"import scripts.missing\n"},
        )


def test_policy_import_closure_rejects_ambiguous_internal_module() -> None:
    with pytest.raises(PolicyImportError, match="policy-import-ambiguous"):
        admission._policy_import_closure(
            roots=("scripts/root.py",),
            sources={
                "scripts/root.py": b"import scripts.ambiguous\n",
                "scripts/ambiguous.py": b"value = 1\n",
                "scripts/ambiguous/__init__.py": b"value = 2\n",
            },
        )


def test_policy_import_closure_handles_cycles_once() -> None:
    closure = admission._policy_import_closure(
        roots=("scripts/a.py",),
        sources={
            "scripts/a.py": b"import scripts.b\n",
            "scripts/b.py": b"import scripts.a\n",
        },
    )

    assert closure == ("scripts/a.py", "scripts/b.py")


def test_real_policy_closure_includes_executed_package_initializers() -> None:
    sources = {
        path.relative_to(REPO_ROOT).as_posix(): path.read_bytes()
        for source_root in (REPO_ROOT / "scripts", REPO_ROOT / "src/entroping")
        for path in source_root.rglob("*.py")
    }

    closure = admission._policy_import_closure(
        roots=("scripts/factory_scheduler_delivery.py",),
        sources=sources,
    )

    assert "scripts/__init__.py" in closure
    assert "src/entroping/__init__.py" in closure
    assert "src/entroping/models/__init__.py" in closure
    assert "src/entroping/models/architect.py" in closure
    assert closure.index("src/entroping/__init__.py") < closure.index(
        "src/entroping/models/__init__.py"
    )


def test_committed_policy_closure_includes_package_initializers(tmp_path: Path) -> None:
    root = admission_repository(tmp_path)

    sources = committed_policy_sources(
        root,
        commit="main",
        roots=("scripts/factory_scheduler_delivery.py",),
    )

    paths = tuple(source.path for source in sources)
    assert "scripts/__init__.py" in paths
    assert "src/entroping/__init__.py" in paths
    assert "src/entroping/models/__init__.py" in paths
    assert "src/entroping/models/architect.py" in paths


def test_loaded_package_initializer_drift_rejects_policy_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = admission_repository(tmp_path)
    sibling = tmp_path / "Entroping-issue-package-drift"
    git(root, "worktree", "add", "-b", "feat/package-drift", str(sibling), "main")
    relative = "src/entroping/models/__init__.py"
    drifted = sibling / relative
    drifted.parent.mkdir(parents=True, exist_ok=True)
    source = Path(entroping_models.__file__)
    drifted.write_bytes(source.read_bytes() + b"\n# package drift\n")
    monkeypatch.setattr(entroping_models, "__file__", str(drifted))

    with pytest.raises(DeliveryAdmissionError):
        admission.selector_policy_digest(root)
