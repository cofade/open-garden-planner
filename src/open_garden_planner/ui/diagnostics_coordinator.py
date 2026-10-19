"""One publisher for all cached diagnostics, regardless of producer."""

import contextlib
from typing import Any

from PyQt6.QtCore import QObject, QTimer

from open_garden_planner.core.project import ProjectManager
from open_garden_planner.services.diagnostics import diagnostics_from_records


class DiagnosticsCoordinator(QObject):
    def __init__(self, scene: Any, command_manager: Any, panel: Any, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.scene, self.panel = scene, panel
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.refresh)
        scene.changed.connect(self.schedule)
        scene.diagnostics_changed.connect(self.refresh)
        scene.document_replaced.connect(self.reset)
        command_manager.stack_changed.connect(self.schedule)
        self.schedule()

    def reset(self) -> None:
        self.timer.stop()
        self.panel.set_records([])

    def schedule(self, *_args: Any) -> None:
        with contextlib.suppress(RuntimeError):
            if not self.timer.isActive():
                self.timer.start(100)

    def refresh(self) -> None:
        with contextlib.suppress(RuntimeError):
            self.panel.set_records(diagnostics_from_records(ProjectManager.diagnostics_snapshot(self.scene)))
