"""Executable architecture and provider boundary tests."""

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
