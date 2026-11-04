"""The before/after wipe coordinator for the 3D workspace (Phase 17 L2, issue #583)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import QWidget

from .wipe import BeforeAfterWipe
from .workspace_legend import _locale_date


class WorkspaceWipeCoordinator:
    """Manages showing and closing the BeforeAfterWipe page within the 3D pane."""

    def __init__(
        self,
        get_pane: Callable[[], Any],
        on_pane_showing: Callable[[], None],
    ) -> None:
        self._get_pane = get_pane
        self._on_pane_showing = on_pane_showing
        self._wipe: BeforeAfterWipe | None = None

    @property
    def wipe(self) -> BeforeAfterWipe | None:
        return self._wipe

    def build_wipe(self, body_container: QWidget) -> BeforeAfterWipe:
        """Create and embed the wipe widget into the pane body container."""
        wipe = BeforeAfterWipe(body_container)
        wipe.closed.connect(self.close_wipe)
        self._wipe = wipe
        return wipe

    def is_shown(self) -> bool:
        """Return True if the before/after wipe is currently visible in the pane."""
        pane = self._get_pane()
        if pane is None or self._wipe is None:
            return False
        return getattr(pane, "body", None) is not None and pane.body.currentWidget() is self._wipe

    def show_pair(self, before: Any, after: Any, from_day: Any, to_day: Any) -> None:
        """Display the before/after image pair in the pane."""
        pane = self._get_pane()
        if pane is None or self._wipe is None or getattr(pane, "engine_widget", None) is None:
            return

        before_str = QCoreApplication.translate("Workspace", "Before: {date}").format(
            date=_locale_date(from_day)
        )
        after_str = QCoreApplication.translate("Workspace", "After: {date}").format(
            date=_locale_date(to_day)
        )

        self._wipe.show_pair(before, after, before_str, after_str)
        pane.body.setCurrentWidget(self._wipe)
        self._wipe.setFocus(Qt.FocusReason.OtherFocusReason)
        self._on_pane_showing()

    def close_wipe(self) -> None:
        """Close the wipe and restore the 3D engine view."""
        pane = self._get_pane()
        if not self.is_shown() or pane is None:
            return
        if getattr(pane, "engine_widget", None) is not None:
            pane.body.setCurrentWidget(pane.engine_widget)
        elif getattr(pane, "message_page", None) is not None:
            pane.body.setCurrentWidget(pane.message_page)
        self._on_pane_showing()

