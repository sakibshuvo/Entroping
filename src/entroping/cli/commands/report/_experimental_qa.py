"""Experimental QA-brain and agent bundle report commands."""

from pathlib import Path
from typing import Annotated, cast

import typer

from entroping.cli.shared import console, display_cli_path, print_cli_error

from ._app import app
from ._deps import (
    AGENT_BUNDLE_ROLES,
    AgentBundleError,
    AgentBundleOutput,
    MutationMaterializerError,
    MutationReadinessReplayValidationError,
    QaBrainEvalPlanError,
    QaBrainEvalPlanOutput,
    QaBrainFineTuneReadinessError,
    QaBrainFineTuneReadinessOutput,
    QaBrainModelPackagingPlanError,
    QaBrainModelPackagingPlanOutput,
    QaBrainPromptPlanError,
    QaBrainPromptPlanOutput,
    QaBrainRepairPlanError,
    QaBrainRepairPlanOutput,
    QaBrainRetrievalPlanError,
    QaBrainRetrievalPlanOutput,
    QaBrainRoutingPlanError,
    QaBrainRoutingPlanOutput,
    QaBrainSeedError,
    QaBrainSeedOutput,
    report_dependency,
)
from ._panels import EXPERIMENTAL_REPORT_PANEL

run_agent_bundle_report = report_dependency("run_agent_bundle_report")
run_qa_brain_eval_plan_report = report_dependency("run_qa_brain_eval_plan_report")
run_qa_brain_fine_tune_readiness_report = report_dependency(
    "run_qa_brain_fine_tune_readiness_report"
)
run_qa_brain_model_packaging_plan_report = report_dependency(
    "run_qa_brain_model_packaging_plan_report"
)
run_qa_brain_prompt_plan_report = report_dependency("run_qa_brain_prompt_plan_report")
run_qa_brain_repair_plan_report = report_dependency("run_qa_brain_repair_plan_report")
run_qa_brain_retrieval_plan_report = report_dependency("run_qa_brain_retrieval_plan_report")
run_qa_brain_routing_plan_report = report_dependency("run_qa_brain_routing_plan_report")
run_qa_brain_seed_report = report_dependency("run_qa_brain_seed_report")
run_mutation_readiness_replay_validation = report_dependency(
    "run_mutation_readiness_replay_validation"
)
materialize_mutation_candidate = report_dependency("materialize_mutation_candidate")


