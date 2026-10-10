"""The engine boundary: ``EngineSink`` and its recording double (L1.1, ADR-054).

Everything the 3D pipeline tells a renderer goes through the nine methods of
``EngineSink``. L1.2 implements it with Qt Quick 3D (``ui/view3d/quick3d/``);
``RecordingSink`` implements it with a list and a dict, so builders and the
sync logic are tested with no GPU — and, on the NO-GO path of ADR-048, a Qt 3D
sink could be written against the same protocol.

Protocol rules (``RecordingSink`` raises ``SinkProtocolError`` on each breach):

- every call happens between ``begin()`` and ``commit()``; ``begin`` does not nest;
- ``add`` takes an id the sink does not hold; ``remove``, ``update_transform``,
  ``update_material`` and ``replace_geometry`` take one it does;
- ``parts`` is a sequence of ``MeshPart`` (possibly empty: an item without a
  solid is still an item — its transform and material stay addressable).

A sink poses a part with ``frame.engine_pose(transform)`` and maps its mesh with
``frame.scene_to_engine_points`` — once. A part with ``tinted=True`` is
multiplied with ``material.tint_linear()``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple, Protocol, runtime_checkable

from ..shadow_geometry import MIN_SUN_ELEVATION_DEG
from .legacy import sun_direction_scene
from .mesh import MeshPart
from .record import Material, Transform

if TYPE_CHECKING:
    from ..solar import SolarPosition


@dataclass(frozen=True, slots=True)
class SunState:
    """Where the sun is — plain solar data from ``core/solar``, nothing chosen.

    ``elevation_deg``: geometric elevation above the horizon. ``azimuth_deg``:
    compass bearing, clockwise from north. The light a sink sets up travels
    along ``light_travel_scene`` (ADR-037: light = −sun vector). L1.4 adds the
    look (colour, brightness, sky) on top; the direction is never art-directed.
    """

    elevation_deg: float
    azimuth_deg: float

    def __post_init__(self) -> None:
        if not (math.isfinite(self.elevation_deg) and math.isfinite(self.azimuth_deg)):
            raise ValueError(f"SunState needs finite angles, got {self!r}")

    @classmethod
    def from_solar_position(cls, position: SolarPosition) -> SunState:
        """From ``core.solar.solar_position(...)`` — the only source of sun angles."""
        return cls(position.elevation_deg, position.azimuth_deg)

    @property
    def direction_scene(self) -> tuple[float, float, float]:
        """Unit vector pointing AT the sun, scene frame (E, N, up)."""
        return sun_direction_scene(self.elevation_deg, self.azimuth_deg)

    @property
    def light_travel_scene(self) -> tuple[float, float, float]:
        """Unit vector the sunlight travels along (away from the sun), scene frame."""
        east, north, up = self.direction_scene
        return (-east, -north, -up)

    @property
    def is_up(self) -> bool:
        """False below the 2D overlay's night threshold (``MIN_SUN_ELEVATION_DEG``)."""
        return self.elevation_deg >= MIN_SUN_ELEVATION_DEG


@dataclass(frozen=True, slots=True)
class GroundSpec:
    """The plan's ground: the canvas rectangle from scene (0, 0) to
    (``width_cm`` east, ``depth_cm`` north).

    Deliberately minimal — L1.5 (ground bake) owns the final shape and adds the
    baked surface to it.
    """

    width_cm: float
    depth_cm: float

    def __post_init__(self) -> None:
        for name, value in (("width_cm", self.width_cm), ("depth_cm", self.depth_cm)):
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"GroundSpec.{name} must be a positive length, got {value!r}")


@runtime_checkable
class EngineSink(Protocol):
    """What a renderer must implement to show the plan (module docstring)."""

    def begin(self) -> None:
        """Open a transaction; every other call happens inside one."""

    def commit(self) -> None:
        """Close the transaction: the engine may now show the new state."""

    def add(self, item_id: str, parts: Sequence[MeshPart], transform: Transform,
            material: Material) -> None:
        """A new item: its mesh parts (possibly none), pose and material."""

    def remove(self, item_id: str) -> None:
        """Forget an item and release what it held."""

    def update_transform(self, item_id: str, transform: Transform) -> None:
        """Re-pose an item; its meshes are untouched."""

    def update_material(self, item_id: str, material: Material) -> None:
        """Re-colour an item's tinted parts; its meshes are untouched."""

    def replace_geometry(self, item_id: str, parts: Sequence[MeshPart]) -> None:
        """New mesh parts for an item; pose and material stay as they are."""

    def set_sun(self, sun: SunState) -> None:
        """The sun moved (or rose, or set)."""

    def set_ground(self, ground: GroundSpec) -> None:
        """The plan's ground changed."""


class SinkProtocolError(RuntimeError):
    """A call the ``EngineSink`` protocol forbids."""


class SinkCall(NamedTuple):
    """One recorded call: its name, the item it was about (or None), its other arguments."""

    op: str
    item_id: str | None
    args: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class SinkItem:
    """What the engine holds for one item."""

    parts: tuple[MeshPart, ...]
    transform: Transform
    material: Material


