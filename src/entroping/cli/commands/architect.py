"""Architect command adapter."""

import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse

import typer

from entroping.brain import (
    ArchitectAuditReviewParseError,
    ArchitectOutputParseError,
    ArchitectRefactorError,
    ArchitectWriteError,
    BrainProviderError,
    PersonaLoadError,
    PromptBuildError,
    render_auditor_review_json,
    render_auditor_review_markdown,
    run_architect_auditor_review,
    run_architect_prompt_build,
    run_architect_refactor,
)
from entroping.brain.architect_build import ArchitectBuildAgent
from entroping.bridge.openapi_audit import (
    audit_openapi_coverage,
    audit_report_to_dict,
    render_audit_markdown,
)
from entroping.bridge.openapi_diff import (
    OpenApiOperationChanges,
    audit_openapi_breaking_changes,
    detect_openapi_operation_changes,
)
from entroping.bridge.openapi_to_hurl import (
    GeneratedHurlFile,
    OpenApiCompilationError,
    OpenApiSecurityCoverageFinding,
    compile_openapi_to_hurl_with_report,
)
from entroping.bridge.traffic_openapi_audit import (
    TrafficOpenApiAuditError,
    TrafficOpenApiAuditReport,
    audit_traffic_routes_against_openapi,
)
from entroping.bridge.traffic_sessions import (
    TrafficSessionError,
    build_traffic_session_candidate,
)
from entroping.bridge.traffic_to_graph import (
    TrafficGraphCompilationError,
    compile_traffic_dependency_graph,
)
from entroping.cli.shared import (
    console,
    display_cli_path,
    print_architect_error,
    safe_cli_text,
)
from entroping.core.config_loader import QanstitutionLoadError, load_qanstitution
from entroping.core.git_openapi import GitOpenApiError, load_openapi_document_at_ref
from entroping.core.hurl_discovery import discover_hurl_tests, normalize_tag_filters
from entroping.core.hurl_validator import validate_hurl_content
from entroping.core.openapi_loader import OpenApiLoadError, load_openapi_document
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.traffic_store import TrafficStoreError, list_project_exchanges_readonly

app = typer.Typer(help="Generate, refactor, and audit Hurl tests.")
HurlValidator = Callable[[str, str], None]
ArchitectAuditFocus = Literal["logic", "auditor"]


@dataclass(frozen=True)
class PreparedGeneratedHurlFile:
    """OpenAPI-generated Hurl content after path and parser validation."""

    generated: GeneratedHurlFile
    output_path: Path


