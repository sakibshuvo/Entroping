#!/usr/bin/env python3
"""Smoke optional Entroping runtime extras without credentials or live capture."""

from __future__ import annotations

import importlib
import io
import sys
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout

from entroping.brain.litellm_client import _load_completion_func
from entroping.core.traffic_proxy import load_mitmproxy_runtime
from entroping.studio.status import ensure_studio_available


def _without_optional_library_output[ResultT](callback: Callable[[], ResultT]) -> ResultT:
    """Run optional dependency boot checks without leaking provider library output."""

    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return callback()


def main() -> int:
    """Verify optional AI, proxy, and Studio dependencies are importable."""

    try:
        completion_func = _without_optional_library_output(_load_completion_func)
        if not callable(completion_func):
            print("LiteLLM completion boundary is not callable.", file=sys.stderr)
            return 1

        runtime = _without_optional_library_output(load_mitmproxy_runtime)
        if not callable(runtime.options_factory) or not callable(runtime.dump_master_factory):
            print("mitmproxy runtime factories are not callable.", file=sys.stderr)
            return 1

        _without_optional_library_output(ensure_studio_available)
        _without_optional_library_output(lambda: importlib.import_module("textual.app"))
        _without_optional_library_output(lambda: importlib.import_module("textual.widgets"))
    except Exception as exc:  # noqa: BLE001
        print(f"Optional extras runtime smoke failed: {type(exc).__name__}", file=sys.stderr)
        return 1

    print("Optional extras runtime smoke OK: ai/litellm, proxy/mitmproxy, studio/textual")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
