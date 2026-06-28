from entroping.core._compat import install_core_module_compat
from entroping.core.evidence import connector_intent as _implementation

install_core_module_compat(globals(), __name__, _implementation)
