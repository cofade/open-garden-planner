"""Compatibility identity for :mod:`open_garden_planner.models.parametric_eval` (ADR-068)."""

import sys
from typing import TYPE_CHECKING

from open_garden_planner.models import parametric_eval as _implementation

if TYPE_CHECKING:
    from open_garden_planner.models.parametric_eval import *  # noqa: F403

# Share mutable globals as well as functions: isolation must reach the factory.
sys.modules[__name__] = _implementation
