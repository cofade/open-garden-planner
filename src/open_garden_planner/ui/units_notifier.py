"""Qt lifetime-safe adapter for the process unit preference."""
from __future__ import annotations

from PyQt6 import sip
from PyQt6.QtCore import QObject, pyqtSignal

from open_garden_planner.core.unit_preference import get_unit_preference
from open_garden_planner.core.units import UnitSystem


class UnitsNotifier(QObject):
    changed = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        get_unit_preference().changed.connect(self._forward)

    def _forward(self, system: UnitSystem) -> None:
        if not sip.isdeleted(self):
            self.changed.emit(system)


_notifier: UnitsNotifier | None = None


def units_notifier() -> UnitsNotifier:
    global _notifier
    if _notifier is None or sip.isdeleted(_notifier):
        _notifier = UnitsNotifier()
    return _notifier
