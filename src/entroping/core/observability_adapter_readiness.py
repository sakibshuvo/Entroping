from entroping.core._compat import install_core_module_compat
from entroping.core.readiness import observability_adapter_readiness as _implementation

install_core_module_compat(globals(), __name__, _implementation)