@app.command("qa-brain-seed", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_qa_brain_seed(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local QA brain seed packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported qa-brain-seed output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_qa_brain_seed_report(
            project_root=Path.cwd(),
            output=cast(QaBrainSeedOutput, normalized_output),
        )
    except QaBrainSeedError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote QA brain seed: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("qa-brain-eval-plan", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_qa_brain_eval_plan(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local QA brain eval-plan packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported qa-brain-eval-plan output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_qa_brain_eval_plan_report(
            project_root=Path.cwd(),
            output=cast(QaBrainEvalPlanOutput, normalized_output),
        )
    except QaBrainEvalPlanError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote QA brain eval plan: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("qa-brain-retrieval-plan", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_qa_brain_retrieval_plan(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local QA brain retrieval-plan packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported qa-brain-retrieval-plan output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_qa_brain_retrieval_plan_report(
            project_root=Path.cwd(),
            output=cast(QaBrainRetrievalPlanOutput, normalized_output),
        )
    except QaBrainRetrievalPlanError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote QA brain retrieval plan: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("qa-brain-prompt-plan", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_qa_brain_prompt_plan(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local QA brain prompt-plan packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported qa-brain-prompt-plan output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_qa_brain_prompt_plan_report(
            project_root=Path.cwd(),
            output=cast(QaBrainPromptPlanOutput, normalized_output),
        )
    except QaBrainPromptPlanError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote QA brain prompt plan: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("qa-brain-fine-tune-readiness", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_qa_brain_fine_tune_readiness(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local QA brain fine-tune readiness packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported qa-brain-fine-tune-readiness output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_qa_brain_fine_tune_readiness_report(
            project_root=Path.cwd(),
            output=cast(QaBrainFineTuneReadinessOutput, normalized_output),
        )
    except QaBrainFineTuneReadinessError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote QA brain fine-tune readiness: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("qa-brain-model-packaging-plan", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_qa_brain_model_packaging_plan(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local QA brain model-packaging plan packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(
            f"[yellow]Unsupported qa-brain-model-packaging-plan output: {output}[/yellow]"
        )
        raise typer.Exit(2)

    try:
        result = run_qa_brain_model_packaging_plan_report(
            project_root=Path.cwd(),
            output=cast(QaBrainModelPackagingPlanOutput, normalized_output),
        )
    except QaBrainModelPackagingPlanError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote QA brain model packaging plan: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("qa-brain-routing-plan", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_qa_brain_routing_plan(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local QA brain routing-plan packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported qa-brain-routing-plan output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_qa_brain_routing_plan_report(
            project_root=Path.cwd(),
            output=cast(QaBrainRoutingPlanOutput, normalized_output),
        )
    except QaBrainRoutingPlanError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote QA brain routing plan: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("qa-brain-repair-plan", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_qa_brain_repair_plan(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
) -> None:
    """Write a local QA brain repair-plan packet."""

    normalized_output = output.strip().lower()
    if normalized_output not in {"md", "json"}:
        console.print(f"[yellow]Unsupported qa-brain-repair-plan output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        result = run_qa_brain_repair_plan_report(
            project_root=Path.cwd(),
            output=cast(QaBrainRepairPlanOutput, normalized_output),
        )
    except QaBrainRepairPlanError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote QA brain repair plan: {display_cli_path(result.output_path)}")
    raise typer.Exit(0)


@app.command("agent-bundle", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_agent_bundle(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: md or json."),
    ] = "md",
    role: Annotated[
        list[str] | None,
        typer.Option("--role", help="Agent role to include; repeatable."),
    ] = None,
    scope: Annotated[
        Path,
        typer.Option("--scope", help="Project-relative output path scope."),
    ] = Path("."),
) -> None:
    """Write a local multi-agent review bundle from sanitized manifests."""

    normalized_output = _agent_bundle_output(output)
    selected_roles = _agent_bundle_roles(role)

    try:
        result = run_agent_bundle_report(
            project_root=Path.cwd(),
            output=cast(AgentBundleOutput, normalized_output),
            roles=selected_roles,
            scope=scope,
        )
    except AgentBundleError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote agent review bundle: {display_cli_path(result.output_path)}")
    raise typer.Exit(0 if result.report.summary.status != "fail" else 1)


def _agent_bundle_output(output: str) -> AgentBundleOutput:
    normalized = output.strip().lower()
    if normalized not in {"md", "json"}:
        console.print(f"[yellow]Unsupported agent-bundle output: {output}[/yellow]")
        raise typer.Exit(2)
    return cast(AgentBundleOutput, normalized)


def _agent_bundle_roles(role: list[str] | None) -> tuple[str, ...]:
    selected = tuple(role or ())
    unsupported = sorted(name for name in selected if name not in AGENT_BUNDLE_ROLES)
    if unsupported:
        joined = ", ".join(unsupported)
        console.print(
            "[yellow]Unsupported agent-bundle role "
            f"{joined}; expected builder, breaker, or auditor.[/yellow]"
        )
        raise typer.Exit(2)
    return selected


@app.command("mutation-readiness-replay", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_mutation_readiness_replay(
    manifest: Annotated[
        Path,
        typer.Option("--manifest", help="Path to the mutation-readiness JSON manifest."),
    ] = Path("reports") / "mutation-readiness.json",
) -> None:
    """Validate a local mutation-readiness manifest for deterministic replay."""

    try:
        result = run_mutation_readiness_replay_validation(
            project_root=Path.cwd(),
            manifest_path=manifest,
        )
    except MutationReadinessReplayValidationError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    for warning in result.warnings:
        console.print(f"[yellow]warn: {warning}[/yellow]")
    if result.errors:
        for error in result.errors:
            console.print(f"[red]error: {error}[/red]")
        raise typer.Exit(1)

    console.print(
        f"mutation-readiness replay manifest valid: {display_cli_path(result.manifest_path)}"
    )
    raise typer.Exit(0)


@app.command("mutation-materialize", rich_help_panel=EXPERIMENTAL_REPORT_PANEL)
def report_mutation_materialize(
    manifest: Annotated[
        Path,
        typer.Option(..., "--manifest", help="Path to the reviewed mutation manifest."),
    ],
) -> None:
    """Materialize one reviewed status-code mutation as a local Hurl artifact."""

    try:
        output_path = materialize_mutation_candidate(
            project_root=Path.cwd(),
            manifest_path=manifest,
        )
    except MutationMaterializerError as exc:
        print_cli_error(exc)
        raise typer.Exit(1) from exc

    console.print(f"Wrote review-only mutation candidate: {display_cli_path(output_path)}")
    raise typer.Exit(0)
