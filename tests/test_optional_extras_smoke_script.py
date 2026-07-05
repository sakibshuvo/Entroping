"""Direct coverage for the optional extras smoke helper."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "optional_extras_smoke.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("optional_extras_smoke_test", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _non_callable_completion_boundary() -> object:
    return object()


def test_optional_extras_smoke_success_suppresses_dependency_noise(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script_module()

    def noisy_completion() -> object:
        print("provider stdout")
        return lambda: None

    def noisy_runtime() -> SimpleNamespace:
        print("proxy stdout")
        return SimpleNamespace(
            options_factory=lambda: None,
            dump_master_factory=lambda: None,
        )

    def noisy_studio_check() -> None:
        print("studio stdout")

    def fake_import_module(name: str) -> object:
        print(f"textual import stdout: {name}")
        return object()

    monkeypatch.setattr(module, "_load_completion_func", noisy_completion)
    monkeypatch.setattr(module, "load_mitmproxy_runtime", noisy_runtime)
    monkeypatch.setattr(module, "ensure_studio_available", noisy_studio_check)
    monkeypatch.setattr(module.importlib, "import_module", fake_import_module)

    exit_code = module.main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == (
        "Optional extras runtime smoke OK: ai/litellm, proxy/mitmproxy, studio/textual\n"
    )
    assert captured.err == ""
    assert "provider stdout" not in captured.out
    assert "proxy stdout" not in captured.out
    assert "studio stdout" not in captured.out
    assert "textual import stdout" not in captured.out


def test_optional_extras_smoke_rejects_non_callable_completion(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script_module()

    monkeypatch.setattr(
        module,
        "_load_completion_func",
        _non_callable_completion_boundary,
    )

    exit_code = module.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == "LiteLLM completion boundary is not callable.\n"


def test_optional_extras_smoke_rejects_non_callable_proxy_factories(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script_module()

    monkeypatch.setattr(module, "_load_completion_func", lambda: (lambda: None))
    monkeypatch.setattr(
        module,
        "load_mitmproxy_runtime",
        lambda: SimpleNamespace(options_factory=object(), dump_master_factory=lambda: None),
    )

    exit_code = module.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == "mitmproxy runtime factories are not callable.\n"


def test_optional_extras_smoke_reports_dependency_exception_safely(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script_module()

    def fail_completion() -> object:
        raise RuntimeError("secret provider token should not be printed")

    monkeypatch.setattr(module, "_load_completion_func", fail_completion)

    exit_code = module.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == "Optional extras runtime smoke failed: RuntimeError\n"
    assert "secret provider token" not in captured.err
