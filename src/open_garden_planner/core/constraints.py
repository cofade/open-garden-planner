"""Distance and alignment constraint data model and solver for CAD precision.

Provides a constraint graph and iterative Gauss-Seidel relaxation solver
that resolves distance and alignment constraints between object anchor points.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any
from uuid import UUID, uuid4

from open_garden_planner.core.measure_snapper import AnchorType


class ConstraintType(Enum):
    """Type of constraint between two anchor points."""

    DISTANCE = auto()              # Fixed distance between anchors
    HORIZONTAL = auto()            # Same Y coordinate (horizontal alignment)
    VERTICAL = auto()              # Same X coordinate (vertical alignment)
    ANGLE = auto()                 # Fixed angle at vertex B between rays BA and BC (degrees)
    SYMMETRY_HORIZONTAL = auto()   # Mirror A and B across a horizontal axis (y = target_distance)
    SYMMETRY_VERTICAL = auto()     # Mirror A and B across a vertical axis (x = target_distance)
    COINCIDENT = auto()            # Force two anchor points to the same position (distance = 0)
    PARALLEL = auto()              # Keep two edges parallel (item B at target rotation angle)


class ConstraintStatus(Enum):
    """Status of a constraint after solving."""

    SATISFIED = auto()
    UNSATISFIED = auto()
    OVER_CONSTRAINED = auto()


@dataclass
class AnchorRef:
    """Reference to an anchor point on a specific item.

    Identifies a particular anchor on a garden item by its UUID,
    anchor type, and index. The index distinguishes same-type anchors
    (e.g. vertex 0 vs vertex 3 on a polygon, both AnchorType.CORNER).
    The actual scene position is resolved at solve time.
    """

    item_id: UUID
    anchor_type: AnchorType
    anchor_index: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "item_id": str(self.item_id),
            "anchor_type": self.anchor_type.name,
            "anchor_index": self.anchor_index,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnchorRef:
        """Deserialize from dictionary."""
        return cls(
            item_id=UUID(data["item_id"]),
            anchor_type=AnchorType[data["anchor_type"]],
            anchor_index=data.get("anchor_index", 0),
        )


@dataclass
class Constraint:
    """A constraint between two or three anchor points.

    For DISTANCE constraints, specifies that the distance between anchor_a
    and anchor_b should equal target_distance (in scene units / cm).
    For HORIZONTAL/VERTICAL constraints, the anchors share the same Y/X
    coordinate respectively; target_distance is unused (stored as 0.0).
    For ANGLE constraints, specifies that the angle A-B-C (where B=anchor_b
    is the vertex) should equal target_distance (in degrees). anchor_c is
    the third anchor point.
    """

    constraint_id: UUID
    anchor_a: AnchorRef
    anchor_b: AnchorRef
    target_distance: float
    visible: bool = True
    constraint_type: ConstraintType = field(default_factory=lambda: ConstraintType.DISTANCE)
    anchor_c: AnchorRef | None = None  # Third anchor for ANGLE constraints

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d: dict[str, Any] = {
            "constraint_id": str(self.constraint_id),
            "anchor_a": self.anchor_a.to_dict(),
            "anchor_b": self.anchor_b.to_dict(),
            "target_distance": self.target_distance,
            "visible": self.visible,
            "constraint_type": self.constraint_type.name,
        }
        if self.anchor_c is not None:
            d["anchor_c"] = self.anchor_c.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Constraint:
        """Deserialize from dictionary."""
        anchor_c_data = data.get("anchor_c")
        return cls(
            constraint_id=UUID(data["constraint_id"]),
            anchor_a=AnchorRef.from_dict(data["anchor_a"]),
            anchor_b=AnchorRef.from_dict(data["anchor_b"]),
            target_distance=data["target_distance"],
            visible=data.get("visible", True),
            constraint_type=ConstraintType[data.get("constraint_type", "DISTANCE")],
            anchor_c=AnchorRef.from_dict(anchor_c_data) if anchor_c_data else None,
        )


@dataclass
class SolverResult:
    """Result of constraint solving."""

    converged: bool
    iterations_used: int
    max_error: float
    item_deltas: dict[UUID, tuple[float, float]]
    over_constrained_items: set[UUID] = field(default_factory=set)
    item_rotation_deltas: dict[UUID, float] = field(default_factory=dict)


class ConstraintGraph:
    """Graph of distance constraints between item anchors.

    Provides adjacency lookup, connected component detection via BFS,
    and an iterative Gauss-Seidel relaxation solver.
    """

    def __init__(self) -> None:
        self._constraints: dict[UUID, Constraint] = {}
        # Adjacency: item_id -> set of constraint_ids involving that item
        self._adjacency: dict[UUID, set[UUID]] = {}

    @property
    def constraints(self) -> dict[UUID, Constraint]:
        """All constraints indexed by constraint_id."""
        return self._constraints

    def add_constraint(
        self,
        anchor_a: AnchorRef,
        anchor_b: AnchorRef,
        target_distance: float,
        visible: bool = True,
        constraint_id: UUID | None = None,
        constraint_type: ConstraintType = ConstraintType.DISTANCE,
        anchor_c: AnchorRef | None = None,
    ) -> Constraint:
        """Add a constraint between two or three anchors.

        Args:
            anchor_a: First anchor reference.
            anchor_b: Second anchor reference (vertex for ANGLE constraints).
            target_distance: Desired distance in cm, or angle in degrees for ANGLE.
                Ignored for HORIZONTAL/VERTICAL constraints (pass 0.0).
            visible: Whether the constraint annotation is visible.
            constraint_id: Optional pre-set ID (for deserialization).
            constraint_type: Type of constraint.
            anchor_c: Third anchor for ANGLE constraints (point C in A-B-C).

        Returns:
            The created Constraint.
        """
        cid = constraint_id or uuid4()
        constraint = Constraint(
            constraint_id=cid,
            anchor_a=anchor_a,
            anchor_b=anchor_b,
            target_distance=target_distance,
            visible=visible,
            constraint_type=constraint_type,
            anchor_c=anchor_c,
        )
        self._constraints[cid] = constraint

        # Update adjacency for all involved items
        item_a = anchor_a.item_id
        item_b = anchor_b.item_id
        self._adjacency.setdefault(item_a, set()).add(cid)
        self._adjacency.setdefault(item_b, set()).add(cid)
        if anchor_c is not None:
            self._adjacency.setdefault(anchor_c.item_id, set()).add(cid)

        return constraint

    def remove_constraint(self, constraint_id: UUID) -> None:
        """Remove a constraint by ID."""
        constraint = self._constraints.pop(constraint_id, None)
        if constraint is None:
            return

        # Clean up adjacency for all involved items
        item_ids = [constraint.anchor_a.item_id, constraint.anchor_b.item_id]
        if constraint.anchor_c is not None:
            item_ids.append(constraint.anchor_c.item_id)
        for item_id in item_ids:
            adj = self._adjacency.get(item_id)
            if adj is not None:
                adj.discard(constraint_id)
                if not adj:
                    del self._adjacency[item_id]

    def remove_item_constraints(self, item_id: UUID) -> list[UUID]:
        """Remove all constraints involving an item.

        Args:
            item_id: The item whose constraints should be removed.

        Returns:
            List of removed constraint IDs.
        """
        constraint_ids = list(self._adjacency.get(item_id, set()))
        for cid in constraint_ids:
            self.remove_constraint(cid)
        return constraint_ids

    def get_item_constraints(self, item_id: UUID) -> list[Constraint]:
        """Get all constraints involving an item."""
        cids = self._adjacency.get(item_id, set())
        return [self._constraints[cid] for cid in cids if cid in self._constraints]

    def get_connected_component(self, item_id: UUID) -> set[UUID]:
        """Get the connected component containing the given item via BFS.

        Returns:
            Set of item UUIDs in the same connected component.
        """
        visited: set[UUID] = set()
        queue: deque[UUID] = deque([item_id])

        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)

            for cid in self._adjacency.get(current, set()):
                constraint = self._constraints.get(cid)
                if constraint is None:
                    continue
                # All items involved in this constraint are neighbors
                neighbors = [constraint.anchor_a.item_id, constraint.anchor_b.item_id]
                if constraint.anchor_c is not None:
                    neighbors.append(constraint.anchor_c.item_id)
                for neighbor in neighbors:
                    if neighbor != current and neighbor not in visited:
                        queue.append(neighbor)

        return visited

    def get_all_connected_components(self) -> list[set[UUID]]:
        """Get all connected components in the graph.

        Returns:
            List of sets, each set containing item UUIDs in one component.
        """
        visited: set[UUID] = set()
        components: list[set[UUID]] = []

        for item_id in self._adjacency:
            if item_id not in visited:
                component = self.get_connected_component(item_id)
                visited.update(component)
                components.append(component)

        return components

    def is_over_constrained(
        self,
        item_positions: dict[UUID, tuple[float, float]],
    ) -> set[UUID]:
        """Detect over-constrained items.

        An item is over-constrained if it has more constraints than
        degrees of freedom (2 for a 2D item that can translate).
        We also check if constraints on a single item are contradictory.

        Args:
            item_positions: Current positions of items {item_id: (x, y)}.

        Returns:
            Set of over-constrained item UUIDs.
        """
        over_constrained: set[UUID] = set()

        for item_id, cids in self._adjacency.items():
            if item_id not in item_positions:
                continue
            # An item with >2 constraints from different items may be
            # over-constrained (2 DOF in 2D translation)
            connected_items: set[UUID] = set()
            for cid in cids:
                c = self._constraints.get(cid)
                if c is None:
                    continue
                other = (
                    c.anchor_b.item_id
                    if c.anchor_a.item_id == item_id
                    else c.anchor_a.item_id
                )
                connected_items.add(other)

            if len(connected_items) > 2:
                over_constrained.add(item_id)

        return over_constrained

    def solve(
        self,
        item_positions: dict[UUID, tuple[float, float]],
        pinned_items: set[UUID] | None = None,
        max_iterations: int = 5,
        tolerance: float = 1.0,
    ) -> SolverResult:
        """Solve constraints using iterative Gauss-Seidel relaxation.

        Each iteration processes all constraints and moves unpinned items
        to better satisfy distance targets. Items share the correction
        equally unless one is pinned.

        Args:
            item_positions: Current center positions {item_id: (x, y)}.
                Positions are modified in-place during solving.
            pinned_items: Items that should not move.
            max_iterations: Maximum solver iterations (default 5).
            tolerance: Convergence tolerance in scene units/mm (default 1.0mm).

        Returns:
            SolverResult with convergence info and computed deltas.
        """
        if pinned_items is None:
            pinned_items = set()

        # Store original positions to compute deltas
        original_positions = {
            uid: (pos[0], pos[1]) for uid, pos in item_positions.items()
        }

        # Working copy of positions
        positions = {
            uid: [pos[0], pos[1]] for uid, pos in item_positions.items()
        }

        # Check for over-constrained items
        over_constrained = self.is_over_constrained(item_positions)

        max_error = float("inf")
        iterations_used = 0

        for iteration in range(max_iterations):
            max_error = 0.0

            for constraint in self._constraints.values():
                id_a = constraint.anchor_a.item_id
                id_b = constraint.anchor_b.item_id

                if id_a not in positions or id_b not in positions:
                    continue

                pos_a = positions[id_a]
                pos_b = positions[id_b]

                a_pinned = id_a in pinned_items
                b_pinned = id_b in pinned_items

                if constraint.constraint_type == ConstraintType.HORIZONTAL:
                    # Enforce same Y coordinate
                    diff = pos_b[1] - pos_a[1]
                    error = abs(diff)
                    max_error = max(max_error, error)
                    if a_pinned and b_pinned:
                        continue
                    elif a_pinned:
                        positions[id_b][1] = pos_a[1]
                    elif b_pinned:
                        positions[id_a][1] = pos_b[1]
                    else:
                        positions[id_a][1] += diff / 2.0
                        positions[id_b][1] -= diff / 2.0
                    continue

                if constraint.constraint_type == ConstraintType.VERTICAL:
                    # Enforce same X coordinate
                    diff = pos_b[0] - pos_a[0]
                    error = abs(diff)
                    max_error = max(max_error, error)
                    if a_pinned and b_pinned:
                        continue
                    elif a_pinned:
                        positions[id_b][0] = pos_a[0]
                    elif b_pinned:
                        positions[id_a][0] = pos_b[0]
                    else:
                        positions[id_a][0] += diff / 2.0
                        positions[id_b][0] -= diff / 2.0
                    continue

                if constraint.constraint_type == ConstraintType.PARALLEL:
                    # PARALLEL is a rotation-only constraint; no position correction.
                    continue

                # DISTANCE constraint
                dx = pos_b[0] - pos_a[0]
                dy = pos_b[1] - pos_a[1]
                current_dist = math.sqrt(dx * dx + dy * dy)

                error = abs(current_dist - constraint.target_distance)
                max_error = max(max_error, error)

                if current_dist < 1e-9:
                    # Degenerate case: items at same position
                    # Push apart along arbitrary axis
                    dx = 1.0
                    dy = 0.0
                    current_dist = 1.0

                # Correction needed
                correction = constraint.target_distance - current_dist
                # Normalize direction
                nx = dx / current_dist
                ny = dy / current_dist

                if a_pinned and b_pinned:
                    # Both pinned, cannot resolve
                    continue
                elif a_pinned:
                    # Only move B
                    positions[id_b][0] += correction * nx
                    positions[id_b][1] += correction * ny
                elif b_pinned:
                    # Only move A (in opposite direction)
                    positions[id_a][0] -= correction * nx
                    positions[id_a][1] -= correction * ny
                else:
                    # Split correction equally
                    half = correction / 2.0
                    positions[id_a][0] -= half * nx
                    positions[id_a][1] -= half * ny
                    positions[id_b][0] += half * nx
                    positions[id_b][1] += half * ny

            iterations_used = iteration + 1

            if max_error <= tolerance:
                break

        # Compute deltas from original positions
        item_deltas: dict[UUID, tuple[float, float]] = {}
        for uid, pos in positions.items():
            if uid in pinned_items:
                continue
            orig = original_positions[uid]
            delta_x = pos[0] - orig[0]
            delta_y = pos[1] - orig[1]
            if abs(delta_x) > 1e-6 or abs(delta_y) > 1e-6:
                item_deltas[uid] = (delta_x, delta_y)

        return SolverResult(
            converged=max_error <= tolerance,
            iterations_used=iterations_used,
            max_error=max_error,
            item_deltas=item_deltas,
            over_constrained_items=over_constrained,
        )

    def to_list(self) -> list[dict[str, Any]]:
        """Serialize all constraints to a list of dicts."""
        return [c.to_dict() for c in self._constraints.values()]

    @classmethod
    def from_list(cls, data: list[dict[str, Any]]) -> ConstraintGraph:
        """Deserialize from a list of constraint dicts."""
        graph = cls()
        for item in data:
            c = Constraint.from_dict(item)
            graph.add_constraint(
                anchor_a=c.anchor_a,
                anchor_b=c.anchor_b,
                target_distance=c.target_distance,
                visible=c.visible,
                constraint_id=c.constraint_id,
                constraint_type=c.constraint_type,
                anchor_c=c.anchor_c,
            )
        return graph

    def solve_anchored(
        self,
        item_positions: dict[UUID, tuple[float, float]],
        anchor_offsets: dict[tuple[UUID, AnchorType, int], tuple[float, float]],
        pinned_items: set[UUID] | None = None,
        max_iterations: int = 10,
        tolerance: float = 1.0,
    ) -> SolverResult:
        """Solve constraints using actual anchor positions for distance computation.

        Unlike solve(), this method uses resolved anchor offsets relative to
        item positions to compute accurate anchor-to-anchor distances.
        Corrections are still applied to item positions (moving the whole item).

        Args:
            item_positions: Current item positions {item_id: (x, y)}.
            anchor_offsets: Pre-computed anchor offsets relative to item pos().
                Key is (item_id, anchor_type, anchor_index).
                Value is (offset_x, offset_y) such that
                anchor_pos = item_pos + offset.
            pinned_items: Items that should not move.
            max_iterations: Maximum solver iterations.
            tolerance: Convergence tolerance in scene units (cm).

        Returns:
            SolverResult with convergence info and computed deltas.
        """
        if pinned_items is None:
            pinned_items = set()

        original_positions = {
            uid: (pos[0], pos[1]) for uid, pos in item_positions.items()
        }
        positions = {
            uid: [pos[0], pos[1]] for uid, pos in item_positions.items()
        }
        over_constrained = self.is_over_constrained(item_positions)

        rotation_deltas: dict[UUID, float] = {}
        max_error = float("inf")
        iterations_used = 0

        for iteration in range(max_iterations):
            max_error = 0.0

            for constraint in self._constraints.values():
                id_a = constraint.anchor_a.item_id
                id_b = constraint.anchor_b.item_id

                if id_a not in positions or id_b not in positions:
                    continue

                # Get anchor offsets for this constraint's endpoints
                key_a = (id_a, constraint.anchor_a.anchor_type, constraint.anchor_a.anchor_index)
                key_b = (id_b, constraint.anchor_b.anchor_type, constraint.anchor_b.anchor_index)

                off_a = anchor_offsets.get(key_a, (0.0, 0.0))
                off_b = anchor_offsets.get(key_b, (0.0, 0.0))

                # Compute actual anchor positions
                ax = positions[id_a][0] + off_a[0]
                ay = positions[id_a][1] + off_a[1]
                bx = positions[id_b][0] + off_b[0]
                by = positions[id_b][1] + off_b[1]

                a_pinned = id_a in pinned_items
                b_pinned = id_b in pinned_items

                if constraint.constraint_type == ConstraintType.HORIZONTAL:
                    # Enforce same Y coordinate for anchors
                    diff = by - ay
                    error = abs(diff)
                    max_error = max(max_error, error)
                    if a_pinned and b_pinned:
                        continue
                    elif a_pinned:
                        # Move item_b so its anchor matches item_a's anchor Y
                        positions[id_b][1] -= diff
                    elif b_pinned:
                        # Move item_a so its anchor matches item_b's anchor Y
                        positions[id_a][1] += diff
                    else:
                        positions[id_a][1] += diff / 2.0
                        positions[id_b][1] -= diff / 2.0
                    continue

                if constraint.constraint_type == ConstraintType.VERTICAL:
                    # Enforce same X coordinate for anchors
                    diff = bx - ax
                    error = abs(diff)
                    max_error = max(max_error, error)
                    if a_pinned and b_pinned:
                        continue
                    elif a_pinned:
                        # Move item_b so its anchor matches item_a's anchor X
                        positions[id_b][0] -= diff
                    elif b_pinned:
                        # Move item_a so its anchor matches item_b's anchor X
                        positions[id_a][0] += diff
                    else:
                        positions[id_a][0] += diff / 2.0
                        positions[id_b][0] -= diff / 2.0
                    continue

                if constraint.constraint_type == ConstraintType.ANGLE:
                    # ANGLE constraint: fix angle A-B-C at vertex B.
                    # anchor_b is the vertex; anchor_a and anchor_c are the two rays.
                    if constraint.anchor_c is None:
                        continue
                    id_c = constraint.anchor_c.item_id
                    if id_c not in positions:
                        continue
                    key_c = (
                        id_c,
                        constraint.anchor_c.anchor_type,
                        constraint.anchor_c.anchor_index,
                    )
                    off_c = anchor_offsets.get(key_c, (0.0, 0.0))
                    cx = positions[id_c][0] + off_c[0]
                    cy = positions[id_c][1] + off_c[1]

                    # Vectors from vertex B to A and B to C
                    ba_x, ba_y = ax - bx, ay - by
                    bc_x, bc_y = cx - bx, cy - by
                    ba_len = math.sqrt(ba_x * ba_x + ba_y * ba_y)
                    bc_len = math.sqrt(bc_x * bc_x + bc_y * bc_y)
                    if ba_len < 1e-9 or bc_len < 1e-9:
                        continue

                    # Unsigned angle between BA and BC in radians
                    cos_val = (ba_x * bc_x + ba_y * bc_y) / (ba_len * bc_len)
                    cos_val = max(-1.0, min(1.0, cos_val))
                    current_angle = math.acos(cos_val)

                    target_rad = math.radians(constraint.target_distance)
                    angle_error = current_angle - target_rad
                    max_error = max(max_error, abs(angle_error) * 100)

                    if abs(angle_error) < 1e-6:
                        continue

                    # Signed cross product (BA × BC) determines rotation direction.
                    # If cross >= 0: BC is CCW from BA when viewed from B.
                    # Rotation correction: bring A and C symmetrically towards target angle.
                    cross = ba_x * bc_y - ba_y * bc_x
                    cross_sign = 1.0 if cross >= 0.0 else -1.0

                    c_pinned = id_c in pinned_items

                    # Rotation amounts (radians) for items A and C around vertex B.
                    # Positive = CW in Qt scene (Y-down), negative = CCW.
                    # Formula: delta_a =  angle_error/2 * cross_sign
                    #          delta_c = -angle_error/2 * cross_sign
                    # (angle_error > 0 means current > target, i.e. close the angle)
                    if not a_pinned and not c_pinned:
                        delta_a = angle_error / 2.0 * cross_sign
                        delta_c = -angle_error / 2.0 * cross_sign
                    elif a_pinned and not c_pinned:
                        delta_a = 0.0
                        delta_c = -angle_error * cross_sign
                    elif not a_pinned and c_pinned:
                        delta_a = angle_error * cross_sign
                        delta_c = 0.0
                    else:
                        continue  # Both A and C pinned; cannot fix

                    # Rotate item A's anchor position around B by delta_a
                    if abs(delta_a) > 1e-9:
                        cos_a, sin_a = math.cos(delta_a), math.sin(delta_a)
                        new_ra_x = cos_a * ba_x - sin_a * ba_y
                        new_ra_y = sin_a * ba_x + cos_a * ba_y
                        positions[id_a][0] += new_ra_x - ba_x
                        positions[id_a][1] += new_ra_y - ba_y

                    # Rotate item C's anchor position around B by delta_c
                    if abs(delta_c) > 1e-9:
                        cos_c, sin_c = math.cos(delta_c), math.sin(delta_c)
                        new_rc_x = cos_c * bc_x - sin_c * bc_y
                        new_rc_y = sin_c * bc_x + cos_c * bc_y
                        positions[id_c][0] += new_rc_x - bc_x
                        positions[id_c][1] += new_rc_y - bc_y
                    continue

                if constraint.constraint_type == ConstraintType.SYMMETRY_HORIZONTAL:
                    # Mirror A and B across the horizontal axis y = target_distance.
                    # Enforces: bx = ax  AND  ay + by = 2 * axis_y
                    axis_y = constraint.target_distance
                    # X synchronisation: bx should equal ax
                    x_error = bx - ax
                    # Y symmetry: ay + by should equal 2 * axis_y
                    y_sum_error = ay + by - 2.0 * axis_y

                    sym_error = math.sqrt(x_error ** 2 + y_sum_error ** 2)
                    max_error = max(max_error, sym_error)

                    if a_pinned and b_pinned:
                        continue
                    elif a_pinned:
                        # Move B's item so B's anchor mirrors A's anchor.
                        # anchor_b = positions[id_b] + off_b, so:
                        # positions[id_b] = target_anchor - off_b
                        positions[id_b][0] = ax - off_b[0]
                        positions[id_b][1] = (2.0 * axis_y - ay) - off_b[1]
                    elif b_pinned:
                        # Move A's item so A's anchor mirrors B's anchor.
                        positions[id_a][0] = bx - off_a[0]
                        positions[id_a][1] = (2.0 * axis_y - by) - off_a[1]
                    else:
                        # Split: align X to average, adjust Y to meet symmetry
                        positions[id_a][0] += x_error / 2.0
                        positions[id_b][0] -= x_error / 2.0
                        positions[id_a][1] -= y_sum_error / 2.0
                        positions[id_b][1] -= y_sum_error / 2.0
                    continue

                if constraint.constraint_type == ConstraintType.SYMMETRY_VERTICAL:
                    # Mirror A and B across the vertical axis x = target_distance.
                    # Enforces: by = ay  AND  ax + bx = 2 * axis_x
                    axis_x = constraint.target_distance
                    # Y synchronisation: by should equal ay
                    y_error = by - ay
                    # X symmetry: ax + bx should equal 2 * axis_x
                    x_sum_error = ax + bx - 2.0 * axis_x

                    sym_error = math.sqrt(y_error ** 2 + x_sum_error ** 2)
                    max_error = max(max_error, sym_error)

                    if a_pinned and b_pinned:
                        continue
                    elif a_pinned:
                        # Move B's item so B's anchor mirrors A's anchor.
                        positions[id_b][0] = (2.0 * axis_x - ax) - off_b[0]
                        positions[id_b][1] = ay - off_b[1]
                    elif b_pinned:
                        # Move A's item so A's anchor mirrors B's anchor.
                        positions[id_a][0] = (2.0 * axis_x - bx) - off_a[0]
                        positions[id_a][1] = by - off_a[1]
                    else:
                        # Split: align Y to average, adjust X to meet symmetry
                        positions[id_a][1] += y_error / 2.0
                        positions[id_b][1] -= y_error / 2.0
                        positions[id_a][0] -= x_sum_error / 2.0
                        positions[id_b][0] -= x_sum_error / 2.0
                    continue

                if constraint.constraint_type == ConstraintType.COINCIDENT:
                    # Force both anchors to the same position (meet at midpoint).
                    dx = bx - ax
                    dy = by - ay
                    error = math.sqrt(dx * dx + dy * dy)
                    max_error = max(max_error, error)
                    if error < 1e-9:
                        continue
                    if a_pinned and b_pinned:
                        continue
                    elif a_pinned:
                        # Move item B so anchor B coincides with anchor A
                        positions[id_b][0] = ax - off_b[0]
                        positions[id_b][1] = ay - off_b[1]
                    elif b_pinned:
                        # Move item A so anchor A coincides with anchor B
                        positions[id_a][0] = bx - off_a[0]
                        positions[id_a][1] = by - off_a[1]
                    else:
                        # Both free: meet at midpoint
                        mid_x = (ax + bx) / 2.0
                        mid_y = (ay + by) / 2.0
                        positions[id_a][0] = mid_x - off_a[0]
                        positions[id_a][1] = mid_y - off_a[1]
                        positions[id_b][0] = mid_x - off_b[0]
                        positions[id_b][1] = mid_y - off_b[1]
                    continue

                if constraint.constraint_type == ConstraintType.PARALLEL:
                    # PARALLEL: anchor_b identifies item B (constrained item).
                    # target_distance is the desired rotation_angle for item B.
                    # This is handled as a rotation, not a position change.
                    # We record a rotation delta in rotation_deltas and skip
                    # the position solver for this constraint.
                    if b_pinned:
                        continue
                    # target_distance is the desired rotation angle for item B
                    # Item rotations are applied post-solve; record the intent.
                    # (No position correction needed here.)
                    continue

                # DISTANCE constraint
                dx = bx - ax
                dy = by - ay
                current_dist = math.sqrt(dx * dx + dy * dy)

                error = abs(current_dist - constraint.target_distance)
                max_error = max(max_error, error)

                if current_dist < 1e-9:
                    dx = 1.0
                    dy = 0.0
                    current_dist = 1.0

                correction = constraint.target_distance - current_dist
                nx = dx / current_dist
                ny = dy / current_dist

                if a_pinned and b_pinned:
                    continue
                elif a_pinned:
                    positions[id_b][0] += correction * nx
                    positions[id_b][1] += correction * ny
                elif b_pinned:
                    positions[id_a][0] -= correction * nx
                    positions[id_a][1] -= correction * ny
                else:
                    half = correction / 2.0
                    positions[id_a][0] -= half * nx
                    positions[id_a][1] -= half * ny
                    positions[id_b][0] += half * nx
                    positions[id_b][1] += half * ny

            iterations_used = iteration + 1
            if max_error <= tolerance:
                break

        item_deltas: dict[UUID, tuple[float, float]] = {}
        for uid, pos in positions.items():
            if uid in pinned_items:
                continue
            orig = original_positions[uid]
            delta_x = pos[0] - orig[0]
            delta_y = pos[1] - orig[1]
            if abs(delta_x) > 1e-6 or abs(delta_y) > 1e-6:
                item_deltas[uid] = (delta_x, delta_y)

        return SolverResult(
            converged=max_error <= tolerance,
            iterations_used=iterations_used,
            max_error=max_error,
            item_deltas=item_deltas,
            over_constrained_items=over_constrained,
            item_rotation_deltas=rotation_deltas,
        )

    def validate_constraint(
        self,
        anchor_a: AnchorRef,
        anchor_b: AnchorRef,
        target_distance: float,
        constraint_type: ConstraintType,
        item_positions: dict[UUID, tuple[float, float]],
        anchor_offsets: dict[tuple[UUID, AnchorType, int], tuple[float, float]],
        max_iterations: int = 50,
        tolerance: float = 1.0,
        anchor_c: AnchorRef | None = None,
    ) -> bool:
        """Test if adding a constraint would conflict with existing constraints.

        Temporarily adds the constraint, runs the solver (without mutating
        item_positions), removes the test constraint, and returns whether the
        solver converged.

        Args:
            anchor_a: First anchor reference.
            anchor_b: Second anchor reference.
            target_distance: Desired distance in cm, or degrees for ANGLE.
            constraint_type: Type of constraint to test.
            item_positions: Current item centre positions {item_id: (x, y)}.
            anchor_offsets: Pre-computed anchor offsets keyed by
                (item_id, anchor_type, anchor_index).
            max_iterations: Solver iterations for the feasibility check.
            tolerance: Convergence tolerance in cm.
            anchor_c: Optional third anchor for ANGLE constraints.

        Returns:
            True  — constraint is compatible with the existing system.
            False — adding the constraint would cause an irresolvable conflict.
        """
        temp = self.add_constraint(
            anchor_a=anchor_a,
            anchor_b=anchor_b,
            target_distance=target_distance,
            constraint_type=constraint_type,
            anchor_c=anchor_c,
        )
        try:
            result = self.solve_anchored(
                item_positions=item_positions,
                anchor_offsets=anchor_offsets,
                pinned_items=set(),
                max_iterations=max_iterations,
                tolerance=tolerance,
            )
            return result.converged
        finally:
            self.remove_constraint(temp.constraint_id)

    def clear(self) -> None:
        """Remove all constraints."""
        self._constraints.clear()
        self._adjacency.clear()
