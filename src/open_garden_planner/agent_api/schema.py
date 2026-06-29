"""Curated, stable data shapes the Agent API exposes to MCP clients.

These pydantic models are an API contract for agents — intentionally decoupled
from the on-disk ``.ogp`` format (``FILE_VERSION``) so the file format can
evolve without breaking agent integrations. Field descriptions are English on
purpose: they are read by agents, not shown in the UI, and are therefore exempt
from the project's i18n rules.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PlanSummary(BaseModel):
    """A high-level overview of the garden plan currently open in the app."""

    file_name: str | None = Field(
        default=None,
        description=(
            "Project file name (e.g. 'my_garden.ogp'), or null if the plan has "
            "not been saved yet."
        ),
    )
    is_dirty: bool = Field(
        description="True if the plan has unsaved changes.",
    )
    canvas_width_cm: float = Field(
        description="Width of the plan canvas in centimetres.",
    )
    canvas_height_cm: float = Field(
        description="Height of the plan canvas in centimetres.",
    )
    bed_count: int = Field(
        description=(
            "Number of soil-bearing beds/containers (garden beds, raised beds, "
            "containers, wall planters)."
        ),
    )
    plant_count: int = Field(
        description="Number of plants (trees, shrubs, perennials).",
    )
    shape_count: int = Field(
        description=(
            "Number of other objects (structures, paths, generic shapes, "
            "annotations, etc.)."
        ),
    )
    layer_names: list[str] = Field(
        default_factory=list,
        description="Names of the layers in the plan, in order.",
    )
