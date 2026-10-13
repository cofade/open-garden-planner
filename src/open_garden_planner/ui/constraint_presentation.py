"""Canonical constraint-row presentation; geometry stays in the solver (#457)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from PyQt6.QtCore import QT_TR_NOOP, QCoreApplication

from open_garden_planner.core.constraints import ConstraintType

_PAIR = QT_TR_NOOP("{a} – {b}   {detail}")
_SINGLE = QT_TR_NOOP("{a}   {detail}")
_TRIPLE = QT_TR_NOOP("{a} – {b} – {c}   {detail}")
_METRES = QT_TR_NOOP("{d:.2f} m")
VIOLATED_COLOR = (220, 40, 40)


def _tr(source: str) -> str:
    # Keep the established context when moving literals out of the QWidget.
    return QCoreApplication.translate("ConstraintListItem", source)


@dataclass(frozen=True)
class ConstraintDescriptor:
    """Immutable display semantics, with targets still supplied in scene units."""

    icon_name: str
    satisfied_color: tuple[int, int, int]
    detail_template: str
    tooltip_template: str
    row_template: str = _PAIR
    target_divisor: float = 100.0
    absolute_target: bool = False
    always_colored: bool = False

    def render(self, label_a: str, label_b: str, target: float) -> tuple[str, str]:
        """Translate first, then interpolate; no cached language-dependent text."""
        values = {
            "a": label_a, "b": label_b, "c": _tr("…"),
            # Preserve the prior division operation, including rounding ties.
            "d": (abs(target) if self.absolute_target else target) / self.target_divisor,
        }
        detail = _tr(self.detail_template).format(**values)
        text = _tr(self.row_template).format(**values, detail=detail).rstrip()
        return text, _tr(self.tooltip_template).format(**values)


CONSTRAINT_DESCRIPTORS: Mapping[ConstraintType, ConstraintDescriptor] = MappingProxyType({
    ConstraintType.DISTANCE: ConstraintDescriptor(
        "constraint_distance", (0, 120, 200), _METRES,
        QT_TR_NOOP("{a} to {b}: {d:.2f} m")),
    ConstraintType.EDGE_LENGTH: ConstraintDescriptor(
        "constraint_edge_length", (0, 120, 200), QT_TR_NOOP("Edge {d:.2f} m"),
        QT_TR_NOOP("{a} edge length: {d:.2f} m"), row_template=_SINGLE),
    ConstraintType.HORIZONTAL: ConstraintDescriptor(
        "constraint_horizontal", (120, 0, 180), QT_TR_NOOP("Horizontal"),
        QT_TR_NOOP("{a} horizontal align {b}")),
    ConstraintType.VERTICAL: ConstraintDescriptor(
        "constraint_vertical", (120, 0, 180), QT_TR_NOOP("Vertical"),
        QT_TR_NOOP("{a} vertical align {b}")),
    ConstraintType.ANGLE: ConstraintDescriptor(
        "constraint_angle", (200, 100, 0), QT_TR_NOOP("{d:.1f}°"),
        QT_TR_NOOP("Angle {a}–{b}–{c}: {d:.1f}°"), row_template=_TRIPLE, target_divisor=1.0),
    ConstraintType.SYMMETRY_HORIZONTAL: ConstraintDescriptor(
        "constraint_symmetric", (0, 120, 200), QT_TR_NOOP("Symmetric"),
        QT_TR_NOOP("{a} symmetric to {b} about the horizontal axis")),
    ConstraintType.SYMMETRY_VERTICAL: ConstraintDescriptor(
        "constraint_symmetric", (0, 120, 200), QT_TR_NOOP("Symmetric"),
        QT_TR_NOOP("{a} symmetric to {b} about the vertical axis")),
    ConstraintType.COINCIDENT: ConstraintDescriptor(
        "constraint_coincident", (0, 160, 200), QT_TR_NOOP("Coincident"),
        QT_TR_NOOP("{a} coincident with {b}")),
    ConstraintType.PARALLEL: ConstraintDescriptor(
        "constraint_parallel", (20, 160, 100), QT_TR_NOOP("Parallel"),
        QT_TR_NOOP("{a} parallel to {b}")),
    ConstraintType.PERPENDICULAR: ConstraintDescriptor(
        "constraint_perpendicular", (20, 120, 160), QT_TR_NOOP("Perpendicular"),
        QT_TR_NOOP("{a} perpendicular to {b}")),
    ConstraintType.EQUAL: ConstraintDescriptor(
        "constraint_equal", (200, 100, 0), QT_TR_NOOP("Equal"),
        QT_TR_NOOP("{a} equal size to {b}")),
    ConstraintType.FIXED: ConstraintDescriptor(
        "constraint_fixed", (180, 130, 0), QT_TR_NOOP("Fixed"),
        QT_TR_NOOP("{a} is fixed in place"), row_template=_SINGLE, always_colored=True),
    ConstraintType.HORIZONTAL_DISTANCE: ConstraintDescriptor(
        "constraint_h_distance", (0, 120, 200), _METRES,
        QT_TR_NOOP("{a} to {b}: horizontal distance {d:.2f} m")),
    ConstraintType.VERTICAL_DISTANCE: ConstraintDescriptor(
        "constraint_v_distance", (0, 120, 200), _METRES,
        QT_TR_NOOP("{a} to {b}: vertical distance {d:.2f} m")),
    ConstraintType.POINT_ON_EDGE: ConstraintDescriptor(
        "snap_nearest", (0, 120, 200), QT_TR_NOOP("On edge"),
        QT_TR_NOOP("{a} lies on the edge of {b}")),
    ConstraintType.POINT_ON_CIRCLE: ConstraintDescriptor(
        "snap_tangent", (0, 120, 200), QT_TR_NOOP("On circle"),
        QT_TR_NOOP("{a} lies on the circle of {b}")),
    ConstraintType.TANGENT: ConstraintDescriptor(
        "snap_tangent", (0, 120, 200), QT_TR_NOOP("Tangent"),
        QT_TR_NOOP("{a} tangent to {b} (r={d:.2f} m)"), absolute_target=True),
})


def descriptor_for_name(name: str) -> ConstraintDescriptor:
    """Preserve distance presentation for an unknown external row type name."""
    kind = ConstraintType.__members__.get(name, ConstraintType.DISTANCE)
    return CONSTRAINT_DESCRIPTORS[kind]
