"""The choices of the 3D pane's Analyze menu (Phase 17 L2, #386) — and nothing else.

Its own module on purpose: the workspace builds the menu's actions with the main
window, long before 3D is first asked for, and the workspace must load no engine
module then (gate G1, ``tests/integration/test_view3d_workspace.py``). The analysis
itself (``analysis_controller``) and the growth jump (``growth_jump``, which knows the
host's state contract) are imported only with the engine.
"""

from __future__ import annotations

import enum
from typing import Final


class DrapeMode(enum.Enum):
    """What lies on the 3D ground."""

    NONE = "none"
    SHADOWS = "shadows"
    SUN_HOURS = "sun_hours"


#: The growth jumps the 3D pane offers, in years (L2.3).
JUMP_YEARS: Final = (1, 3, 10)
