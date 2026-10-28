"""Regression tests for widget leak reclamation and popup parentage (#515, #561, AUD-019)."""

from __future__ import annotations

import gc

from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QApplication

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.ui.widgets.category_dropdown import CategoryDropdown
from open_garden_planner.ui.widgets.category_toolbar import CategoryToolbar


def _flush_events(app: QApplication) -> None:
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def test_category_dropdowns_are_parented_to_toolbar(qtbot) -> None:
    """CategoryDropdown popups must have their CategoryToolbar as parent (#515).

    When parent is None, Qt treats each popup as an independent top-level widget that
    survives window destruction and leaks 870 child widgets into app.allWidgets().
    """
    toolbar = CategoryToolbar()
    qtbot.addWidget(toolbar)
    assert len(toolbar._category_dropdowns) > 0
    for dropdown in toolbar._category_dropdowns:
        assert isinstance(dropdown, CategoryDropdown)
        assert dropdown.parent() is toolbar


def test_app_destruction_reclaims_all_child_widgets(qtbot) -> None:
    """Closing and deleting GardenPlannerApp must leave 0 orphaned widgets (#515, AUD-019)."""
    app = QApplication.instance()
    assert app is not None
    _flush_events(app)

    before_count = len(app.allWidgets())
    window = GardenPlannerApp()
    qtbot.addWidget(window)
    window.show()

    # Window was created and added to qtbot
    assert len(app.allWidgets()) > before_count

    window.close()
    window.deleteLater()
    window = None
    del window
    gc.collect()
    _flush_events(app)

    # All widgets created by the window must be completely deleted
    assert len(app.allWidgets()) == before_count

