"""Distance constraint data model and solver for CAD precision.

Provides a constraint graph and iterative Gauss-Seidel relaxation solver
that resolves distance constraints between object anchor points.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any
from uuid import UUID, uuid4

from open_garden_planner.core.measure_snapper import AnchorType


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
    """A distance constraint between two anchor points.

    Specifies that the distance between anchor_a and anchor_b should
    equal target_distance (in scene units / cm).
    """

    constraint_id: UUID
    anchor_a: AnchorRef
    anchor_b: AnchorRef
    target_distance: float
    visible: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "constraint_id": str(self.constraint_id),
            "anchor_a": self.anchor_a.to_dict(),
            "anchor_b": self.anchor_b.to_dict(),
            "target_distance": self.target_distance,
            "visible": self.visible,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Constraint:
        """Deserialize from dictionary."""
        return cls(
            constraint_id=UUID(data["constraint_id"]),
            anchor_a=AnchorRef.from_dict(data["anchor_a"]),
            anchor_b=AnchorRef.from_dict(data["anchor_b"]),
            target_distance=data["target_distance"],
            visible=data.get("visible", True),
        )


@dataclass
class SolverResult:
    """Result of constraint solving."""

    converged: bool
    iterations_used: int
    max_error: float
    item_deltas: dict[UUID, tuple[float, float]]
    over_constrained_items: set[UUID] = field(default_factory=set)


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
    ) -> Constraint:
        """Add a distance constraint between two anchors.

        Args:
            anchor_a: First anchor reference.
            anchor_b: Second anchor reference.
            target_distance: Desired distance in scene units (cm).
            visible: Whether the constraint dimension line is visible.
            constraint_id: Optional pre-set ID (for deserialization).

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
        )
        self._constraints[cid] = constraint

        # Update adjacency
        item_a = anchor_a.item_id
        item_b = anchor_b.item_id
        self._adjacency.setdefault(item_a, set()).add(cid)
        self._adjacency.setdefault(item_b, set()).add(cid)

        return constraint

    def remove_constraint(self, constraint_id: UUID) -> None:
        """Remove a constraint by ID."""
        constraint = self._constraints.pop(constraint_id, None)
        if constraint is None:
            return

        # Clean up adjacency
        for item_id in (constraint.anchor_a.item_id, constraint.anchor_b.item_id):
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
                neighbor = (
                    constraint.anchor_b.item_id
                    if constraint.anchor_a.item_id == current
                    else constraint.anchor_a.item_id
                )
                if neighbor not in visited:
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

                a_pinned = id_a in pinned_items
                b_pinned = id_b in pinned_items

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

                a_pinned = id_a in pinned_items
                b_pinned = id_b in pinned_items

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
        )

    def clear(self) -> None:
        """Remove all constraints."""
        self._constraints.clear()
        self._adjacency.clear()
