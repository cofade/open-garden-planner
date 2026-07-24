"""Issue #277: the 3D view's Qt3D bindings load lazily (ADR-038). A frozen
build with a Qt micro-version mismatch fails that import with a DLL-load
ImportError. Opening the view must show a recoverable dialog and keep the app
alive — the pre-fix behaviour let the unhandled error abort the process and
silently discard unsaved plan changes.

Platform-independent: the import is forced to fail before any real Qt3D touch,
so no RHI/GL context is needed (runs on the offscreen CI runner).
"""

from __future__ import annotations

import sys


def test_open_3d_view_shows_dialog_instead_of_crashing(qtbot, monkeypatch) -> None:  # noqa: ARG001
    from open_garden_planner.app import application
    from open_garden_planner.app.application import GardenPlannerApp

    win = GardenPlannerApp()
    qtbot.addWidget(win)
    assert win._view3d_window is None

    # Force the lazy import to fail exactly the way #277 does: a None entry in
    # sys.modules makes ``from … import View3DWindow`` raise ImportError.
    monkeypatch.setitem(
        sys.modules, "open_garden_planner.ui.view3d.view3d_window", None
    )
    calls: list[tuple] = []
    monkeypatch.setattr(
        application.QMessageBox, "critical", lambda *a, **_k: calls.append(a)
    )

    # Must neither raise nor create a half-built window.
    win._on_open_3d_view()

    assert calls, "expected a recoverable error dialog on 3D import failure"
    assert win._view3d_window is None
