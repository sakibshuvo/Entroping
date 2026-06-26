import importlib
import os
from pathlib import Path

import pytest

_AFFECTED_OUTPUT_HELPERS = (
    ("entroping.core.evidence_action_plan", "EvidenceActionPlanError"),
    ("entroping.core.evidence_cloud_dashboard", "EvidenceCloudDashboardError"),
    ("entroping.core.evidence_cloud_export", "EvidenceCloudExportError"),
    ("entroping.core.evidence_cloud_workspace", "EvidenceCloudWorkspaceError"),
    ("entroping.core.evidence_links", "EvidenceLinksError"),
    ("entroping.core.evidence_portal", "EvidencePortalError"),
    ("entroping.core.pilot_outcome", "PilotOutcomeError"),
    ("entroping.core.pr_evidence_card", "PrEvidenceCardError"),
    ("entroping.core.work_item_draft", "WorkItemDraftError"),
    ("entroping.core.work_item_import_bundle", "WorkItemImportBundleError"),
)


@pytest.mark.parametrize(("module_name", "error_name"), _AFFECTED_OUTPUT_HELPERS)
def test_report_output_helpers_reject_symlinked_parent_components(
    tmp_path: Path,
    module_name: str,
    error_name: str,
) -> None:
    root = tmp_path.resolve()
    real_dir = root / "real"
    real_dir.mkdir()
    os.symlink(real_dir, root / "link")

    module = importlib.import_module(module_name)
    error_type = getattr(module, error_name)

    with pytest.raises(error_type, match="symlinked component"):
        module._resolve_output_path(Path("link") / "packet.json", root=root)


@pytest.mark.parametrize(("module_name", "error_name"), _AFFECTED_OUTPUT_HELPERS)
def test_report_output_helpers_reject_symlinked_output_files(
    tmp_path: Path,
    module_name: str,
    error_name: str,
) -> None:
    root = tmp_path.resolve()
    reports = root / "reports"
    reports.mkdir()
    real_output = reports / "real.json"
    real_output.write_text("{}\n", encoding="utf-8")
    os.symlink(real_output, reports / "packet.json")

    module = importlib.import_module(module_name)
    error_type = getattr(module, error_name)

    with pytest.raises(error_type, match="symlinked component|symlinked .*output"):
        module._resolve_output_path(Path("reports") / "packet.json", root=root)


@pytest.mark.parametrize(("module_name", "error_name"), _AFFECTED_OUTPUT_HELPERS)
@pytest.mark.parametrize("forbidden_component", (".entroping", "envs"))
def test_report_output_helpers_reject_nested_local_state_components(
    tmp_path: Path,
    module_name: str,
    error_name: str,
    forbidden_component: str,
) -> None:
    module = importlib.import_module(module_name)
    error_type = getattr(module, error_name)

    with pytest.raises(error_type, match="must not be written"):
        module._resolve_output_path(
            Path("reports") / forbidden_component / "packet.json",
            root=tmp_path.resolve(),
        )
