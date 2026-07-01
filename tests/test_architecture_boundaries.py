"""Executable architecture and provider boundary tests."""

import ast
from collections.abc import Iterable
from importlib import import_module
from pathlib import Path

from support.architecture_guard import (
    ImportBoundaryRule,
    collect_python_modules,
    find_forbidden_imports,
    find_provider_imports,
    format_violations,
)

SOURCE_ROOT = Path("src/entroping")
SCRIPTS_ROOT = Path("scripts")
READ_TEXT_SCAN_EXCLUDED_PARTS = frozenset(
    {
        ".entroping",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "htmlcov",
        "reports",
        "site",
    }
)
APPROVED_READ_TEXT_FUNCTIONS_BY_FILE = {
    Path("scripts/ai_jobs.py"): frozenset({"_read_job"}),
    Path("scripts/deepseek_worker.py"): frozenset({"_build_prompt"}),
    Path("scripts/dependency_license_check.py"): frozenset(
        {"_declared_dependencies", "_load_policy"}
    ),
    Path("scripts/docs_inventory.py"): frozenset({"_entry_for_path"}),
    Path("scripts/factory_inbox_io.py"): frozenset({"read_json_object"}),
    Path("scripts/factory_metrics_modules/context_scorecard_validation.py"): frozenset(
        {"_load_context_scorecard"}
    ),
    Path("scripts/install_reference_sync.py"): frozenset(
        {"latest_release_tag", "find_references", "sync_references"}
    ),
    Path("scripts/local_wheel_install_smoke.py"): frozenset({"_expected_wheel"}),
    Path("scripts/monkeypatch_hotspots.py"): frozenset({"_build_payload"}),
    Path("scripts/opencode_readiness.py"): frozenset({"_check_prompt_guardrails"}),
    Path("scripts/opencode_worker.py"): frozenset({"_build_prompt"}),
    Path("scripts/package_index_readiness_checks.py"): frozenset({"_read_text"}),
    Path("scripts/pr_body_check.py"): frozenset({"main"}),
    Path("scripts/public_claims_audit.py"): frozenset({"_audit_files"}),
    Path("scripts/quality_trend_summary.py"): frozenset({"_read_text"}),
    Path("scripts/release_evidence.py"): frozenset({"_load_ledger", "_load_freshness_fixture"}),
    Path("scripts/test_taxonomy.py"): frozenset({"_declared_pytest_markers", "collect_test_files"}),
    Path("src/entroping/brain/architect_build.py"): frozenset({"_read_merge_target"}),
    Path("src/entroping/brain/architect_refactor.py"): frozenset({"_read_refactor_target"}),
    Path("src/entroping/brain/persona_loader.py"): frozenset({"_read_persona"}),
    Path("src/entroping/core/config_writer.py"): frozenset({"_read_yaml_mapping"}),
    Path("src/entroping/core/coverage_badges.py"): frozenset({"_read_json_object"}),
    Path("src/entroping/core/effective_policy_diff_report.py"): frozenset(
        {"load_effective_policy_report"}
    ),
    Path("src/entroping/core/env_loader.py"): frozenset({"_read_env_file"}),
    Path("src/entroping/core/evidence/agent_bundle.py"): frozenset({"_load_manifests"}),
    Path("src/entroping/core/evidence/pilot_metrics.py"): frozenset({"_load_json_object"}),
    Path("src/entroping/core/github_actions_starter.py"): frozenset({"<module>"}),
    Path("src/entroping/core/policy_pack_vendor.py"): frozenset(
        {"_read_yaml_mapping", "_read_config_mapping"}
    ),
    Path("src/entroping/core/run_suite_manifest.py"): frozenset({"_read_yaml_mapping"}),
    Path("src/entroping/core/runtime_card.py"): frozenset({"_load_json_object"}),
    Path("src/entroping/core/story_documents.py"): frozenset({"discover_story_documents"}),
}


ARCHITECTURE_RULES = (
    ImportBoundaryRule(
        source_prefixes=("entroping.models",),
        forbidden_import_prefixes=(
            "entroping.cli",
            "entroping.core",
            "entroping.brain",
            "entroping.studio",
        ),
        reason="domain models must not import adapters",
    ),
    ImportBoundaryRule(
        source_prefixes=("entroping.bridge",),
        forbidden_import_prefixes=(
            "entroping.cli",
            "entroping.core",
            "entroping.brain",
            "entroping.studio",
        ),
        reason="bridge compilers must stay adapter-free",
    ),
    ImportBoundaryRule(
        source_prefixes=("entroping.core", "entroping.brain"),
        forbidden_import_prefixes=("entroping.cli",),
        reason="secondary adapters must not import primary CLI adapters",
    ),
)

