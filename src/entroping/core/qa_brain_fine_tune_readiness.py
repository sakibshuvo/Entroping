from entroping.core._compat import install_core_module_compat
from entroping.core.plan import qa_brain_fine_tune_readiness as _implementation

install_core_module_compat(globals(), __name__, _implementation)
