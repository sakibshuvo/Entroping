"""Strict GitHub payload projections used by the production delivery port."""

from __future__ import annotations

from typing import Literal

from scripts.factory_issue_selector_models import JsonObject, JsonValue
from scripts.factory_pr_delivery_github_io import (
    GitHubTransportError,
    body_digest,
    bool_field,
    int_field,
    list_field,
    require_object,
    string_field,
)
from scripts.factory_pr_delivery_github_models import (
    CheckObservation,
    IssueObservation,
    PullRequestObservation,
    RequiredCheck,
)


def parse_issue(repo: str, payload: JsonObject) -> IssueObservation:
    labels = tuple(sorted(label_name(item) for item in list_field(payload, "labels")))
    state_value = _issue_state(string_field(payload, "state").lower())
    return IssueObservation(
        repo=repo,
        number=int_field(payload, "number"),
        state=state_value,
        title=string_field(payload, "title", max_bytes=4096),
        labels=labels,
        body_sha256=body_digest(payload.get("body", "")),
        is_pull_request="pull_request" in payload,
    )


def parse_pull_request(repo: str, payload: JsonValue) -> PullRequestObservation:
    item = require_object(payload)
    files = tuple(sorted(file_path(entry) for entry in list_field(item, "files")))
    issues = tuple(
        sorted(issue_number(entry) for entry in list_field(item, "closingIssuesReferences"))
    )
    merge = item.get("mergeCommit")
    merged_head = (
        None if merge is None else string_field(require_object(merge), "oid", max_bytes=40)
    )
    state_value = _pr_state(string_field(item, "state").lower())
    mergeable = _mergeable(string_field(item, "mergeable"))
    merge_status = _merge_status(string_field(item, "mergeStateStatus"))
    return PullRequestObservation(
        repo=repo,
        number=int_field(item, "number"),
        title=string_field(item, "title", max_bytes=4096),
        body_sha256=body_digest(item.get("body", "")),
        state=state_value,
        draft=bool_field(item, "isDraft"),
        head_branch=string_field(item, "headRefName"),
        head_sha=string_field(item, "headRefOid", max_bytes=40),
        base_ref=string_field(item, "baseRefName"),
        base_sha=string_field(item, "baseRefOid", max_bytes=40),
        mergeable=mergeable,
        merge_state_status=merge_status,
        changed_files=files,
        closing_issue_numbers=issues,
        merged_head=merged_head,
    )


def parse_check(payload: JsonObject, requested_head: str) -> CheckObservation:
    app = payload.get("app")
    app_id = None if app is None else int_field(require_object(app), "id")
    status = string_field(payload, "status").lower()
    conclusion = payload.get("conclusion")
    if status != "completed":
        state: Literal[
            "pending",
            "success",
            "failure",
            "cancelled",
            "timed-out",
            "stale",
            "superseded",
            "neutral",
            "skipped",
            "unknown",
        ] = "pending"
    elif conclusion == "success":
        state = "success"
    elif conclusion == "cancelled":
        state = "cancelled"
    elif conclusion == "timed_out":
        state = "timed-out"
    elif conclusion == "stale":
        state = "stale"
    elif conclusion == "superseded":
        state = "superseded"
    elif conclusion == "neutral":
        state = "neutral"
    elif conclusion == "skipped":
        state = "skipped"
    elif conclusion is None:
        state = "unknown"
    else:
        state = "failure"
    head_sha = string_field(payload, "head_sha", max_bytes=40)
    if head_sha != requested_head:
        raise GitHubTransportError("stale-check")
    return CheckObservation(
        context=string_field(payload, "name"),
        app_id=app_id,
        status=state,
        head_sha=head_sha,
    )


def parse_branch_checks(payload: JsonObject) -> list[RequiredCheck]:
    required = payload.get("required_status_checks")
    if not isinstance(required, dict):
        return []
    contexts = required.get("contexts")
    if not isinstance(contexts, list):
        raise GitHubTransportError("protection-incomplete")
    if any(not isinstance(item, str) for item in contexts):
        raise GitHubTransportError("protection-incomplete")
    result: list[RequiredCheck] = []
    for item in contexts:
        if not isinstance(item, str):
            raise GitHubTransportError("protection-incomplete")
        result.append(RequiredCheck(context=item))
    return result


def parse_ruleset_checks(value: JsonValue | list[JsonObject]) -> list[RequiredCheck]:
    if not isinstance(value, list) or len(value) >= 100:
        raise GitHubTransportError("protection-incomplete")
    checks: list[RequiredCheck] = []
    for item in value:
        ruleset = require_object(item)
        rules = ruleset.get("rules")
        if rules is None:
            raise GitHubTransportError("protection-incomplete")
        if not isinstance(rules, list):
            raise GitHubTransportError("protection-incomplete")
        for rule in rules:
            entry = require_object(rule)
            kind = string_field(entry, "type")
            if kind in {
                "creation",
                "update",
                "deletion",
                "required_linear_history",
                "merge_queue",
                "required_deployments",
                "required_signatures",
                "pull_request",
                "non_fast_forward",
                "code_scanning",
                "copilot_code_review",
                "workflows",
            }:
                continue
            if kind != "required_status_checks":
                raise GitHubTransportError("protection-rule-unsupported")
            parameters = require_object(entry.get("parameters"))
            contexts = list_field(parameters, "required_status_checks")
            for context in contexts:
                if isinstance(context, str):
                    checks.append(RequiredCheck(context=context))
                    continue
                obj = require_object(context)
                checks.append(
                    RequiredCheck(
                        context=string_field(obj, "context"),
                        app_id=int_field(obj, "integration_id"),
                    )
                )
    return checks


def label_name(value: JsonValue) -> str:
    return string_field(require_object(value), "name")


def file_path(value: JsonValue) -> str:
    return string_field(require_object(value), "path")


def issue_number(value: JsonValue) -> int:
    return int_field(require_object(value), "number")


def _issue_state(value: str) -> Literal["open", "closed"]:
    if value == "open":
        return "open"
    if value == "closed":
        return "closed"
    raise GitHubTransportError("github-response-invalid")


def _pr_state(value: str) -> Literal["open", "closed", "merged"]:
    if value == "open":
        return "open"
    if value == "closed":
        return "closed"
    if value == "merged":
        return "merged"
    raise GitHubTransportError("github-response-invalid")


def _mergeable(value: str) -> Literal["MERGEABLE", "CONFLICTING", "UNKNOWN"]:
    if value == "MERGEABLE":
        return "MERGEABLE"
    if value == "CONFLICTING":
        return "CONFLICTING"
    if value == "UNKNOWN":
        return "UNKNOWN"
    raise GitHubTransportError("github-response-invalid")


def _merge_status(value: str) -> Literal[
    "CLEAN", "BLOCKED", "UNSTABLE", "DIRTY", "BEHIND", "UNKNOWN"
]:
    if value == "CLEAN":
        return "CLEAN"
    if value == "BLOCKED":
        return "BLOCKED"
    if value == "UNSTABLE":
        return "UNSTABLE"
    if value == "DIRTY":
        return "DIRTY"
    if value == "BEHIND":
        return "BEHIND"
    if value == "UNKNOWN":
        return "UNKNOWN"
    raise GitHubTransportError("github-response-invalid")
