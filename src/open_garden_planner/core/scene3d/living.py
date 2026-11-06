"""Unified living garden buffer assembly (Phase 17 L5 follow-up, #689).

Assembles ambient life emitters (falling leaves, butterflies, fireflies) and
lamp sources/bulbs into the unified ambient particles buffer and the nearest
lamp point lights.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from open_garden_planner.core.phenology import PhenologyState

from .interleave import EngineBuffers
from .lights import LampSource, lamp_sources, nearest_lamps
from .particles import Emitter, ambient_buffers, ambient_emitters
from .record import Record


@dataclass(frozen=True, slots=True)
class LivingAssembly:
    """The assembled living garden ambient buffers, nearest lamps, and emitters (#689)."""

    buffers: EngineBuffers
    lamps: tuple[LampSource, ...]
    emitters: tuple[Emitter, ...]
    sources: tuple[LampSource, ...]
    bulbs: tuple[Emitter, ...] = ()

    def __iter__(self) -> Iterator[Any]:
        """Allow tuple unpacking: ``buffers, lamps = living_buffers(...)``."""
        yield self.buffers
        yield self.lamps


def living_buffers(
    records: Mapping[str, Record] | Iterable[Record],
    seasons: Mapping[str, PhenologyState],
    plan_date: date,
    latitude_deg: float,
    target: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> LivingAssembly:
    """Assemble ambient particle buffers and nearest lamps for the living garden.

    Qt-free. Used by WorkspaceLivingCoordinator, render_beauty_board, and
    integration test drivers to guarantee unified path execution (#689).
    """
    record_list = tuple(records.values()) if isinstance(records, Mapping) else tuple(records)
    emitters = ambient_emitters(record_list, seasons, plan_date, latitude_deg) if seasons else ()
    sources = lamp_sources(record_list)
    lamps = nearest_lamps(sources, target)
    bulbs = tuple(bulb for source in sources for bulb in source.bulbs())
    buffers = ambient_buffers((*emitters, *bulbs))
    return LivingAssembly(
        buffers=buffers, lamps=lamps, emitters=emitters, sources=sources, bulbs=bulbs
    )
