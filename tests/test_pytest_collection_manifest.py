from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "pytest_collection_manifest.py"


def _run_manifest(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT), *args],
        check=False,
        cwd=cwd,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": str(cwd)},
        text=True,
    )


def _run_pytest_collect(
    cwd: Path,
    source: Path,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "--disable-warnings",
            source.name,
        ],
        check=False,
        cwd=cwd,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": str(cwd)},
        text=True,
    )
    node_ids = sorted(
        line.split("::", maxsplit=1)[1]
        for line in result.stdout.splitlines()
        if line.startswith(f"{source.name}::")
    )
    return result, node_ids


def _load_manifest_module() -> ModuleType:
    module_name = "pytest_collection_manifest_test"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _manifest(nodes: list[tuple[str, list[str]]]) -> dict[str, object]:
    return {
        "schema_version": "entroping.pytest-collection-manifest.v1",
        "generated_by": "scripts/pytest_collection_manifest.py",
        "parameter_id_projection": "normalized-away",
        "source_files": ["tests/test_example.py"],
        "test_definition_count": len({node_id for node_id, _markers in nodes}),
        "collected_case_count": len(nodes),
        "nodes": [
            {"normalized_node_id": node_id, "effective_markers": markers}
            for node_id, markers in nodes
        ],
    }


