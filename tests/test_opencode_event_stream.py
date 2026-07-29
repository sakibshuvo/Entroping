from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.opencode_event_stream import OpenCodeEventStream  # noqa: E402


def _event(event_type: str, **payload: object) -> bytes:
    return (json.dumps({"type": event_type, **payload}) + "\n").encode()


def _usage_event(
    *,
    part_id: str = "step-1",
    message_id: str = "message-1",
    session_id: str = "session-1",
    cost: object = 0.0125,
    input_tokens: object = 100,
    output_tokens: object = 20,
    reasoning_tokens: object = 5,
    cache_read_tokens: object = 7,
    cache_write_tokens: object = 3,
) -> bytes:
    return _event(
        "step_finish",
        sessionID=session_id,
        part={
            "id": part_id,
            "messageID": message_id,
            "sessionID": session_id,
            "cost": cost,
            "tokens": {
                "input": input_tokens,
                "output": output_tokens,
                "reasoning": reasoning_tokens,
                "cache": {
                    "read": cache_read_tokens,
                    "write": cache_write_tokens,
                },
            },
        },
    )


def test_fragmented_jsonl_collects_text_and_late_usage() -> None:
    stream = OpenCodeEventStream()
    payload = b"".join(
        (
            _event(
                "text",
                sessionID="session-1",
                part={"text": "Review complete."},
            ),
            _usage_event(),
        )
    )

    for offset in range(0, len(payload), 7):
        stream.feed(payload[offset : offset + 7])
    summary = stream.finish()

    assert summary.output_text == "Review complete."
    assert summary.accounting_status == "accounted"
    assert summary.accounting_reason == "complete"
    assert summary.session_fingerprint is not None
    assert "session-1" not in summary.session_fingerprint
    assert summary.usage is not None
    assert summary.usage.to_payload() == {
        "cache_read_tokens": 7,
        "cache_write_tokens": 3,
        "cost_usd": 0.0125,
        "input_tokens": 100,
        "output_tokens": 20,
        "reasoning_tokens": 5,
    }


def test_duplicate_step_finish_is_counted_once() -> None:
    stream = OpenCodeEventStream()
    usage = _usage_event()
    stream.feed(usage + usage)

    summary = stream.finish()

    assert summary.accounting_status == "accounted"
    assert summary.usage is not None
    assert summary.usage.input_tokens == 100
    assert summary.usage.cost_usd == 0.0125


def test_reused_step_id_with_different_message_is_unaccounted() -> None:
    stream = OpenCodeEventStream()
    stream.feed(_usage_event() + _usage_event(message_id="message-2"))

    summary = stream.finish()

    assert summary.accounting_status == "unaccounted"
    assert summary.accounting_reason == "conflicting_duplicate_usage"
    assert summary.usage is None


def test_unique_steps_sum_and_utf8_can_split_at_every_byte() -> None:
    stream = OpenCodeEventStream()
    payload = (
        _event("text", sessionID="session-1", part={"text": "café"})
        + _usage_event()
        + _usage_event(
            part_id="step-2",
            message_id="message-2",
            cost=0.25,
            input_tokens=2,
            output_tokens=3,
            reasoning_tokens=4,
            cache_read_tokens=5,
            cache_write_tokens=6,
        )
    )

    for byte in payload:
        stream.feed(bytes((byte,)))
    summary = stream.finish()

    assert summary.output_text == "café"
    assert summary.accounting_status == "accounted"
    assert summary.unique_step_count == 2
    assert summary.usage is not None
    assert summary.usage.to_payload() == {
        "cache_read_tokens": 12,
        "cache_write_tokens": 9,
        "cost_usd": 0.2625,
        "input_tokens": 102,
        "output_tokens": 23,
        "reasoning_tokens": 9,
    }


def test_conflicting_duplicate_step_finish_is_unaccounted() -> None:
    stream = OpenCodeEventStream()
    stream.feed(_usage_event() + _usage_event(cost=0.25))

    summary = stream.finish()

    assert summary.accounting_status == "unaccounted"
    assert summary.accounting_reason == "conflicting_duplicate_usage"
    assert summary.usage is None


def test_absent_cost_is_unaccounted_without_fabricating_zero() -> None:
    event = json.loads(_usage_event())
    cast(dict[str, object], event["part"]).pop("cost")
    stream = OpenCodeEventStream()
    stream.feed((json.dumps(event) + "\n").encode())

    summary = stream.finish()

    assert summary.accounting_status == "unaccounted"
    assert summary.accounting_reason == "missing_cost"
    assert summary.usage is None