@app.command("build")
def architect_build(
    new: Annotated[bool, typer.Option("--new", help="Generate new tests.")] = False,
    prompt: Annotated[
        str | None,
        typer.Option("--prompt", help="Scoped generation intent."),
    ] = None,
    strategy: Annotated[str | None, typer.Option("--strategy", help="Merge strategy.")] = None,
    tag: Annotated[list[str] | None, typer.Option("--tag", help="Tag generated tests.")] = None,
    agent: Annotated[
        str | None,
        typer.Option("--agent", help="Prompt generation agent: builder or breaker."),
    ] = None,
    changed_from: Annotated[
        str | None,
        typer.Option(
            "--changed-from",
            help="Generate only OpenAPI operations changed from a Git ref.",
        ),
    ] = None,
) -> None:
    """Generate Hurl tests from configured sources or prompts."""

    normalized_strategy: str | None = None
    if strategy is not None:
        normalized_strategy = strategy.strip().lower()
        if normalized_strategy != "merge":
            console.print(f"[yellow]Unsupported architect build strategy: {strategy}[/yellow]")
            raise typer.Exit(2)
    build_agent = _normalize_architect_build_agent(agent)
    if prompt is not None:
        if changed_from is not None:
            console.print("[yellow]--changed-from applies only to architect build --new.[/yellow]")
            raise typer.Exit(2)
        _run_architect_prompt_build(
            prompt=prompt,
            tag=tag,
            strategy="merge" if normalized_strategy == "merge" else "create",
            agent=build_agent,
        )
        return
    if agent is not None:
        console.print("[yellow]--agent applies only to prompt-backed architect build.[/yellow]")
        raise typer.Exit(2)
    if normalized_strategy == "merge":
        console.print("[yellow]--strategy merge requires --prompt in the current alpha.[/yellow]")
        raise typer.Exit(2)
    if changed_from is not None and not new:
        console.print("[yellow]--changed-from requires architect build --new.[/yellow]")
        raise typer.Exit(2)
    if not new:
        console.print("[yellow]Choose a supported architect build mode:[/yellow]")
        console.print("  entroping architect build --new")
        console.print('  entroping architect build --prompt "<intent>"')
        console.print('  entroping architect build --agent breaker --prompt "<intent>"')
        console.print('  entroping architect build --strategy merge --prompt "<intent>"')
        raise typer.Exit(2)

    try:
        tag_filters = normalize_tag_filters(tag)
        law = load_qanstitution(Path("qanstitution.yaml"))
        if law.sources is None or law.sources.spec is None or not law.sources.spec.strip():
            msg = "sources.spec is required for architect build --new"
            raise ValueError(msg)
        spec_root = _configured_spec_root()
        spec_reference = _configured_spec_reference(law.sources.spec)
        baseline_spec_reference: Path | None = None
        if changed_from is not None:
            if not isinstance(spec_reference, Path):
                msg = "--changed-from requires a local OpenAPI sources.spec path"
                raise ValueError(msg)
            baseline_spec_reference = spec_reference
        document = load_openapi_document(
            spec_reference,
            root=spec_root if isinstance(spec_reference, Path) else None,
        )
        operation_ids: frozenset[str] | None = None
        if changed_from is not None and baseline_spec_reference is not None:
            base_document = load_openapi_document_at_ref(
                project_root=Path.cwd(),
                base_ref=changed_from,
                spec_path=baseline_spec_reference,
            )
            changes = detect_openapi_operation_changes(base_document, document)
            _print_openapi_change_summary(base_ref=changed_from, changes=changes)
            if not changes.generation_operation_ids:
                console.print(
                    "No current OpenAPI operation changes require generation from "
                    f"{safe_cli_text(changed_from)}.",
                    markup=False,
                    soft_wrap=True,
                )
                return
            operation_ids = frozenset(changes.generation_operation_ids)
        compilation = compile_openapi_to_hurl_with_report(
            document,
            tags=tag_filters,
            operation_ids=operation_ids,
        )
        prepared = _prepare_generated_hurl_files(compilation.files)
        written = [_write_prepared_generated_hurl_file(item) for item in prepared]
    except (
        QanstitutionLoadError,
        GitOpenApiError,
        OpenApiLoadError,
        OpenApiCompilationError,
        ValueError,
    ) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    noun = "test" if len(written) == 1 else "tests"
    console.print(f"[green]Generated {len(written)} Hurl {noun} under tests/generated.[/green]")
    for path in written:
        console.print(f"Wrote Hurl test: {display_cli_path(path)}")
    _print_security_coverage_findings(compilation.security_findings)


@app.command("refactor")
def architect_refactor(
    target: Annotated[str, typer.Option("--target", help="Target Hurl glob.")],
    prompt: Annotated[str, typer.Option("--prompt", help="Refactor instruction.")],
    preview: Annotated[
        bool,
        typer.Option(
            "--preview",
            help="Print a proposed unified diff without writing target Hurl files.",
        ),
    ] = False,
) -> None:
    """Safely update existing Hurl tests."""

    try:
        law = load_qanstitution(Path("qanstitution.yaml"))
        result = run_architect_refactor(
            law=law,
            target_glob=target,
            prompt=prompt,
            project_root=Path.cwd(),
            config_path=Path("qanstitution.yaml"),
            preview=preview,
        )
    except (
        ArchitectOutputParseError,
        ArchitectRefactorError,
        ArchitectWriteError,
        BrainProviderError,
        PersonaLoadError,
        PromptBuildError,
        QanstitutionLoadError,
        ValueError,
    ) as exc:
        print_architect_error(exc)
        raise typer.Exit(1) from exc

    if result.preview:
        noun = "test" if len(result.preview_paths) == 1 else "tests"
        console.print(
            f"[green]Previewed {len(result.preview_paths)} Architect Hurl {noun}.[/green]"
        )
        console.print(f"Summary: {safe_cli_text(result.summary)}", markup=False)
        console.print(
            f"Model: {safe_cli_text(result.model)} ({result.latency_ms} ms)",
            markup=False,
        )
        _print_budget_evidence(
            provider=result.provider,
            estimated_cost_usd=result.cost.estimated_usd,
        )
        for warning in result.warnings:
            console.print(f"Warning: {safe_cli_text(warning)}", style="yellow", markup=False)
        console.print("Preview diff:", style="cyan")
        if result.preview_diff:
            console.print(result.preview_diff.rstrip(), markup=False, soft_wrap=False)
        else:
            console.print("(no textual diff)", markup=False)
        console.print(
            f"Wrote agent run manifest: {safe_cli_text(display_cli_path(result.manifest_path))}",
            markup=False,
        )
        return

    noun = "test" if len(result.written_paths) == 1 else "tests"
    console.print(f"[green]Refactored {len(result.written_paths)} Architect Hurl {noun}.[/green]")
    console.print(f"Summary: {safe_cli_text(result.summary)}", markup=False)
    console.print(f"Model: {safe_cli_text(result.model)} ({result.latency_ms} ms)", markup=False)
    _print_budget_evidence(provider=result.provider, estimated_cost_usd=result.cost.estimated_usd)
    for warning in result.warnings:
        console.print(f"Warning: {safe_cli_text(warning)}", style="yellow", markup=False)
    for path in result.written_paths:
        console.print(f"Wrote Hurl test: {safe_cli_text(display_cli_path(path))}", markup=False)
    console.print(
        f"Wrote agent run manifest: {safe_cli_text(display_cli_path(result.manifest_path))}",
        markup=False,
    )