DETERMINISTIC_RUN_MODULES = (
    "entroping.core.env_loader",
    "entroping.core.gate_injector",
    "entroping.core.hurl_discovery",
    "entroping.core.hurl_runner",
    "entroping.core.report_writer",
)

TRAFFIC_STATE_MODULES = (
    "entroping.core.traffic_proxy",
    "entroping.core.traffic_redactor",
    "entroping.core.traffic_store",
)

CORE_BOUNDED_PACKAGE_MODULES = {
    "entroping.core.evidence": (
        "agent_bundle",
        "api_inventory",
        "connector_intent",
        "evidence_bundle",
        "evidence_cloud_dashboard",
        "evidence_index",
        "evidence_index_report",
        "evidence_links",
        "evidence_portal",
        "external_test_evidence",
        "handoff_packet",
        "notification_packet",
        "observability_packet",
        "otel_mapping",
        "pilot_cohort",
        "pilot_metrics",
        "pilot_outcome",
        "pr_evidence_card",
        "test_pyramid_report",
    ),
    "entroping.core.export": (
        "evidence_cloud_export",
        "evidence_cloud_workspace",
        "work_item_draft",
        "work_item_import_bundle",
    ),
    "entroping.core.plan": (
        "evidence_action_plan",
        "qa_brain_eval_plan",
        "qa_brain_fine_tune_readiness",
        "qa_brain_model_packaging_plan",
        "qa_brain_prompt_plan",
        "qa_brain_repair_plan",
        "qa_brain_retrieval_plan",
        "qa_brain_routing_plan",
        "qa_brain_seed",
        "team_access_control_plan",
    ),
    "entroping.core.readiness": (
        "devex_readiness",
        "evidence_cloud_readiness",
        "integration_readiness",
        "mutation_readiness",
        "observability_adapter_readiness",
        "team_evidence_readiness",
    ),
}


def _repo_relative_path(path: Path) -> Path:
    try:
        return path.relative_to(Path.cwd())
    except ValueError:
        return path


def _is_read_text_scan_candidate(path: Path) -> bool:
    return path.suffix == ".py" and not any(
        part in READ_TEXT_SCAN_EXCLUDED_PARTS for part in path.parts
    )


def _read_text_guard_source_paths() -> tuple[Path, ...]:
    source_paths = sorted(
        path for path in SOURCE_ROOT.rglob("*.py") if _is_read_text_scan_candidate(path)
    )
    script_paths = sorted(
        path for path in SCRIPTS_ROOT.rglob("*.py") if _is_read_text_scan_candidate(path)
    )
    return tuple([*source_paths, *script_paths])


def _enclosing_function_name(node: ast.AST, parent_map: dict[ast.AST, ast.AST | None]) -> str:
    current: ast.AST | None = node
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
        current = parent_map.get(current)
    return "<module>"


def _find_unapproved_read_text_calls(
    paths: Iterable[Path],
    *,
    allowed_functions_by_file: dict[Path, frozenset[str]],
) -> list[str]:
    violations: list[str] = []
    for path in paths:
        display_path = _repo_relative_path(path)
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(display_path))
        parent_map: dict[ast.AST, ast.AST | None] = {tree: None}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parent_map[child] = node

        allowed_functions = allowed_functions_by_file.get(display_path, frozenset())
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "read_text"
            ):
                continue
            function_name = _enclosing_function_name(node, parent_map)
            if function_name not in allowed_functions:
                violations.append(
                    f"{display_path}:{node.lineno} uses unbounded read_text outside an approved "
                    f"helper ({function_name})"
                )
    return violations


def test_import_boundary_checker_detects_synthetic_violations(tmp_path: Path) -> None:
    package = tmp_path / "entroping"
    (package / "models").mkdir(parents=True)
    (package / "models" / "leaky.py").write_text(
        "from entroping.core import hurl_runner\n",
        encoding="utf-8",
    )

    modules = collect_python_modules(package, package_name="entroping")
    violations = find_forbidden_imports(modules, rules=ARCHITECTURE_RULES)

    assert violations
    assert "entroping.models.leaky imports entroping.core" in format_violations(violations)


def test_provider_checker_detects_synthetic_direct_sdk_imports(tmp_path: Path) -> None:
    package = tmp_path / "entroping"
    (package / "brain").mkdir(parents=True)
    (package / "brain" / "leaky.py").write_text(
        "import deepseek\nimport openai\nfrom anthropic import Anthropic\n",
        encoding="utf-8",
    )

    modules = collect_python_modules(package, package_name="entroping")
    violations = find_provider_imports(modules)

    assert violations
    assert "entroping.brain.leaky imports deepseek" in format_violations(violations)
    assert "entroping.brain.leaky imports openai" in format_violations(violations)
    assert "entroping.brain.leaky imports anthropic" in format_violations(violations)


