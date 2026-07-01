from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_BOARD_LIB = REPO_ROOT / "scripts" / "_project_board_lib.sh"
START_ISSUE_SCRIPT = REPO_ROOT / "scripts" / "start_issue.sh"
FINISH_ISSUE_SCRIPT = REPO_ROOT / "scripts" / "finish_issue.sh"

PROJECT_BOARD_FUNCTIONS = (
    "project_item_list_limit",
    "json_project_status_ids",
    "json_project_item_id",
    "retry_project_item_id",
    "project_graphql_quota_allows_update",
)


def _source_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_issue_scripts_source_shared_project_board_helpers() -> None:
    lib_text = _source_text(PROJECT_BOARD_LIB)
    start_text = _source_text(START_ISSUE_SCRIPT)
    finish_text = _source_text(FINISH_ISSUE_SCRIPT)

    assert 'source "$script_dir/_project_board_lib.sh"' in start_text
    assert 'source "$script_dir/_project_board_lib.sh"' in finish_text
    for function_name in PROJECT_BOARD_FUNCTIONS:
        assert f"{function_name}() {{" in lib_text
        assert f"{function_name}() {{" not in start_text
        assert f"{function_name}() {{" not in finish_text