@app.command("audit")
def architect_audit(
    focus: Annotated[
        str | None,
        typer.Option("--focus", help="Audit focus: logic or auditor."),
    ] = None,
    output: Annotated[str | None, typer.Option("--output", help="json or md.")] = None,
    changed_from: Annotated[
        str | None,
        typer.Option(
            "--changed-from",
            help="Compare the configured OpenAPI spec against a Git base ref.",
        ),
    ] = None,
) -> None:
    """Audit test quality and governance gaps."""

    try:
        audit_focus = _normalize_architect_audit_focus(focus)
        audit_output = _normalize_architect_audit_output(output)
        law = load_qanstitution(Path("qanstitution.yaml"))
        if law.sources is None or law.sources.spec is None or not law.sources.spec.strip():
            msg = "sources.spec is required for architect audit"
            raise ValueError(msg)
        spec_root = _configured_spec_root()
        spec_reference = _configured_spec_reference(law.sources.spec)
        if changed_from is not None and not isinstance(spec_reference, Path):
            msg = "--changed-from requires a local OpenAPI sources.spec path"
            raise ValueError(msg)
        baseline_spec_reference: Path | None = None
        if changed_from is not None and isinstance(spec_reference, Path):
            baseline_spec_reference = spec_reference
        document = load_openapi_document(
            spec_reference,
            root=spec_root if isinstance(spec_reference, Path) else None,
        )
        openapi_diff = None
        if changed_from is not None and baseline_spec_reference is not None:
            base_document = load_openapi_document_at_ref(
                project_root=Path.cwd(),
                base_ref=changed_from,
                spec_path=baseline_spec_reference,
            )
            openapi_diff = audit_openapi_breaking_changes(
                base_document,
                document,
                base_ref=changed_from,
            )
        hurl_tests = discover_hurl_tests() if Path("tests").exists() else []
        traffic_routes = _load_traffic_openapi_audit(document)
        report = audit_openapi_coverage(
            document,
            hurl_tests,
            project_root=Path.cwd(),
            traffic_routes=traffic_routes,
            openapi_diff=openapi_diff,
        )
    except (
        QanstitutionLoadError,
        GitOpenApiError,
        OpenApiLoadError,
        OpenApiCompilationError,
        ValueError,
    ) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    if audit_focus == "auditor":
        try:
            auditor_result = run_architect_auditor_review(
                law=law,
                deterministic_report=report,
                project_root=Path.cwd(),
                config_path=Path("qanstitution.yaml"),
            )
        except (
            ArchitectAuditReviewParseError,
            BrainProviderError,
            PersonaLoadError,
            PromptBuildError,
            ValueError,
        ) as exc:
            print_architect_error(exc)
            raise typer.Exit(1) from exc

        if audit_output == "json":
            sys.stdout.write(render_auditor_review_json(auditor_result))
        else:
            sys.stdout.write(render_auditor_review_markdown(auditor_result))
            sys.stdout.write("\n")
        raise typer.Exit(0 if auditor_result.passed else 1)

    if audit_output == "json":
        sys.stdout.write(json.dumps(audit_report_to_dict(report), indent=2, sort_keys=True))
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_audit_markdown(report))
        sys.stdout.write("\n")

    raise typer.Exit(0 if report.passed else 1)