def test_provider_checker_detects_bare_import_module_dynamic_imports(
    tmp_path: Path,
) -> None:
    package = tmp_path / "entroping"
    (package / "brain").mkdir(parents=True)
    (package / "brain" / "dynamic_leak.py").write_text(
        "from importlib import import_module\n\nimport_module('deepseek')\n",
        encoding="utf-8",
    )

    modules = collect_python_modules(package, package_name="entroping")
    violations = find_provider_imports(modules)

    assert "entroping.brain.dynamic_leak imports deepseek" in format_violations(violations)


def test_domain_and_bridge_modules_do_not_import_adapters() -> None:
    modules = collect_python_modules(SOURCE_ROOT, package_name="entroping")

    violations = find_forbidden_imports(modules, rules=ARCHITECTURE_RULES)

    assert not violations, format_violations(violations)


def test_deterministic_run_core_modules_do_not_import_brain_or_litellm() -> None:
    modules = collect_python_modules(SOURCE_ROOT, package_name="entroping")
    rules = (
        ImportBoundaryRule(
            source_prefixes=DETERMINISTIC_RUN_MODULES,
            forbidden_import_prefixes=("entroping.brain", "litellm"),
            reason="deterministic run core must not import Brain or model providers",
        ),
    )

    violations = find_forbidden_imports(modules, rules=rules)

    assert not violations, format_violations(violations)


def test_product_source_does_not_import_factory_worker_routing() -> None:
    modules = collect_python_modules(SOURCE_ROOT, package_name="entroping")
    rules = (
        ImportBoundaryRule(
            source_prefixes=("entroping",),
            forbidden_import_prefixes=(
                "scripts.ai_jobs",
                "scripts.opencode_worker",
                "scripts.deepseek_worker",
            ),
            reason="factory worker routing must stay maintainer tooling, not product runtime",
        ),
    )

    violations = find_forbidden_imports(modules, rules=rules)

    assert not violations, format_violations(violations)


def test_unbounded_read_text_guard_reports_unapproved_source_file(tmp_path: Path) -> None:
    source_path = tmp_path / "src" / "entroping" / "core" / "hurl_indexer.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "from pathlib import Path\n\n"
        "def load_hurl(path: Path) -> str:\n"
        "    return path.read_text(encoding='utf-8')\n",
        encoding="utf-8",
    )

    violations = _find_unapproved_read_text_calls(
        (source_path,),
        allowed_functions_by_file={},
    )

    assert violations == [
        f"{source_path}:4 uses unbounded read_text outside an approved helper "
        "(load_hurl)",
    ]


def test_security_sensitive_source_loaders_do_not_use_unbounded_read_text() -> None:
    violations = _find_unapproved_read_text_calls(
        _read_text_guard_source_paths(),
        allowed_functions_by_file=APPROVED_READ_TEXT_FUNCTIONS_BY_FILE,
    )

    assert not violations, "\n".join(violations)


def test_hurl_source_loaders_share_one_max_size_contract() -> None:
    hurl_source = import_module("entroping.hurl_source")
    assert hurl_source.HURL_SOURCE_MAX_BYTES == 10 * 1024 * 1024

    expected_importers = (
        "entroping.core.hurl_discovery",
        "entroping.core.gate_injector",
        "entroping.core.gate_injection_report",
        "entroping.core.hurl_variable_preflight",
        "entroping.core.failure_bundle",
        "entroping.bridge.test_quality",
    )
    for module_name in expected_importers:
        module = import_module(module_name)
        assert module.read_hurl_source_text is hurl_source.read_hurl_source_text


def test_litellm_is_the_only_model_provider_abstraction_in_source() -> None:
    modules = collect_python_modules(SOURCE_ROOT, package_name="entroping")

    violations = find_provider_imports(modules)

    assert not violations, format_violations(violations)


def test_traffic_state_modules_do_not_import_brain_or_litellm() -> None:
    modules = collect_python_modules(SOURCE_ROOT, package_name="entroping")
    rules = (
        ImportBoundaryRule(
            source_prefixes=TRAFFIC_STATE_MODULES,
            forbidden_import_prefixes=("entroping.brain", "litellm"),
            reason="traffic capture state must never call model providers",
        ),
    )

    violations = find_forbidden_imports(modules, rules=rules)

    assert not violations, format_violations(violations)


def test_core_evidence_families_live_in_bounded_packages_with_old_path_shims() -> None:
    for package_name, module_names in CORE_BOUNDED_PACKAGE_MODULES.items():
        import_module(package_name)
        for module_name in module_names:
            new_module = import_module(f"{package_name}.{module_name}")
            old_module = import_module(f"entroping.core.{module_name}")
            marker_name = f"_compat_marker_{module_name}"

            assert old_module is new_module
            setattr(old_module, marker_name, package_name)
            try:
                assert getattr(new_module, marker_name) == package_name
            finally:
                delattr(old_module, marker_name)
