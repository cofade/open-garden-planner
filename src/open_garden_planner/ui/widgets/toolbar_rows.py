"""Toolbar rows that wrap with the window (#796).

The main window's tools are three toolbars in one row (core tools, CAD
constraints, object categories with the search field). Their size hints add up
to about 1670 px, so below that width Qt squeezed the LAST toolbar: at
1280 x 720 three category buttons and the search field went into the overflow
popup. A search field inside a popup is not a search field, so the row wraps
instead: a toolbar that no longer fits starts a new row, and comes back up when
the window is wide enough again.
"""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import QEvent, QObject, QTimer
from PyQt6.QtWidgets import QMainWindow, QToolBar


def rows_for_width(widths: Sequence[int], available: int) -> list[bool]:
    """Which toolbars start a new row: greedy line wrap over their widths.

    ``widths`` are the toolbars' size hints in row order. The first toolbar
    never breaks; a toolbar wider than the window still gets a row of its own
    (Qt's overflow popup then takes what does not fit).
    """
    breaks: list[bool] = []
    used = 0
    for index, width in enumerate(widths):
        # A toolbar of no width (hidden) never starts a row.
        starts_row = index > 0 and width > 0 and used + width > available
        if starts_row:
            used = 0
        used += width
        breaks.append(starts_row)
    return breaks


class ToolbarRows(QObject):
    """Keeps a row of toolbars wrapped to the width of their main window.

    The window's resize and show events are watched, and every toolbar's own
    show and hide (a toolbar that is hidden takes no room and starts no row);
    the wrap itself runs on the next turn of the event loop, after the window
    has its new size.
    """

    def __init__(self, window: QMainWindow, toolbars: Sequence[QToolBar]) -> None:
        super().__init__(window)
        self._window = window
        self._toolbars: list[QToolBar] = []
        self._pending = False
        window.installEventFilter(self)
        for toolbar in toolbars:
            self.append(toolbar)

    def append(self, toolbar: QToolBar) -> None:
        """Add the next toolbar of the row (in the order the window holds them)."""
        self._toolbars.append(toolbar)
        toolbar.installEventFilter(self)
        self.fit()

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        if event is None or self._pending:
            return False
        kind = event.type()
        resized = obj is self._window and kind in (QEvent.Type.Resize, QEvent.Type.Show)
        toggled = obj in self._toolbars and kind in (
            QEvent.Type.ShowToParent, QEvent.Type.HideToParent)
        if resized or toggled:
            self._pending = True
            QTimer.singleShot(0, self.fit)
        return False

    def fit(self) -> None:
        """Insert or remove toolbar breaks so every toolbar is shown in full."""
        self._pending = False
        window = self._window
        widths = [
            0 if toolbar.isHidden() else toolbar.sizeHint().width()
            for toolbar in self._toolbars
        ]
        for toolbar, starts_row in zip(
            self._toolbars, rows_for_width(widths, window.width()), strict=True
        ):
            if starts_row == window.toolBarBreak(toolbar):
                continue
            if starts_row:
                window.insertToolBarBreak(toolbar)
            else:
                window.removeToolBarBreak(toolbar)
