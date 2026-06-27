"""Report command package."""

from entroping.cli.commands.report import _deps as _deps
from entroping.cli.commands.report import _experimental as _experimental
from entroping.cli.commands.report import _launch as _launch
from entroping.cli.commands.report import _maintainer as _maintainer
from entroping.cli.commands.report import _stable as _stable
from entroping.cli.commands.report._app import app

_DEPENDENCY_EXPORTS = frozenset(_deps.__all__) - {"report_dependency"}

__all__ = ["app", *sorted(_DEPENDENCY_EXPORTS)]


def __getattr__(name: str) -> object:
    """Resolve legacy report-package dependency attributes."""

    if name in _DEPENDENCY_EXPORTS:
        return getattr(_deps, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
