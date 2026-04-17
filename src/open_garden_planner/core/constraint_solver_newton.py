"""Newton-Raphson refinement for the constraint solver.

The primary ``solve_anchored`` routine in :mod:`constraints` uses Gauss-Seidel
relaxation — each constraint is resolved by a 1D projection along its own
direction.  That works for isolated constraints but fails for coupled systems
where the same free variable appears in multiple constraints with independent
geometric directions.  The canonical failure case is two EDGE_LENGTH
constraints sharing a vertex: the feasible position for the shared vertex is
the intersection of two circles, which cannot be reached by alternating 1D
projections.

This module runs AFTER Gauss-Seidel as a refinement step.  It treats the free
item positions and free vertex positions as a single variable vector ``x``,
builds a residual vector ``F(x)`` from the constraints, and performs damped
Newton-Raphson steps on ``J · Δx = −F`` (solved via ``numpy.linalg.lstsq`` so
rank-deficient systems yield a minimum-norm step) with Armijo backtracking.
The Jacobian is computed numerically by central differences.

See ``docs/08-crosscutting-concepts/README.md`` §8.12 and ADR-012 for the
architectural rationale.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING
from uuid import UUID

import numpy as np

from open_garden_planner.core.measure_snapper import AnchorType

if TYPE_CHECKING:
    from open_garden_planner.core.constraints import AnchorRef, Constraint

_VERTEX_TYPES = {AnchorType.CORNER, AnchorType.ENDPOINT}

# Central-difference step for the numerical Jacobian (scene units = cm).
# Small enough for 2nd-order accuracy, large enough to keep rounding noise
# well below the cm-scale tolerances the planner cares about.
_JACOBIAN_H = 1e-3


def two_circle_intersection(
    c1: tuple[float, float],
    r1: float,
    c2: tuple[float, float],
    r2: float,
    seed: tuple[float, float],
) -> tuple[float, float] | None:
    """Closed-form intersection of two circles; returns the root nearest ``seed``.

    Returns ``None`` if the circles don't intersect (too far apart or one
    contains the other with no touch).  Tangent circles return their single
    contact point.
    """
    dx = c2[0] - c1[0]
    dy = c2[1] - c1[1]
    d = math.sqrt(dx * dx + dy * dy)
    if d < 1e-9:
        return None
    if d > r1 + r2 + 1e-9 or d + min(r1, r2) + 1e-9 < max(r1, r2):
        return None
    a = (r1 * r1 - r2 * r2 + d * d) / (2.0 * d)
    h_sq = r1 * r1 - a * a
    h = math.sqrt(h_sq) if h_sq > 0.0 else 0.0
    mx = c1[0] + a * dx / d
    my = c1[1] + a * dy / d
    if h < 1e-9:
        return (mx, my)
    ox = -dy * h / d
    oy = dx * h / d
    root1 = (mx + ox, my + oy)
    root2 = (mx - ox, my - oy)
    d1 = (root1[0] - seed[0]) ** 2 + (root1[1] - seed[1]) ** 2
    d2 = (root2[0] - seed[0]) ** 2 + (root2[1] - seed[1]) ** 2
    return root1 if d1 <= d2 else root2


def newton_refine(
    positions: dict[UUID, list[float]],
    vertex_pos: dict[tuple[UUID, int], list[float]],
    anchor_offsets: dict[tuple[UUID, AnchorType, int], tuple[float, float]],
    deformable_items: set[UUID],
    deformable_vkeys: dict[UUID, list[tuple[UUID, int]]],
    constraints: list[Constraint],
    pinned_items: set[UUID],
    max_iter: int = 25,
    tol: float = 0.1,
) -> tuple[bool, float]:
    """Refine ``positions`` and ``vertex_pos`` by damped Newton-Raphson.

    Mutates ``positions`` and ``vertex_pos`` in place.  Returns
    ``(converged, max_residual)`` after the final step.

    The input state is expected to be warm-started by Gauss-Seidel relaxation;
    Newton converges quickly near the feasible set but can diverge from a poor
    initial guess.
    """
    from open_garden_planner.core.constraints import ConstraintType  # noqa: PLC0415

    # ── Variable layout ────────────────────────────────────────────────────
    # Each free rigid item contributes a single 2-DOF variable (item translation).
    # Each free deformable vertex contributes a 2-DOF variable (vertex position).
    # For deformable items we use per-vertex variables ONLY — the rigid
    # ``positions[uid]`` slot is not exposed, mirroring how ``solve_anchored``
    # routes anchor lookups for deformable items.
    var_slots: list[tuple[str, UUID, int]] = []
    slot_index: dict[tuple[str, UUID, int], int] = {}

    for uid in positions:
        if uid in pinned_items:
            continue
        if uid in deformable_items:
            for vk in deformable_vkeys.get(uid, []):
                key = ("vertex", vk[0], vk[1])
                slot_index[key] = len(var_slots)
                var_slots.append(key)
        else:
            key = ("item", uid, 0)
            slot_index[key] = len(var_slots)
            var_slots.append(key)

    if not var_slots:
        return True, 0.0

    # ── Constraint filter ──────────────────────────────────────────────────
    # Rotation-only constraints (PARALLEL / PERPENDICULAR / EQUAL) and FIXED
    # are delegated to the warm-start pass; Newton handles position/distance
    # residuals only.
    active: list[Constraint] = [
        c
        for c in constraints
        if c.constraint_type
        not in (
            ConstraintType.PARALLEL,
            ConstraintType.PERPENDICULAR,
            ConstraintType.EQUAL,
            ConstraintType.FIXED,
        )
    ]
    if not active:
        return True, 0.0

    # ── State accessors ────────────────────────────────────────────────────
    def read_x() -> np.ndarray:
        x = np.zeros(len(var_slots) * 2)
        for i, key in enumerate(var_slots):
            p = positions[key[1]] if key[0] == "item" else vertex_pos[(key[1], key[2])]
            x[2 * i] = p[0]
            x[2 * i + 1] = p[1]
        return x

    def write_x(x: np.ndarray) -> None:
        for i, key in enumerate(var_slots):
            p = positions[key[1]] if key[0] == "item" else vertex_pos[(key[1], key[2])]
            p[0] = float(x[2 * i])
            p[1] = float(x[2 * i + 1])

    def anchor_xy(
        x: np.ndarray, item_id: UUID, anchor: AnchorRef
    ) -> tuple[float, float]:
        if (
            item_id in deformable_items
            and anchor.anchor_type in _VERTEX_TYPES
            and ("vertex", item_id, anchor.anchor_index) in slot_index
        ):
            idx = slot_index[("vertex", item_id, anchor.anchor_index)]
            return float(x[2 * idx]), float(x[2 * idx + 1])
        off = anchor_offsets.get(
            (item_id, anchor.anchor_type, anchor.anchor_index), (0.0, 0.0)
        )
        if ("item", item_id, 0) in slot_index:
            idx = slot_index[("item", item_id, 0)]
            return float(x[2 * idx]) + off[0], float(x[2 * idx + 1]) + off[1]
        # Pinned item — constant wrt x.
        if item_id in positions:
            p = positions[item_id]
            return p[0] + off[0], p[1] + off[1]
        return 0.0, 0.0

    def eval_residuals(x: np.ndarray) -> np.ndarray:
        F: list[float] = []
        for c in active:
            ct = c.constraint_type
            ax, ay = anchor_xy(x, c.anchor_a.item_id, c.anchor_a)
            bx, by = anchor_xy(x, c.anchor_b.item_id, c.anchor_b)

            if ct in (ConstraintType.EDGE_LENGTH, ConstraintType.DISTANCE):
                F.append(
                    math.sqrt((ax - bx) ** 2 + (ay - by) ** 2) - c.target_distance
                )
            elif ct == ConstraintType.HORIZONTAL:
                F.append(ay - by)
            elif ct == ConstraintType.VERTICAL:
                F.append(ax - bx)
            elif ct == ConstraintType.HORIZONTAL_DISTANCE:
                current = bx - ax
                sign = 1.0 if current >= 0.0 else -1.0
                F.append(current - sign * c.target_distance)
            elif ct == ConstraintType.VERTICAL_DISTANCE:
                current = by - ay
                sign = 1.0 if current >= 0.0 else -1.0
                F.append(current - sign * c.target_distance)
            elif ct == ConstraintType.COINCIDENT:
                F.append(ax - bx)
                F.append(ay - by)
            elif ct == ConstraintType.SYMMETRY_HORIZONTAL:
                axis_y = c.target_distance
                F.append(bx - ax)
                F.append(ay + by - 2.0 * axis_y)
            elif ct == ConstraintType.SYMMETRY_VERTICAL:
                axis_x = c.target_distance
                F.append(by - ay)
                F.append(ax + bx - 2.0 * axis_x)
            elif ct == ConstraintType.POINT_ON_EDGE:
                if c.anchor_c is None:
                    F.append(0.0)
                    continue
                cx, cy = anchor_xy(x, c.anchor_c.item_id, c.anchor_c)
                edx, edy = cx - bx, cy - by
                edge_sq = edx * edx + edy * edy
                if edge_sq < 1e-12:
                    F.append(0.0)
                    continue
                cross = (ax - bx) * edy - (ay - by) * edx
                F.append(cross / math.sqrt(edge_sq))
            elif ct == ConstraintType.POINT_ON_CIRCLE:
                F.append(
                    math.sqrt((ax - bx) ** 2 + (ay - by) ** 2) - c.target_distance
                )
            elif ct == ConstraintType.ANGLE:
                if c.anchor_c is None:
                    F.append(0.0)
                    continue
                cx, cy = anchor_xy(x, c.anchor_c.item_id, c.anchor_c)
                ba_x, ba_y = ax - bx, ay - by
                bc_x, bc_y = cx - bx, cy - by
                ba_len = math.sqrt(ba_x * ba_x + ba_y * ba_y)
                bc_len = math.sqrt(bc_x * bc_x + bc_y * bc_y)
                if ba_len < 1e-9 or bc_len < 1e-9:
                    F.append(0.0)
                    continue
                cos_val = (ba_x * bc_x + ba_y * bc_y) / (ba_len * bc_len)
                cos_val = max(-1.0, min(1.0, cos_val))
                angle_err = math.acos(cos_val) - math.radians(c.target_distance)
                # Scale to cm-equivalent so the cm-scale tolerance applies uniformly.
                F.append(angle_err * min(ba_len, bc_len))
            # Unhandled types intentionally contribute no residual — the warm-start
            # handled them, and Newton adjusts only position residuals here.
        return np.asarray(F, dtype=float)

    # ── Main Newton loop ───────────────────────────────────────────────────
    x = read_x()
    F = eval_residuals(x)
    max_err = float(np.max(np.abs(F))) if F.size > 0 else 0.0
    if max_err <= tol:
        return True, max_err

    n = x.size
    for _iteration in range(max_iter):
        # Numerical Jacobian (central differences).
        m = F.size
        jac = np.zeros((m, n))
        for j in range(n):
            saved = x[j]
            x[j] = saved + _JACOBIAN_H
            f_plus = eval_residuals(x)
            x[j] = saved - _JACOBIAN_H
            f_minus = eval_residuals(x)
            x[j] = saved
            jac[:, j] = (f_plus - f_minus) / (2.0 * _JACOBIAN_H)

        # Least-squares step (handles rank-deficient / over-determined systems).
        dx, *_ = np.linalg.lstsq(jac, -F, rcond=None)

        # Armijo backtracking: accept the shortest step that strictly reduces max|F|.
        alpha = 1.0
        accepted = False
        for _ in range(15):
            x_trial = x + alpha * dx
            F_trial = eval_residuals(x_trial)
            err_trial = (
                float(np.max(np.abs(F_trial))) if F_trial.size > 0 else 0.0
            )
            if err_trial < max_err - 1e-9:
                x = x_trial
                F = F_trial
                max_err = err_trial
                accepted = True
                break
            alpha *= 0.5
        if not accepted:
            break
        if max_err <= tol:
            break

    write_x(x)
    return max_err <= tol, max_err
