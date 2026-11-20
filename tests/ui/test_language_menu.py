"""UI tests for the Language submenu in the View menu.

One window for the whole file, deliberately. The submenu's structure does not
change between assertions, and a full ``GardenPlannerApp`` per assertion was
needless heap churn in one process: after the app grew one more menu action and
one more language, the tenth window in this file turned a latent Qt teardown
fault into an intermittent ``0xC0000374`` at pytest-qt's ``_process_events``
(PF-TST-41). The autouse widget reclaimer deletes top-level windows after every
test, so the window is built and asserted on inside the one test rather than
shared across test boundaries.
"""

from PyQt6.QtWidgets import QApplication

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.core.i18n import SUPPORTED_LANGUAGES


def _get_language_submenu(window: GardenPlannerApp):
    """Return the View > Language submenu, or None when it is missing."""
    view_menu = None
    for action in window.menuBar().actions():
        if action.text() == "&View":
            view_menu = action.menu()
            break
    if view_menu is None:
        return None
    for action in view_menu.actions():
        if action.menu() and "Language" in action.text().replace("&", ""):
            return action.menu()
    return None


def test_language_submenu_lists_every_supported_language(qtbot) -> None:
    """One checkable action per supported language, and exactly one is checked."""
    window = GardenPlannerApp()
    qtbot.addWidget(window)

    language_menu = _get_language_submenu(window)
    assert language_menu is not None, "Language submenu not found in View menu"

    actions = language_menu.actions()
    action_texts = [action.text() for action in actions]
    # The labels are the language's own name, in the order the product lists
    # them - not a second copy of the table.
    assert action_texts == list(SUPPORTED_LANGUAGES.values())
    assert all(action.isCheckable() for action in actions), (
        "Language actions must be checkable (radio-style)"
    )

    assert hasattr(window, "_language_actions")
    assert set(window._language_actions) == set(SUPPORTED_LANGUAGES)

    # The checked language is set by a deferred call (QTimer.singleShot(0, ...)).
    QApplication.processEvents()
    checked = [
        lang_code
        for lang_code, action in window._language_actions.items()
        if action.isChecked()
    ]
    assert len(checked) == 1, (
        f"Expected exactly 1 checked language, got {len(checked)}: {checked}"
    )
