"""Executable architecture and provider boundary tests."""

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
