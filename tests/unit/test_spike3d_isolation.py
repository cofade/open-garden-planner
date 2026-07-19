"""US-E5 spike isolation (#260): dormant spike code must not tax startup.

The issue's one hard rule for merged spike code: \"it must not import at
app startup.\" main.py imports ``spike3d.qt3d_spike`` only inside the
``--spike-3d`` branch — these tests pin that.
"""

from __future__ import annotations

import sys


def test_spike_module_not_imported_by_main() -> None:
    for module in list(sys.modules):
        if module.startswith("open_garden_planner.spike3d"):
            del sys.modules[module]

    import open_garden_planner.main  # noqa: F401 — the import IS the test

    assert not any(
        name.startswith("open_garden_planner.spike3d") for name in sys.modules
    ), "spike3d must only load behind the --spike-3d flag"


def test_spike_module_has_no_qt3d_import_at_module_level() -> None:
    """Importing the spike module itself stays cheap — Qt3D binds inside
    run_spike(), so even a stray import of the module can't drag DLLs in."""
    before = {name for name in sys.modules if name.startswith("PyQt6.Qt3D")}

    import open_garden_planner.spike3d.qt3d_spike  # noqa: F401

    after = {name for name in sys.modules if name.startswith("PyQt6.Qt3D")}
    assert after == before