def test_manifest_is_deterministic_static_and_preserves_source(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    sentinel = tmp_path / "imported"
    (root / "sentinel_module.py").write_text(
        f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('executed')\n",
        encoding="utf-8",
    )
    source = root / "test_example.py"
    source.write_text(
        "import sentinel_module\n"
        "import pytest\n"
        "pytestmark = pytest.mark.regression\n\n"
        "@pytest.mark.unit\n"
        "def test_top() -> None:\n"
        "    pass\n\n"
        "@pytest.mark.integration\n"
        "class TestGroup:\n"
        "    @pytest.mark.smoke\n"
        "    @pytest.mark.parametrize('left', [\n"
        "        pytest.param(1, marks=pytest.mark.security),\n"
        "        2,\n"
        "    ])\n"
        "    @pytest.mark.parametrize('right', ('a', 'b'))\n"
        "    def test_case(self, left, right) -> None:\n"
        "        pass\n",
        encoding="utf-8",
    )
    (root / "conftest.py").write_text(
        f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('conftest')\n",
        encoding="utf-8",
    )
    before_bytes = source.read_bytes()
    before_mode = source.stat().st_mode
    before_hash = hashlib.sha256(before_bytes).hexdigest()
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    first_result = _run_manifest(root, "--output", str(first), str(source))
    second_result = _run_manifest(root, "--output", str(second), str(source))

    assert first_result.returncode == 0, first_result.stderr
    assert second_result.returncode == 0, second_result.stderr
    assert first.read_bytes() == second.read_bytes()
    assert not sentinel.exists()
    assert source.read_bytes() == before_bytes
    assert source.stat().st_mode == before_mode
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before_hash
    payload = json.loads(first.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.pytest-collection-manifest.v1"
    assert payload["parameter_id_projection"] == "normalized-away"
    assert payload["source_files"] == ["test_example.py"]
    assert payload["test_definition_count"] == 2
    assert payload["collected_case_count"] == 5
    group_nodes = [
        node for node in payload["nodes"] if node["normalized_node_id"].startswith("TestGroup")
    ]
    assert len(group_nodes) == 4
    assert sum("security" in node["effective_markers"] for node in group_nodes) == 2
    assert all(
        node["effective_markers"]
        == sorted(
            {
                "integration",
                "parametrize",
                "regression",
                "smoke",
                *(["security"] if "security" in node["effective_markers"] else []),
            }
        )
        for node in group_nodes
    )


def test_compare_accepts_canonicalized_parent_alias_but_rejects_final_symlink(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    source = root / "test_case.py"
    source.write_text("def test_case() -> None:\n    pass\n", encoding="utf-8")
    real_output_parent = tmp_path / "host-output"
    real_output_parent.mkdir()
    aliased_output_parent = tmp_path / "host-output-alias"
    aliased_output_parent.symlink_to(real_output_parent, target_is_directory=True)
    first = aliased_output_parent / "first.json"
    second = aliased_output_parent / "second.json"

    first_result = _run_manifest(root, "--output", str(first), str(source))
    second_result = _run_manifest(root, "--output", str(second), str(source))
    compare_result = _run_manifest(root, "--compare", str(first), str(second))

    assert first_result.returncode == 0, first_result.stderr
    assert second_result.returncode == 0, second_result.stderr
    assert compare_result.returncode == 0, compare_result.stderr
    final_link = real_output_parent / "final-link.json"
    final_link.symlink_to(real_output_parent / "first.json")

    symlink_result = _run_manifest(
        root,
        "--compare",
        str(final_link),
        str(second),
    )

    assert symlink_result.returncode == 2
    assert "symlink" in symlink_result.stderr.lower()


def test_compare_ignores_module_moves_and_classifies_semantic_drift(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    (root / "before").mkdir(parents=True)
    (root / "after").mkdir()
    source = "@pytest.mark.security\ndef test_same() -> None:\n    pass\n"
    for relative in ("before/test_old.py", "after/test_new.py"):
        (root / relative).write_text("import pytest\n" + source, encoding="utf-8")
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    assert _run_manifest(root, "--output", str(before), "before/test_old.py").returncode == 0
    assert _run_manifest(root, "--output", str(after), "after/test_new.py").returncode == 0

    equal = _run_manifest(root, "--compare", str(before), str(after))

    assert equal.returncode == 0, equal.stderr
    drift_cases: dict[
        str,
        tuple[list[tuple[str, list[str]]], list[tuple[str, list[str]]]],
    ] = {
        "count drift": (
            [("test_a", [])],
            [("test_a", []), ("test_b", [])],
        ),
        "ID drift": (
            [("test_a", []), ("test_b", [])],
            [("test_a", []), ("test_c", [])],
        ),
        "duplicate drift": (
            [("test_a", []), ("test_a", []), ("test_b", [])],
            [("test_a", []), ("test_b", []), ("test_b", [])],
        ),
        "marker drift": (
            [("test_a", ["security"])],
            [("test_a", ["regression"])],
        ),
    }
    for index, (message, (left_nodes, right_nodes)) in enumerate(drift_cases.items()):
        left = tmp_path / f"left-{index}.json"
        right = tmp_path / f"right-{index}.json"
        left.write_text(json.dumps(_manifest(left_nodes)), encoding="utf-8")
        right.write_text(json.dumps(_manifest(right_nodes)), encoding="utf-8")

        result = _run_manifest(root, "--compare", str(left), str(right))

        assert result.returncode == 1
        assert message in result.stderr

    left_definition_count = tmp_path / "left-definition-count.json"
    right_definition_count = tmp_path / "right-definition-count.json"
    repeated_nodes: list[tuple[str, list[str]]] = [
        ("test_same", []),
        ("test_same", []),
    ]
    left_payload = _manifest(repeated_nodes)
    right_payload = {
        **_manifest(repeated_nodes),
        "test_definition_count": 2,
    }
    left_definition_count.write_text(json.dumps(left_payload), encoding="utf-8")
    right_definition_count.write_text(json.dumps(right_payload), encoding="utf-8")

    definition_count_drift = _run_manifest(
        root,
        "--compare",
        str(left_definition_count),
        str(right_definition_count),
    )

    assert definition_count_drift.returncode == 2
    assert "invalid manifest definition count" in definition_count_drift.stderr


def test_compare_accepts_cross_file_duplicate_normalized_ids(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    for name in ("test_first.py", "test_second.py"):
        (root / name).write_text(
            "def test_same() -> None:\n"
            "    pass\n",
            encoding="utf-8",
        )
    manifest = tmp_path / "duplicates.json"

    generated = _run_manifest(
        root,
        "--output",
        str(manifest),
        "test_first.py",
        "test_second.py",
    )
    compared = _run_manifest(
        root,
        "--compare",
        str(manifest),
        str(manifest),
    )

    assert generated.returncode == 0, generated.stderr
    assert compared.returncode == 0, compared.stderr


def test_manifest_fails_closed_for_dynamic_collection_and_unsafe_inputs(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    dynamic = root / "test_dynamic.py"
    dynamic.write_text(
        "import pytest\n"
        "@pytest.mark.parametrize('case', build_cases())\n"
        "def test_dynamic(case) -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )
    hook = root / "test_hook.py"
    hook.write_text("def pytest_generate_tests(metafunc) -> None:\n    pass\n", encoding="utf-8")
    plugin = root / "test_plugin.py"
    plugin.write_text(
        "pytest_plugins = ['unsafe_plugin']\ndef test_plugin() -> None:\n    pass\n",
        encoding="utf-8",
    )
    syntax = root / "test_syntax.py"
    syntax.write_text("def test_broken(\n", encoding="utf-8")
    outside = tmp_path / "test_outside.py"
    outside.write_text("def test_outside() -> None:\n    pass\n", encoding="utf-8")
    link = root / "test_link.py"
    link.symlink_to(outside)

    cases = (
        ("dynamic parametrization", ("--output", str(tmp_path / "dynamic.json"), str(dynamic))),
        ("collection hook", ("--output", str(tmp_path / "hook.json"), str(hook))),
        ("plugin declaration", ("--output", str(tmp_path / "plugin.json"), str(plugin))),
        ("syntax", ("--output", str(tmp_path / "syntax.json"), str(syntax))),
        (
            "duplicate source",
            (
                "--output",
                str(tmp_path / "duplicate.json"),
                str(dynamic),
                str(dynamic),
            ),
        ),
        ("outside repository", ("--output", str(tmp_path / "outside.json"), str(outside))),
        ("symlink", ("--output", str(tmp_path / "link.json"), str(link))),
    )
    for message, args in cases:
        result = _run_manifest(root, *args)
        assert result.returncode == 2
        assert message in result.stderr.lower()

    existing = tmp_path / "existing.json"
    existing.write_text("keep", encoding="utf-8")
    result = _run_manifest(root, "--output", str(existing), str(dynamic))
    assert result.returncode == 2
    assert existing.read_text(encoding="utf-8") == "keep"
    assert "already exists" in result.stderr


def test_manifest_rejects_dynamic_call_rows_and_empty_parameter_sets(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    sources = {
        "dynamic row": (
            "import pytest\n"
            "@pytest.mark.parametrize('case', [marker_returning_call()])\n"
            "def test_dynamic(case) -> None:\n"
            "    pass\n"
        ),
        "empty parameter set": (
            "import pytest\n"
            "@pytest.mark.parametrize('case', [])\n"
            "def test_empty(case) -> None:\n"
            "    pass\n"
        ),
    }
    for index, (message, source_text) in enumerate(sources.items()):
        source = root / f"test_case_{index}.py"
        source.write_text(source_text, encoding="utf-8")

        result = _run_manifest(
            root,
            "--output",
            str(tmp_path / f"case-{index}.json"),
            str(source),
        )

        assert result.returncode == 2
        assert message in result.stderr.lower()


def test_manifest_matches_pytest_test_function_prefix(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    source = root / "test_prefix.py"
    source.write_text("def testlegacy() -> None:\n    pass\n", encoding="utf-8")
    output = tmp_path / "prefix.json"

    live_result, live_nodes = _run_pytest_collect(root, source)
    result = _run_manifest(root, "--output", str(output), str(source))

    assert live_result.returncode == 0, live_result.stderr
    assert live_nodes == ["testlegacy"]
    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["test_definition_count"] == 1
    assert payload["collected_case_count"] == 1
    assert payload["nodes"] == [
        {"normalized_node_id": "testlegacy", "effective_markers": []}
    ]


def test_manifest_rejects_duplicate_parametrize_keywords(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    sources = {
        "argnames": (
            "import pytest\n"
            "@pytest.mark.parametrize(argnames='case', argnames='case', argvalues=[1])\n"
            "def test_case(case) -> None:\n"
            "    pass\n"
        ),
        "marks": (
            "import pytest\n"
            "@pytest.mark.parametrize(\n"
            "    'case',\n"
            "    [pytest.param(1, marks=pytest.mark.security, marks=pytest.mark.regression)],\n"
            ")\n"
            "def test_case(case) -> None:\n"
            "    pass\n"
        ),
    }
    for index, (message, source_text) in enumerate(sources.items()):
        source = root / f"test_duplicate_keyword_{index}.py"
        source.write_text(source_text, encoding="utf-8")

        result = _run_manifest(
            root,
            "--output",
            str(tmp_path / f"duplicate-keyword-{index}.json"),
            str(source),
        )

        assert result.returncode == 2
        assert message in result.stderr.lower()


def test_manifest_rejects_invalid_parametrize_semantics_and_marker_keywords(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    sources = {
        "dynamic parametrize argnames": (
            "import pytest\n"
            "@pytest.mark.parametrize('case,case', [(1, 2)])\n"
            "def test_case(case) -> None:\n"
            "    pass\n"
        ),
        "dynamic parametrize indirect": (
            "import pytest\n"
            "@pytest.mark.parametrize('case', [1], indirect=['missing'])\n"
            "def test_case(case) -> None:\n"
            "    pass\n"
        ),
        "dynamic parametrize scope": (
            "import pytest\n"
            "@pytest.mark.parametrize('case', [1], scope='evil')\n"
            "def test_case(case) -> None:\n"
            "    pass\n"
        ),
        "keyword argument repeated": (
            "import pytest\n"
            "@pytest.mark.security(reason=1, reason=2)\n"
            "def test_case() -> None:\n"
            "    pass\n"
        ),
        "nested marker collection": (
            "import pytest\n"
            "@pytest.mark.parametrize(\n"
            "    'case',\n"
            "    [pytest.param(1, marks=[[pytest.mark.security]])],\n"
            ")\n"
            "def test_case(case) -> None:\n"
            "    pass\n"
        ),
    }
    for index, (message, source_text) in enumerate(sources.items()):
        source = root / f"test_invalid_semantics_{index}.py"
        source.write_text(source_text, encoding="utf-8")

        result = _run_manifest(
            root,
            "--output",
            str(tmp_path / f"invalid-semantics-{index}.json"),
            str(source),
        )

        assert result.returncode == 2
        assert message in result.stderr.lower()


def test_manifest_rejects_parametrize_contracts_pytest_cannot_collect(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    sources = {
        "parameter row arity": (
            "import pytest\n"
            "@pytest.mark.parametrize('left,right', [(1,)])\n"
            "def test_case(left, right) -> None:\n"
            "    pass\n"
        ),
        "row arity is unsupported": (
            "import pytest\n"
            "@pytest.mark.parametrize(['case'], [1])\n"
            "def test_case(case) -> None:\n"
            "    pass\n"
        ),
        "arity is unsupported": (
            "import pytest\n"
            "@pytest.mark.parametrize(('case',), [1])\n"
            "def test_case(case) -> None:\n"
            "    pass\n"
        ),
        "parametrize function signature": (
            "import pytest\n"
            "@pytest.mark.parametrize('case', [1])\n"
            "def test_case() -> None:\n"
            "    pass\n"
        ),
        "duplicate parametrization": (
            "import pytest\n"
            "@pytest.mark.parametrize('case', [1])\n"
            "@pytest.mark.parametrize('case', [2])\n"
            "def test_case(case) -> None:\n"
            "    pass\n"
        ),
        "dynamic parametrize argnames": (
            "import pytest\n"
            "@pytest.mark.parametrize('request', [1])\n"
            "def test_case(request) -> None:\n"
            "    pass\n"
        ),
        "signature is unsupported": (
            "import pytest\n"
            "@pytest.mark.parametrize('case', [1])\n"
            "def test_case(case=0) -> None:\n"
            "    pass\n"
        ),
        "function signature is unsupported": (
            "import pytest\n"
            "@pytest.mark.parametrize('case', [1])\n"
            "def test_case(*, case=0) -> None:\n"
            "    pass\n"
        ),
        "argnames are unsupported": (
            "import pytest\n"
            "class TestCase:\n"
            "    @pytest.mark.parametrize('self', [1])\n"
            "    def test_case(self) -> None:\n"
            "        pass\n"
        ),
        "starred pytest.param argument": (
            "import pytest\n"
            "@pytest.mark.parametrize('case', [pytest.param(*[])])\n"
            "def test_case(case) -> None:\n"
            "    pass\n"
        ),
    }
    for index, (message, source_text) in enumerate(sources.items()):
        source = root / f"test_uncollectable_parametrize_{index}.py"
        source.write_text(source_text, encoding="utf-8")
        live_result, live_nodes = _run_pytest_collect(root, source)

        result = _run_manifest(
            root,
            "--output",
            str(tmp_path / f"uncollectable-parametrize-{index}.json"),
            str(source),
        )

        assert live_result.returncode == 2, live_result.stderr
        assert not any(node.startswith("test_case[") for node in live_nodes)
        assert result.returncode == 2
        assert message in result.stderr.lower()


def test_manifest_rejects_even_single_row_class_parametrization(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    source = root / "test_parametrized_class.py"
    source.write_text(
        "import pytest\n"
        "@pytest.mark.parametrize('case', [1])\n"
        "class TestCase:\n"
        "    def test_case(self, case) -> None:\n"
        "        pass\n",
        encoding="utf-8",
    )

    result = _run_manifest(
        root,
        "--output",
        str(tmp_path / "parametrized-class.json"),
        str(source),
    )

    assert result.returncode == 2
    assert "parametrized test classes" in result.stderr.lower()


def test_manifest_rejects_unbound_definition_names_and_compiler_invalid_modules(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    sources = (
        ("definition-time expression", (
            "def test_case(value=MISSING) -> None:\n"
            "    pass\n"
        )),
        ("annotation", (
            "def test_case(value: MISSING) -> None:\n"
            "    pass\n"
        )),
        ("source syntax", (
            "from __future__ import made_up\n"
            "def test_case() -> None:\n"
            "    pass\n"
        )),
        ("source syntax", (
            "def test_case() -> None:\n"
            "    break\n"
        )),
    )
    for index, (message, source_text) in enumerate(sources):
        source = root / f"test_invalid_definition_{index}.py"
        source.write_text(source_text, encoding="utf-8")

        result = _run_manifest(
            root,
            "--output",
            str(tmp_path / f"invalid-definition-{index}.json"),
            str(source),
        )

        assert result.returncode == 2
        assert message in result.stderr.lower()


def test_generated_large_manifest_can_compare_to_itself(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    source = root / "test_large.py"
    rows = ", ".join(str(index) for index in range(20_000))
    source.write_text(
        "import pytest\n"
        f"@pytest.mark.parametrize('case', [{rows}])\n"
        "def test_case(case) -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )
    output = tmp_path / "large.json"

    generate_result = _run_manifest(root, "--output", str(output), str(source))
    compare_result = _run_manifest(root, "--compare", str(output), str(output))

    assert generate_result.returncode == 0, generate_result.stderr
    assert output.stat().st_size > 2 * 1024 * 1024
    assert compare_result.returncode == 0, compare_result.stderr


def test_manifest_rejects_dynamic_name_and_starred_parameter_rows(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    sources = {
        "dynamic row": (
            "import pytest\n"
            "from package import case\n"
            "@pytest.mark.parametrize('case', [case])\n"
            "def test_dynamic(case) -> None:\n"
            "    pass\n"
        ),
        "starred row": (
            "import pytest\n"
            "cases = [1, 2]\n"
            "@pytest.mark.parametrize('case', [*cases])\n"
            "def test_starred(case) -> None:\n"
            "    pass\n"
        ),
    }
    for index, (message, source_text) in enumerate(sources.items()):
        source = root / f"test_dynamic_row_{index}.py"
        source.write_text(source_text, encoding="utf-8")

        result = _run_manifest(
            root,
            "--output",
            str(tmp_path / f"dynamic-row-{index}.json"),
            str(source),
        )

        assert result.returncode == 2
        assert message in result.stderr.lower()


def test_manifest_keeps_child_expressions_opaque_in_literal_container_rows(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    source = root / "test_container_rows.py"
    source.write_text(
        "import pytest\n"
        "@pytest.mark.parametrize('case', [\n"
        "    (build_case(),),\n"
        "    [build_case()],\n"
        "    {'case': build_case()},\n"
        "    {build_case()},\n"
        "])\n"
        "def test_container(case) -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )
    output = tmp_path / "container-rows.json"

    result = _run_manifest(root, "--output", str(output), str(source))

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["test_definition_count"] == 1
    assert payload["collected_case_count"] == 4


def test_manifest_uses_last_module_and_class_pytestmark_assignments(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    source = root / "test_overridden_marks.py"
    source.write_text(
        "import pytest\n"
        "pytestmark = pytest.mark.security\n"
        "pytestmark = pytest.mark.regression\n\n"
        "class TestGroup:\n"
        "    pytestmark = pytest.mark.smoke\n"
        "    pytestmark = pytest.mark.adapter\n\n"
        "    def test_case(self) -> None:\n"
        "        pass\n",
        encoding="utf-8",
    )
    output = tmp_path / "overridden-marks.json"

    result = _run_manifest(root, "--output", str(output), str(source))

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["nodes"] == [
        {
            "normalized_node_id": "TestGroup::test_case",
            "effective_markers": ["adapter", "regression"],
        }
    ]


def test_manifest_rejects_unprovable_module_collection_bindings(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    sources = (
        ("test binding", "test_alias = None\n"),
        (
            "__test__ assignment",
            "def test_hidden() -> None:\n    pass\ntest_hidden.__test__ = False\n",
        ),
        ("test import alias", "from package import case as test_alias\n"),
        ("pytestmark import", "from pytest import mark as pytestmark\n"),
        ("annotated test binding", "test_alias: object = object()\n"),
        ("augmented test binding", "test_alias += 1\n"),
        ("augmented pytestmark", "pytestmark += ()\n"),
        ("collect ignore", "collect_ignore = ['test_hidden.py']\n"),
        (
            "__test__ assignment",
            "class Helper:\n"
            "    __test__ = True\n"
            "    def test_promoted(self) -> None:\n"
            "        pass\n",
        ),
        (
            "test class binding",
            "class Helper:\n    def test_case(self) -> None:\n        pass\nTestAlias = Helper\n",
        ),
    )
    for index, (message, source_text) in enumerate(sources):
        source = root / f"test_binding_{index}.py"
        source.write_text(source_text, encoding="utf-8")

        result = _run_manifest(
            root,
            "--output",
            str(tmp_path / f"binding-{index}.json"),
            str(source),
        )

        assert result.returncode == 2
        assert message in result.stderr.lower()


def test_manifest_rejects_collection_bindings_hidden_in_compound_statements(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    sources = (
        ("if condition:\n    test_alias = None\n"),
        ("if condition:\n    def test_conditional() -> None:\n        pass\n"),
        (
            "def test_hidden() -> None:\n"
            "    pass\n"
            "try:\n"
            "    test_hidden.__test__ = False\n"
            "except Exception:\n"
            "    pass\n"
        ),
        (
            "import pytest\n"
            "if condition:\n"
            "    pytestmark = pytest.mark.security\n"
            "def test_case() -> None:\n"
            "    pass\n"
        ),
        (
            "class Helper:\n"
            "    def test_case(self) -> None:\n"
            "        pass\n"
            "if condition:\n"
            "    TestAlias = Helper\n"
        ),
    )
    for index, source_text in enumerate(sources):
        source = root / f"test_compound_{index}.py"
        source.write_text(source_text, encoding="utf-8")

        result = _run_manifest(
            root,
            "--output",
            str(tmp_path / f"compound-{index}.json"),
            str(source),
        )

        assert result.returncode == 2
        assert "unsupported" in result.stderr.lower()


def test_manifest_rejects_definition_time_collection_bindings(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    sources = (
        ("def helper(value=(test_alias := lambda: None)) -> None:\n    pass\n"),
        (
            "import pytest\n"
            "def helper(value=(pytestmark := pytest.mark.security)) -> None:\n"
            "    pass\n"
            "def test_case() -> None:\n"
            "    pass\n"
        ),
        (
            "class TestHidden:\n"
            "    def test_case(self, value=(__test__ := False)) -> None:\n"
            "        pass\n"
        ),
    )
    for index, source_text in enumerate(sources):
        source = root / f"test_definition_time_{index}.py"
        source.write_text(source_text, encoding="utf-8")

        result = _run_manifest(
            root,
            "--output",
            str(tmp_path / f"definition-time-{index}.json"),
            str(source),
        )

        assert result.returncode == 2
        assert "unsupported" in result.stderr.lower()


def test_manifest_rejects_executable_marker_and_annotation_expressions(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    sources = (
        (
            "import pytest\n"
            "pytestmark = pytest.mark.security(build_mark())\n"
            "def test_case() -> None:\n"
            "    pass\n"
        ),
        (
            "import pytest\n"
            "@pytest.mark.security(build_mark())\n"
            "def test_case() -> None:\n"
            "    pass\n"
        ),
        (
            "import pytest\n"
            "@pytest.mark.parametrize(build_names(), [1])\n"
            "def test_case(value) -> None:\n"
            "    pass\n"
        ),
        (
            "import pytest\n"
            "@pytest.mark.parametrize('case', [1], indirect=inject())\n"
            "def test_case(case) -> None:\n"
            "    pass\n"
        ),
        (
            "import pytest\n"
            "@pytest.mark.parametrize('case', [1], scope=inject())\n"
            "def test_case(case) -> None:\n"
            "    pass\n"
        ),
        (
            "import pytest\n"
            "@pytest.mark.parametrize(\n"
            "    'case',\n"
            "    [pytest.param(1, marks=pytest.mark.security(build_mark()))],\n"
            ")\n"
            "def test_case(case) -> None:\n"
            "    pass\n"
        ),
        (
            "def helper() -> None:\n"
            "    pass\n"
            "probe: globals().__setitem__('test_injected', helper)\n"
            "def test_declared() -> None:\n"
            "    pass\n"
        ),
    )
    for index, source_text in enumerate(sources):
        source = root / f"test_executable_expression_{index}.py"
        source.write_text(source_text, encoding="utf-8")

        result = _run_manifest(
            root,
            "--output",
            str(tmp_path / f"executable-expression-{index}.json"),
            str(source),
        )

        assert result.returncode == 2
        assert "unsupported" in result.stderr.lower()


def test_manifest_rejects_noncanonical_or_shadowed_pytest_bindings(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "helper.py").write_text(
        "class Mark:\n"
        "    def __getattr__(self, name):\n"
        "        def suppress(function):\n"
        "            function.__test__ = False\n"
        "            return function\n"
        "        return suppress\n"
        "mark = Mark()\n",
        encoding="utf-8",
    )
    sources = (
        "import helper as pytest\n"
        "@pytest.mark.security\n"
        "def test_declared() -> None:\n"
        "    pass\n",
        "import pytest\n"
        "import helper\n"
        "pytest = helper\n"
        "@pytest.mark.security\n"
        "def test_declared() -> None:\n"
        "    pass\n",
    )
    for index, source_text in enumerate(sources):
        source = root / f"test_shadowed_pytest_{index}.py"
        source.write_text(source_text, encoding="utf-8")

        live_result, live_nodes = _run_pytest_collect(root, source)
        manifest_result = _run_manifest(
            root,
            "--output",
            str(tmp_path / f"shadowed-pytest-{index}.json"),
            str(source),
        )

        assert live_result.returncode == 5, live_result.stderr
        assert live_nodes == []
        assert manifest_result.returncode == 2
        assert "pytest" in manifest_result.stderr.lower()


def test_manifest_rejects_multi_target_pytestmark_assignment(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    source = root / "test_multi_target_mark.py"
    source.write_text(
        "from pathlib import Path\n"
        "import pytest\n"
        "ROOT = Path(__file__).resolve()\n"
        "pytestmark = ROOT = pytest.mark.security\n"
        "ROOT2 = ROOT.parents[0]\n"
        "def test_declared() -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )

    live_result, live_nodes = _run_pytest_collect(root, source)
    manifest_result = _run_manifest(
        root,
        "--output",
        str(tmp_path / "multi-target-mark.json"),
        str(source),
    )

    assert live_result.returncode == 2, live_result.stderr
    assert live_nodes == []
    assert manifest_result.returncode == 2
    assert "multi-target pytestmark" in manifest_result.stderr.lower()


def test_manifest_matches_annotation_evaluation_semantics(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "helper.py").write_text(
        "import inspect\n"
        "def __getattr__(name):\n"
        "    caller = inspect.currentframe().f_back\n"
        "    caller.f_globals['test_injected'] = lambda: None\n"
        "    return object\n",
        encoding="utf-8",
    )
    executable_sources = (
        "import helper\n"
        "def test_declared(value: helper.trigger) -> None:\n"
        "    pass\n",
        "class Marker:\n"
        "    def __class_getitem__(cls, item):\n"
        "        globals()['test_injected'] = lambda: None\n"
        "        return object\n"
        "probe: Marker[0]\n"
        "def test_declared() -> None:\n"
        "    pass\n",
    )
    for index, source_text in enumerate(executable_sources):
        source = root / f"test_executable_annotation_{index}.py"
        source.write_text(source_text, encoding="utf-8")

        live_result, live_nodes = _run_pytest_collect(root, source)
        manifest_result = _run_manifest(
            root,
            "--output",
            str(tmp_path / f"executable-annotation-{index}.json"),
            str(source),
        )

        assert live_result.returncode == 0, live_result.stderr
        assert live_nodes == ["test_declared", "test_injected"]
        assert manifest_result.returncode == 2
        assert "annotation" in manifest_result.stderr.lower()

    deferred = root / "test_deferred_annotation.py"
    deferred.write_text(
        "from __future__ import annotations\n"
        "import helper\n"
        "def test_declared(value: helper.trigger) -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )
    deferred_output = tmp_path / "deferred-annotation.json"

    live_result, live_nodes = _run_pytest_collect(root, deferred)
    manifest_result = _run_manifest(
        root,
        "--output",
        str(deferred_output),
        str(deferred),
    )

    assert live_result.returncode == 0, live_result.stderr
    assert live_nodes == ["test_declared"]
    assert manifest_result.returncode == 0, manifest_result.stderr
    assert json.loads(deferred_output.read_text(encoding="utf-8"))["collected_case_count"] == 1


def test_manifest_rejects_shadowed_set_literal_call(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    source = root / "test_shadowed_set.py"
    source.write_text(
        "import pytest\n"
        "def helper() -> None:\n"
        "    pass\n"
        "def set():\n"
        "    globals()['test_injected'] = helper\n"
        "    return ()\n"
        "@pytest.mark.security(set())\n"
        "def test_declared() -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )

    live_result, live_nodes = _run_pytest_collect(root, source)
    manifest_result = _run_manifest(
        root,
        "--output",
        str(tmp_path / "shadowed-set.json"),
        str(source),
    )

    assert live_result.returncode == 0, live_result.stderr
    assert live_nodes == ["test_declared", "test_injected"]
    assert manifest_result.returncode == 2
    assert "unsupported" in manifest_result.stderr.lower()


def test_manifest_rejects_collection_hook_and_constructor_aliases(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    sources: tuple[tuple[str, str, list[str]], ...] = (
        (
            "collection hook",
            "def helper(metafunc) -> None:\n"
            "    if 'case' in metafunc.fixturenames:\n"
            "        metafunc.parametrize('case', [1, 2])\n"
            "pytest_generate_tests = helper\n"
            "def test_declared(case) -> None:\n"
            "    pass\n",
            ["test_declared[1]", "test_declared[2]"],
        ),
        (
            "module __getattr__",
            "def generated(metafunc) -> None:\n"
            "    if 'case' in metafunc.fixturenames:\n"
            "        metafunc.parametrize('case', [1, 2])\n"
            "def __getattr__(name):\n"
            "    if name == 'pytest_generate_tests':\n"
            "        return generated\n"
            "    raise AttributeError(name)\n"
            "def test_declared(case) -> None:\n"
            "    pass\n",
            ["test_declared[1]", "test_declared[2]"],
        ),
        (
            "module __getattr__",
            "def generated(metafunc) -> None:\n"
            "    if 'case' in metafunc.fixturenames:\n"
            "        metafunc.parametrize('case', [1, 2])\n"
            "def helper(name):\n"
            "    if name == 'pytest_generate_tests':\n"
            "        return generated\n"
            "    raise AttributeError(name)\n"
            "__getattr__ = helper\n"
            "def test_declared(case) -> None:\n"
            "    pass\n",
            ["test_declared[1]", "test_declared[2]"],
        ),
        (
            "test class constructor",
            "def helper(self) -> None:\n"
            "    pass\n"
            "class TestHidden:\n"
            "    __init__ = helper\n"
            "    def test_case(self) -> None:\n"
            "        pass\n",
            [],
        ),
    )
    for index, (message, source_text, expected_live_nodes) in enumerate(sources):
        source = root / f"test_alias_{index}.py"
        source.write_text(source_text, encoding="utf-8")

        live_result, live_nodes = _run_pytest_collect(root, source)
        manifest_result = _run_manifest(
            root,
            "--output",
            str(tmp_path / f"alias-{index}.json"),
            str(source),
        )

        assert live_result.returncode == (0 if expected_live_nodes else 5), live_result.stderr
        assert live_nodes == expected_live_nodes
        assert manifest_result.returncode == 2
        assert message in manifest_result.stderr.lower()


def test_manifest_fails_closed_for_excessive_expression_depth(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    source = root / "test_deep_expression.py"
    expression = "Path(__file__)" + " / 'segment'" * 1_000
    source.write_text(
        "from pathlib import Path\n"
        f"ROOT = {expression}\n"
        "def test_declared() -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )

    result = _run_manifest(
        root,
        "--output",
        str(tmp_path / "deep-expression.json"),
        str(source),
    )

    assert result.returncode == 2
    assert "traceback" not in result.stderr.lower()
    assert "depth" in result.stderr.lower() or "unsupported" in result.stderr.lower()


def test_manifest_fails_closed_for_excessive_case_expansion(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    source = root / "test_case_expansion.py"
    decorators = "".join(
        f"@pytest.mark.parametrize('case_{index}', [0, 1])\n"
        for index in range(17)
    )
    arguments = ", ".join(f"case_{index}" for index in range(17))
    source.write_text(
        "import pytest\n"
        f"{decorators}"
        f"def test_declared({arguments}) -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )

    result = _run_manifest(
        root,
        "--output",
        str(tmp_path / "case-expansion.json"),
        str(source),
    )

    assert result.returncode == 2
    assert "case expansion" in result.stderr.lower()


def test_manifest_fails_closed_for_marker_amplification(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    source = root / "test_marker_amplification.py"
    markers = "".join(f"@pytest.mark.marker_{index}\n" for index in range(200))
    parameters = "".join(
        f"@pytest.mark.parametrize('case_{index}', [0, 1])\n"
        for index in range(13)
    )
    arguments = ", ".join(f"case_{index}" for index in range(13))
    source.write_text(
        "import pytest\n"
        f"{markers}"
        f"{parameters}"
        f"def test_declared({arguments}) -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )

    result = _run_manifest(
        root,
        "--output",
        str(tmp_path / "marker-amplification.json"),
        str(source),
    )

    assert result.returncode == 2
    assert "output work" in result.stderr.lower()


def test_manifest_statement_grammar_classifies_every_ast_field() -> None:
    module = _load_manifest_module()
    source = (
        '"""module"""\n'
        "import pytest\n"
        "from pathlib import Path\n"
        "VALUE = 1\n"
        "ANNOTATED: object = None\n"
        "def helper() -> None:\n"
        "    pass\n"
        "async def async_helper() -> None:\n"
        "    pass\n"
        "class Helper:\n"
        "    pass\n"
        "pass\n"
    )
    statements = ast.parse(source).body

    for statement in statements:
        expected = module.STATEMENT_FIELD_CLASSIFICATION[type(statement)]
        actual = frozenset(name for name, _value in ast.iter_fields(statement))
        assert expected == actual
        module._require_classified_statement_fields(statement)

    assignment = next(statement for statement in statements if isinstance(statement, ast.Assign))
    with pytest.raises(module.ManifestError, match="unclassified AST field"):
        module._require_classified_fields(
            assignment,
            module.STATEMENT_FIELD_CLASSIFICATION[ast.Assign] - {"value"},
        )


def test_manifest_rejects_shadowed_static_helper_calls(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    sources = (
        (
            "from helper import mutate as frozenset\n"
            "evidence = frozenset()\n"
            "def test_declared() -> None:\n"
            "    pass\n"
        ),
        (
            "class Resolver:\n"
            "    def resolve(self):\n"
            "        globals()['test_injected'] = helper\n"
            "        return self\n"
            "ROOT = Resolver.resolve()\n"
            "def test_declared() -> None:\n"
            "    pass\n"
        ),
        (
            "from helper import mutate as Path\n"
            "ROOT = Path(__file__).resolve().parents[1]\n"
            "def test_declared() -> None:\n"
            "    pass\n"
        ),
    )
    for index, source_text in enumerate(sources):
        source = root / f"test_shadowed_helper_{index}.py"
        source.write_text(source_text, encoding="utf-8")

        result = _run_manifest(
            root,
            "--output",
            str(tmp_path / f"shadowed-helper-{index}.json"),
            str(source),
        )

        assert result.returncode == 2
        assert "unsupported" in result.stderr.lower()


def test_manifest_rejects_indirect_collection_mutation_and_suppression(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    sources = (
        ("def test_hidden() -> None:\n    pass\ntest_hidden.__dict__['__test__'] = False\n"),
        (
            "def test_hidden() -> None:\n"
            "    pass\n"
            "(lambda: setattr(test_hidden, '__test__', False))()\n"
        ),
        ("def helper() -> None:\n    pass\nglobals()['test_injected'] = helper\n"),
        ("def helper() -> None:\n    pass\nglobals()[dynamic_name] = helper\n"),
        ("def helper() -> None:\n    pass\nglobals().update({'test_injected': helper})\n"),
        (
            "def test_hidden() -> None:\n"
            "    pass\n"
            "test_hidden.__dict__.update({'__test__': False})\n"
        ),
        (
            "def test_hidden() -> None:\n"
            "    pass\n"
            "setter = lambda: setattr(test_hidden, dynamic_name, False)\n"
        ),
        (
            "class TestHidden:\n"
            "    def __init__(self) -> None:\n"
            "        pass\n"
            "    def test_case(self) -> None:\n"
            "        pass\n"
        ),
        (
            "class TestHidden:\n"
            "    def __new__(cls):\n"
            "        return super().__new__(cls)\n"
            "    def test_case(self) -> None:\n"
            "        pass\n"
        ),
        ("def test_duplicate() -> None:\n    pass\ndef test_duplicate() -> None:\n    pass\n"),
        (
            "class TestDuplicate:\n"
            "    def test_case(self) -> None:\n"
            "        pass\n"
            "    def test_case(self) -> None:\n"
            "        pass\n"
        ),
    )
    for index, source_text in enumerate(sources):
        source = root / f"test_indirect_{index}.py"
        source.write_text(source_text, encoding="utf-8")

        result = _run_manifest(
            root,
            "--output",
            str(tmp_path / f"indirect-{index}.json"),
            str(source),
        )

        assert result.returncode == 2
        assert "unsupported" in result.stderr.lower()


def test_manifest_rejects_explicit_parameter_id_contracts(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    sources = {
        "parametrize ids": (
            "import pytest\n"
            "@pytest.mark.parametrize('case', [1], ids=['named'])\n"
            "def test_named(case) -> None:\n"
            "    pass\n"
        ),
        "pytest.param id": (
            "import pytest\n"
            "@pytest.mark.parametrize('case', [pytest.param(1, id='named')])\n"
            "def test_named(case) -> None:\n"
            "    pass\n"
        ),
        "dynamic parametrize keyword": (
            "import pytest\n"
            "@pytest.mark.parametrize('case', [1], **options)\n"
            "def test_named(case) -> None:\n"
            "    pass\n"
        ),
        "positional parametrize ids": (
            "import pytest\n"
            "@pytest.mark.parametrize('case', [1], False, ['named'])\n"
            "def test_named(case) -> None:\n"
            "    pass\n"
        ),
    }
    for index, (message, source_text) in enumerate(sources.items()):
        source = root / f"test_id_{index}.py"
        source.write_text(source_text, encoding="utf-8")

        result = _run_manifest(
            root,
            "--output",
            str(tmp_path / f"id-{index}.json"),
            str(source),
        )

        assert result.returncode == 2
        assert message in result.stderr.lower()


def test_source_read_rejects_parent_replaced_by_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_manifest_module()
    root = tmp_path / "repo"
    source_parent = root / "inside"
    source_parent.mkdir(parents=True)
    (source_parent / "test_case.py").write_text(
        "def test_case() -> None:\n    pass\n",
        encoding="utf-8",
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "test_case.py").write_text("host secret", encoding="utf-8")
    moved_parent = root / "inside-original"
    real_open = os.open
    swapped = False

    def swapping_open(
        path: os.PathLike[str] | str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if os.fspath(path) == "inside" and dir_fd is not None and not swapped:
            source_parent.rename(moved_parent)
            source_parent.symlink_to(outside, target_is_directory=True)
            swapped = True
        if dir_fd is None:
            return real_open(path, flags, mode)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", swapping_open)

    with pytest.raises(module.ManifestError, match="symlink"):
        module._read_source(root, Path("inside/test_case.py"))


def test_source_read_closes_parent_descriptors_when_descendant_open_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_manifest_module()
    root = tmp_path / "repo"
    (root / "inside").mkdir(parents=True)
    opened_descriptors: list[int] = []
    closed_descriptors: list[int] = []
    real_open = os.open
    real_close = os.close

    def tracking_open(
        path: os.PathLike[str] | str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if os.fspath(path) == "blocked":
            raise PermissionError("blocked")
        if dir_fd is None:
            descriptor = real_open(path, flags, mode)
        else:
            descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        opened_descriptors.append(descriptor)
        return descriptor

    def tracking_close(descriptor: int) -> None:
        closed_descriptors.append(descriptor)
        real_close(descriptor)

    monkeypatch.setattr(os, "open", tracking_open)
    monkeypatch.setattr(os, "close", tracking_close)

    with pytest.raises(module.ManifestError, match="source is not readable"):
        module._read_source(root, Path("inside/blocked/test_case.py"))

    assert closed_descriptors == list(reversed(opened_descriptors))


def test_compare_rejects_unrepresentable_manifest_labels(tmp_path: Path) -> None:
    invalid_payloads = {
        "traversal source": {
            **_manifest([("test_a", [])]),
            "source_files": ["../test_a.py"],
        },
        "absolute source": {
            **_manifest([("test_a", [])]),
            "source_files": ["/tests/test_a.py"],
        },
        "parameterized node suffix": _manifest([("test_a[named]", [])]),
        "invalid marker": _manifest([("test_a", ["bad marker"])]),
        "definition count": {
            **_manifest([("test_a", [])]),
            "test_definition_count": 0,
        },
        "manifest definition count": {
            **_manifest([("test_a", []), ("test_a", ["security"])]),
            "test_definition_count": 2,
        },
    }
    for index, (message, payload) in enumerate(invalid_payloads.items()):
        manifest = tmp_path / f"invalid-{index}.json"
        manifest.write_text(json.dumps(payload), encoding="utf-8")

        result = _run_manifest(
            tmp_path,
            "--compare",
            str(manifest),
            str(manifest),
        )

        assert result.returncode == 2
        assert message in result.stderr.lower()


def test_compare_rejects_malformed_or_unsupported_manifests(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    deeply_nested = tmp_path / "deeply-nested.json"
    deeply_nested.write_text("[" * 10_000 + "0" + "]" * 10_000, encoding="utf-8")
    duplicate = tmp_path / "duplicate.json"
    valid_json = json.dumps(_manifest([("test_a", [])]))
    duplicate.write_text(
        valid_json.replace(
            '"schema_version": "entroping.pytest-collection-manifest.v1"',
            (
                '"schema_version": "entroping.pytest-collection-manifest.v1", '
                '"schema_version": "entroping.pytest-collection-manifest.v1"'
            ),
            1,
        ),
        encoding="utf-8",
    )
    unsupported = tmp_path / "unsupported.json"
    unsupported.write_text(
        json.dumps(
            {
                **_manifest([("test_a", [])]),
                "schema_version": "entroping.pytest-collection-manifest.v2",
            }
        ),
        encoding="utf-8",
    )

    malformed_result = _run_manifest(tmp_path, "--compare", str(malformed), str(unsupported))
    unsupported_result = _run_manifest(tmp_path, "--compare", str(unsupported), str(unsupported))
    duplicate_result = _run_manifest(
        tmp_path,
        "--compare",
        str(duplicate),
        str(duplicate),
    )
    deeply_nested_result = _run_manifest(
        tmp_path,
        "--compare",
        str(deeply_nested),
        str(deeply_nested),
    )

    assert malformed_result.returncode == 2
    assert "malformed json" in malformed_result.stderr.lower()
    assert deeply_nested_result.returncode == 2
    assert "malformed json" in deeply_nested_result.stderr.lower()
    assert unsupported_result.returncode == 2
    assert "unsupported schema" in unsupported_result.stderr.lower()
    assert duplicate_result.returncode == 2
    assert "duplicate json key" in duplicate_result.stderr.lower()
