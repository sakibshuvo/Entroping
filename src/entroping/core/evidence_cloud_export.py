from entroping.core._compat import install_core_module_compat
from entroping.core.export import evidence_cloud_export as _implementation

install_core_module_compat(globals(), __name__, _implementation)
