"""The greenhouse's glazing bay — one constant for its 2D bars and its 3D frame (#768).

A glasshouse's walls and roof are divided into bays of about ``BAY_CM`` along the
ridge: the 3D builder puts an aluminium bar at every bay line
(``core.scene3d.builders.structures._greenhouse_box``) and the 2D painter draws
the same lines over the glass (``ui.canvas.items.greenhouse_paint``). One module
owns the count so the picture and the model cannot disagree.

Qt-free: floats and ints only.
"""

from __future__ import annotations

from typing import Final

#: One glazing bay, centre to centre, in cm.
BAY_CM: Final = 60.0
#: Fewer bays than this make a toy; more than ``MAX_BAYS`` would flood the 3D
#: frame (the builder's ``MAX_REPEATS`` divided by the bars it emits per bay).
MIN_BAYS: Final = 2
MAX_BAYS: Final = 20
#: The anodised-aluminium ridge (#768): body and shadow tone, shared by the 2D
#: ridge cap, the 3D cap and the ``ROOF_RIDGE`` polyline.
RIDGE_ALUMINIUM_HEX: Final = "#B0B5B9"
RIDGE_ALUMINIUM_SHADOW_HEX: Final = "#9EA3A8"


def bay_count(length_cm: float) -> int:
    """How many bays a run of ``length_cm`` is divided into: ``BAY_CM`` each,
    rounded to the nearest whole bay, held between ``MIN_BAYS`` and ``MAX_BAYS``."""
    if not length_cm > 0.0:
        return MIN_BAYS
    return min(MAX_BAYS, max(MIN_BAYS, round(length_cm / BAY_CM)))


__all__ = [
    "BAY_CM", "MAX_BAYS", "MIN_BAYS", "RIDGE_ALUMINIUM_HEX",
    "RIDGE_ALUMINIUM_SHADOW_HEX", "bay_count",
]