@dataclass(frozen=True, slots=True)
class SinkState:
    """What the engine would hold now — comparable: two sinks that were driven
    differently but hold the same scene have equal states (item order is not
    part of it: the depth buffer sorts solids)."""

    items: dict[str, SinkItem]
    sun: SunState | None
    ground: GroundSpec | None


def _checked(parts: Sequence[MeshPart]) -> tuple[MeshPart, ...]:
    result = tuple(parts)
    if not all(isinstance(part, MeshPart) for part in result):
        raise SinkProtocolError(f"parts must be MeshPart objects, got {result!r:.120}")
    return result


class RecordingSink:
    """An ``EngineSink`` that records every call and enforces the protocol.

    ``calls`` is the ordered log (``ops()`` for a compact view); ``state()`` /
    ``item()`` / ``item_ids()`` / ``sun`` / ``ground`` answer "what would the
    engine hold now?". A refused call raises and is NOT recorded.
    """

    def __init__(self) -> None:
        self.calls: list[SinkCall] = []
        self.transactions = 0
        self._items: dict[str, SinkItem] = {}
        self._sun: SunState | None = None
        self._ground: GroundSpec | None = None
        self._open = False

    # ── what the engine would hold ──────────────────────────────────────────

    @property
    def in_transaction(self) -> bool:
        return self._open

    @property
    def sun(self) -> SunState | None:
        return self._sun

    @property
    def ground(self) -> GroundSpec | None:
        return self._ground

    def item_ids(self) -> tuple[str, ...]:
        return tuple(self._items)

    def item(self, item_id: str) -> SinkItem:
        return self._items[item_id]

    def state(self) -> SinkState:
        return SinkState(dict(self._items), self._sun, self._ground)

    def ops(self) -> list[tuple[str, str | None]]:
        """The call log as ``(name, item_id)`` pairs."""
        return [(call.op, call.item_id) for call in self.calls]

    def clear_calls(self) -> None:
        """Forget the log, keep the state (tests look at one step at a time)."""
        self.calls.clear()

    def reset(self) -> None:
        """The engine was torn down: an empty scene, an empty log, no transaction."""
        self.calls.clear()
        self.transactions = 0
        self._items.clear()
        self._sun = None
        self._ground = None
        self._open = False

    # ── EngineSink ──────────────────────────────────────────────────────────

    def begin(self) -> None:
        if self._open:
            raise SinkProtocolError("begin(): a transaction is already open")
        self._open = True
        self.calls.append(SinkCall("begin", None, ()))

    def commit(self) -> None:
        self._require_open("commit")
        self._open = False
        self.transactions += 1
        self.calls.append(SinkCall("commit", None, ()))

    def add(self, item_id: str, parts: Sequence[MeshPart], transform: Transform,
            material: Material) -> None:
        self._require_open("add")
        if item_id in self._items:
            raise SinkProtocolError(f"add(): item {item_id!r} is already in the sink")
        checked = _checked(parts)
        self._items[item_id] = SinkItem(checked, transform, material)
        self.calls.append(SinkCall("add", item_id, (checked, transform, material)))

    def remove(self, item_id: str) -> None:
        self._require_known("remove", item_id)
        del self._items[item_id]
        self.calls.append(SinkCall("remove", item_id, ()))

    def update_transform(self, item_id: str, transform: Transform) -> None:
        held = self._require_known("update_transform", item_id)
        self._items[item_id] = SinkItem(held.parts, transform, held.material)
        self.calls.append(SinkCall("update_transform", item_id, (transform,)))

    def update_material(self, item_id: str, material: Material) -> None:
        held = self._require_known("update_material", item_id)
        self._items[item_id] = SinkItem(held.parts, held.transform, material)
        self.calls.append(SinkCall("update_material", item_id, (material,)))

    def replace_geometry(self, item_id: str, parts: Sequence[MeshPart]) -> None:
        held = self._require_known("replace_geometry", item_id)
        checked = _checked(parts)
        self._items[item_id] = SinkItem(checked, held.transform, held.material)
        self.calls.append(SinkCall("replace_geometry", item_id, (checked,)))

    def set_sun(self, sun: SunState) -> None:
        self._require_open("set_sun")
        self._sun = sun
        self.calls.append(SinkCall("set_sun", None, (sun,)))

    def set_ground(self, ground: GroundSpec) -> None:
        self._require_open("set_ground")
        self._ground = ground
        self.calls.append(SinkCall("set_ground", None, (ground,)))

    # ── protocol checks ─────────────────────────────────────────────────────

    def _require_open(self, op: str) -> None:
        if not self._open:
            raise SinkProtocolError(f"{op}() called outside begin()/commit()")

    def _require_known(self, op: str, item_id: str) -> SinkItem:
        self._require_open(op)
        held = self._items.get(item_id)
        if held is None:
            raise SinkProtocolError(f"{op}(): unknown item {item_id!r}")
        return held
