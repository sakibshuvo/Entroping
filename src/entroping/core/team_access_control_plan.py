from entroping.core._compat import install_core_module_compat
from entroping.core.plan import team_access_control_plan as _implementation

install_core_module_compat(globals(), __name__, _implementation)
