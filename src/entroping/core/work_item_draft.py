from entroping.core._compat import install_core_module_compat
from entroping.core.export import work_item_draft as _implementation

install_core_module_compat(globals(), __name__, _implementation)
