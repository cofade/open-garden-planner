"""Qt lifetime-safe adapter for the process unit preference."""

from __future__ import annotations

from PyQt6 import sip
from PyQt6.QtCore import QObject, pyqtSignal

from open_garden_planner.core.unit_preference import UnitProfile, get_unit_preference
from open_garden_planner.core.units import UnitSystem


class UnitsNotifier(QObject):
    #: The length system, for the pre-#907 single-choice surfaces.
    changed = pyqtSignal(object)
    #: The whole profile, for a surface whose quantity is not length (#907).
    profile_changed = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        preference = get_unit_preference()
        preference.changed.connect(self._forward)
        preference.profile_changed.connect(self._forward_profile)

    def _forward(self, system: UnitSystem) -> None:
        if not sip.isdeleted(self):
            self.changed.emit(system)

    def _forward_profile(self, profile: UnitProfile) -> None:
        if not sip.isdeleted(self):
            self.profile_changed.emit(profile)


_notifier: UnitsNotifier | None = None


def units_notifier() -> UnitsNotifier:
    global _notifier
    if _notifier is None or sip.isdeleted(_notifier):
        _notifier = UnitsNotifier()
    return _notifier