def _run_architect_prompt_build(
    *,
    prompt: str,
    tag: list[str] | None,
    strategy: str = "create",
    agent: ArchitectBuildAgent = "builder",
) -> None:
    try:
        tag_filters = normalize_tag_filters(tag)
        law = load_qanstitution(Path("qanstitution.yaml"))
        result = run_architect_prompt_build(
            law=law,
            intent=prompt,
            tags=tuple(sorted(tag_filters)),
            strategy="merge" if strategy == "merge" else "create",
            agent=agent,
            project_root=Path.cwd(),
            config_path=Path("qanstitution.yaml"),
        )
    except (
        ArchitectOutputParseError,
        ArchitectWriteError,
        BrainProviderError,
        PersonaLoadError,
        PromptBuildError,
        QanstitutionLoadError,
        ValueError,
    ) as exc:
        print_architect_error(exc)
        raise typer.Exit(1) from exc

    noun = "test" if len(result.written_paths) == 1 else "tests"
    console.print(f"[green]Generated {len(result.written_paths)} Architect Hurl {noun}.[/green]")
    console.print(f"Summary: {safe_cli_text(result.summary)}", markup=False)
    console.print(f"Agent: {safe_cli_text(result.agent)}", markup=False)
    console.print(f"Model: {safe_cli_text(result.model)} ({result.latency_ms} ms)", markup=False)
    _print_budget_evidence(provider=result.provider, estimated_cost_usd=result.cost.estimated_usd)
    for warning in result.warnings:
        console.print(f"Warning: {safe_cli_text(warning)}", style="yellow", markup=False)
    for path in result.written_paths:
        console.print(f"Wrote Hurl test: {safe_cli_text(display_cli_path(path))}", markup=False)
    console.print(
        f"Wrote agent run manifest: {safe_cli_text(display_cli_path(result.manifest_path))}",
        markup=False,
    )


def _normalize_architect_build_agent(agent: str | None) -> ArchitectBuildAgent:
    if agent is None:
        return "builder"
    normalized = agent.strip().lower()
    if normalized == "builder":
        return "builder"
    if normalized == "breaker":
        return "breaker"
    console.print(
        f"Unsupported architect build agent: {safe_cli_text(agent)}; "
        "supported agents: builder, breaker",
        style="yellow",
        markup=False,
    )
    raise typer.Exit(2)


def _print_budget_evidence(*, provider: str | None, estimated_cost_usd: float | None) -> None:
    console.print(f"Provider: {safe_cli_text(provider or 'unknown')}", markup=False)
    console.print(
        f"Estimated cost: {safe_cli_text(_format_estimated_cost(estimated_cost_usd))}",
        markup=False,
    )


