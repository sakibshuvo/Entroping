import sys
from collections.abc import MutableMapping
from types import ModuleType


def install_core_module_compat(
    module_globals: MutableMapping[str, object],
    module_name: str,
    implementation: ModuleType,
) -> None:
    module_globals.update(implementation.__dict__)
    sys.modules[module_name] = implementation
