from entroping.core._compat import install_core_module_compat
from entroping.core.plan import qa_brain_eval_plan as _implementation

install_core_module_compat(globals(), __name__, _implementation)
