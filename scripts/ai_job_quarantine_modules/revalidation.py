from __future__ import annotations

from scripts import ai_jobs


def issue_number(value: object) -> str:
    issue = ai_jobs._issue_number(value, required=True)
    if issue is None:
        raise ai_jobs.AiJobError("job must name a numeric GitHub issue")
    return issue


def github_issue_snapshot(issue: str) -> dict[str, object]:
    return ai_jobs._github_issue_snapshot(issue)