def _format_estimated_cost(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"${value:.8f}".rstrip("0").rstrip(".")


def _normalize_architect_audit_focus(focus: str | None) -> ArchitectAuditFocus:
    if focus is None:
        return "logic"
    normalized = focus.strip().lower()
    if normalized == "logic":
        return "logic"
    if normalized == "auditor":
        return "auditor"
    msg = f"Unsupported architect audit focus {focus!r}; supported focus: logic, auditor"
    raise ValueError(msg)


def _normalize_architect_audit_output(output: str | None) -> str:
    if output is None:
        return "md"
    normalized = output.strip().lower()
    if normalized not in {"json", "md"}:
        msg = f"Unsupported architect audit output {output!r}; supported outputs: json, md"
        raise ValueError(msg)
    return normalized


def _print_openapi_change_summary(
    *,
    base_ref: str,
    changes: OpenApiOperationChanges,
) -> None:
    summary = changes.summary
    console.print(
        "OpenAPI changes from "
        f"{safe_cli_text(base_ref)}: "
        f"added={summary['added']}, "
        f"modified={summary['modified']}, "
        f"renamed={summary['renamed']}, "
        f"removed={summary['removed']}, "
        f"unchanged={summary['unchanged']}",
        markup=False,
        soft_wrap=True,
    )
    removed_operation_ids = tuple(
        item.operation_id for item in changes.items if item.change_type == "removed"
    )
    if removed_operation_ids:
        console.print(
            "Removed OpenAPI operations require manual review: "
            f"{safe_cli_text(', '.join(removed_operation_ids))}",
            markup=False,
            soft_wrap=True,
        )


def _print_security_coverage_findings(
    findings: Sequence[OpenApiSecurityCoverageFinding],
) -> None:
    for finding in findings:
        console.print(
            "OpenAPI security coverage warning: "
            f"{safe_cli_text(finding.operation_id)} "
            f"{safe_cli_text(finding.scheme_name)} "
            f"({safe_cli_text(finding.method)} {safe_cli_text(finding.path)}): "
            f"{safe_cli_text(finding.reason)}",
            style="yellow",
            markup=False,
            soft_wrap=True,
        )


def _load_traffic_openapi_audit(
    document: Mapping[str, object],
) -> TrafficOpenApiAuditReport | None:
    try:
        exchanges = list_project_exchanges_readonly(Path.cwd())
    except TrafficStoreError as exc:
        if str(exc) == "traffic state not found":
            return None
        msg = f"could not read traffic state for architect audit: {exc}"
        raise ValueError(msg) from exc
    if not exchanges:
        return None

    try:
        session = build_traffic_session_candidate(
            exchanges,
            name="architect_audit",
            target_url=None,
        )
        graph = compile_traffic_dependency_graph(session)
        return audit_traffic_routes_against_openapi(document, graph)
    except (
        TrafficGraphCompilationError,
        TrafficOpenApiAuditError,
        TrafficSessionError,
    ) as exc:
        msg = f"could not audit traffic routes against OpenAPI: {exc}"
        raise ValueError(msg) from exc


def _configured_spec_root() -> Path:
    return Path("qanstitution.yaml").resolve().parent


def _configured_spec_reference(spec: str) -> str | Path:
    parsed = urlparse(spec)
    if parsed.scheme:
        return spec

    spec_path = Path(spec)
    if spec_path.is_absolute():
        return spec_path
    return _configured_spec_root() / spec_path


def _write_generated_hurl_file(generated: GeneratedHurlFile) -> Path:
    prepared = _prepare_generated_hurl_file(generated)
    return _write_prepared_generated_hurl_file(prepared)


def _prepare_generated_hurl_files(
    generated: Sequence[GeneratedHurlFile],
    *,
    hurl_validator: HurlValidator | None = None,
) -> tuple[PreparedGeneratedHurlFile, ...]:
    prepared = tuple(_prepare_generated_hurl_file(item) for item in generated)
    active_validator = hurl_validator or validate_hurl_content
    for item in prepared:
        active_validator(item.generated.content, item.generated.relative_path)
    return prepared


def _prepare_generated_hurl_file(generated: GeneratedHurlFile) -> PreparedGeneratedHurlFile:
    relative_path = Path(generated.relative_path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        msg = f"Generated Hurl path must stay inside the project: {generated.relative_path}"
        raise ValueError(msg)

    project_root = Path.cwd().resolve()
    candidate = project_root / relative_path
    _reject_symlink_path_components(candidate, root=project_root)

    generated_root = project_root / "tests" / "generated"
    output_path = candidate.resolve()
    if not output_path.is_relative_to(generated_root):
        msg = f"Generated Hurl path must stay under tests/generated: {generated.relative_path}"
        raise ValueError(msg)

    if output_path.is_symlink():
        msg = f"Refusing to overwrite symlinked generated Hurl file: {output_path}"
        raise ValueError(msg)
    if output_path.exists():
        existing = output_path.read_text(encoding="utf-8")
        if not _has_openapi_generated_header(existing):
            msg = f"Refusing to overwrite non-OpenAPI Hurl file: {display_cli_path(output_path)}"
            raise ValueError(msg)

    return PreparedGeneratedHurlFile(generated=generated, output_path=output_path)


def _has_openapi_generated_header(content: str) -> bool:
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            return False
        if not stripped.startswith("# entroping: "):
            return False
        if stripped == "# entroping: source=openapi":
            return True
    return False


def _write_prepared_generated_hurl_file(prepared: PreparedGeneratedHurlFile) -> Path:
    output_path = prepared.output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(prepared.generated.content, encoding="utf-8")
    return output_path


def _reject_symlink_path_components(path: Path, *, root: Path) -> None:
    symlink_component = first_symlink_path_component(path, root=root)
    if symlink_component is not None:
        msg = (
            "Refusing to write symlinked generated Hurl path component: "
            f"{symlink_component}"
        )
        raise ValueError(msg)
