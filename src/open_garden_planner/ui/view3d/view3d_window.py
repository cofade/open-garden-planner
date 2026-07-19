"""The 3D View window (US-E6, #261) — a viewer, not an editor.

Hosts the Qt3D adapter's window container, offers a manual Refresh (the
MVP's stated live-sync choice: snapshot on open + on demand, FR-SUN-06),
and exposes ``set_sun``/``rebuild`` for the application's wiring. The sun
follows the US-E3 sim time control while the window is open.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction, QCloseEvent
from PyQt6.QtWidgets import QMainWindow, QToolBar, QWidget

from open_garden_planner.core.scene3d import Scene3DRecord

from .qt3d_adapter import Garden3DView


class View3DWindow(QMainWindow):
    """Top-level 3D viewer window."""

    refresh_requested = pyqtSignal()
    closed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("3D View"))
        self.resize(1024, 640)
        self._adapter = Garden3DView()
        self.setCentralWidget(self._adapter.container(self))

        toolbar = QToolBar(self.tr("3D View"), self)
        toolbar.setObjectName("View3DToolbar")
        toolbar.setMovable(False)
        refresh_action = QAction(self.tr("&Refresh"), self)
        refresh_action.setStatusTip(
            self.tr("Rebuild the 3D scene from the current plan")
        )
        refresh_action.triggered.connect(self.refresh_requested)
        toolbar.addAction(refresh_action)

        # Walkthrough (US-E7): orbit ⇄ walk camera-mode toggle.
        self._walk_action = QAction(self.tr("&Walk"), self)
        self._walk_action.setCheckable(True)
        self._walk_action.setStatusTip(
            self.tr(
                "Walk the garden at eye level — WASD/arrow keys move, hold "
                "the left mouse button to look around, Esc exits"
            )
        )
        self._walk_action.toggled.connect(self._on_walk_toggled)
        toolbar.addAction(self._walk_action)

        from PyQt6.QtWidgets import QLabel

        self._walk_hint = QLabel("", self)
        self._walk_hint.setStyleSheet("color: #666; font-style: italic;")
        self._walk_hint.setContentsMargins(12, 0, 0, 0)
        toolbar.addWidget(self._walk_hint)
        self.addToolBar(toolbar)

    @property
    def adapter(self) -> Garden3DView:
        return self._adapter

    def rebuild(
        self,
        records: list[Scene3DRecord],
        width_cm: float,
        height_cm: float,
    ) -> None:
        self._adapter.rebuild(records, width_cm, height_cm)

    def set_sun(self, elevation_deg: float, azimuth_deg: float) -> None:
        self._adapter.set_sun(elevation_deg, azimuth_deg)

    def _on_walk_toggled(self, checked: bool) -> None:
        self._adapter.set_camera_mode("walk" if checked else "orbit")
        self._walk_hint.setText(
            self.tr("WASD/arrows move · hold left mouse to look · Esc exits")
            if checked
            else ""
        )

    def keyPressEvent(self, event) -> None:  # noqa: N802 — Qt override
        from PyQt6.QtCore import Qt

        if (
            event.key() == Qt.Key.Key_Escape
            and self._adapter.camera_mode == "walk"
        ):
            self._walk_action.setChecked(False)
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.closed.emit()
        super().closeEvent(event)
