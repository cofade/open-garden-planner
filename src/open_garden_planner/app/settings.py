"""Compatibility identity for :mod:`open_garden_planner.config.settings` (ADR-068)."""

import sys
from typing import TYPE_CHECKING

from open_garden_planner.config import settings as _implementation

if TYPE_CHECKING:
    from open_garden_planner.config.settings import *  # noqa: F403

# Share mutable globals as well as functions: isolation must reach the factory.
sys.modules[__name__] = _implementation
