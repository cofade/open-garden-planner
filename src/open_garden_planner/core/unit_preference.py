"""The process's display preference; never persisted in a plan."""
from __future__ import annotations

from open_garden_planner.core.sim_clock import Channel
from open_garden_planner.core.units import UnitSystem


class UnitPreference:
    def __init__(self) -> None:
        self._system = UnitSystem.METRIC
        self.changed: Channel[UnitSystem] = Channel()

    @property
    def system(self) -> UnitSystem:
        return self._system

    def set_system(self, system: UnitSystem) -> None:
        system = UnitSystem(system)
        if system != self._system:
            self._system = system
            self.changed.emit(system)


_preference = UnitPreference()


def get_unit_preference() -> UnitPreference:
    return _preference


def active_unit_system() -> UnitSystem:
    return _preference.system
