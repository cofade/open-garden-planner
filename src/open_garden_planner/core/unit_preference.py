"""The process's display preference; never persisted in a plan.

One profile carries the unit system of each quantity a surface displays
(#673, #907): length, area, volume, temperature, precipitation and harvest
mass are independently configurable. A preset is a named profile; Canada
(mixed) deliberately mixes imperial length/area with metric weather and mass,
and Custom may mix any rows.

Qt-free and plan-free: this is a preference of the running process, not of a
garden file (ADR-078).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from open_garden_planner.core.sim_clock import Channel
from open_garden_planner.core.units import UnitSystem


class Quantity(StrEnum):
    """The quantities whose display unit is chosen independently (#907)."""

    LENGTH = "length"
    AREA = "area"
    VOLUME = "volume"
    TEMPERATURE = "temperature"
    PRECIPITATION = "precipitation"
    MASS = "mass"


class UnitPreset(StrEnum):
    """A named set of per-quantity systems."""

    METRIC = "metric"
    IMPERIAL = "imperial"
    CANADA_MIXED = "canada_mixed"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class UnitProfile:
    """The display system of every quantity, in one immutable value."""

    length: UnitSystem = UnitSystem.METRIC
    area: UnitSystem = UnitSystem.METRIC
    volume: UnitSystem = UnitSystem.METRIC
    temperature: UnitSystem = UnitSystem.METRIC
    precipitation: UnitSystem = UnitSystem.METRIC
    mass: UnitSystem = UnitSystem.METRIC

    @classmethod
    def all(cls, system: UnitSystem) -> UnitProfile:
        """One system for every quantity - the pre-#907 single choice."""
        system = UnitSystem(system)
        return cls(
            length=system,
            area=system,
            volume=system,
            temperature=system,
            precipitation=system,
            mass=system,
        )

    @classmethod
    def for_preset(cls, preset: UnitPreset | str) -> UnitProfile:
        """The profile of a named preset.

        ``CUSTOM`` falls back to all-metric; any other unrecognized name raises
        ``ValueError``. A profile that happens to be all-metric reports
        ``METRIC`` through :attr:`preset`, so ``CUSTOM`` is a storage label
        rather than a distinct system set.
        """
        preset = UnitPreset(preset)
        if preset == UnitPreset.IMPERIAL:
            return cls.all(UnitSystem.IMPERIAL)
        if preset == UnitPreset.CANADA_MIXED:
            # Provisional until Canadian gardeners' feedback settles it (#907):
            # lengths in feet/inches (the building and bed convention), weather
            # and harvest in the metric units Canada reports them in.
            return cls(
                length=UnitSystem.IMPERIAL,
                area=UnitSystem.IMPERIAL,
                volume=UnitSystem.METRIC,
                temperature=UnitSystem.METRIC,
                precipitation=UnitSystem.METRIC,
                mass=UnitSystem.METRIC,
            )
        return cls.all(UnitSystem.METRIC)

    @property
    def preset(self) -> UnitPreset:
        """The preset this profile is, or ``CUSTOM`` when it is none of them."""
        for preset in (UnitPreset.METRIC, UnitPreset.IMPERIAL, UnitPreset.CANADA_MIXED):
            if self == type(self).for_preset(preset):
                return preset
        return UnitPreset.CUSTOM

    def system_for(self, quantity: Quantity | str) -> UnitSystem:
        return UnitSystem(getattr(self, Quantity(quantity).value))

    def with_system(self, quantity: Quantity | str, system: UnitSystem) -> UnitProfile:
        return replace(self, **{Quantity(quantity).value: UnitSystem(system)})


class UnitPreference:
    def __init__(self) -> None:
        self._profile = UnitProfile()
        #: The length system, for every pre-#907 surface that has one choice.
        self.changed: Channel[UnitSystem] = Channel()
        #: The whole profile, for surfaces whose quantity is not length.
        self.profile_changed: Channel[UnitProfile] = Channel()

    @property
    def system(self) -> UnitSystem:
        """The length system (the legacy single-choice view)."""
        return self._profile.length

    @property
    def profile(self) -> UnitProfile:
        return self._profile

    def set_system(self, system: UnitSystem) -> None:
        """Set every quantity to one system (the pre-#907 API)."""
        self.set_profile(UnitProfile.all(UnitSystem(system)))

    def set_profile(self, profile: UnitProfile) -> None:
        """Replace the profile, notifying once per changed channel.

        ``changed`` fires for a length change only - it is the pre-#907 signal
        and a second emission would replay every length widget for nothing.
        ``profile_changed`` always fires when any quantity moved.
        """
        new = UnitProfile(
            length=UnitSystem(profile.length),
            area=UnitSystem(profile.area),
            volume=UnitSystem(profile.volume),
            temperature=UnitSystem(profile.temperature),
            precipitation=UnitSystem(profile.precipitation),
            mass=UnitSystem(profile.mass),
        )
        if new == self._profile:
            return
        length_changed = new.length != self._profile.length
        self._profile = new
        if length_changed:
            self.changed.emit(new.length)
        self.profile_changed.emit(new)

    def set_quantity_system(self, quantity: Quantity | str, system: UnitSystem) -> None:
        self.set_profile(self._profile.with_system(quantity, system))


_preference = UnitPreference()


def get_unit_preference() -> UnitPreference:
    return _preference


def active_unit_system(quantity: Quantity | str = Quantity.LENGTH) -> UnitSystem:
    """The active system of one quantity (length by default, the legacy API)."""
    return _preference.profile.system_for(quantity)
