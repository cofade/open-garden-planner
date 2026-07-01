"""Curated, stable data shapes the Agent API exposes to MCP clients.

These pydantic models are an API contract for agents — intentionally decoupled
from the on-disk ``.ogp`` format (``FILE_VERSION``) so the file format can
evolve without breaking agent integrations. Field descriptions are English on
purpose: they are read by agents, not shown in the UI, and are therefore exempt
from the project's i18n rules.
"""

from __future__ import annotations

from typing import Any

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


# --- US-D1.2: read / query tools -------------------------------------------
#
# Coordinates are in the plan's native scene frame: centimetres, origin at the
# top-left, +x right and +y DOWN (the Qt scene frame the file format stores).
# This is the same frame used by every object's stored position. (Aligning the
# y-axis with the rendered canvas image is deferred to US-D1.3, where the render
# tool lands and the two can be reconciled together.) Non-rectangular shapes are
# summarised by their axis-aligned bounding box.


class ObjectRef(BaseModel):
    """Lightweight reference to one object, returned by list/spatial queries."""

    item_id: str = Field(description="Stable UUID — address objects by this id.")
    type: str = Field(
        description="Geometry kind: 'rectangle', 'circle', 'ellipse', 'polygon', "
        "'polyline', 'group', etc.",
    )
    object_type: str | None = Field(
        default=None,
        description="Semantic type name (e.g. 'RAISED_BED', 'TREE', 'CONTAINER'), "
        "or null for a plain shape.",
    )
    name: str | None = Field(default=None, description="User-given label, if any.")
    layer_name: str | None = Field(
        default=None, description="Name of the layer the object is on, if assigned."
    )
    center_x_cm: float = Field(description="Bounding-box centre X, in scene cm.")
    center_y_cm: float = Field(description="Bounding-box centre Y, in scene cm.")
    width_cm: float = Field(description="Bounding-box width in cm (0 for a point).")
    height_cm: float = Field(description="Bounding-box height in cm (0 for a point).")


class ObjectDetail(ObjectRef):
    """Full single-object view, returned by ``get_object``."""

    rotation_deg: float = Field(
        default=0.0, description="Rotation in degrees (0 if not rotated)."
    )
    area_cm2: float = Field(
        description="Object area in cm² (exact for circle/ellipse/polygon/rectangle; "
        "bounding-box area otherwise).",
    )
    fill_color: str | None = Field(
        default=None, description="Fill colour as #AARRGGBB hex, if the shape has a fill."
    )
    stroke_color: str | None = Field(
        default=None, description="Stroke/outline colour as #AARRGGBB hex."
    )
    parent_bed_id: str | None = Field(
        default=None, description="UUID of the bed/container this object sits in, if any."
    )
    child_item_ids: list[str] = Field(
        default_factory=list,
        description="UUIDs of objects contained in this bed/container (if it is one).",
    )
    species_key: str | None = Field(
        default=None,
        description="Species/gallery key for a plant (e.g. an SVG key), if assigned.",
    )
    species_name: str | None = Field(
        default=None,
        description="Human-readable species name for a plant (common or scientific), "
        "if assigned.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Raw per-object metadata (species record, container settings, etc.).",
    )


class Diagnostic(BaseModel):
    """One already-computed plan warning, mirroring an on-canvas badge."""

    kind: str = Field(
        description="One of: 'companion_conflict', 'spacing_overlap', 'soil_mismatch', "
        "'capacity_overrun', 'crop_rotation'.",
    )
    severity: str = Field(description="'info', 'warning', or 'critical'.")
    item_ids: list[str] = Field(
        default_factory=list, description="UUIDs of the objects this warning concerns."
    )
    message: str = Field(description="Short English description of the issue.")


class Measurement(BaseModel):
    """Distance between two objects' bounding-box centres."""

    distance_cm: float = Field(description="Straight-line centre-to-centre distance, cm.")
    dx_cm: float = Field(description="X offset (object B centre − object A centre), cm.")
    dy_cm: float = Field(description="Y offset (object B centre − object A centre), cm.")


# --- US-D1.3: vision tool ---------------------------------------------------
#
# render_canvas_image renders with y_flip=True (matching the live CAD view and
# every existing PNG/PDF export), which INVERTS the D1.2 y-down scene frame in
# the output pixel buffer — see RenderMeta.px_per_cm below for the correction
# formula. Empirically verified in
# tests/unit/test_agent_api_render_coordinate_frame.py.


class RenderMeta(BaseModel):
    """Structured metadata alongside a ``render_canvas_image`` PNG."""

    region_x_cm: float = Field(description="Left edge of the rendered region, scene cm.")
    region_y_cm: float = Field(
        description="Top edge of the rendered region, scene cm (native D1.2 frame)."
    )
    region_width_cm: float = Field(description="Rendered region width, cm.")
    region_height_cm: float = Field(description="Rendered region height, cm.")
    image_width_px: int = Field(description="Output image width, pixels.")
    image_height_px: int = Field(description="Output image height, pixels.")
    px_per_cm: float = Field(
        description="Pixels per cm (uniform — aspect ratio preserved). Maps a "
        "D1.2 object position (scene cm, +y down) to a pixel in this image: "
        "px_x = (x_cm - region_x_cm) * px_per_cm; "
        "px_y = image_height_px - (y_cm - region_y_cm) * px_per_cm "
        "(the image is Y-up/CAD-style like the live canvas view, so the D1.2 "
        "y-down frame is inverted relative to pixel rows)."
    )
    layers_rendered: list[str] | None = Field(
        default=None,
        description="Layer names included, or null if all currently-visible "
        "layers were rendered.",
    )
