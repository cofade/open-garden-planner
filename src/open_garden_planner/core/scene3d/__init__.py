"""Qt-free 3D scene core (Phase 17 L1.1, #385, ADR-059; concept: §8.29).

The pipeline::

    live canvas items ──snapshot_records()──▶ {item_id: Record}      (ui/view3d/snapshot.py)
                                                   │ diff() against the last snapshot
                                                   ▼
                              SceneSync.apply ──▶ builders (added + geometry only)
                                                   │ MeshPart, item-local frame
                                                   ▼
                                               EngineSink   (Qt Quick 3D: L1.2 · RecordingSink: tests)

Modules: ``record`` (the contract: ``Record``, ``Transform``, ``Material``,
``Params``, three signatures), ``scene_diff`` (the diff), ``frame`` (scene ↔ engine, local ↔
scene), ``mesh``, ``sink``, ``build`` (builder seam + default prism builder),
``sync``, ``color``, ``interleave`` (a mesh as the bytes an engine uploads —
L1.2). Nothing here imports Qt (pinned by an AST scan); numpy and
the standard library only.

The production builders are the sub-package ``builders`` (L1.6: buildings,
fences, walls, beds, hedges — ``builders.production_registry()``). It is not
re-exported here: a consumer of the contract does not need the built world.

The pre-L1.1 contract of the Qt 3D window (``legacy``: ``Scene3DRecord``,
``extrude_footprint``, the scalar ``to_engine_frame``) was deleted with that window
in L1.10; the two functions contract v2 shares with it stay: ``triangulate_polygon``
in ``polygon`` (plane polygons — orientation, outer rings and holes, triangulation)
and ``sun_direction_scene`` in ``frame``. The module of ``diff``
is ``scene_diff``, so that ``core.scene3d.diff`` is one thing: the function.

Since L1.5: ``ground`` — the plan's flat surfaces as tiles of plain data
(``GroundGrid``, ``GroundTile``, ``GroundBaking``); ``record`` carries what the 2D
paint of an item needs (``Paint``, ``Record.outline``), and ``SceneSync`` drives a
ground baker with the diff the builders get (the baker itself paints with
``QPainter`` and lives in ``ui/view3d/ground_bake.py``; concept: §8.29.5).

"Imports no Qt" is a statement about this package's SOURCE. Importing it still
runs ``core/__init__.py``, which loads the command system and with it PyQt6.
"""

from __future__ import annotations

from .build import (
    BUILT_HEIGHT_TOLERANCE,
    Builder,
    BuilderContractError,
    BuilderRegistry,
    default_builder,
    item_seed,
    plan_overreach,
    prism_mesh,
    verify_builder,
)
from .color import Rgba, srgb8_to_linear, srgb_channel_to_linear, srgb_to_linear
from .frame import (
    ENGINE_TO_SCENE,
    SCENE_TO_ENGINE,
    EnginePose,
    LocalFrame,
    engine_model_matrix,
    engine_pose,
    engine_to_scene_points,
    engine_to_scene_vectors,
    local_frame,
    pose_point,
    pose_points,
    pose_ring,
    scene_to_engine_points,
    scene_to_engine_vectors,
    sun_direction_scene,
)
from .interleave import (
    COLOR_OFFSET,
    NORMAL_OFFSET,
    POSITION_OFFSET,
    UV_OFFSET,
    VERTEX_STRIDE,
    EngineBuffers,
    engine_buffers,
)
from .mesh import (
    BENT_NORMAL_KINDS,
    FLAT_NORMAL_MIN_DOT,
    MATERIAL_KINDS,
    Mesh,
    MeshError,
    MeshPart,
    normal_vs_winding,
)
from .polygon import (
    Region,
    RegionTooLargeError,
    ccw,
    cut_region,
    cut_work,
    cw,
    exceeds_work_bound,
    group_rings,
    is_buildable_region,
    is_flat_ring,
    is_region_too_large,
    is_simple_ring,
    point_in_regions,
    point_in_ring,
    region_work,
    regions_area,
    ring_area,
    signed_area,
    triangulate_polygon,
    triangulate_region,
)
from .record import (
    ANGLE_DECIMALS,
    DIMENSIONLESS_PARAMS,
    EMPTY_PARAMS,
    FALLBACK_RGBA,
    GEOMETRY_FIELDS,
    LENGTH_DECIMALS,
    MATERIAL_FIELDS,
    MAX_LENGTH_CM,
    MIN_HEIGHT_CM,
    PARAM_CONTAINER_MATERIAL,
    PARAM_OUTLINE_RESOLVED,
    PARAM_PATH_STYLE,
    PARAM_PLANT_CATEGORY,
    PARAM_RADIUS_CM,
    PARAM_RIDGE,
    PARAM_SEED,
    PARAM_SPECIES_KEY,
    PARAM_SPECIES_NAME,
    PARAM_SPRITE_SPECIES,
    SHAPE_CIRCLE,
    SHAPE_ELLIPSE,
    SHAPE_POLYGON,
    SHAPE_POLYLINE,
    SHAPE_RECTANGLE,
    SHAPES,
    SIGNATURE_FIELDS,
    TRANSFORM_FIELDS,
    UNSIGNED_FIELDS,
    Material,
    Params,
    ParamValue,
    Point,
    Record,
    RecordRangeError,
    Ring,
    Transform,
    quantize_cm,
    quantize_deg,
)
from .scene_diff import SceneDiff, diff
from .sink import (
    EngineSink,
    GroundSpec,
    RecordingSink,
    SinkCall,
    SinkItem,
    SinkProtocolError,
    SinkState,
    SunState,
)
from .sync import BuildFailure, SceneSync, SyncStateError

