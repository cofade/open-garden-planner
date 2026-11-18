"""What each bundled example plan is meant to be, written down a second time.

The generator (``scripts/example_plans/``) authors the plans; this table states, by hand
and independently of it, the facts a test holds each shipped plan to. Every rule that
applies to all examples is parametrised over ``SPECS``, and ``tests/unit/test_example_specs.py``
requires that the table, the shipped files and the generator name the same plans: a new
plan cannot ship without a row here, and a row cannot stand for a plan that is gone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time

#: The name of the stored orbit every example ships with, in English.
ORBIT = "Garden orbit"
#: The hint layer's name, by plan language.
HINTS = {"": "Hints", "de": "Hinweise", "es": "Indicaciones"}
#: The time zones an example may name. All share Central European Time: the app's clock
#: and a tour's time range read the computer's zone, and the plan's own zone is not read
#: (#945), so a garden in another zone would show shifted times on the owner's machine.
CENTRAL_EUROPEAN_ZONES = frozenset({"Europe/Berlin", "Europe/Madrid", "Europe/Vienna"})

#: Sun elevation above the horizon at the showcase moment, in degrees, and the half of the
#: sky the sun stands in (``None``: either). A plan never opens after sunset: the 2D canvas
#: would show its night overlay (FR-EXAMPLE-08).
LIGHT = {
    "day": (30.0, 90.0, None),
    "morning": (15.0, 45.0, "east"),
    "afternoon": (12.0, 45.0, "west"),
    "golden": (2.0, 12.0, "west"),
}


@dataclass(frozen=True)
class ExampleSpec:
    order: int                              # place in the gallery, 1 first
    reference: str                          # the showcase date
    light: str                              # a key of LIGHT
    place: tuple[float, float]              # latitude, longitude
    plants: int                             # items that are plants
    hint: bool = True                       # a hint text on its own layer
    harvests: tuple[int, int] = (3, 8)      # how many plants carry a harvest history
    woody_harvests: int = 0                 # ... of which trees and shrubs
    paths: bool = True                      # has at least one path
    more_tours: tuple[str, ...] = ()        # stored tours beside the orbit, in English
    north_angle_deg: float = 0.0
    heavy: bool = False                     # also runs the export and render gates

    @property
    def tours(self) -> tuple[str, ...]:
        return (ORBIT, *self.more_tours)

    @property
    def day(self) -> date:
        return date.fromisoformat(self.reference)


SPECS: dict[str, ExampleSpec] = {
    "family-garden": ExampleSpec(1, "2026-06-21", "day", (52.52, 13.405), plants=61, hint=False,
                                 woody_harvests=1, heavy=True),
    "food-forest": ExampleSpec(10, "2026-09-21", "day", (50.7374, 7.0982), plants=114,
                               woody_harvests=3, heavy=True),
    "raised-bed": ExampleSpec(12, "2026-09-21", "day", (52.52, 13.405), plants=174, heavy=True),
    "balcony": ExampleSpec(13, "2026-09-21", "day", (47.999, 7.8421), plants=14, paths=False,
                           heavy=True),
}

#: The first three plans: teaching plans with a dated tutorial note, pinned in detail by
#: ``tests/unit/test_example_content.py``.
TEACHING = ("raised-bed", "food-forest", "balcony")
#: The first four, in the order the gallery listed them before it had an order of its own.
FIRST_FOUR = ("balcony", "family-garden", "food-forest", "raised-bed")
#: The plans the costly export and render gates run on.
HEAVY = tuple(slug for slug, spec in SPECS.items() if spec.heavy)

#: A plant's common name that is the same word in English and in the plan's language.
COGNATES = {
    "de": frozenset({"Aster", "Magnolia", "Oregano", "Rhododendron", "Rose", "Zucchini"}),
    "es": frozenset({"Cosmos", "Magnolia", "Zinnia"}),
}


def showcase_utc(spec: ExampleSpec, utc_time: str) -> datetime:
    """The showcase moment as an instant: the sidecar's UTC time on the reference date."""
    return datetime.combine(spec.day, time.fromisoformat(utc_time), tzinfo=UTC)
