"""Illustrative fallback heights for plants with unknown height (#557).

When a plan gives a plant NO usable height (no species data, no
measured/current size, no explicit height), the 3D view previously showed a
pale low marker. A tree then reads as a white patch on the ground. This module
provides ONE canonical category table so the 3D view can render the matching
plant form at a documented illustrative height instead.

Contract (explicit product-policy decision, #557):

- The values below are ILLUSTRATIVE, not measured. They must never be written
  into species data, instance measurements, or the saved plan — the plan keeps
  ``height_cm is None`` (unknown stays unknown).
- The estimate lives only on the transient 3D record
  (``params["estimated_height_cm"]``). Viewing 3D mutates nothing and adds no
  undo step.
- The estimate drives DECORATIVE 3D geometry (and its shadow) only. The
  analytical 2D sun/shade model keeps treating the height as unknown
  (``effective_height_cm`` still returns ``None``).
- The UI must label the dimension as estimated wherever it is shown.
"""

from __future__ import annotations

ESTIMATED_HEIGHT_PARAM: str = "estimated_height_cm"

# Illustrative heights in cm, by plant category group. Documented, not measured.
_TREE_CATEGORIES = frozenset(
    {
        "ROUND_DECIDUOUS",
        "COLUMNAR_TREE",
        "WEEPING_TREE",
        "CONIFER",
        "FRUIT_TREE",
        "PALM",
    }
)
_SHRUB_CATEGORIES = frozenset(
    {
        "SPREADING_SHRUB",
        "COMPACT_SHRUB",
        "HEDGE_SECTION",
        "CLIMBING_PLANT",
    }
)
_PERENNIAL_CATEGORIES = frozenset(
    {
        "FLOWERING_PERENNIAL",
        "ORNAMENTAL_GRASS",
        "GROUND_COVER",
    }
)
_VEGETABLE_CATEGORIES = frozenset({"VEGETABLE", "HERB"})

#: Canonical illustrative heights (cm) by group. Record kinds are only
#: TREE/SHRUB/PERENNIAL, so the "vegetable" entry is reached through the
#: category path (a VEGETABLE-category plant on a perennial record reads
#: 50 cm); it stays in the table so a future vegetable kind resolves sanely.
CATEGORY_ESTIMATED_HEIGHTS_CM: dict[str, float] = {
    "tree": 400.0,
    "shrub": 150.0,
    "perennial": 60.0,
    "vegetable": 50.0,
}


def estimated_height_cm(kind: str | None, category: str | None) -> float | None:
    """Return the illustrative fallback height for a plant, or None.

    Args:
        kind: Record kind (e.g. ``"tree"``, ``"shrub"``, ``"perennial"``).
        category: Plant category name (e.g. ``"ROUND_DECIDUOUS"``).

    Resolution: category group first (a shrub-category plant on a perennial
    record still reads as a shrub), then kind, defaulting to perennial scale.
    Returns None for non-plant kinds.
    """
    cat = (category or "").upper()
    if cat in _TREE_CATEGORIES:
        return CATEGORY_ESTIMATED_HEIGHTS_CM["tree"]
    if cat in _SHRUB_CATEGORIES:
        return CATEGORY_ESTIMATED_HEIGHTS_CM["shrub"]
    if cat in _PERENNIAL_CATEGORIES:
        return CATEGORY_ESTIMATED_HEIGHTS_CM["perennial"]
    if cat in _VEGETABLE_CATEGORIES:
        return CATEGORY_ESTIMATED_HEIGHTS_CM["vegetable"]
    k = (kind or "").lower()
    if k == "tree":
        return CATEGORY_ESTIMATED_HEIGHTS_CM["tree"]
    if k == "shrub":
        return CATEGORY_ESTIMATED_HEIGHTS_CM["shrub"]
    if k == "perennial":
        return CATEGORY_ESTIMATED_HEIGHTS_CM["perennial"]
    return None