__all__ = [
    "ANGLE_DECIMALS",
    "BENT_NORMAL_KINDS",
    "BUILT_HEIGHT_TOLERANCE",
    "COLOR_OFFSET",
    "EMPTY_PARAMS",
    "ENGINE_TO_SCENE",
    "FALLBACK_RGBA",
    "FLAT_NORMAL_MIN_DOT",
    "GEOMETRY_FIELDS",
    "LENGTH_DECIMALS",
    "MATERIAL_FIELDS",
    "MATERIAL_KINDS",
    "NORMAL_OFFSET",
    "PARAM_CONTAINER_MATERIAL",
    "PARAM_OUTLINE_RESOLVED",
    "PARAM_PATH_STYLE",
    "PARAM_PLANT_CATEGORY",
    "PARAM_RADIUS_CM",
    "PARAM_RIDGE",
    "PARAM_SEED",
    "PARAM_SPECIES_KEY",
    "PARAM_SPECIES_NAME",
    "PARAM_SPRITE_SPECIES",
    "POSITION_OFFSET",
    "SCENE_TO_ENGINE",
    "SHAPES",
    "SHAPE_CIRCLE",
    "SHAPE_ELLIPSE",
    "SHAPE_POLYGON",
    "SHAPE_POLYLINE",
    "SHAPE_RECTANGLE",
    "SIGNATURE_FIELDS",
    "TRANSFORM_FIELDS",
    "UNSIGNED_FIELDS",
    "UV_OFFSET",
    "VERTEX_STRIDE",
    "BuildFailure",
    "Builder",
    "BuilderContractError",
    "BuilderRegistry",
    "EngineBuffers",
    "EnginePose",
    "EngineSink",
    "GroundSpec",
    "LocalFrame",
    "Material",
    "Mesh",
    "MeshError",
    "MeshPart",
    "ParamValue",
    "Params",
    "Point",
    "Record",
    "RecordRangeError",
    "RecordingSink",
    "Region",
    "Rgba",
    "Ring",
    "SceneDiff",
    "SceneSync",
    "SinkCall",
    "SinkItem",
    "SinkProtocolError",
    "SinkState",
    "SunState",
    "SyncStateError",
    "Transform",
    "ccw",
    "cut_region",
    "cw",
    "default_builder",
    "diff",
    "engine_buffers",
    "engine_model_matrix",
    "engine_pose",
    "engine_to_scene_points",
    "engine_to_scene_vectors",
    "group_rings",
    "is_buildable_region",
    "is_flat_ring",
    "is_simple_ring",
    "item_seed",
    "local_frame",
    "normal_vs_winding",
    "plan_overreach",
    "point_in_regions",
    "point_in_ring",
    "pose_point",
    "pose_points",
    "pose_ring",
    "prism_mesh",
    "quantize_cm",
    "quantize_deg",
    "regions_area",
    "ring_area",
    "scene_to_engine_points",
    "scene_to_engine_vectors",
    "signed_area",
    "srgb8_to_linear",
    "srgb_channel_to_linear",
    "srgb_to_linear",
    "sun_direction_scene",
    "triangulate_polygon",
    "triangulate_region",
    "verify_builder",
]
# Appended, not sorted into the list above: the engine package (L1.2) inserts a name at the
# very line this one would take, and two insertions at one line do not merge.
__all__ += ["MAX_LENGTH_CM"]
# … and what fix round 3 added, for the same reason. (``polygon.MAX_REGION_WORK`` is
# deliberately not re-exported: a copy of it here would not follow the module's own.)
__all__ += [
    "DIMENSIONLESS_PARAMS",
    "MIN_HEIGHT_CM",
    "RegionTooLargeError",
    "cut_work",
    "exceeds_work_bound",
    "is_region_too_large",
    "region_work",
]
# The ground bake (L1.5): the tiles of ``ground`` and a record's ``Paint`` — imported and
# listed down here, in a block of their own, for the same reason.
from .ground import (  # noqa: E402
    MAX_GROUND_PIXELS,
    MEADOW_RGB,
    TILE_PX,
    GroundBaking,
    GroundGrid,
    GroundTile,
    TileKey,
    changed_tiles,
)
from .record import (  # noqa: E402
    PARAM_PAINT_ORIGIN,
    PEN_CAPS,
    PEN_JOINS,
    PEN_STYLES,
    Paint,
)

__all__ += [
    "MAX_GROUND_PIXELS",
    "MEADOW_RGB",
    "PARAM_PAINT_ORIGIN",
    "PEN_CAPS",
    "PEN_JOINS",
    "PEN_STYLES",
    "TILE_PX",
    "GroundBaking",
    "GroundGrid",
    "GroundTile",
    "Paint",
    "TileKey",
    "changed_tiles",
]
