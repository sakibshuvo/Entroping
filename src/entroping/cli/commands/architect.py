"""Architect command adapter."""

import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

import typer

from entroping.brain import (
    ArchitectOutputParseError,
    ArchitectRefactorError,
    ArchitectWriteError,
    BrainProviderError,
    PersonaLoadError,
    PromptBuildError,
    run_architect_prompt_build,
    run_architect_refactor,
)
from entroping.bridge.openapi_audit import (
    audit_openapi_coverage,
    audit_report_to_dict,
    render_audit_markdown,
)
from entroping.bridge.openapi_to_hurl import (
    GeneratedHurlFile,
    OpenApiCompilationError,
    compile_openapi_to_hurl,
)
from entroping.cli.shared import (
    console,
    display_cli_path,
    print_architect_error,
    safe_cli_text,
)
from entroping.core.config_loader import QanstitutionLoadError, load_qanstitution
from entroping.core.hurl_discovery import discover_hurl_tests, normalize_tag_filters
from entroping.core.hurl_validator import validate_hurl_content
from entroping.core.openapi_loader import OpenApiLoadError, load_openapi_document
from entroping.core.path_safety import first_symlink_path_component

app = typer.Typer(help="Generate, refactor, and audit Hurl tests.")
HurlValidator = Callable[[str, str], None]


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
) -> None:
    """Generate Hurl tests from configured sources or prompts."""

    normalized_strategy: str | None = None
    if strategy is not None:
        normalized_strategy = strategy.strip().lower()
        if normalized_strategy != "merge":
            console.print(f"[yellow]Unsupported architect build strategy: {strategy}[/yellow]")
            raise typer.Exit(2)
    if prompt is not None:
        _run_architect_prompt_build(
            prompt=prompt,
            tag=tag,
            strategy="merge" if normalized_strategy == "merge" else "create",
        )
        return
    if normalized_strategy == "merge":
        console.print("[yellow]--strategy merge requires --prompt in the current alpha.[/yellow]")
        raise typer.Exit(2)
    if not new:
        console.print("[yellow]Choose a supported architect build mode:[/yellow]")
        console.print("  entroping architect build --new")
        console.print('  entroping architect build --prompt "<intent>"')
        console.print('  entroping architect build --strategy merge --prompt "<intent>"')
        raise typer.Exit(2)

    try:
        tag_filters = normalize_tag_filters(tag)
        law = load_qanstitution(Path("qanstitution.yaml"))
        if law.sources is None or law.sources.spec is None or not law.sources.spec.strip():
            msg = "sources.spec is required for architect build --new"
            raise ValueError(msg)
        document = load_openapi_document(_configured_spec_reference(law.sources.spec))
        generated = compile_openapi_to_hurl(document, tags=tag_filters)
        prepared = _prepare_generated_hurl_files(generated)
        written = [_write_prepared_generated_hurl_file(item) for item in prepared]
    except (QanstitutionLoadError, OpenApiLoadError, OpenApiCompilationError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    noun = "test" if len(written) == 1 else "tests"
    console.print(f"[green]Generated {len(written)} Hurl {noun} under tests/generated.[/green]")
    for path in written:
        console.print(f"Wrote Hurl test: {display_cli_path(path)}")


@app.command("refactor")
def architect_refactor(
    target: Annotated[str, typer.Option("--target", help="Target Hurl glob.")],
    prompt: Annotated[str, typer.Option("--prompt", help="Refactor instruction.")],
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

    noun = "test" if len(result.written_paths) == 1 else "tests"
    console.print(f"[green]Refactored {len(result.written_paths)} Architect Hurl {noun}.[/green]")
    console.print(f"Summary: {safe_cli_text(result.summary)}", markup=False)
    console.print(f"Model: {safe_cli_text(result.model)} ({result.latency_ms} ms)", markup=False)
    for warning in result.warnings:
        console.print(f"Warning: {safe_cli_text(warning)}", style="yellow", markup=False)
    for path in result.written_paths:
        console.print(f"Wrote Hurl test: {safe_cli_text(display_cli_path(path))}", markup=False)


@app.command("audit")
def architect_audit(
    focus: Annotated[
        str | None,
        typer.Option("--focus", help="Audit focus. Currently: logic."),
    ] = None,
    output: Annotated[str | None, typer.Option("--output", help="json or md.")] = None,
) -> None:
    """Audit test quality and governance gaps."""

    try:
        audit_focus = _normalize_architect_audit_focus(focus)
        audit_output = _normalize_architect_audit_output(output)
        law = load_qanstitution(Path("qanstitution.yaml"))
        if law.sources is None or law.sources.spec is None or not law.sources.spec.strip():
            msg = "sources.spec is required for architect audit"
            raise ValueError(msg)
        document = load_openapi_document(_configured_spec_reference(law.sources.spec))
        hurl_tests = discover_hurl_tests() if Path("tests").exists() else []
        report = audit_openapi_coverage(document, hurl_tests)
    except (QanstitutionLoadError, OpenApiLoadError, OpenApiCompilationError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    _ = audit_focus
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
) -> None:
    try:
        tag_filters = normalize_tag_filters(tag)
        law = load_qanstitution(Path("qanstitution.yaml"))
        result = run_architect_prompt_build(
            law=law,
            intent=prompt,
            tags=tuple(sorted(tag_filters)),
            strategy="merge" if strategy == "merge" else "create",
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
    console.print(f"Model: {safe_cli_text(result.model)} ({result.latency_ms} ms)", markup=False)
    for warning in result.warnings:
        console.print(f"Warning: {safe_cli_text(warning)}", style="yellow", markup=False)
    for path in result.written_paths:
        console.print(f"Wrote Hurl test: {safe_cli_text(display_cli_path(path))}", markup=False)


def _normalize_architect_audit_focus(focus: str | None) -> str:
    if focus is None:
        return "logic"
    normalized = focus.strip().lower()
    if normalized != "logic":
        msg = f"Unsupported architect audit focus {focus!r}; supported focus: logic"
        raise ValueError(msg)
    return normalized


def _normalize_architect_audit_output(output: str | None) -> str:
    if output is None:
        return "md"
    normalized = output.strip().lower()
    if normalized not in {"json", "md"}:
        msg = f"Unsupported architect audit output {output!r}; supported outputs: json, md"
        raise ValueError(msg)
    return normalized


def _configured_spec_reference(spec: str) -> str | Path:
    parsed = urlparse(spec)
    if parsed.scheme:
        return spec

    spec_path = Path(spec)
    if spec_path.is_absolute():
        return spec_path
    return Path("qanstitution.yaml").resolve().parent / spec_path


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
        if "# entroping: source=openapi" not in existing:
            msg = f"Refusing to overwrite non-OpenAPI Hurl file: {display_cli_path(output_path)}"
            raise ValueError(msg)

    return PreparedGeneratedHurlFile(generated=generated, output_path=output_path)


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
