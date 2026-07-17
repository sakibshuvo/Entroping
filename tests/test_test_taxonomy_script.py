"""Tests for deterministic test-suite taxonomy reporting."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "test_taxonomy.py"


def run_test_taxonomy(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_test_taxonomy_help_documents_strict_marker_evidence() -> None:
    result = run_test_taxonomy("--help")

    assert result.returncode == 0, result.stderr
    assert "explicit marker evidence" in result.stdout


def _write_taxonomy_repo(root: Path, files: dict[str, str]) -> None:
    (root / "tests").mkdir()
    (root / "pyproject.toml").write_text(
        """
[tool.pytest.ini_options]
markers = [
  "integration: integration evidence",
  "regression: regression evidence",
  "security: security evidence",
  "smoke: smoke evidence",
  "unit: unit evidence",
]
""".lstrip(),
        encoding="utf-8",
    )
    for name, source in files.items():
        (root / "tests" / name).write_text(source, encoding="utf-8")


def test_test_taxonomy_writes_reviewable_json_artifact(tmp_path: Path) -> None:
    output = tmp_path / "test-taxonomy.json"

    result = run_test_taxonomy("--output", str(output), "--strict")

    assert result.returncode == 0, result.stderr
    assert "Wrote test taxonomy: " in result.stdout
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.test-taxonomy.v1"
    assert payload["generated_by"] == "scripts/test_taxonomy.py"
    assert payload["test_file_count"] > 100
    assert payload["static_test_count"] > 1000
    assert set(payload["required_categories"]) == {
        "behavior",
        "docs-compliance",
        "script-integrity",
        "integration",
        "smoke",
        "regression",
        "security",
    }

    categories = payload["categories"]
    for category in payload["required_categories"]:
        assert categories[category]["file_count"] > 0
        assert categories[category]["static_test_count"] > 0

    assert any(
        entry["path"] == "tests/test_cli_real_hurl_e2e.py"
        for entry in categories["integration"]["files"]
    )
    assert any(
        entry["path"] == "tests/test_release_docs.py"
        for entry in categories["docs-compliance"]["files"]
    )
    assert any(
        entry["path"] == "tests/test_audit_quality_script.py"
        for entry in categories["script-integrity"]["files"]
    )


def test_test_taxonomy_dry_run_prints_summary_without_writing(tmp_path: Path) -> None:
    output = tmp_path / "test-taxonomy.json"

    result = run_test_taxonomy("--output", str(output), "--dry-run")

    assert result.returncode == 0, result.stderr
    assert "Would write test taxonomy: " in result.stdout
    assert "behavior:" in result.stdout
    assert not output.exists()


def test_test_taxonomy_records_explicit_inferred_and_mixed_provenance(
    tmp_path: Path,
) -> None:
    _write_taxonomy_repo(
        tmp_path,
        {
            "test_guard.py": (
                "import pytest\n\n@pytest.mark.security\ndef test_explicit() -> None:\n    pass\n"
            ),
            "test_security_path_safety.py": "def test_inferred() -> None:\n    pass\n",
            "test_security_mixed.py": (
                "import pytest\n\n@pytest.mark.security\ndef test_mixed() -> None:\n    pass\n"
            ),
        },
    )
    output = tmp_path / "taxonomy.json"

    result = run_test_taxonomy(
        "--repo-root",
        str(tmp_path),
        "--output",
        str(output),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.test-taxonomy.v1"
    assert payload["strict_explicit_categories"] == [
        "integration",
        "regression",
        "security",
    ]
    security = payload["categories"]["security"]
    assert security["provenance"] == {
        "explicit": {"file_count": 1, "static_test_count": 1},
        "inferred": {"file_count": 1, "static_test_count": 1},
        "mixed": {"file_count": 1, "static_test_count": 1},
    }
    files = {entry["path"]: entry for entry in security["files"]}
    assert files["tests/test_guard.py"] == {
        "path": "tests/test_guard.py",
        "static_test_count": 1,
        "markers": ["security"],
        "provenance": "explicit",
        "explicit_markers": ["security"],
        "inference_rules": [],
    }
    assert files["tests/test_security_path_safety.py"]["provenance"] == "inferred"
    assert files["tests/test_security_path_safety.py"]["inference_rules"] == [
        "filename:path_safety",
        "filename:security",
    ]
    assert files["tests/test_security_mixed.py"]["provenance"] == "mixed"


def test_test_taxonomy_uses_effective_module_and_class_markers(
    tmp_path: Path,
) -> None:
    _write_taxonomy_repo(
        tmp_path,
        {
            "test_module_guard.py": (
                "import pytest\n\n"
                "pytestmark = pytest.mark.regression\n"
                "pytestmark = pytest.mark.security\n\n"
                "def test_module_guard() -> None:\n"
                "    pass\n"
            ),
            "test_class_boundary.py": (
                "import pytest\n\n"
                "class TestBoundary:\n"
                "    pytestmark = pytest.mark.security\n"
                "    pytestmark = pytest.mark.regression\n\n"
                "    def test_boundary(self) -> None:\n"
                "        pass\n"
            ),
        },
    )
    output = tmp_path / "taxonomy.json"

    result = run_test_taxonomy(
        "--repo-root",
        str(tmp_path),
        "--output",
        str(output),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    security_file = payload["categories"]["security"]["files"][0]
    regression_file = payload["categories"]["regression"]["files"][0]
    assert security_file["markers"] == []
    assert security_file["explicit_markers"] == ["security"]
    assert security_file["provenance"] == "explicit"
    assert regression_file["markers"] == []
    assert regression_file["explicit_markers"] == ["regression"]
    assert regression_file["provenance"] == "explicit"
    assert all(
        file_entry["path"] != "tests/test_module_guard.py"
        for file_entry in payload["categories"]["regression"]["files"]
    )
    assert all(
        file_entry["path"] != "tests/test_class_boundary.py"
        for file_entry in payload["categories"]["security"]["files"]
    )


def test_test_taxonomy_uses_effective_parameter_row_markers(
    tmp_path: Path,
) -> None:
    _write_taxonomy_repo(
        tmp_path,
        {
            "test_case.py": (
                "import pytest\n\n"
                "@pytest.mark.parametrize(\n"
                "    'case',\n"
                "    [pytest.param(1, marks=pytest.mark.security)],\n"
                ")\n"
                "def test_case(case) -> None:\n"
                "    pass\n"
            )
        },
    )
    output = tmp_path / "taxonomy.json"

    result = run_test_taxonomy(
        "--repo-root",
        str(tmp_path),
        "--output",
        str(output),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    security_file = payload["categories"]["security"]["files"][0]
    assert security_file["markers"] == ["parametrize"]
    assert security_file["explicit_markers"] == ["security"]
    assert security_file["provenance"] == "explicit"


def test_test_taxonomy_excludes_markers_from_suppressed_test_classes(
    tmp_path: Path,
) -> None:
    _write_taxonomy_repo(
        tmp_path,
        {
            "test_suppressed.py": (
                "import pytest\n\n"
                "@pytest.mark.security\n"
                "class TestSuppressed:\n"
                "    __test__ = False\n\n"
                "    def test_case(self) -> None:\n"
                "        pass\n"
            )
        },
    )
    output = tmp_path / "taxonomy.json"
    live_result = subprocess.run(
        [
            "python",
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "--disable-warnings",
            "tests/test_suppressed.py",
        ],
        check=False,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    report_result = run_test_taxonomy(
        "--repo-root",
        str(tmp_path),
        "--output",
        str(output),
    )

    assert live_result.returncode == 5, live_result.stderr
    assert "::" not in live_result.stdout
    assert report_result.returncode == 0, report_result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert all(
        entry["path"] != "tests/test_suppressed.py"
        for entry in payload["categories"]["security"]["files"]
    )


def test_test_taxonomy_excludes_uncollected_marked_functions(
    tmp_path: Path,
) -> None:
    _write_taxonomy_repo(
        tmp_path,
        {
            "test_module_disabled.py": (
                "import pytest\n\n"
                "__test__ = False\n\n"
                "@pytest.mark.security\n"
                "def test_guard() -> None:\n"
                "    pass\n"
            ),
            "test_attribute_disabled.py": (
                "import pytest\n\n"
                "@pytest.mark.security\n"
                "def test_guard() -> None:\n"
                "    pass\n\n"
                "test_guard.__test__ = False\n"
            ),
            "test_overwritten.py": (
                "import pytest\n\n"
                "@pytest.mark.security\n"
                "def test_guard() -> None:\n"
                "    pass\n\n"
                "test_guard = object()\n"
            ),
            "test_decorator_disabled.py": (
                "import pytest\n\n"
                "def suppress(function):\n"
                "    function.__test__ = False\n"
                "    return function\n\n"
                "@pytest.mark.security\n"
                "@suppress\n"
                "def test_guard() -> None:\n"
                "    pass\n"
            ),
            "test_conditional_overwrite.py": (
                "import pytest\n\n"
                "@pytest.mark.security\n"
                "def test_guard() -> None:\n"
                "    pass\n\n"
                "if True:\n"
                "    test_guard = object()\n"
            ),
            "test_setattr_disabled.py": (
                "import pytest\n\n"
                "@pytest.mark.security\n"
                "def test_guard() -> None:\n"
                "    pass\n\n"
                "setattr(test_guard, '__test__', False)\n"
            ),
            "test_class_attribute_disabled.py": (
                "import pytest\n\n"
                "@pytest.mark.security\n"
                "class TestGuard:\n"
                "    def test_guard(self) -> None:\n"
                "        pass\n\n"
                "TestGuard.__test__ = False\n"
            ),
            "test_inherited_suppression.py": (
                "import pytest\n\n"
                "class SuppressedBase:\n"
                "    __test__ = False\n\n"
                "@pytest.mark.security\n"
                "class TestGuard(SuppressedBase):\n"
                "    def test_guard(self) -> None:\n"
                "        pass\n"
            ),
            "test_globals_overwrite.py": (
                "import pytest\n\n"
                "@pytest.mark.security\n"
                "def test_guard() -> None:\n"
                "    pass\n\n"
                "globals()['test_guard'] = object()\n"
            ),
            "test_dict_attribute_disabled.py": (
                "import pytest\n\n"
                "@pytest.mark.security\n"
                "def test_guard() -> None:\n"
                "    pass\n\n"
                "test_guard.__dict__['__test__'] = False\n"
            ),
            "test_globals_module_disabled.py": (
                "import pytest\n\n"
                "globals()['__test__'] = False\n\n"
                "@pytest.mark.security\n"
                "def test_guard() -> None:\n"
                "    pass\n"
            ),
            "test_exception_overwrite.py": (
                "import pytest\n\n"
                "@pytest.mark.security\n"
                "def test_guard() -> None:\n"
                "    pass\n\n"
                "try:\n"
                "    raise RuntimeError\n"
                "except RuntimeError as test_guard:\n"
                "    pass\n"
            ),
            "test_match_overwrite.py": (
                "import pytest\n\n"
                "@pytest.mark.security\n"
                "def test_guard() -> None:\n"
                "    pass\n\n"
                "match object():\n"
                "    case test_guard:\n"
                "        pass\n"
            ),
            "test_conditional_class_disabled.py": (
                "import pytest\n\n"
                "@pytest.mark.security\n"
                "class TestGuard:\n"
                "    if True:\n"
                "        __test__ = False\n"
                "    def test_guard(self) -> None:\n"
                "        pass\n"
            ),
        },
    )
    output = tmp_path / "taxonomy.json"
    live_result = subprocess.run(
        [
            "python",
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "--disable-warnings",
            *sorted(str(path.relative_to(tmp_path)) for path in (tmp_path / "tests").glob("*.py")),
        ],
        check=False,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    report_result = run_test_taxonomy(
        "--repo-root",
        str(tmp_path),
        "--output",
        str(output),
    )

    assert live_result.returncode == 5, live_result.stderr
    assert "::" not in live_result.stdout
    assert report_result.returncode == 0, report_result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["categories"]["security"]["files"] == []


def test_test_taxonomy_uses_final_reenabled_test_binding(
    tmp_path: Path,
) -> None:
    _write_taxonomy_repo(
        tmp_path,
        {
            "test_reenabled.py": (
                "import pytest\n\n"
                "@pytest.mark.security\n"
                "def test_guard() -> None:\n"
                "    pass\n\n"
                "test_guard.__test__ = False\n"
                "test_guard.__test__ = True\n"
            )
        },
    )
    output = tmp_path / "taxonomy.json"
    live_result = subprocess.run(
        [
            "python",
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "--disable-warnings",
            "tests/test_reenabled.py",
        ],
        check=False,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    report_result = run_test_taxonomy(
        "--repo-root",
        str(tmp_path),
        "--output",
        str(output),
    )

    assert live_result.returncode == 0, live_result.stderr
    assert "test_guard" in live_result.stdout
    assert report_result.returncode == 0, report_result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    security_files = payload["categories"]["security"]["files"]
    assert len(security_files) == 1
    assert security_files[0]["explicit_markers"] == ["security"]


def test_test_taxonomy_rejects_ambiguous_collection_namespace_mutations(
    tmp_path: Path,
) -> None:
    sources = {
        "test_globals_update.py": (
            "import pytest\n\n"
            "@pytest.mark.security\n"
            "def test_guard() -> None:\n"
            "    pass\n\n"
            "globals().update({'test_guard': object()})\n"
        ),
        "test_globals_pop.py": (
            "import pytest\n\n"
            "@pytest.mark.security\n"
            "def test_guard() -> None:\n"
            "    pass\n\n"
            "globals().pop('test_guard')\n"
        ),
        "test_globals_setitem.py": (
            "import pytest\n\n"
            "@pytest.mark.security\n"
            "def test_guard() -> None:\n"
            "    pass\n\n"
            "globals().__setitem__('test_guard', None)\n"
        ),
        "test_dict_update.py": (
            "import pytest\n\n"
            "@pytest.mark.security\n"
            "def test_guard() -> None:\n"
            "    pass\n\n"
            "test_guard.__dict__.update({'__test__': False})\n"
        ),
        "test_dict_keyword_update.py": (
            "import pytest\n\n"
            "@pytest.mark.security\n"
            "def test_guard() -> None:\n"
            "    pass\n\n"
            "test_guard.__dict__.update(__test__=False)\n"
        ),
        "test_dict_setitem.py": (
            "import pytest\n\n"
            "@pytest.mark.security\n"
            "def test_guard() -> None:\n"
            "    pass\n\n"
            "test_guard.__dict__.__setitem__('__test__', False)\n"
        ),
        "test_builtins_setattr.py": (
            "import builtins\n"
            "import pytest\n\n"
            "@pytest.mark.security\n"
            "def test_guard() -> None:\n"
            "    pass\n\n"
            "builtins.setattr(test_guard, '__test__', False)\n"
        ),
        "test_object_setattr.py": (
            "import pytest\n\n"
            "@pytest.mark.security\n"
            "def test_guard() -> None:\n"
            "    pass\n\n"
            "object.__setattr__(test_guard, '__test__', False)\n"
        ),
        "test_marker_mutation.py": (
            "import pytest\n\n"
            "def suppress(function):\n"
            "    function.__test__ = False\n"
            "    return function\n\n"
            "pytest.mark.security = suppress\n\n"
            "@pytest.mark.security\n"
            "def test_guard() -> None:\n"
            "    pass\n"
        ),
        "test_conditional_control.py": (
            "import pytest\n\n"
            "@pytest.mark.security\n"
            "def test_guard() -> None:\n"
            "    pass\n\n"
            "if True:\n"
            "    test_guard.__test__ = False\n"
            "else:\n"
            "    test_guard.__test__ = True\n"
        ),
        "test_unreachable_reenable.py": (
            "import pytest\n\n"
            "@pytest.mark.security\n"
            "def test_guard() -> None:\n"
            "    pass\n\n"
            "test_guard.__test__ = False\n"
            "if False:\n"
            "    setattr(test_guard, '__test__', True)\n"
        ),
        "test_conditional_pytestmark.py": (
            "import pytest\n\n"
            "pytestmark = pytest.mark.security\n"
            "if True:\n"
            "    pytestmark = pytest.mark.regression\n\n"
            "def test_guard() -> None:\n"
            "    pass\n"
        ),
    }
    _write_taxonomy_repo(tmp_path, sources)
    output = tmp_path / "taxonomy.json"

    report_result = run_test_taxonomy(
        "--repo-root",
        str(tmp_path),
        "--output",
        str(output),
    )

    assert report_result.returncode == 0, report_result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["categories"]["security"]["files"] == []


def test_test_taxonomy_rejects_invalid_parameter_row_marker_evidence(
    tmp_path: Path,
) -> None:
    _write_taxonomy_repo(
        tmp_path,
        {
            "test_invalid_row.py": (
                "import pytest\n\n"
                "@pytest.mark.parametrize(\n"
                "    'case',\n"
                "    [pytest.param(1, marks=[pytest.mark.security, 'invalid'])],\n"
                ")\n"
                "def test_case(case) -> None:\n"
                "    pass\n"
            )
        },
    )
    output = tmp_path / "taxonomy.json"
    live_result = subprocess.run(
        [
            "python",
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "--disable-warnings",
            "tests/test_invalid_row.py",
        ],
        check=False,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    report_result = run_test_taxonomy(
        "--repo-root",
        str(tmp_path),
        "--output",
        str(output),
    )

    assert live_result.returncode == 2, live_result.stderr
    assert report_result.returncode == 0, report_result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["categories"]["security"]["files"] == []


def test_test_taxonomy_rejects_malformed_canonical_marker_evidence(
    tmp_path: Path,
) -> None:
    _write_taxonomy_repo(
        tmp_path,
        {
            "test_dynamic_marker.py": (
                "import pytest\n\n"
                "@pytest.mark.security(missing())\n"
                "def test_case() -> None:\n"
                "    pass\n"
            ),
            "test_invalid_stacked_row.py": (
                "import pytest\n\n"
                "@pytest.mark.security\n"
                "@pytest.mark.parametrize(\n"
                "    'case',\n"
                "    [pytest.param(1, marks=[pytest.mark.regression, 'invalid'])],\n"
                ")\n"
                "def test_case(case) -> None:\n"
                "    pass\n"
            ),
            "test_mismatched_ids.py": (
                "import pytest\n\n"
                "@pytest.mark.security\n"
                "@pytest.mark.parametrize('case', [1, 2], ids=['only-one'])\n"
                "def test_case(case) -> None:\n"
                "    pass\n"
            ),
            "test_nested_marks.py": (
                "import pytest\n\n"
                "@pytest.mark.security\n"
                "@pytest.mark.parametrize(\n"
                "    'case',\n"
                "    [pytest.param(1, marks=[[pytest.mark.regression]])],\n"
                ")\n"
                "def test_case(case) -> None:\n"
                "    pass\n"
            ),
            "test_module_raise.py": (
                "import pytest\n\n"
                "@pytest.mark.security\n"
                "def test_case() -> None:\n"
                "    pass\n\n"
                "raise RuntimeError('collection stops')\n"
            ),
        },
    )
    output = tmp_path / "taxonomy.json"

    report_result = run_test_taxonomy(
        "--repo-root",
        str(tmp_path),
        "--output",
        str(output),
    )

    assert report_result.returncode == 0, report_result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["categories"]["security"]["files"] == []


def test_test_taxonomy_rejects_parametrize_contracts_pytest_cannot_collect(
    tmp_path: Path,
) -> None:
    sources = {
        "test_bad_arity.py": (
            "import pytest\n\n"
            "@pytest.mark.security\n"
            "@pytest.mark.parametrize('left,right', [(1,)])\n"
            "def test_case(left, right) -> None:\n"
            "    pass\n"
        ),
        "test_list_argname_scalar.py": (
            "import pytest\n\n"
            "@pytest.mark.security\n"
            "@pytest.mark.parametrize(['case'], [1])\n"
            "def test_case(case) -> None:\n"
            "    pass\n"
        ),
        "test_tuple_argname_scalar.py": (
            "import pytest\n\n"
            "@pytest.mark.security\n"
            "@pytest.mark.parametrize(('case',), [1])\n"
            "def test_case(case) -> None:\n"
            "    pass\n"
        ),
        "test_missing_argument.py": (
            "import pytest\n\n"
            "@pytest.mark.security\n"
            "@pytest.mark.parametrize('case', [1])\n"
            "def test_case() -> None:\n"
            "    pass\n"
        ),
        "test_duplicate_argument.py": (
            "import pytest\n\n"
            "@pytest.mark.security\n"
            "@pytest.mark.parametrize('case', [1])\n"
            "@pytest.mark.parametrize('case', [2])\n"
            "def test_case(case) -> None:\n"
            "    pass\n"
        ),
        "test_reserved_argument.py": (
            "import pytest\n\n"
            "@pytest.mark.security\n"
            "@pytest.mark.parametrize('request', [1])\n"
            "def test_case(request) -> None:\n"
            "    pass\n"
        ),
        "test_default_argument.py": (
            "import pytest\n\n"
            "@pytest.mark.security\n"
            "@pytest.mark.parametrize('case', [1])\n"
            "def test_case(case=0) -> None:\n"
            "    pass\n"
        ),
        "test_keyword_default_argument.py": (
            "import pytest\n\n"
            "@pytest.mark.security\n"
            "@pytest.mark.parametrize('case', [1])\n"
            "def test_case(*, case=0) -> None:\n"
            "    pass\n"
        ),
        "test_method_receiver.py": (
            "import pytest\n\n"
            "class TestCase:\n"
            "    @pytest.mark.security\n"
            "    @pytest.mark.parametrize('self', [1])\n"
            "    def test_case(self) -> None:\n"
            "        pass\n"
        ),
        "test_module_parametrize.py": (
            "import pytest\n\n"
            "pytestmark = pytest.mark.parametrize('case', [1])\n\n"
            "@pytest.mark.security\n"
            "def test_case() -> None:\n"
            "    pass\n"
        ),
    }
    _write_taxonomy_repo(tmp_path, sources)
    output = tmp_path / "taxonomy.json"

    for source_name in sources:
        live_result = subprocess.run(
            [
                "python",
                "-m",
                "pytest",
                "--collect-only",
                "-q",
                "--disable-warnings",
                f"tests/{source_name}",
            ],
            check=False,
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert live_result.returncode == 2, live_result.stderr

    report_result = run_test_taxonomy(
        "--repo-root",
        str(tmp_path),
        "--output",
        str(output),
    )

    assert report_result.returncode == 0, report_result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["categories"]["security"]["files"] == []


def test_test_taxonomy_fails_closed_for_compiler_invalid_modules(
    tmp_path: Path,
) -> None:
    _write_taxonomy_repo(
        tmp_path,
        {
            "test_invalid_future.py": (
                "from __future__ import made_up\n"
                "import pytest\n\n"
                "@pytest.mark.security\n"
                "def test_case() -> None:\n"
                "    pass\n"
            )
        },
    )
    output = tmp_path / "taxonomy.json"

    result = run_test_taxonomy(
        "--repo-root",
        str(tmp_path),
        "--output",
        str(output),
    )

    assert result.returncode == 2
    assert "source syntax error" in result.stderr.lower()
    assert not output.exists()


def test_test_taxonomy_excludes_noncanonical_pytest_marker_namespaces(
    tmp_path: Path,
) -> None:
    _write_taxonomy_repo(
        tmp_path,
        {
            "test_guard.py": (
                "import helper as pytest\n\n"
                "@pytest.mark.security\n"
                "def test_guard() -> None:\n"
                "    pass\n"
            ),
            "test_guard_compound.py": (
                "import pytest\n"
                "import helper\n"
                "if True:\n"
                "    pytest = helper\n\n"
                "@pytest.mark.security\n"
                "def test_guard_compound() -> None:\n"
                "    pass\n"
            ),
        },
    )
    (tmp_path / "helper.py").write_text(
        "class Mark:\n"
        "    def __getattr__(self, name):\n"
        "        def suppress(function):\n"
        "            function.__test__ = False\n"
        "            return function\n"
        "        return suppress\n"
        "mark = Mark()\n",
        encoding="utf-8",
    )
    output = tmp_path / "taxonomy.json"
    live_result = subprocess.run(
        [
            "python",
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "--disable-warnings",
            "tests/test_guard.py",
            "tests/test_guard_compound.py",
        ],
        check=False,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    report_result = run_test_taxonomy(
        "--repo-root",
        str(tmp_path),
        "--output",
        str(output),
    )

    assert live_result.returncode == 5, live_result.stderr
    assert "::" not in live_result.stdout
    assert report_result.returncode == 0, report_result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    security_paths = {
        entry["path"] for entry in payload["categories"]["security"]["files"]
    }
    assert "tests/test_guard.py" not in security_paths
    assert "tests/test_guard_compound.py" not in security_paths


def test_test_taxonomy_helper_markers_do_not_satisfy_strict_evidence(
    tmp_path: Path,
) -> None:
    _write_taxonomy_repo(
        tmp_path,
        {
            "test_docs.py": "def test_docs() -> None:\n    pass\n",
            "test_script.py": "def test_script() -> None:\n    pass\n",
            "test_smoke.py": "def test_smoke() -> None:\n    pass\n",
            "test_integration.py": (
                "import pytest\n\n"
                "@pytest.mark.integration\n"
                "def test_integration() -> None:\n"
                "    pass\n"
            ),
            "test_regression.py": (
                "import pytest\n\n"
                "@pytest.mark.regression\n"
                "def test_regression() -> None:\n"
                "    pass\n"
            ),
            "test_security.py": (
                "import pytest\n\n"
                "@pytest.mark.security\n"
                "def helper() -> None:\n"
                "    pass\n\n"
                "def test_security() -> None:\n"
                "    pass\n"
            ),
        },
    )
    output = tmp_path / "taxonomy.json"

    report_result = run_test_taxonomy(
        "--repo-root",
        str(tmp_path),
        "--output",
        str(output),
    )
    strict_result = run_test_taxonomy(
        "--repo-root",
        str(tmp_path),
        "--dry-run",
        "--strict",
    )

    assert report_result.returncode == 0, report_result.stderr
    security_file = json.loads(output.read_text(encoding="utf-8"))["categories"]["security"][
        "files"
    ][0]
    assert security_file["markers"] == ["security"]
    assert security_file["explicit_markers"] == []
    assert security_file["provenance"] == "inferred"
    assert strict_result.returncode == 1
    assert "security has no explicit marker evidence" in strict_result.stderr


def test_test_taxonomy_strict_requires_aggregate_explicit_protected_evidence(
    tmp_path: Path,
) -> None:
    files = {
        "test_docs.py": "def test_docs() -> None:\n    pass\n",
        "test_script.py": "def test_script() -> None:\n    pass\n",
        "test_integration.py": "def test_integration() -> None:\n    pass\n",
        "test_regression.py": "def test_regression() -> None:\n    pass\n",
        "test_security.py": "def test_security() -> None:\n    pass\n",
        "test_smoke.py": "def test_smoke() -> None:\n    pass\n",
    }
    _write_taxonomy_repo(tmp_path, files)

    inferred_only = run_test_taxonomy(
        "--repo-root",
        str(tmp_path),
        "--dry-run",
        "--strict",
    )

    assert inferred_only.returncode == 1
    assert "integration has no explicit marker evidence" in inferred_only.stderr
    assert "regression has no explicit marker evidence" in inferred_only.stderr
    assert "security has no explicit marker evidence" in inferred_only.stderr

    for category in ("integration", "regression", "security"):
        (tmp_path / "tests" / f"test_{category}.py").write_text(
            f"import pytest\n\n@pytest.mark.{category}\ndef test_{category}() -> None:\n    pass\n",
            encoding="utf-8",
        )

    explicit_evidence = run_test_taxonomy(
        "--repo-root",
        str(tmp_path),
        "--dry-run",
        "--strict",
    )

    assert explicit_evidence.returncode == 0, explicit_evidence.stderr