def test_absent_usage_and_zero_cost_are_distinct_unaccounted_states() -> None:
    absent = OpenCodeEventStream()
    absent.feed(_event("text", sessionID="session-1", part={"text": "review"}))
    zero = OpenCodeEventStream()
    zero.feed(_usage_event(cost=0))

    absent_summary = absent.finish()
    zero_summary = zero.finish()

    assert absent_summary.accounting_reason == "usage_absent"
    assert zero_summary.accounting_reason == "ambiguous_zero_cost"
    assert absent_summary.usage is None
    assert zero_summary.usage is None


def test_positive_cost_that_underflows_float_is_unaccounted() -> None:
    stream = OpenCodeEventStream()
    stream.feed(
        b'{"type":"step_finish","sessionID":"session-1","part":'
        b'{"id":"step-1","messageID":"message-1","sessionID":"session-1",'
        b'"cost":1e-10000,"tokens":{"input":1,"output":1,"reasoning":0,'
        b'"cache":{"read":0,"write":0}}}}\n'
    )

    summary = stream.finish()

    assert summary.accounting_status == "unaccounted"
    assert summary.accounting_reason == "ambiguous_zero_cost"
    assert summary.usage is None


def test_malformed_middle_record_invalidates_later_complete_usage() -> None:
    stream = OpenCodeEventStream()
    stream.feed(
        _event("text", sessionID="session-1", part={"text": "review"})
        + b'{"type":"tool_use","secret":"do-not-retain"\n'
        + _usage_event()
    )

    summary = stream.finish()

    assert summary.output_text == "review"
    assert summary.accounting_status == "unaccounted"
    assert summary.accounting_reason == "malformed_event"
    assert "do-not-retain" not in json.dumps(summary.to_sanitized_payload())


def test_aggregate_usage_overflow_is_unaccounted() -> None:
    stream = OpenCodeEventStream()
    stream.feed(
        _usage_event(input_tokens=9_223_372_036_854_775_807)
        + _usage_event(
            part_id="step-2",
            message_id="message-2",
            input_tokens=1,
        )
    )

    summary = stream.finish()

    assert summary.accounting_status == "unaccounted"
    assert summary.accounting_reason == "malformed_usage"
    assert summary.usage is None


def test_malformed_event_reason_does_not_echo_event_content() -> None:
    secret = "api_key=abcdefghijklmnopqrstuvwxyz123456"
    stream = OpenCodeEventStream()
    stream.feed(f'{{"type":"text","part":{{"text":"{secret}"}}\n'.encode())

    summary = stream.finish()
    rendered = json.dumps(summary.to_sanitized_payload(), sort_keys=True)

    assert summary.accounting_status == "unaccounted"
    assert summary.accounting_reason == "malformed_event"
    assert secret not in rendered


def test_tool_payload_is_never_retained_in_sanitized_summary() -> None:
    secret = "sk-test-super-secret-provider-value"
    stream = OpenCodeEventStream()
    stream.feed(
        _event(
            "tool_use",
            sessionID="session-1",
            part={"tool": "bash", "state": {"input": {"token": secret}}},
        )
        + _usage_event()
    )

    summary = stream.finish()
    rendered = json.dumps(summary.to_sanitized_payload(), sort_keys=True)

    assert summary.accounting_status == "accounted"
    assert secret not in rendered
    assert "tool" not in rendered


def test_inconsistent_session_identity_is_unaccounted() -> None:
    stream = OpenCodeEventStream()
    stream.feed(
        _event("text", sessionID="session-1", part={"text": "review"})
        + _usage_event(session_id="session-2")
    )

    summary = stream.finish()

    assert summary.accounting_status == "unaccounted"
    assert summary.accounting_reason == "inconsistent_session"
    assert summary.session_fingerprint is None


def test_nonfinite_or_non_integer_usage_is_unaccounted() -> None:
    for usage in (
        b'{"type":"step_finish","sessionID":"s","part":{"id":"p","cost":NaN,'
        b'"tokens":{"input":1,"output":1,"reasoning":0,"cache":{"read":0,"write":0}}}}\n',
        _usage_event(input_tokens=1.5),
        _usage_event(output_tokens=-1),
    ):
        stream = OpenCodeEventStream()
        stream.feed(usage)

        summary = stream.finish()

        assert summary.accounting_status == "unaccounted"
        assert summary.accounting_reason in {"malformed_event", "malformed_usage"}
        assert summary.usage is None


def test_error_event_fails_accounting_without_retaining_provider_payload() -> None:
    stream = OpenCodeEventStream()
    stream.feed(
        _event(
            "error",
            sessionID="session-1",
            error={"message": "provider token abcdefghijklmnopqrstuvwxyz123456"},
        )
        + _usage_event()
    )

    summary = stream.finish()

    assert summary.saw_error_event is True
    assert summary.accounting_status == "unaccounted"
    assert summary.accounting_reason == "error_event"
    assert "provider token" not in json.dumps(summary.to_sanitized_payload())
