"""Plants stand on their parent (Phase 17 L1.6, #385 — gates G3 and G4's drift guard).

Truth gate "Base" (``ogp-lush-cinematic`` §1): a plant in a raised bed or a
container stands on the soil, not inside the box. The rule lives ONCE —
``core.object_height.standing_base_cm`` behind ``ui.canvas.footprints.item_base_cm``
— and is asked by

- ``snapshot_records`` → a record's ``transform.base_cm`` (3D), and
- ``collect_shadow_casters`` → ``ShadowCaster.base_cm`` (the 2D shadow overlay
  and the hours-of-sun heatmap).

Everything here goes through a real scene, real items and the app's own commands.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import math
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PyQt6.QtCore import QPointF

import open_garden_planner
from open_garden_planner.core import ProjectManager
from open_garden_planner.core.alignment import AlignMode
from open_garden_planner.core.commands import (
    ChangePropertyCommand,
    CreateItemCommand,
    MoveItemsCommand,
    ResizeItemCommand,
    SetParentBedCommand,
)
from open_garden_planner.core.object_height import METADATA_KEY, SOIL_DROP_CM
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.scene3d import (
    BuilderRegistry,
    MeshPart,
    Record,
    RecordingSink,
    SceneDiff,
    SceneSync,
    default_builder,
    diff,
)
from open_garden_planner.core.shade_aggregation import (
    SAMPLE_STEP_MINUTES,
    HeatmapGrid,
    daylight_samples,
)
from open_garden_planner.core.shadow_geometry import (
    ShadowCaster,
    compute_scene_shadows,
    shadow_direction_scene,
)
from open_garden_planner.core.solar import solar_position
from open_garden_planner.core.tools.base_tool import ToolType
from open_garden_planner.ui.canvas import (
    footprints,
    sun_exposure_snapshot,
    sun_heatmap,
    sun_shadow_controller,
)
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.geometry_apply import (
    apply_rect_like_geometry,
    apply_rotation,
    build_rect_resize,
)
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.sun_heatmap import SunHeatmapController
from open_garden_planner.ui.canvas.sun_shadow_controller import (
    SunShadowController,
    SunShadowOverlayItem,
    collect_shadow_casters,
)
from open_garden_planner.ui.view3d import snapshot as snapshot_module
from open_garden_planner.ui.view3d.snapshot import snapshot_records

PLANS = Path(__file__).resolve().parents[1] / "fixtures" / "plans"
JUNE = date(2026, 6, 21)
BERLIN = {"latitude": 52.52, "longitude": 13.405}
BEGIN, COMMIT = ("begin", None), ("commit", None)


class Garden:
    """A raised bed with one perennial on it, created through the command path."""

    def __init__(self, view: CanvasView, parent_type: ObjectType = ObjectType.RAISED_BED) -> None:
        self.view = view
        self.scene = view.scene()
        self.commands = view.command_manager
        layer = self.scene.active_layer.id
        if parent_type is ObjectType.CONTAINER_ROUND:
            self.bed: Any = CircleItem(500.0, 400.0, 60.0, object_type=parent_type, layer_id=layer)
        elif parent_type is ObjectType.GARDEN_BED:
            self.bed = PolygonItem(
                [QPointF(400.0, 300.0), QPointF(700.0, 300.0), QPointF(700.0, 500.0),
                 QPointF(400.0, 500.0)], object_type=parent_type, layer_id=layer)
        else:
            self.bed = RectangleItem(400.0, 300.0, 300.0, 200.0, object_type=parent_type,
                                     layer_id=layer)
        self.plant = CircleItem(500.0, 400.0, 15.0, object_type=ObjectType.PERENNIAL, layer_id=layer)
        self.plant.metadata[METADATA_KEY] = 60.0
        self.commands.execute(CreateItemCommand(self.scene, self.bed, "bed"))
        self.commands.execute(CreateItemCommand(self.scene, self.plant, "plant"))  # auto-parents
        self.bed_id, self.plant_id = str(self.bed.item_id), str(self.plant.item_id)

    def records(self) -> dict[str, Record]:
        return snapshot_records(self.scene)

    def base(self) -> float:
        return self.records()[self.plant_id].transform.base_cm

    def caster_base(self) -> float:
        (caster,) = [c for c in collect_shadow_casters(self.scene) if c.height_cm == 60.0]
        return caster.base_cm


class TestGateG3:
    def test_a_plant_in_a_40_cm_raised_bed_stands_at_38(self, canvas: CanvasView) -> None:
        """The issue's "plant in a 40 cm bed at base 40" and the style contract's
        "base = parent's effective height (- 2 cm soil drop)" are one gate: the bed
        is 40 cm tall, the soil lies 2 cm below its rim, the plant stands on the soil."""
        garden = Garden(canvas)
        records = garden.records()
        assert garden.plant.parent_bed_id == garden.bed.item_id  # the PROPERTY, set by the command
        assert "parent_bed_id" not in garden.plant.metadata
        assert records[garden.bed_id].height_cm == 40.0 and SOIL_DROP_CM == 2.0
        assert records[garden.plant_id].parent_id == garden.bed_id
        assert records[garden.plant_id].transform.base_cm == 38.0
        assert records[garden.plant_id].base_cm == 38.0
        assert records[garden.bed_id].transform.base_cm == 0.0  # the bed stands on the ground
        # the plant's own height is measured from its soil: it occupies 38 … 98 cm
        assert records[garden.plant_id].height_cm == 60.0

    def test_a_bed_height_change_reaches_the_plant_as_a_transform_only(self, canvas: CanvasView) -> None:
        garden = Garden(canvas)
        built: list[str] = []

        def build(record: Record) -> tuple[MeshPart, ...]:
            built.append(record.item_id)
            return default_builder(record)

        sink = RecordingSink()
        sync = SceneSync(sink, BuilderRegistry(default=build), validate=True)
        sync.apply(garden.records())
        assert sink.item(garden.plant_id).transform.base_cm == 38.0
        plant_parts = sink.item(garden.plant_id).parts
        sink.clear_calls()
        built.clear()

        garden.bed.metadata[METADATA_KEY] = 75.0  # the bed grows from 40 to 75 cm
        result = sync.apply(garden.records())
        assert result == SceneDiff(transform=(garden.plant_id,), geometry=(garden.bed_id,))
        assert sink.ops() == [BEGIN, ("replace_geometry", garden.bed_id),
                              ("update_transform", garden.plant_id), COMMIT]
        assert built == [garden.bed_id]  # the plant's mesh was NOT rebuilt
        held = sink.item(garden.plant_id)
        assert held.transform.base_cm == 73.0 and held.parts is plant_parts
        assert float(sink.item(garden.bed_id).parts[0].mesh.bounds()[1][2]) == 75.0

    def test_moving_the_bed_does_not_change_the_base(self, canvas: CanvasView) -> None:
        garden = Garden(canvas)
        before = garden.records()
        garden.commands.execute(MoveItemsCommand([garden.bed, garden.plant], QPointF(55.5, -20.25)))
        after = garden.records()
        assert diff(before, after) == SceneDiff(transform=(garden.bed_id, garden.plant_id))
        assert after[garden.plant_id].transform.base_cm == 38.0

    def test_the_base_is_on_the_record_grid(self, canvas: CanvasView) -> None:
        garden = Garden(canvas)
        garden.bed.metadata[METADATA_KEY] = 40.0 + 1.0 / 3.0
        assert garden.base() == round(40.0 + 1.0 / 3.0 - 2.0, 7)


PARENT_CASES = [
    # parent type, parent metadata, expected base
    (ObjectType.RAISED_BED, {}, 38.0),
    (ObjectType.RAISED_BED, {METADATA_KEY: 90.0}, 88.0),
    (ObjectType.CONTAINER, {}, 30.0),                      # a container: AT its fill height
    (ObjectType.CONTAINER, {"container_height_cm": 45.0}, 45.0),
    (ObjectType.WALL_PLANTER, {}, 30.0),
    (ObjectType.CONTAINER_ROUND, {}, 30.0),
    (ObjectType.GARDEN_BED, {}, 0.0),                      # in the ground
    (ObjectType.GARDEN_BED, {METADATA_KEY: 25.0}, 23.0),   # the user raised it
    (ObjectType.TRELLIS, {}, 0.0),                         # a plant parent without soil
]


class TestTheOneRule:
    @pytest.mark.parametrize(("parent_type", "metadata", "expected"), PARENT_CASES,
                             ids=lambda v: v.name if isinstance(v, ObjectType) else str(v))
    def test_3d_base_and_2d_caster_base_agree(
        self, canvas: CanvasView, parent_type: ObjectType, metadata: dict, expected: float
    ) -> None:
        garden = Garden(canvas, parent_type)
        garden.bed.metadata.update(metadata)
        assert garden.plant.parent_bed_id == garden.bed.item_id
        assert garden.base() == expected
        assert garden.caster_base() == expected

    def test_no_parent_is_the_ground(self, canvas: CanvasView) -> None:
        garden = Garden(canvas)
        loner = CircleItem(2000.0, 1500.0, 15.0, object_type=ObjectType.PERENNIAL)
        loner.metadata[METADATA_KEY] = 45.0
        garden.scene.addItem(loner)
        assert garden.records()[str(loner.item_id)].transform.base_cm == 0.0
        assert all(c.base_cm == 0.0 for c in collect_shadow_casters(garden.scene)
                   if c.height_cm == 45.0)

    def test_re_parenting_is_a_transform_change_and_nothing_else(self, canvas: CanvasView) -> None:
        garden = Garden(canvas)
        before = garden.records()
        garden.plant.parent_bed_id = None  # the link, not geometry
        loose = garden.records()
        assert diff(before, loose) == SceneDiff(transform=(garden.plant_id,))
        assert loose[garden.plant_id].transform.base_cm == 0.0
        garden.plant.parent_bed_id = garden.bed.item_id
        assert diff(loose, garden.records()) == SceneDiff(transform=(garden.plant_id,))
        assert garden.records() == before

    def test_a_dangling_parent_link_is_the_ground(self, canvas: CanvasView) -> None:
        garden = Garden(canvas)
        garden.scene.removeItem(garden.bed)
        assert garden.plant.parent_bed_id is not None
        assert garden.base() == 0.0 and garden.caster_base() == 0.0

    def test_a_hidden_parent_is_not_there(self, canvas: CanvasView) -> None:
        """A hidden bed has no shadow and no solid; its plants must not float above
        nothing. The rule follows what is visible, like the caster walk itself."""
        garden = Garden(canvas)
        garden.bed.setVisible(False)
        assert garden.base() == 0.0 and garden.caster_base() == 0.0
        garden.bed.setVisible(True)
        assert garden.base() == 38.0 and garden.caster_base() == 38.0

    def test_a_nonsense_parent_height_is_the_ground(self, canvas: CanvasView) -> None:
        garden = Garden(canvas)
        garden.bed.metadata[METADATA_KEY] = float("inf")
        assert garden.base() == 0.0 and garden.caster_base() == 0.0

    @pytest.mark.parametrize("height", [float("inf"), 1e6 + 1.0, 1e6 + 2.0, 1e6 + 3.0, 2e6])
    def test_a_parent_the_scene_cannot_hold_is_not_there(self, canvas: CanvasView,
                                                        height: float) -> None:
        """The HEIGHT axis. The contract holds no length beyond 10 km (``MAX_LENGTH_CM``),
        so a bed taller than that gets no record and is reported. Its plant is NOT taken
        down with it and does not float where the bed's soil would be.

        On these five heights ONE rule acts — ``object_height``'s: no base is derived
        from a height beyond the bound. Such a base would be out of the record's own
        range (measured before: a 20 km bed had no record and neither had its plant) or,
        in the 2 cm above the bound, a base of 999,999 cm over a bed that has no record.
        It acts in 2D too: the plant casts from the ground, although the bed itself still
        casts there.

        The snapshot's rule — a record whose parent got none stands on the ground —
        finds nothing left to do here: every height that costs the bed its record is
        beyond the bound already. It is pinned on the axes where it does act, in
        ``test_a_parent_without_a_record_lifts_nothing`` (review round 3, P2-3)."""
        from open_garden_planner.core.scene3d import MAX_LENGTH_CM
        from open_garden_planner.ui.view3d.snapshot import SkippedItem, SkipReason

        garden = Garden(canvas)
        garden.bed.metadata[METADATA_KEY] = height
        skipped: list[SkippedItem] = []
        records = snapshot_records(garden.scene, skipped=skipped)
        assert [(item.item_id, item.reason) for item in skipped] == [
            (garden.bed_id, SkipReason.OUT_OF_RANGE)]            # the bed: reported, no record
        assert list(records) == [garden.plant_id]                 # the plant: still there …
        assert records[garden.plant_id].transform.base_cm == 0.0  # … on the ground
        assert garden.caster_base() == 0.0                        # and it casts from the ground

        garden.bed.metadata[METADATA_KEY] = MAX_LENGTH_CM         # the tallest the scene holds
        skipped.clear()
        records = snapshot_records(garden.scene, skipped=skipped)
        assert skipped == [] and records[garden.bed_id].height_cm == MAX_LENGTH_CM
        assert records[garden.plant_id].transform.base_cm == MAX_LENGTH_CM - SOIL_DROP_CM
        assert garden.caster_base() == MAX_LENGTH_CM - SOIL_DROP_CM

    @pytest.mark.parametrize("why", ["out of range: 30 km wide", "its record failed",
                                     "its outline cannot be built"])
    def test_a_parent_without_a_record_lifts_nothing(self, canvas: CanvasView, why: str,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
        """Review round 3, P2-3 — the OTHER axes. "A parent that has no solid is not
        there" was stated as a rule and held for a parent's height only: a raised bed
        30 km WIDE got no record (``out_of_range``) while its plant's record stood at 38
        over nothing. Whether a parent is in the 3D scene is the snapshot's knowledge,
        so the snapshot settles it, for every reason a parent can be left out: a record
        whose parent got none stands on the ground.

        2D is a different view with its own facts: there the wide bed IS a caster, and
        its plant casts from the bed's soil."""
        from open_garden_planner.ui.view3d.snapshot import SkippedItem, SkipReason

        scene = canvas.scene()
        layer = scene.active_layer.id
        wide = why.startswith("out of range")
        bed = (RectangleItem(-1.5e6, 300.0, 3.0e6, 200.0, object_type=ObjectType.RAISED_BED,
                             layer_id=layer) if wide else
               RectangleItem(400.0, 300.0, 300.0, 200.0, object_type=ObjectType.RAISED_BED,
                             layer_id=layer))
        plant = CircleItem(500.0, 400.0, 15.0, object_type=ObjectType.PERENNIAL, layer_id=layer)
        plant.metadata[METADATA_KEY] = 60.0
        canvas.command_manager.execute(CreateItemCommand(scene, bed, "bed"))
        canvas.command_manager.execute(CreateItemCommand(scene, plant, "plant"))
        bed_id, plant_id = str(bed.item_id), str(plant.item_id)
        assert plant.parent_bed_id == bed.item_id  # linked, and its centre is inside
        expected = SkipReason.OUT_OF_RANGE
        if not wide:  # the bed's record fails for a reason the plan's numbers do not show
            real = snapshot_module._record_of
            failure: Exception = (ZeroDivisionError("a bed nobody can build") if why.startswith("its record")
                                  else snapshot_module._UnbuildableOutline("no reading of the outline"))
            expected = (SkipReason.RECORD_FAILED if why.startswith("its record")
                        else SkipReason.OUTLINE_UNBUILDABLE)

            def record_of(item: Any, *args: Any) -> Any:
                if item is bed:
                    raise failure
                return real(item, *args)

            monkeypatch.setattr(snapshot_module, "_record_of", record_of)

        skipped: list[SkippedItem] = []
        records = snapshot_records(scene, skipped=skipped)
        assert [(item.item_id, item.reason) for item in skipped] == [(bed_id, expected)]
        assert list(records) == [plant_id]                     # the plant keeps its record …
        assert records[plant_id].parent_id == bed_id           # … and still says whose it is …
        assert records[plant_id].transform.base_cm == 0.0      # … but stands on the ground
        # the rule the lift itself answers is unchanged: it knows nothing of records
        assert footprints.item_base_cm(plant, footprints.ItemLookup(scene.items())) == 38.0
        # 2D holds the bed (it casts), so there the plant stands on it
        casters = collect_shadow_casters(scene)
        assert sorted((caster.height_cm, caster.base_cm) for caster in casters) == [
            (40.0, 0.0), (60.0, 38.0)]

    def test_a_plant_is_grounded_whichever_of_the_two_is_stacked_higher(
        self, canvas: CanvasView, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The snapshot walks bottom to top; a parent can lie ABOVE its plant. The rule
        is applied when every record is known, so the order does not matter."""
        garden = Garden(canvas)
        garden.bed.setZValue(garden.plant.zValue() + 5.0)  # the bed is walked AFTER its plant
        order = [str(item.item_id) for item in reversed(garden.scene.items())
                 if hasattr(item, "item_id")]
        assert order.index(garden.plant_id) < order.index(garden.bed_id)
        assert garden.base() == 38.0  # with its bed in the scene: on the soil, as ever
        real = snapshot_module._record_of

        def record_of(item: Any, *args: Any) -> Any:
            if item is garden.bed:
                raise ZeroDivisionError("a bed nobody can build")
            return real(item, *args)

        monkeypatch.setattr(snapshot_module, "_record_of", record_of)
        records = snapshot_records(garden.scene)
        assert list(records) == [garden.plant_id]
        assert records[garden.plant_id].transform.base_cm == 0.0

    def test_the_base_follows_the_date_of_the_height_resolver(self, canvas: CanvasView) -> None:
        """``at_date`` reaches the parent's height exactly as it reaches the item's."""
        garden = Garden(canvas)
        seen: list[Any] = []
        original = footprints.standing_base_cm

        def spy(parent_type: Any, parent_metadata: Any, at_date: Any = None) -> float:
            seen.append(at_date)
            return original(parent_type, parent_metadata, at_date)

        footprints.standing_base_cm = spy  # type: ignore[assignment]
        try:
            snapshot_records(garden.scene, JUNE)
            collect_shadow_casters(garden.scene, at_date=JUNE)
        finally:
            footprints.standing_base_cm = original  # type: ignore[assignment]
        assert seen == [JUNE, JUNE]

    @pytest.mark.parametrize(("plan", "raised"), [("bench_small.ogp", 22), ("bench_large.ogp", 240)])
    def test_the_bench_plans(self, qtbot: Any, plan: str, raised: int) -> None:  # noqa: ARG002
        scene = CanvasScene()
        ProjectManager().load(scene, PLANS / plan)
        records = snapshot_records(scene, JUNE)
        bases = {rid: r.transform.base_cm for rid, r in records.items()}
        on_soil = [rid for rid, base in bases.items() if base > 0.0]
        assert len(on_soil) == raised
        expected = {"RAISED_BED": (40.0, 38.0), "CONTAINER_ROUND": (30.0, 30.0)}
        for rid in on_soil:
            parent = records[records[rid].parent_id or ""]
            assert (parent.height_cm, bases[rid]) == expected[parent.kind]
        in_ground = [r for r in records.values() if r.parent_id and r.transform.base_cm == 0.0]
        # an in-ground bed has no height, a trellis holds no soil: both are the ground
        assert {records[r.parent_id or ""].kind for r in in_ground} <= {"GARDEN_BED", "TRELLIS"}
        casters = collect_shadow_casters(scene, at_date=JUNE)
        assert sum(1 for c in casters if c.base_cm > 0.0) == raised
        assert {c.base_cm for c in casters} <= {0.0, 30.0, 38.0}


def _add(garden: Garden, item: Any, name: str) -> Any:
    garden.commands.execute(CreateItemCommand(garden.scene, item, name))
    return item


def _perennial(garden: Garden, x: float, y: float, height: float,
               radius: float = 15.0) -> CircleItem:
    plant = CircleItem(x, y, radius, object_type=ObjectType.PERENNIAL,
                       layer_id=garden.scene.active_layer.id)
    plant.metadata[METADATA_KEY] = height
    return plant


def _bases(garden: Garden, plant: Any) -> tuple[float, float]:
    """(3D record base, 2D caster base) of one plant, found by its unique height."""
    record = garden.records()[str(plant.item_id)]
    (caster,) = [c for c in collect_shadow_casters(garden.scene)
                 if c.height_cm == plant.metadata[METADATA_KEY]]
    return record.transform.base_cm, caster.base_cm


def _is_mapped(node: ast.AST, names: set[str]) -> bool:
    return any(
        (isinstance(sub, ast.Call) and getattr(sub.func, "attr", "") == "mapFromScene")
        or (isinstance(sub, ast.Name) and sub.id in names)
        for sub in ast.walk(node))


def contains_of_a_mapped_point(tree: ast.AST) -> set[tuple[str, int]]:
    """``(function, line)`` of every ``x.contains(p)`` whose ``p`` derives from
    ``mapFromScene`` — written as one expression (``bed.contains(bed.mapFromScene(q))``)
    or through a local name bound in the same function (``local = bed.mapFromScene(q)``,
    then ``bed.contains(local)`` or ``shape.contains(local)``), also through a second
    name, a walrus or an annotated assignment.

    LIMIT, stated: a point that reaches ``contains`` through an attribute, a container,
    a tuple unpacking, a parameter or another function's return value is not seen, and
    at module level only the one-expression spelling is."""
    hits: set[tuple[str, int]] = set()
    functions = [node for node in ast.walk(tree)
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    in_a_function = {id(node) for function in functions for node in ast.walk(function)}
    for scope in [*functions, tree]:
        names: set[str] = set()
        growing = scope is not tree
        while growing:  # a name bound to a name that was bound to a mapped point
            growing = False
            for node in ast.walk(scope):
                if isinstance(node, ast.Assign):
                    targets, value = node.targets, node.value
                elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and node.value is not None:
                    targets, value = [node.target], node.value
                else:
                    continue
                if _is_mapped(value, names):
                    for target in targets:
                        if isinstance(target, ast.Name) and target.id not in names:
                            names.add(target.id)
                            growing = True
        for node in ast.walk(scope):
            if scope is tree and id(node) in in_a_function:
                continue  # reported under its function
            if (isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "contains"
                    and node.args and _is_mapped(node.args[0], names)):
                hits.add((getattr(scope, "name", "<module>"), node.lineno))
    return hits


def _is_item_lookup_call(node: ast.AST) -> bool:
    return (isinstance(node, ast.Call)
            and getattr(node.func, "id", getattr(node.func, "attr", "")) == "ItemLookup")


#: The functions that take a lookup — the only ones a walk may hand its own to.
#: Matched by NAME (a stated limit of ``lookup_escapes``).
#: ``standing_parent`` is the membership half of ``item_base_cm`` (which calls it); the
#: sun receivers' walk asks it alone (master's US-F3, merged in L1.3's fix round 1).
LOOKUP_TAKERS = frozenset({"item_base_cm", "standing_parent", "_record_of"})


def _parent_map(tree: ast.AST) -> dict[int, ast.AST]:
    return {id(child): node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}


def item_lookup_identifiers(tree: ast.AST) -> list[tuple[str, str]]:
    """``(function, role)`` for every appearance of the identifier ``ItemLookup`` in
    ``tree``: "import" (under its own name), "import under another name", "class
    definition", "parameter annotation", "annotation of a name", "call", and "used as
    a value" for everything else — ``make = ItemLookup``, ``partial(ItemLookup, items)``,
    a base class, a return annotation, ``isinstance``. A string that is not a docstring
    and names it is "named in a string" (``getattr(module, "ItemLookup")``).

    LIMIT, stated: a spelling that never writes the identifier is not seen —
    ``type(lookup)(items)``, ``lookup.__class__``, ``copy.copy(lookup)``,
    ``getattr(module, "Item" + "Lookup")``, ``vars(module)[name]``. Comments are not
    read at all."""
    parents = _parent_map(tree)

    def function_of(node: ast.AST) -> str:
        up = parents.get(id(node))
        while up is not None:
            if isinstance(up, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return up.name
            up = parents.get(id(up))
        return "<module>"

    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    found: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        role = ""
        if isinstance(node, ast.alias):
            if node.name.split(".")[-1] == "ItemLookup" or node.asname == "ItemLookup":
                role = ("import" if node.name == "ItemLookup" and node.asname is None
                        else "import under another name")
        elif isinstance(node, ast.ClassDef) and node.name == "ItemLookup":
            role = "class definition"
        elif (isinstance(node, (ast.Name, ast.Attribute))
              and getattr(node, "id", getattr(node, "attr", "")) == "ItemLookup"):
            parent = parents.get(id(node))
            if isinstance(parent, ast.Call) and parent.func is node:
                role = "call"
            elif isinstance(parent, ast.arg):
                role = "parameter annotation"
            elif isinstance(parent, ast.AnnAssign) and parent.annotation is node:
                role = "annotation of a name"
            else:
                role = "used as a value"
        elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
              and "ItemLookup" in node.value and id(node) not in docstrings):
            role = "named in a string"
        if role:
            found.append((function_of(node), role))
    return found


def lookup_parameters(tree: ast.AST) -> list[tuple[Any, str]]:
    """``(function node, parameter name)`` for every parameter annotated ``ItemLookup``."""
    found: list[tuple[Any, str]] = []
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        spec = function.args
        for arg in (*spec.posonlyargs, *spec.args, *spec.kwonlyargs, spec.vararg, spec.kwarg):
            if arg is not None and arg.annotation is not None and any(
                    getattr(node, "id", getattr(node, "attr", "")) == "ItemLookup"
                    for node in ast.walk(arg.annotation)):
                found.append((function, arg.arg))
    return found


def lookup_escapes(function: ast.AST, name: str) -> list[str]:
    """How the lookup bound to ``name`` in ``function`` could outlive the call: one
    reason for every READ of the name that is neither

    - an argument of a call to one of ``LOOKUP_TAKERS`` — ``item_base_cm(item, lookup)`` —
    - nor a method CALL on the lookup itself — ``lookup.get(…)``, ``lookup.shape_of(…)``.

    So a list or a dict that holds it, ``kept.append(lookup)``, ``setattr(…, lookup)``,
    ``return lookup, 1``, ``self.kept += [lookup]``, a closure over it and a bound
    method taken from it (``keep = lookup.get``) are all reported.

    LIMITS, stated: a taker is matched by NAME — what another function of that name
    does with its argument is not seen; and ``locals()`` or a frame object hands out
    every local without writing its name."""
    parents = _parent_map(function)
    reasons: set[str] = set()
    for node in ast.walk(function):
        if not (isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Load)):
            continue
        scope = parents.get(id(node))
        while scope is not None and not isinstance(
                scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            scope = parents.get(id(scope))
        if scope is not None and scope is not function:
            reasons.add("used in a closure")
            continue
        parent = parents[id(node)]
        if isinstance(parent, ast.keyword):
            parent = parents[id(parent)]
        if isinstance(parent, ast.Call) and parent.func is not node:
            callee = getattr(parent.func, "id", getattr(parent.func, "attr", "")) or "an expression"
            if callee not in LOOKUP_TAKERS:
                reasons.add(f"handed to {callee}")
        elif isinstance(parent, ast.Attribute):
            call = parents.get(id(parent))
            if not (isinstance(call, ast.Call) and call.func is parent):
                reasons.add(f"attribute {parent.attr} taken without a call")
        else:
            reasons.add("used as a value")
    return sorted(reasons)


def lookups_constructed(tree: ast.AST) -> list[tuple[str, str]]:
    """``(function, problem)`` for every ``ItemLookup(...)`` constructed in ``tree``;
    ``problem`` is "" when the lookup is bound to a local name of the function that
    makes it and that name does not escape (``lookup_escapes``: it is only ever handed
    to a taker or asked itself).

    A construction this function does not recognise as one — an alias, a partial — is
    the census's to find (``item_lookup_identifiers``)."""
    functions = [node for node in ast.walk(tree)
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    found: list[tuple[str, str]] = []
    claimed: set[int] = set()
    for function in functions:
        escaping = {name for node in ast.walk(function)
                    if isinstance(node, (ast.Global, ast.Nonlocal)) for name in node.names}
        body_nodes = [node for statement in function.body for node in ast.walk(statement)]
        for node in body_nodes:
            if (isinstance(node, (ast.Assign, ast.AnnAssign)) and _is_item_lookup_call(node.value)
                    and id(node.value) not in claimed):  # a nested function: reported once
                claimed.add(id(node.value))
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if not all(isinstance(target, ast.Name) for target in targets):
                    found.append((function.name, "bound to something that is not a local name"))
                    continue
                names = {target.id for target in targets}
                if names & escaping:
                    found.append((function.name, "the local name is declared global or nonlocal: "
                                  + ", ".join(sorted(names & escaping))))
                    continue
                reasons = sorted({reason for name in names
                                  for reason in lookup_escapes(function, name)})
                found.append((function.name, "the local name escapes: " + "; ".join(reasons)
                              if reasons else ""))
        for node in body_nodes:
            if _is_item_lookup_call(node) and id(node) not in claimed:
                claimed.add(id(node))
                found.append((function.name, "not bound to a local name"))
    for node in ast.walk(tree):  # what is left: a module or class level, a default argument
        if _is_item_lookup_call(node) and id(node) not in claimed:
            found.append(("<module>", "constructed outside a function"))
    return found


class TestMembershipIsReconciledAndTheLinkAloneNeverLifts:
    """Review round 1, P1-1 / issue #443. ``parent_bed_id`` is bookkeeping, and
    since #443 every geometry edit reconciles it: creating, resizing, turning or
    vertex-editing a BED, moving a plant, copying it (paste, duplicate, array,
    mirror) and the agent all re-ask the same question. A solid is still lifted
    only when the link holds AND its centre is inside the parent's shape — an
    explicit ``set_parent_bed`` link that geometry does not support lifts
    nothing.

    (a) used to pin the stale link after a bed resize; it now pins the reconciled
    one. (c)-(d) are the nesting limits that remain: parents do not nest, so the
    smallest parent wins and the base is that parent's soil, not a sum.

    (a) and (b) changed KNOWINGLY with the #443 fix."""

    def test_a_shrinking_the_bed_away_from_its_plant_unlinks_it(
        self, canvas: CanvasView
    ) -> None:
        """Expected base 0 and NO link. WHY: the resize command reconciles the
        membership (#443 (i)), so a plant the bed no longer contains is unlinked —
        not left pointing at a bed it stands outside. The base is 0 either way
        (the lift also requires containment), but the panel, the soil-mismatch
        and the companion logic now read the truth. Undo restores link + base."""
        garden = Garden(canvas)  # bed x 400 … 700, plant centre at x = 500
        before = garden.records()
        assert _bases(garden, garden.plant) == (38.0, 38.0)

        old, new = build_rect_resize(garden.bed, 60.0, 200.0)  # the panel's and the agent's path
        garden.commands.execute(ResizeItemCommand(garden.bed, old, new, apply_rect_like_geometry))
        assert garden.bed.mapRectToScene(garden.bed.rect()).right() == 460.0
        assert garden.plant.parent_bed_id is None  # reconciled: it is not in the bed
        assert garden.plant.item_id not in garden.bed.child_item_ids
        assert not footprints.centre_is_inside(garden.plant, garden.bed)
        assert _bases(garden, garden.plant) == (0.0, 0.0)
        after = garden.records()
        # the bed: a new outline around a new centre; the plant: only its base (38 -> 0)
        assert diff(before, after) == SceneDiff(transform=(garden.bed_id, garden.plant_id),
                                                geometry=(garden.bed_id,))
        assert after[garden.plant_id].transform == dataclasses.replace(
            before[garden.plant_id].transform, base_cm=0.0)

        # the shadow starts AT the plant again: no lit gap between a plant and its own shadow
        (plant,) = [c for c in collect_shadow_casters(garden.scene) if c.height_cm == 60.0]
        direction = shadow_direction_scene(180.0)
        shadow = compute_scene_shadows([plant], 15.0, 180.0)
        near = min(x * direction[0] + y * direction[1] for polygon in shadow for x, y in polygon)
        footprint_far = max(x * direction[0] + y * direction[1] for x, y in plant.footprint)
        assert near < footprint_far  # round 0: near - footprint_far == 111.8 cm of lit ground

        garden.commands.undo()  # the bed is 3 m wide again: the plant is back on its soil
        assert garden.plant.parent_bed_id == garden.bed.item_id
        assert _bases(garden, garden.plant) == (38.0, 38.0)
        assert garden.records() == before

    def test_b_a_bed_drawn_around_a_plant_lifts_it(self, canvas: CanvasView) -> None:
        """Expected base 38 and a link. WHY: creating a bed now reconciles every
        plant's membership (#443 (i)), so a plant that geometrically stands inside
        the new bed is linked — the plan no longer depends on whether the bed or
        the plant was drawn first."""
        scene = canvas.scene()
        layer = scene.active_layer.id
        plant = CircleItem(500.0, 400.0, 15.0, object_type=ObjectType.PERENNIAL, layer_id=layer)
        plant.metadata[METADATA_KEY] = 60.0
        canvas.command_manager.execute(CreateItemCommand(scene, plant, "plant"))
        bed = RectangleItem(400.0, 300.0, 300.0, 200.0, object_type=ObjectType.RAISED_BED,
                            layer_id=layer)
        canvas.command_manager.execute(CreateItemCommand(scene, bed, "bed"))
        assert footprints.centre_is_inside(plant, bed)
        assert plant.parent_bed_id == bed.item_id
        assert plant.item_id in bed.child_item_ids
        assert snapshot_records(scene)[str(plant.item_id)].transform.base_cm == 38.0
        assert [c.base_cm for c in collect_shadow_casters(scene) if c.height_cm == 60.0] == [38.0]

        # Undo removes the bed AND restores the plant to the ground, in one step.
        canvas.command_manager.undo()
        assert plant.parent_bed_id is None
        assert snapshot_records(scene)[str(plant.item_id)].transform.base_cm == 0.0

    def test_c_a_climber_on_a_trellis_inside_a_raised_bed_stays_on_the_ground(
        self, canvas: CanvasView
    ) -> None:
        """Expected: climber 0, its neighbour in the same bed 38 — a KNOWN LIMIT. WHY:
        a plant is linked to the SMALLEST parent that contains it
        (``find_smallest_bed_containing``), which is the trellis; a trellis holds no
        soil and has no base of its own (parents do not nest), so the rule has
        nothing to lift the climber onto."""
        garden = Garden(canvas)  # bed 400 … 700 x 300 … 500 with a plant at (500, 400)
        trellis = _add(garden, RectangleItem(560.0, 440.0, 120.0, 40.0, object_type=ObjectType.TRELLIS,
                                             layer_id=garden.scene.active_layer.id), "trellis")
        climber = _add(garden, _perennial(garden, 620.0, 460.0, 61.0), "climber")
        assert climber.parent_bed_id == trellis.item_id
        assert footprints.centre_is_inside(climber, garden.bed)  # it stands in the bed's box
        assert _bases(garden, climber) == (0.0, 0.0)
        assert _bases(garden, garden.plant) == (38.0, 38.0)      # 120 cm away, same bed
        assert garden.records()[str(trellis.item_id)].transform.base_cm == 0.0

    def test_d_a_pot_on_a_raised_bed_stands_on_the_ground_with_its_plant_at_the_pot_s_soil(
        self, canvas: CanvasView
    ) -> None:
        """Expected: plant 30 (the pot's soil: its fill height), pot 0 — a KNOWN LIMIT.
        WHY: only plants carry a parent link; a container has none, so it stands on the
        ground whatever it is drawn on, and its plant stands on the pot's own soil, not
        at 38 + 30 = 68."""
        garden = Garden(canvas)
        pot = _add(garden, CircleItem(620.0, 440.0, 30.0, object_type=ObjectType.CONTAINER_ROUND,
                                      layer_id=garden.scene.active_layer.id), "pot")
        potted = _add(garden, _perennial(garden, 620.0, 440.0, 61.0), "potted plant")
        assert potted.parent_bed_id == pot.item_id  # the smallest parent again
        records = garden.records()
        assert records[str(pot.item_id)].height_cm == 30.0
        assert records[str(pot.item_id)].transform.base_cm == 0.0
        assert records[str(pot.item_id)].parent_id is None
        assert _bases(garden, potted) == (30.0, 30.0)

    def test_an_explicit_link_without_containment_does_not_lift(self, canvas: CanvasView) -> None:
        """The agent's ``set_parent_bed`` and the panel's Link action may link a plant
        that is not in the bed (``link_is_geometric: false``). Expected base 0: the
        same predicate answers ``link_is_geometric`` and the lift (with their two
        points, which agree everywhere but in a badge's margin of a bed's edge —
        ``TestWhereAPlantStandsDoesNotDependOnABadge``)."""
        garden = Garden(canvas)
        loner = _add(garden, _perennial(garden, 1500.0, 1200.0, 61.0), "loner")
        assert loner.parent_bed_id is None
        garden.commands.execute(SetParentBedCommand(garden.scene, loner, None, garden.bed.item_id))
        assert loner.parent_bed_id == garden.bed.item_id
        assert not footprints.centre_is_inside(loner, garden.bed)
        assert _bases(garden, loner) == (0.0, 0.0)

    def test_a_plant_dragged_inside_its_bed_keeps_its_base(self, canvas: CanvasView) -> None:
        garden = Garden(canvas)
        garden.commands.execute(MoveItemsCommand([garden.plant], QPointF(150.0, 60.0)))
        assert footprints.centre_is_inside(garden.plant, garden.bed)
        assert _bases(garden, garden.plant) == (38.0, 38.0)

    def test_a_turned_bed_is_tested_in_its_own_frame(self, canvas: CanvasView) -> None:
        """Containment is Qt's (``mapFromScene`` + ``contains``), so a rotated bed
        is tested as it is drawn, not by its scene bounding box."""
        garden = Garden(canvas)
        apply_rotation(garden.bed, 45.0)  # about the bed's centre (550, 400)
        inside = _add(garden, _perennial(garden, 550.0, 400.0, 61.0), "centre")
        corner = _add(garden, _perennial(garden, 690.0, 310.0, 62.0), "old corner")
        assert _bases(garden, inside) == (38.0, 38.0)
        # (690, 310) was inside the unrotated bed and is inside its scene bounding box,
        # but not inside the turned rectangle: never linked, never lifted
        assert garden.bed.sceneBoundingRect().contains(QPointF(690.0, 310.0))
        assert corner.parent_bed_id is None
        assert _bases(garden, corner) == (0.0, 0.0)

    def test_one_point_in_bed_predicate_in_the_app(self) -> None:
        """A containment test of a point mapped into an item's frame exists ONCE as a
        bed-membership test (``footprints.shape_contains``), and each of the two points
        it is asked with has one maker. ``contains_of_a_mapped_point`` sees both
        spellings (its limit is in its docstring)."""
        src = Path(open_garden_planner.__file__).parent
        contains_sites: dict[str, set[str]] = {}
        users: dict[str, set[str]] = {}
        for path in src.rglob("*.py"):
            relative = path.relative_to(src).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for function, _line in contains_of_a_mapped_point(tree):
                contains_sites.setdefault(relative, set()).add(function)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "id", getattr(node.func, "attr", ""))
                if name in ("bed_membership_point", "standing_point", "shape_contains",
                            "centre_is_inside", "contains_path", "shape_of"):
                    users.setdefault(name, set()).add(relative)
        assert contains_sites == {
            "ui/canvas/footprints.py": {"shape_contains"},   # THE predicate
            # not a membership test: is the CURSOR inside the selected shape, i.e. which
            # way does the offset tool offset — no plant, no bed
            "core/tools/offset_tool.py": {"mouse_move", "mouse_press"},
        }
        assert users["shape_contains"] == {
            "ui/canvas/footprints.py",      # centre_is_inside (links) and item_base_cm (the lift)
            "ui/canvas/canvas_scene.py",    # find_smallest_bed_containing
        }
        assert users["bed_membership_point"] == {   # the LINK decisions' point
            "ui/canvas/footprints.py",      # inside centre_is_inside
            "core/commands.py",             # auto-parenting: create, bulk create, paste
            "ui/canvas/canvas_view.py",     # the re-link after a drag
            "app/agent_host.py",            # the agent's re-link after move_object
        }
        assert users["centre_is_inside"] == {"app/agent_host.py"}  # set_parent_bed's link_is_geometric
        assert users["standing_point"] == {
            "ui/canvas/footprints.py",      # the LIFT's point
            "ui/canvas/canvas_scene.py",    # the stacking clamp asks the SAME point (#629)
        }
        assert users["contains_path"] == {
            "ui/canvas/footprints.py",      # inside ItemLookup.shape_of
            "ui/canvas/canvas_scene.py",    # the stacking clamp's per-call shape cache (#629)
        }
        assert users["shape_of"] == {"ui/canvas/footprints.py"}        # inside item_base_cm

    @pytest.mark.parametrize(("source", "expected"), [
        ("def f(b, p):\n    return b.contains(b.mapFromScene(p))\n", [("f", 2)]),
        ("def f(b, p):\n    local = b.mapFromScene(p)\n    return b.contains(local)\n", [("f", 3)]),
        ("def f(b, p):\n    local = b.mapFromScene(p)\n    return b.shape().contains(local)\n",
         [("f", 3)]),
        ("def f(b, p):\n    local = b.mapFromScene(p)\n    again = local\n"
         "    return b.contains(again)\n", [("f", 4)]),
        ("def f(b, p):\n    return b.contains(local := b.mapFromScene(p))\n", [("f", 2)]),
        ("def f(b, p):\n    local: object = b.mapFromScene(p)\n    return b.contains(local)\n",
         [("f", 3)]),
        ("x = b.contains(b.mapFromScene(p))\n", [("<module>", 1)]),
        # not a mapped point: a plain point, a rect, another function's local of the same name
        ("def f(b, p):\n    return b.contains(p)\n", []),
        ("def f(b, p):\n    local = b.mapFromScene(p)\n    return local\n"
         "def g(b, local):\n    return b.contains(local)\n", []),
    ])
    def test_the_guard_sees_both_spellings(self, source: str, expected: list) -> None:
        assert sorted(contains_of_a_mapped_point(ast.parse(source))) == expected


EAST_EDGE_CM = 700.0   # the Garden's bed: x 400 … 700, y 300 … 500
BADGE_SHIFT_CM = 1.8   # 0.3 * min(0.45 * 30, 12) / 2: what the badge moves the rect's centre by


class TestWhereAPlantStandsDoesNotDependOnABadge:
    """Review round 2, P2-1 / issue #443 (iii). The antagonist badge grows a
    plant's ``boundingRect()`` towards +x / +y. Until #443 the LINK decisions
    asked that rect's centre (up to 1.8 cm off along each axis) while the LIFT
    asked ``standing_point``; a linked plant 1 cm inside its bed's east edge
    could therefore drop from 38 to 0 whenever the badge appeared, in the 3D
    record and in the 2D caster.

    Both questions are now asked at ``standing_point``, so painting a warning
    over a plant cannot move it — or re-decide which bed holds it."""

    def test_a_badge_does_not_move_a_plant_off_its_soil(self, canvas: CanvasView) -> None:
        garden = Garden(canvas)
        edge = _add(garden, _perennial(garden, EAST_EDGE_CM - 1.0, 400.0, 61.0, radius=30.0), "edge")
        assert edge.parent_bed_id == garden.bed.item_id  # created without a badge: linked
        assert _bases(garden, edge) == (38.0, 38.0)
        before = garden.records()

        controller = SunShadowController(garden.scene, lambda: BERLIN)
        controller.set_sim_datetime(datetime(2026, 6, 21, 18, 0, tzinfo=UTC))
        controller.set_enabled(True)
        overlay = next(i for i in garden.scene.items() if isinstance(i, SunShadowOverlayItem))

        def painted() -> list[tuple[float, float]]:
            path = overlay.path()
            return [(path.elementAt(i).x, path.elementAt(i).y) for i in range(path.elementCount())]

        shadow, count = painted(), controller.recompute_count

        edge.set_antagonist_warning(True)
        # The link point and the standing point are the same point — the badge
        # changes neither, and the plant stays linked and lifted.
        link_point = footprints.bed_membership_point(edge)
        standing = footprints.standing_point(edge)
        assert standing is not None
        assert (link_point.x(), link_point.y()) == (standing.x(), standing.y())
        assert (standing.x(), standing.y()) == (EAST_EDGE_CM - 1.0, 400.0)
        assert footprints.centre_is_inside(edge, garden.bed)
        assert edge.parent_bed_id == garden.bed.item_id
        assert _bases(garden, edge) == (38.0, 38.0)      # round 1 (badge at the link point): (0.0, 0.0)
        assert garden.records() == before                 # the 3D records: nothing at all
        controller.recompute_now()
        assert controller.recompute_count == count        # the overlay's key (it carries the base) held
        assert painted() == shadow

        edge.set_antagonist_warning(False)
        assert _bases(garden, edge) == (38.0, 38.0) and garden.records() == before
        controller.recompute_now()
        assert controller.recompute_count == count and painted() == shadow
        controller.set_enabled(False)

    def test_against_an_edge_at_45_degrees_the_badge_changes_nothing(
        self, canvas: CanvasView
    ) -> None:
        """The old margin: the badge moved the link point by 1.8 cm in x AND y —
        2.55 cm in all — so a linked plant 2.2 cm inside a (+x, +y)-facing edge
        was "outside" for the link decisions and stood on the soil all the same.
        Both decisions now use the same point: a plant 2.2 cm inside is inside,
        with or without the badge, and stays linked."""
        garden = Garden(canvas)
        apply_rotation(garden.bed, 45.0)
        centre = garden.bed.mapToScene(garden.bed.rect().center())
        axis = garden.bed.mapToScene(garden.bed.rect().center() + QPointF(1.0, 0.0)) - centre
        along = 1.0 / math.sqrt(2.0)
        assert (centre.x(), centre.y()) == pytest.approx((550.0, 400.0))
        # the turned bed's long axis runs along (+x, +y): its short edges, 150 cm from the
        # centre, face (+x, +y) and (-x, -y)
        assert (axis.x(), axis.y()) == pytest.approx((along, along))
        for index, inside_by in enumerate((2.2, 2.6)):
            reach = 150.0 - inside_by
            plant = _add(garden, _perennial(garden, 550.0 + reach * along, 400.0 + reach * along,
                                            61.0 + index, radius=30.0), f"{inside_by} cm inside")
            assert plant.parent_bed_id == garden.bed.item_id
            plant.set_antagonist_warning(True)
            assert footprints.centre_is_inside(plant, garden.bed)
            assert plant.parent_bed_id == garden.bed.item_id
            assert _bases(garden, plant) == (38.0, 38.0)      # where it stands: its own centre

    @pytest.mark.parametrize("painted", ["antagonist badge", "companion highlight"])
    def test_the_standing_point_ignores_what_is_painted_over_the_plant(
        self, canvas: CanvasView, painted: str
    ) -> None:
        garden = Garden(canvas)
        plant = _add(garden, _perennial(garden, 610.0, 420.0, 61.0, radius=30.0), "plant")
        point = footprints.standing_point(plant)
        rect = plant.boundingRect()
        if painted == "antagonist badge":
            plant.set_antagonist_warning(True)
        else:
            plant.set_companion_highlight("antagonistic")
        assert plant.boundingRect() != rect  # the paint-dependent rect DID change
        assert footprints.standing_point(plant) == point
        assert _bases(garden, plant) == (38.0, 38.0)

    def test_the_standing_point_is_the_origin_of_the_outline_and_of_the_record(
        self, canvas: CanvasView
    ) -> None:
        """``standing_point`` is ``item_outline``'s anchor in scene coordinates — for
        every footprint shape, turned and moved — and a plant's is its record's origin."""
        from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
        from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem

        garden = Garden(canvas)
        layer = garden.scene.active_layer.id
        items: list[Any] = [
            garden.plant, garden.bed,
            EllipseItem(100.0, 120.0, 80.0, 40.0, object_type=ObjectType.POND_POOL, layer_id=layer),
            PolygonItem([QPointF(0.0, 0.0), QPointF(300.0, 0.0), QPointF(300.0, 90.0),
                         QPointF(120.0, 200.0)], object_type=ObjectType.HOUSE, layer_id=layer),
            PolylineItem([QPointF(0.0, 0.0), QPointF(250.0, 0.0), QPointF(250.0, 180.0)],
                         object_type=ObjectType.FENCE, layer_id=layer),
        ]
        for index, item in enumerate(items[2:]):
            garden.scene.addItem(item)
            item.setPos(900.0 + 400.0 * index, 700.0)
        for item in items[1:]:
            apply_rotation(item, 33.0)
        shapes = set()
        for item in items:
            outline = footprints.item_outline(item)
            assert outline is not None
            shapes.add(outline.shape)
            expected = item.mapToScene(QPointF(outline.anchor[0], outline.anchor[1]))
            point = footprints.standing_point(item)
            assert point is not None
            assert (point.x(), point.y()) == pytest.approx((expected.x(), expected.y()), abs=1e-9)
        assert shapes == set(footprints.OUTLINE_SHAPES)
        record = garden.records()[garden.plant_id]
        standing = footprints.standing_point(garden.plant)
        assert standing is not None
        assert (record.transform.east_cm, record.transform.north_cm) == (standing.x(), standing.y())
        assert footprints.standing_point(object()) is None  # no footprint: stands nowhere


@pytest.fixture
def window(qtbot: Any, monkeypatch: Any, _reset_app_settings: Any) -> Any:  # noqa: ARG001
    """The real application window: the agent's link decisions live on it."""
    from PyQt6.QtWidgets import QMessageBox

    from open_garden_planner.app.application import GardenPlannerApp
    from open_garden_planner.app.settings import get_settings

    get_settings().show_welcome_on_startup = False
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *_a, **_k: QMessageBox.StandardButton.Discard)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    yield win
    win._stop_agent_api()


class TestLinkAndLiftAskTheSamePoint:
    """Review round 2, P2-1 / issue #443 (iii): ONE test per decision, now pinning
    that every LINK decision and the LIFT ask the SAME point. Round 1's refactor
    moved five inline expressions into shared functions, and a swap of the link
    point for the geometric centre passed every parenting, agent-write,
    container, trellis and base-stacking test — "identical behaviour" held by
    reading only. Since #443 the point is ``standing_point`` everywhere, so the
    probe (a badged plant whose centre is 1 cm inside a bed's east edge) is linked
    by every path and lifted; a plant whose centre is outside is neither."""

    @staticmethod
    def _bed(win: Any) -> RectangleItem:
        bed = RectangleItem(400.0, 300.0, 300.0, 200.0, object_type=ObjectType.RAISED_BED,
                            layer_id=win.canvas_scene.active_layer.id)
        win.canvas_view.command_manager.execute(CreateItemCommand(win.canvas_scene, bed, "bed"))
        return bed

    @staticmethod
    def _probe(win: Any, *, badge: bool) -> CircleItem:
        plant = CircleItem(EAST_EDGE_CM - 1.0, 400.0, 30.0, object_type=ObjectType.PERENNIAL,
                           layer_id=win.canvas_scene.active_layer.id)
        plant.metadata[METADATA_KEY] = 61.0
        if badge:
            plant.set_antagonist_warning(True)
        return plant

    def test_the_link_point_is_the_standing_point(self, window: Any) -> None:
        bed, plant = self._bed(window), self._probe(window, badge=True)
        window.canvas_scene.addItem(plant)
        link, stand = footprints.bed_membership_point(plant), footprints.standing_point(plant)
        assert stand is not None
        assert (link.x(), link.y()) == (stand.x(), stand.y())
        assert footprints.shape_contains(bed, link) and footprints.shape_contains(bed, stand)

    def test_create_links_a_badged_plant_whose_centre_is_inside(self, window: Any) -> None:
        bed, plant = self._bed(window), self._probe(window, badge=True)
        window.canvas_view.command_manager.execute(
            CreateItemCommand(window.canvas_scene, plant, "plant"))
        assert plant.parent_bed_id == bed.item_id and plant.item_id in bed.child_item_ids

    def test_bulk_create_and_paste_link_by_the_same_point(self, window: Any) -> None:
        from open_garden_planner.core.commands import CreateItemsCommand

        bed, plant = self._bed(window), self._probe(window, badge=True)
        window.canvas_view.command_manager.execute(
            CreateItemsCommand(window.canvas_scene, [plant], "pasted objects"))
        assert plant.parent_bed_id == bed.item_id and plant.item_id in bed.child_item_ids

    def test_the_drop_after_a_drag_asks_the_same_point(self, window: Any) -> None:
        bed, plant = self._bed(window), self._probe(window, badge=False)
        window.canvas_view.command_manager.execute(
            CreateItemCommand(window.canvas_scene, plant, "plant"))
        assert plant.parent_bed_id == bed.item_id
        plant.setSelected(True)
        # after selecting: the window's companion check answers a selection change by
        # clearing the badge of a plant that has no antagonist near it
        plant.set_antagonist_warning(True)
        # The real drag-release helper (the click path no longer re-evaluates).
        for command in window.canvas_view._plant_bed_link_commands():
            window.canvas_view.command_manager.execute(command)
        assert plant.antagonist_warning
        assert plant.parent_bed_id == bed.item_id  # the badge no longer re-decides the link

    def test_the_agent_s_move_re_link_asks_the_same_point(self, window: Any) -> None:
        bed, plant = self._bed(window), self._probe(window, badge=False)
        window.canvas_view.command_manager.execute(
            CreateItemCommand(window.canvas_scene, plant, "plant"))
        assert plant.parent_bed_id == bed.item_id
        plant.set_antagonist_warning(True)
        # The prediction the agent's move uses to report the link outcome.
        changed, new_parent, command = window._agent_reconcile_bed_membership_command(plant)
        assert (changed, new_parent, command) == (False, None, None)
        assert plant.parent_bed_id == bed.item_id

    def test_link_is_geometric_and_the_lift_agree(self, window: Any) -> None:
        """``set_parent_bed`` on a plant whose centre is inside reports geometric
        truth, and the plant stands on the soil — one point answers both."""
        bed, plant = self._bed(window), self._probe(window, badge=True)
        window.canvas_scene.addItem(plant)
        assert plant.parent_bed_id is None
        result = window._do_agent_set_parent_bed(str(plant.item_id), str(bed.item_id))
        assert result["link_is_geometric"] is True
        assert plant.parent_bed_id == bed.item_id
        record = snapshot_records(window.canvas_scene)[str(plant.item_id)]
        (caster,) = [c for c in collect_shadow_casters(window.canvas_scene) if c.height_cm == 61.0]
        assert (record.transform.base_cm, caster.base_cm) == (38.0, 38.0)
        # … and the text an AGENT reads about that field says the same predicate
        # answers both questions (rewritten for #443 (iii)).
        from open_garden_planner.agent_api.schema import WriteResult

        told = " ".join((WriteResult.model_fields["link_is_geometric"].description or "").split())
        for words in ("standing point", "sun study", "3D view", "always agree"):
            assert words in told, words

    def test_a_plant_whose_centre_is_outside_is_not_linked(self, window: Any) -> None:
        """At the WEST edge the old badge-margin case: the plant's centre is 1 cm
        OUTSIDE the bed, so the one point says outside — no link, base 0."""
        bed = self._bed(window)
        plant = CircleItem(400.0 - 1.0, 400.0, 30.0, object_type=ObjectType.PERENNIAL,
                           layer_id=window.canvas_scene.active_layer.id)
        plant.metadata[METADATA_KEY] = 61.0
        plant.set_antagonist_warning(True)
        window.canvas_view.command_manager.execute(
            CreateItemCommand(window.canvas_scene, plant, "plant"))
        assert plant.parent_bed_id is None
        assert plant.item_id not in bed.child_item_ids
        record = snapshot_records(window.canvas_scene)[str(plant.item_id)]
        (caster,) = [c for c in collect_shadow_casters(window.canvas_scene) if c.height_cm == 61.0]
        assert (record.transform.base_cm, caster.base_cm) == (0.0, 0.0)


def _accept(monkeypatch: Any, module: str, dialog: str, **settings: Any) -> None:
    """The named array dialog, Accepted with these settings. They are read-only
    properties over spin boxes, so they are patched onto the CLASS (the pattern of
    ``tests/integration/test_array_tools.py``)."""
    import importlib

    from PyQt6.QtWidgets import QDialog

    dialog_class = getattr(importlib.import_module(f"open_garden_planner.ui.dialogs.{module}"), dialog)
    monkeypatch.setattr(dialog_class, "__init__", lambda _self, *_args, **_kwargs: None)
    monkeypatch.setattr(dialog_class, "exec", lambda _self: QDialog.DialogCode.Accepted)
    for key, value in settings.items():
        monkeypatch.setattr(dialog_class, key, property(lambda _self, _value=value: _value))


def _select_only(garden: Garden, *items: Any) -> None:
    for item in garden.scene.selectedItems():
        item.setSelected(False)
    for item in items:
        item.setSelected(True)


def _new_plants(garden: Garden, before: set[int]) -> list[CircleItem]:
    return [item for item in garden.scene.items()
            if isinstance(item, CircleItem) and id(item) not in before]


def _base_pair(garden: Garden, plant: Any) -> tuple[float, float]:
    """(3D record base, 2D caster base) of a plant that shares its height with others:
    the caster is found by where its footprint is."""
    point = footprints.standing_point(plant)
    assert point is not None
    bases = [caster.base_cm for caster in collect_shadow_casters(garden.scene)
             if caster.height_cm == plant.metadata[METADATA_KEY]
             and math.hypot(sum(x for x, _y in caster.footprint) / len(caster.footprint) - point.x(),
                            sum(y for _x, y in caster.footprint) / len(caster.footprint) - point.y()) < 2.0]
    (caster_base,) = bases
    return garden.records()[str(plant.item_id)].transform.base_cm, caster_base


#: (the canvas action, its dialog's module and class, the dialog's settings, where the two
#: copies of the Garden's plant at (500, 400) land — one in the bed, one outside it)
ARRAY_CASES = [
    ("create_linear_array", "linear_array_dialog", "LinearArrayDialog",
     {"count": 3, "spacing_cm": 150.0, "angle_deg": 0.0, "create_constraints": False},
     [(650.0, 400.0), (800.0, 400.0)]),
    ("create_grid_array", "grid_array_dialog", "GridArrayDialog",
     {"rows": 1, "cols": 3, "row_spacing_cm": 50.0, "col_spacing_cm": 150.0,
      "create_constraints": False},
     [(650.0, 400.0), (800.0, 400.0)]),
    ("create_circular_array", "circular_array_dialog", "CircularArrayDialog",
     {"count": 3, "radius_cm": 75.0, "start_angle_deg": 0.0, "sweep_angle_deg": 180.0},
     [(350.0, 400.0), (425.0, 325.0)]),
    ("create_array_along_path", "array_along_path_dialog", "ArrayAlongPathDialog",
     {"count": 2, "spacing_cm": 0.0, "use_spacing_mode": False, "start_offset_pct": 0.0,
      "end_offset_pct": 0.0, "follow_tangent": False},
     [(650.0, 400.0), (800.0, 400.0)]),
]


class TestCopiesAndMovesFollowTheLink:
    """The last pass (the review of round 3, P2-a) / issue #443 (iv)-(vi). One rule
    now decides a plant's link — the smallest plant-parent containing its standing
    point — and every edit path applies it:

    - an ARRAY copy is a NEW item: it does not inherit its source's link, and the
      copy that lands in a bed is linked (the bed's child list too);
    - a plant MIRROR-COPIED without its bed is linked when the copy lands in one;
    - a plant MOVED by the arrow keys, a typed coordinate or align/distribute
      re-evaluates its link;
    - a BED moved by a typed coordinate or by align / distribute takes its plants
      along, as the drag, the arrow keys and the agent already did.

    Where a plant STANDS follows the plant's centre in every one of them (FR-SUN-11).

    Every expectation in this class changed KNOWINGLY with the #443 fix."""

    @pytest.mark.parametrize(("action", "module", "dialog", "settings", "lands"), ARRAY_CASES,
                             ids=[case[0] for case in ARRAY_CASES])
    def test_an_array_copy_is_linked_by_where_it_lands(
        self, canvas: CanvasView, monkeypatch: Any, action: str, module: str, dialog: str,
        settings: dict[str, Any], lands: list[tuple[float, float]],
    ) -> None:
        """Expected: the copy inside the bed is linked to it (and held by its child
        list), the copy outside is unlinked — 38 and 0. WHY: all four array actions
        build a copy from the source's serialised form; the commands now drop the
        inherited ``parent_bed_id`` and reconcile membership from geometry, as
        ``CreateItemsCommand`` does for a pasted plant (#443 (v))."""
        garden = Garden(canvas)  # bed x 400 … 700, y 300 … 500; the plant at (500, 400), linked
        _accept(monkeypatch, module, dialog, **settings)
        _select_only(garden, garden.plant)
        if action == "create_array_along_path":  # this one needs the item AND a polyline selected
            from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem

            path = PolylineItem([QPointF(650.0, 400.0), QPointF(800.0, 400.0)],
                                object_type=ObjectType.PATH, layer_id=garden.scene.active_layer.id)
            garden.scene.addItem(path)
            path.setSelected(True)
        before_records = garden.records()
        before = {id(item) for item in garden.scene.items()}

        getattr(canvas, action)()

        copies = _new_plants(garden, before)
        points = [footprints.standing_point(copy) for copy in copies]
        centres = sorted((point.x(), point.y()) for point in points if point is not None)
        assert [value for centre in centres for value in centre] == pytest.approx(
            [value for centre in lands for value in centre], abs=1e-6)
        inside = [copy for copy, point in zip(copies, points, strict=True)
                  if footprints.shape_contains(garden.bed, point)]
        assert len(copies) == 2 and len(inside) == 1
        (outside,) = [copy for copy in copies if copy is not inside[0]]
        for copy in copies:
            assert copy.item_id != garden.plant.item_id               # a new item …
            assert copy.metadata[METADATA_KEY] == 60.0
        # … whose link is decided by where IT stands, not by its source's
        assert inside[0].parent_bed_id == garden.bed.item_id
        assert inside[0].item_id in garden.bed.child_item_ids
        assert outside.parent_bed_id is None
        assert outside.item_id not in garden.bed.child_item_ids
        assert not footprints.centre_is_inside(outside, garden.bed)
        assert _base_pair(garden, inside[0]) == (38.0, 38.0)
        assert _base_pair(garden, outside) == (0.0, 0.0)
        assert garden.records()[str(outside.item_id)].parent_id is None
        assert _base_pair(garden, garden.plant) == (38.0, 38.0)

        garden.commands.undo()  # one step
        assert _new_plants(garden, before) == [] and garden.records() == before_records
        assert list(garden.bed.child_item_ids) == [garden.plant.item_id]

    def test_a_plant_mirror_copied_without_its_bed_is_linked_where_it_lands(
        self, canvas: CanvasView, mouse_event: Any
    ) -> None:
        """Expected: the copy at (600, 400) — inside the raised bed its source stands
        in — IS linked and stands at 38; its source, 1 m to the west, also 38. WHY:
        ``MirrorItemsCommand`` now reconciles the copies it adds (#443 (v)), so the
        unlinked item ``mirror_geometry`` builds is linked by its geometry."""
        garden = Garden(canvas)
        _select_only(garden, garden.plant)
        before = {id(item) for item in garden.scene.items()}
        canvas.set_active_tool(ToolType.MIRROR)
        tool = canvas.tool_manager.active_tool
        tool._copy_mode = True  # under the offscreen platform the Copy / Move chooser is skipped
        tool.mouse_press(mouse_event, QPointF(550.0, 100.0))  # the axis x = 550 …
        tool.mouse_press(mouse_event, QPointF(550.0, 700.0))  # … the second click applies

        (copy,) = _new_plants(garden, before)
        point = footprints.standing_point(copy)
        assert point is not None and (point.x(), point.y()) == pytest.approx((600.0, 400.0), abs=1e-6)
        assert footprints.centre_is_inside(copy, garden.bed)
        assert copy.parent_bed_id == garden.bed.item_id
        assert copy.item_id in garden.bed.child_item_ids
        assert _base_pair(garden, copy) == (38.0, 38.0)
        assert _base_pair(garden, garden.plant) == (38.0, 38.0)

        garden.commands.undo()
        assert list(garden.bed.child_item_ids) == [garden.plant.item_id]

    def test_moves_re_evaluate_the_link_in_both_directions(
        self, canvas: CanvasView
    ) -> None:
        """FR-SUN-11's invariant / #443 (iv). ``MoveItemsCommand`` backs the arrow
        keys and a coordinate typed into the Properties panel: the link follows the
        plant both ways — out of the bed (unlinked, 0) and back in (linked, 38). A
        plant moved INTO a bed is linked for the first time."""
        garden = Garden(canvas)
        garden.commands.execute(MoveItemsCommand([garden.plant], QPointF(300.0, 0.0)))  # to (800, 400)
        assert garden.plant.parent_bed_id is None                 # re-evaluated: outside
        assert garden.plant.item_id not in garden.bed.child_item_ids
        assert not footprints.centre_is_inside(garden.plant, garden.bed)
        assert _bases(garden, garden.plant) == (0.0, 0.0)
        garden.commands.undo()                                     # back where it was
        assert garden.plant.parent_bed_id == garden.bed.item_id and _bases(garden, garden.plant) == (38.0, 38.0)
        garden.commands.execute(MoveItemsCommand([garden.plant], QPointF(300.0, 0.0)))
        garden.commands.execute(MoveItemsCommand([garden.plant], QPointF(-300.0, 0.0)))
        assert garden.plant.parent_bed_id == garden.bed.item_id
        assert _bases(garden, garden.plant) == (38.0, 38.0)        # back in: on the soil again

        loner = _add(garden, _perennial(garden, 900.0, 400.0, 61.0), "loner")
        assert loner.parent_bed_id is None
        garden.commands.execute(MoveItemsCommand([loner], QPointF(-300.0, 0.0)))       # to (600, 400)
        assert footprints.centre_is_inside(loner, garden.bed)
        assert loner.parent_bed_id == garden.bed.item_id           # moved IN: now linked
        assert loner.item_id in garden.bed.child_item_ids
        assert _bases(garden, loner) == (38.0, 38.0)

    def test_a_bed_moved_by_align_or_a_typed_coordinate_takes_its_plants(
        self, canvas: CanvasView
    ) -> None:
        """Expected: the plant travels WITH the bed, keeps its link, and stays on the
        soil — one undo restores both. WHY: ``MoveItemsCommand``/``AlignItemsCommand``
        now expand a moved plant-parent with its children, the same rule the drag,
        the arrow keys and the agent already followed (#443 (vi))."""
        garden = Garden(canvas)
        post = _add(garden, RectangleItem(100.0, 800.0, 20.0, 20.0, object_type=ObjectType.TOOL_SHED,
                                          layer_id=garden.scene.active_layer.id), "post")
        _select_only(garden, garden.bed, post)
        canvas.align_selected(AlignMode.LEFT)  # the real action: the bed's left edge to x = 100
        assert garden.bed.mapRectToScene(garden.bed.rect()).left() == pytest.approx(100.0, abs=5.0)
        point = footprints.standing_point(garden.plant)
        assert point is not None and (point.x(), point.y()) == pytest.approx((200.0, 400.0), abs=5.0)
        assert footprints.centre_is_inside(garden.plant, garden.bed)  # it went with the bed
        assert garden.plant.parent_bed_id == garden.bed.item_id
        assert _bases(garden, garden.plant) == (38.0, 38.0)
        garden.commands.undo()
        assert _bases(garden, garden.plant) == (38.0, 38.0)
        back = footprints.standing_point(garden.plant)
        assert back is not None and (back.x(), back.y()) == pytest.approx((500.0, 400.0), abs=5.0)

        # the typed coordinate: the command the panel executes for the one item
        garden.commands.execute(MoveItemsCommand([garden.bed], QPointF(400.0, 0.0)))
        assert garden.plant.parent_bed_id == garden.bed.item_id
        assert footprints.centre_is_inside(garden.plant, garden.bed)
        assert _bases(garden, garden.plant) == (38.0, 38.0)
        garden.commands.undo()
        assert _bases(garden, garden.plant) == (38.0, 38.0)


class TestTheParentShapeIsBuiltOncePerWalk:
    """Review round 2, P2-9. Qt's ``contains`` rebuilds an item's shape on every
    call; the lift asked it once per plant. ``ItemLookup.shape_of`` holds the path
    for the walk, and ``shape_contains`` gives the same answer with it."""

    @staticmethod
    def _parents(layer: Any) -> list[Any]:
        from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem

        concave = PolygonItem(
            [QPointF(0.0, 0.0), QPointF(300.0, 0.0), QPointF(300.0, 200.0), QPointF(150.0, 60.0),
             QPointF(0.0, 200.0)], object_type=ObjectType.GARDEN_BED, layer_id=layer)
        return [
            RectangleItem(0.0, 0.0, 300.0, 200.0, object_type=ObjectType.RAISED_BED, layer_id=layer),
            concave,
            CircleItem(150.0, 100.0, 90.0, object_type=ObjectType.CONTAINER_ROUND, layer_id=layer),
            EllipseItem(0.0, 0.0, 300.0, 160.0, object_type=ObjectType.GARDEN_BED, layer_id=layer),
        ]

    def test_the_cached_path_answers_as_qt_s_contains_does(self, canvas: CanvasView) -> None:
        scene = canvas.scene()
        probes = 0
        for index, parent in enumerate(self._parents(scene.active_layer.id)):
            scene.addItem(parent)
            parent.setPos(500.0 + 600.0 * index, 400.0)
            apply_rotation(parent, 27.0 * index)
            lookup = footprints.ItemLookup(scene.items())
            shape = lookup.shape_of(parent)
            assert lookup.shape_of(parent) is shape  # built once
            box = parent.sceneBoundingRect()
            answers = set()
            # a grid over the bounding box and beyond it, plus points ON the outline
            xs = np.linspace(box.left() - 20.0, box.right() + 20.0, 41)
            ys = np.linspace(box.top() - 20.0, box.bottom() + 20.0, 41)
            points = [QPointF(float(x), float(y)) for x in xs for y in ys]
            outline = parent.mapToScene(parent.shape())
            points += [outline.pointAtPercent(t) for t in np.linspace(0.0, 1.0, 101)]
            for point in points:
                expected = bool(parent.contains(parent.mapFromScene(point)))
                assert footprints.shape_contains(parent, point) is expected
                assert footprints.shape_contains(parent, point, shape) is expected
                answers.add(expected)
                probes += 1
            assert answers == {True, False}
        assert probes == 4 * (41 * 41 + 101)

    def test_no_canvas_item_overrides_contains_or_clip_path(self) -> None:
        """``contains_path`` mirrors ``QGraphicsItem::contains`` (the clip path of a
        clipped item, else its shape). A Python ``contains`` or ``clipPath`` on a
        footprint item would be bypassed by the cached path — so there must be none.
        (``shape`` may be overridden freely: the cached path IS the item's own
        ``shape()``, whatever implements it.)"""
        from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
        from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem

        for item_class in (RectangleItem, PolygonItem, CircleItem, EllipseItem, PolylineItem):
            own = [base for base in item_class.__mro__
                   if base.__module__.startswith("open_garden_planner")]
            assert own, item_class
            for base in own:
                assert "contains" not in vars(base), (item_class, base)
                assert "clipPath" not in vars(base), (item_class, base)

    def test_a_lookup_kept_across_an_edit_would_answer_from_the_old_shape(
        self, canvas: CanvasView
    ) -> None:
        """Why the next test exists. ``ItemLookup`` holds each parent's shape (and the
        items) for ONE walk. Kept across an edit it is stale: a bed drawn around a
        plant that stood outside, after the lookup was built, links and lifts it —
        a fresh lookup says 38, the kept one, which never saw that bed, still says 0."""
        from open_garden_planner.ui.canvas.items import RectangleItem as _Rect

        garden = Garden(canvas)
        loner = _add(garden, _perennial(garden, 1500.0, 1200.0, 61.0), "loner")
        assert loner.parent_bed_id is None
        kept = footprints.ItemLookup(garden.scene.items())
        assert footprints.item_base_cm(loner, kept) == 0.0            # nothing around it yet
        around = _Rect(1400.0, 1100.0, 200.0, 200.0,
                       object_type=ObjectType.RAISED_BED,
                       layer_id=garden.scene.active_layer.id)
        garden.commands.execute(CreateItemCommand(garden.scene, around, "bed"))
        assert loner.parent_bed_id == around.item_id                  # #443: the bed linked it
        fresh = footprints.ItemLookup(garden.scene.items())
        assert footprints.item_base_cm(loner, fresh) == 38.0          # the truth
        assert footprints.item_base_cm(loner, kept) == 0.0            # a lookup that outlived its walk
        assert _bases(garden, loner) == (38.0, 38.0)                  # both walks make their own

    def test_a_lookup_lives_for_one_walk_and_is_never_kept(self) -> None:
        """Review round 3, P2-8, strengthened in the last pass. The only thing between
        the shape cache and a stale lift was a docstring sentence, and the next stories
        will be tempted to keep "the scene's lookup". Three things are held, by reading
        every module of the application:

        1. THE CENSUS. The identifier ``ItemLookup`` appears only as an import under its
           own name, as the class, as a parameter's annotation and as a call inside the
           three walks (since master's US-F3 was merged: the caster walk is
           ``collect_identified_casters``, and the walk over the sun RECEIVERS asks the
           base rule too — a plant on a parent's soil is not shaded by that parent).
           An alias import, ``make = ItemLookup``,
           ``functools.partial(ItemLookup, items)`` and ``getattr(module, "ItemLookup")``
           are other appearances and fail here — the first cut did not see them at all.
        2. THE WALKS. Each binds its lookup to a LOCAL name and only ever hands that
           name to a taker (``LOOKUP_TAKERS``): a list, a dict, ``.append(lookup)``,
           ``setattr``, ``return lookup, 1``, ``+=`` and a closure fail here — the first
           cut saw the construction and reported it as not kept.
        3. THE TAKERS. The functions with an ``ItemLookup`` parameter are exactly those
           two, and they use the parameter the same way.

        What is left is stated in the helpers: a spelling that never writes the
        identifier (``type(lookup)(items)``, ``copy.copy(lookup)``), a function that
        only shares a taker's name, ``locals()``. And this reads ``src/`` only: tests
        and scripts construct lookups freely."""
        src = Path(open_garden_planner.__file__).parent
        census: dict[str, list[tuple[str, str]]] = {}
        constructed: dict[str, set[str]] = {}
        kept: list[str] = []
        takers: dict[str, list[str]] = {}
        for path in src.rglob("*.py"):
            relative = path.relative_to(src).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"))
            appearances = sorted(item_lookup_identifiers(tree))
            if appearances:
                census[relative] = appearances
            for where, problem in lookups_constructed(tree):
                constructed.setdefault(relative, set()).add(where)
                if problem:
                    kept.append(f"{relative}::{where}: {problem}")
            for function, parameter in lookup_parameters(tree):
                takers[function.name] = lookup_escapes(function, parameter)
        assert census == {
            "ui/canvas/footprints.py": [("<module>", "class definition"),
                                        ("item_base_cm", "parameter annotation"),
                                        ("standing_parent", "parameter annotation")],
            "ui/canvas/sun_exposure_snapshot.py": [("<module>", "import"),
                                                   ("collect_exposure_snapshot", "call")],
            "ui/canvas/sun_shadow_controller.py": [("<module>", "import"),
                                                   ("collect_identified_casters", "call")],
            "ui/view3d/snapshot.py": [("<module>", "import"),
                                      ("_record_of", "parameter annotation"),
                                      ("snapshot_records", "call")],
        }
        assert constructed == {
            "ui/canvas/sun_exposure_snapshot.py": {"collect_exposure_snapshot"},  # the sun receivers
            "ui/canvas/sun_shadow_controller.py": {"collect_identified_casters"},  # the 2D caster walk
            "ui/view3d/snapshot.py": {"snapshot_records"},                      # the 3D record walk
        }
        assert kept == []
        assert takers == {name: [] for name in sorted(LOOKUP_TAKERS)}

    @pytest.mark.parametrize(("source", "expected"), [
        ("def walk(items):\n    lookup = ItemLookup(items)\n"
         "    return [item_base_cm(i, lookup) for i in items]\n", [("walk", "")]),
        ("def walk(items):\n    lookup: ItemLookup = footprints.ItemLookup(items)\n"
         "    _record_of(items[0], lookup=lookup)\n    lookup.get(1)\n", [("walk", "")]),
        ("class C:\n    def walk(self, items):\n        self._lookup = ItemLookup(items)\n",
         [("walk", "bound to something that is not a local name")]),
        ("LOOKUP = ItemLookup([])\n", [("<module>", "constructed outside a function")]),
        ("def walk(items):\n    return ItemLookup(items)\n",
         [("walk", "not bound to a local name")]),
        ("def walk(items):\n    cache['scene'] = ItemLookup(items)\n",
         [("walk", "bound to something that is not a local name")]),
        ("def walk(items, lookup=ItemLookup(())):\n    pass\n",
         [("<module>", "constructed outside a function")]),
        ("def walk(items):\n    lookup = ItemLookup(items)\n    self.lookup = lookup\n",
         [("walk", "the local name escapes: used as a value")]),
        ("def walk(items):\n    lookup = ItemLookup(items)\n    return lookup\n",
         [("walk", "the local name escapes: used as a value")]),
        ("def walk(items):\n    global lookup\n    lookup = ItemLookup(items)\n",
         [("walk", "the local name is declared global or nonlocal: lookup")]),
        ("def other(items):\n    return base(items)\n", []),
        # the last pass: seen as a construction before, and reported as NOT kept
        ("def walk(items):\n    lookup = ItemLookup(items)\n    self.kept = [lookup]\n",
         [("walk", "the local name escapes: used as a value")]),
        ("def walk(items):\n    lookup = ItemLookup(items)\n    CACHE = {'scene': lookup}\n",
         [("walk", "the local name escapes: used as a value")]),
        ("def walk(items):\n    lookup = ItemLookup(items)\n    self.kept.append(lookup)\n",
         [("walk", "the local name escapes: handed to append")]),
        ("def walk(items):\n    lookup = ItemLookup(items)\n    setattr(self, 'lookup', lookup)\n",
         [("walk", "the local name escapes: handed to setattr")]),
        ("def walk(items):\n    lookup = ItemLookup(items)\n    return lookup, 1\n",
         [("walk", "the local name escapes: used as a value")]),
        ("def walk(items):\n    lookup = ItemLookup(items)\n"
         "    self.ask = lambda item: item_base_cm(item, lookup)\n",
         [("walk", "the local name escapes: used in a closure")]),
        ("def walk(items):\n    lookup = ItemLookup(items)\n    self.kept += [lookup]\n",
         [("walk", "the local name escapes: used as a value")]),
        ("def walk(items):\n    lookup = ItemLookup(items)\n    self.get = lookup.get\n",
         [("walk", "the local name escapes: attribute get taken without a call")]),
        ("def walk(items):\n    lookup = ItemLookup(items)\n    store(lookup=lookup)\n    return lookup\n",
         [("walk", "the local name escapes: handed to store; used as a value")]),
    ])
    def test_the_lifetime_guard_sees_how_a_lookup_can_be_kept(self, source: str,
                                                              expected: list) -> None:
        assert lookups_constructed(ast.parse(source)) == expected

    @pytest.mark.parametrize(("source", "expected"), [
        ("from .footprints import ItemLookup\n", [("<module>", "import")]),
        ("class ItemLookup:\n    pass\n", [("<module>", "class definition")]),
        ("def base(item, lookup: ItemLookup):\n    return lookup.get(item)\n",
         [("base", "parameter annotation")]),
        ("def walk(items):\n    lookup = footprints.ItemLookup(items)\n", [("walk", "call")]),
        ("def walk(items):\n    lookup: ItemLookup = make(items)\n", [("walk", "annotation of a name")]),
        ('def walk(items):\n    """An ItemLookup lives for one walk."""\n', []),  # a docstring may name it
        # the last pass: not seen at all before
        ("from .footprints import ItemLookup as Lookup\n", [("<module>", "import under another name")]),
        ("from .footprints import Other as ItemLookup\n", [("<module>", "import under another name")]),
        ("make = ItemLookup\n", [("<module>", "used as a value")]),
        ("def walk(items):\n    return functools.partial(ItemLookup, items)()\n",
         [("walk", "used as a value")]),
        ("def walk(items):\n    return getattr(footprints, \"ItemLookup\")(items)\n",
         [("walk", "named in a string")]),
        ("class Kept(ItemLookup):\n    pass\n", [("<module>", "used as a value")]),
        ("def make(items) -> ItemLookup:\n    pass\n", [("make", "used as a value")]),
        # the stated limit: a spelling that never writes the identifier
        ("def walk(items, lookup):\n    return type(lookup)(items), copy.copy(lookup)\n", []),
    ])
    def test_the_census_sees_every_appearance_of_the_identifier(self, source: str,
                                                                expected: list) -> None:
        assert item_lookup_identifiers(ast.parse(source)) == expected

    def test_one_shape_per_parent_and_walk(self, canvas: CanvasView, monkeypatch: Any) -> None:
        garden = Garden(canvas)
        for index in range(5):
            _add(garden, _perennial(garden, 430.0 + 40.0 * index, 450.0, 61.0 + index), f"p{index}")
        pot = _add(garden, CircleItem(1500.0, 900.0, 40.0, object_type=ObjectType.CONTAINER_ROUND,
                                      layer_id=garden.scene.active_layer.id), "pot")
        _add(garden, _perennial(garden, 1500.0, 900.0, 70.0), "potted")
        built: list[Any] = []
        original = footprints.contains_path

        def counting(parent: Any) -> Any:
            built.append(parent)
            return original(parent)

        monkeypatch.setattr(footprints, "contains_path", counting)
        casters = collect_shadow_casters(garden.scene)
        assert sum(1 for caster in casters if caster.base_cm > 0.0) == 7  # six in the bed, one potted
        assert sorted(map(id, built)) == sorted([id(garden.bed), id(pot)])  # round 1: seven shapes
        built.clear()
        records = snapshot_records(garden.scene)
        assert sum(1 for record in records.values() if record.transform.base_cm > 0.0) == 7
        assert sorted(map(id, built)) == sorted([id(garden.bed), id(pot)])

    def test_a_plan_without_raised_soil_builds_no_shape(self, canvas: CanvasView,
                                                        monkeypatch: Any) -> None:
        garden = Garden(canvas, ObjectType.GARDEN_BED)  # in the ground: nothing to lift onto
        built: list[Any] = []
        monkeypatch.setattr(footprints, "contains_path", built.append)
        assert garden.caster_base() == 0.0 and garden.base() == 0.0
        assert built == []


class TestHeatmapEndToEnd:
    """Review round 1, P2-3: a raised plant through the real ``SunHeatmapController``
    and its worker thread — the tip shift, read off the hours-of-sun grid."""

    def test_the_raised_plant_s_tip_is_in_the_grid(self, qtbot: Any) -> None:
        scene = CanvasScene(1000.0, 1000.0)
        view = CanvasView(scene)
        qtbot.addWidget(view)
        layer = scene.active_layer.id
        bed = RectangleItem(350.0, 150.0, 300.0, 300.0, object_type=ObjectType.RAISED_BED,
                            layer_id=layer)                      # 3 m x 3 m, 40 cm high
        plant = CircleItem(500.0, 300.0, 30.0, object_type=ObjectType.PERENNIAL, layer_id=layer)
        plant.metadata[METADATA_KEY] = 60.0                      # in the bed's middle
        commands = view.command_manager
        commands.execute(CreateItemCommand(scene, bed, "bed"))
        commands.execute(CreateItemCommand(scene, plant, "plant"))
        assert plant.parent_bed_id == bed.item_id
        winter = date(2026, 12, 21)  # a low sun: at noon the shadows run due north, far

        def hours_of_sun() -> tuple[np.ndarray, HeatmapGrid]:
            controller = SunHeatmapController(scene, lambda: BERLIN)
            with qtbot.waitSignal(controller.finished, timeout=60000) as blocker:
                assert controller.run_for_day(winter)
            assert blocker.args == [True]
            assert controller.last_minutes is not None and controller.last_grid is not None
            return controller.last_minutes.copy(), controller.last_grid

        raised, grid = hours_of_sun()
        commands.execute(SetParentBedCommand(scene, plant, bed.item_id, None))  # same plan, plant
        ground, grid_ground = hours_of_sun()                                    # on the ground
        assert grid == grid_ground and raised.shape == ground.shape

        # Lifting the plant only ADDS shade: what it shaded from the ground lies inside the
        # bed's own shadow or inside its raised shadow.
        assert np.all(raised <= ground)
        lost = ground - raised
        assert lost.max() >= SAMPLE_STEP_MINUTES  # … and it really does add some

        # The tip, due north of the plant at solar noon: r + (base + h) / tan a.
        noon = max(daylight_samples(BERLIN["latitude"], BERLIN["longitude"], winter),
                   key=lambda sample: sample.elevation_deg)
        assert 13.0 < noon.elevation_deg < 15.0 and abs(noon.azimuth_deg - 180.0) < 3.0
        tan_a = math.tan(math.radians(noon.elevation_deg))
        raised_tip = 30.0 + (38.0 + 60.0) / tan_a   # about 4.2 m north of the plant's centre
        ground_tip = 30.0 + 60.0 / tan_a            # about 2.7 m: where the tip was before L1.6
        bed_reach = 150.0 + 40.0 / tan_a            # the bed's own shadow, from the plant's centre
        assert ground_tip < bed_reach < raised_tip  # from the ground the tip never left the bed's

        _row, column = grid.cell_at(500.0, 300.0)
        rows = np.nonzero(lost[:, column] > 0.0)[0]
        north = (rows + 0.5) * grid.cell_cm + grid.y0_cm - 300.0  # cm north of the plant's centre
        assert north.min() > bed_reach - 2.0 * grid.cell_cm   # nothing changed under the bed's shadow
        # the farthest cell that lost sun to the plant is the raised tip, to a cell and the
        # few centimetres the nearest 15-minute sample misses true noon by
        assert north.max() == pytest.approx(raised_tip, abs=2.0 * grid.cell_cm)
        assert north.max() - ground_tip == pytest.approx(38.0 / tan_a, abs=2.0 * grid.cell_cm)
        # … and every cell between the bed's shadow and that tip lost at least one sample
        between = lost[rows.min():rows.max() + 1, column]
        assert np.all(between >= SAMPLE_STEP_MINUTES)


class OverlayWatch:
    """Waits for a ``SunShadowController`` on what it is known to do — never on a duration.

    A recompute sets the overlay's path. The scene answers with ``changed`` one
    event-loop round LATER, and ``changed`` is wired to the controller's debounce:
    150 ms after that echo the controller recomputes once more. While nothing has
    changed that recompute is a no-op (the key holds) — but an edit made in the
    meantime, even one nothing announces, is carried into the overlay by it.

    So "the debounce timer is idle" does not mean "nothing is pending": straight
    after a recompute the timer IS idle and the echo is still on its way. Review
    round 3, P1: a wait built on the timer alone let that echo land inside a negative
    control (CI: ``assert 6 == 1 + 4``). ``settled`` waits for the recompute, then for
    the echo it knows is coming, then for the debounce that echo starts.
    """

    def __init__(self, qtbot: Any, scene: Any, controller: SunShadowController) -> None:
        self.qtbot, self.controller = qtbot, controller
        #: per delivered ``scene.changed``: the controller's recompute count at that moment
        self.changes: list[int] = []
        scene.changed.connect(self._on_changed)

    def _on_changed(self, _regions: Any = None) -> None:
        self.changes.append(self.controller.recompute_count)

    def echo_delivered(self, recompute: int) -> bool:
        """Has the scene emitted ``changed`` since recompute number ``recompute`` set the path?"""
        return bool(self.changes) and self.changes[-1] >= recompute

    def quiet(self) -> None:
        """Until the debounce timer has fired. NOT "nothing is pending" — see the class."""
        self.qtbot.waitUntil(lambda: not self.controller._debounce.isActive(), timeout=5000)

    def settled(self, expected_count: int) -> None:
        """Recompute number ``expected_count`` has happened, its echo has been delivered,
        the debounce the echo started has fired — and the count is still that."""
        self.qtbot.waitUntil(lambda: self.controller.recompute_count >= expected_count, timeout=5000)
        self.qtbot.waitUntil(lambda: self.echo_delivered(expected_count), timeout=5000)
        self.quiet()
        assert self.controller.recompute_count == expected_count


def _set_height(item: Any, value: float | None) -> None:  # the properties panel's apply_func
    if value is None:
        item.metadata.pop(METADATA_KEY, None)
    else:
        item.metadata[METADATA_KEY] = value


class TestTheOverlaysOwnEcho:
    """Review round 3, P1. The two halves of one race, each made deterministic by
    running the recompute SYNCHRONOUSLY — its echo is then certainly undelivered,
    on every machine, not in one CI run out of four."""

    @staticmethod
    def _rig(canvas: CanvasView, qtbot: Any) -> tuple[Garden, SunShadowController, OverlayWatch, int]:
        garden = Garden(canvas)
        controller = SunShadowController(garden.scene, lambda: BERLIN)
        controller.set_sim_datetime(datetime(2026, 6, 21, 18, 0, tzinfo=UTC))
        watch = OverlayWatch(qtbot, garden.scene, controller)
        controller.set_enabled(True)  # recomputes at once: count 1, its echo on the way
        watch.settled(controller.recompute_count)
        return garden, controller, watch, controller.recompute_count

    def test_an_echo_that_was_not_waited_for_carries_a_later_edit_into_the_overlay(
        self, canvas: CanvasView, qtbot: Any
    ) -> None:
        """The mechanism. Nothing here is wired to the command stack, so no edit is
        announced: what reaches the overlay reaches it through the echo alone."""
        garden, controller, watch, count = self._rig(canvas, qtbot)
        garden.commands.execute(
            ChangePropertyCommand(garden.bed, "object height", None, 75.0, _set_height))
        assert not controller._debounce.isActive()  # the edit announced nothing
        controller.recompute_now()                  # synchronously: the overlay shows 75 cm …
        assert controller.recompute_count == count + 1
        assert not watch.echo_delivered(count + 1)  # … and its echo has NOT been delivered
        assert not controller._debounce.isActive()  # "the debounce is idle" is true all the same:
        #                                             a wait on the timer alone returns here
        garden.commands.undo()                      # an edit nothing announces: 40 cm again
        qtbot.waitUntil(lambda: watch.echo_delivered(count + 1), timeout=5000)
        watch.quiet()                               # the debounce the echo started has fired
        # exactly ONE extra recompute: the echo's, and it saw the undone height. This is the
        # recompute that landed in the negative control in CI (6 where 1 + 4 was expected).
        assert controller.recompute_count == count + 2
        watch.settled(count + 2)                    # … whose own echo is a no-op: the key holds
        controller.set_enabled(False)

    def test_settled_waits_for_the_echo_so_a_negative_control_cannot_race_it(
        self, canvas: CanvasView, qtbot: Any
    ) -> None:
        """The same worst case through ``OverlayWatch.settled``: nothing is left to
        carry the unannounced edit, and the count stays. With a ``settled`` that only
        asks the debounce timer this test fails every time, on every machine."""
        garden, controller, watch, count = self._rig(canvas, qtbot)
        garden.commands.execute(
            ChangePropertyCommand(garden.bed, "object height", None, 75.0, _set_height))
        controller.recompute_now()                  # synchronously: the echo is on its way
        assert controller.recompute_count == count + 1 and not watch.echo_delivered(count + 1)
        watch.settled(count + 1)                    # the recompute, ITS ECHO, the debounce after it
        assert watch.echo_delivered(count + 1)

        garden.commands.undo()                      # the negative control: an unannounced edit
        assert not controller._debounce.isActive()  # nothing is scheduled …
        delivered = len(watch.changes)
        qtbot.wait(2 * controller._debounce.interval())
        assert len(watch.changes) == delivered      # … no echo arrived late …
        assert controller.recompute_count == count + 1  # … and nothing recomputed
        controller.set_enabled(False)


class TestOneCasterWalk:
    """Gate G4's drift guard: the heatmap and the overlay consume the same casters,
    and 3D takes its base from the same function."""

    def test_overlay_and_heatmap_call_the_same_function(self) -> None:
        # Since master's US-F3 the heatmap takes its casters from the exposure snapshot,
        # and the snapshot from THE walk; the overlay's ShadowCasters are that walk,
        # flattened. One walk, three consumers.
        assert sun_heatmap.collect_exposure_snapshot is sun_exposure_snapshot.collect_exposure_snapshot
        assert (sun_exposure_snapshot.collect_identified_casters
                is sun_shadow_controller.collect_identified_casters)
        assert not hasattr(sun_heatmap, "collect_shadow_casters")
        assert sun_shadow_controller.item_base_cm is footprints.item_base_cm
        assert snapshot_module.item_base_cm is footprints.item_base_cm

    def test_nothing_else_in_the_app_walks_the_scene_for_casters(self) -> None:
        """Every producer of ``ShadowCaster`` and every reader of ``parent_bed_id``
        that turns it into a height is named here. A second walk fails this test."""
        src = Path(open_garden_planner.__file__).parent
        calls: dict[str, set[str]] = {}
        for path in src.rglob("*.py"):
            relative = path.relative_to(src).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = getattr(node.func, "id", getattr(node.func, "attr", ""))
                    calls.setdefault(name, set()).add(relative)
        assert calls["ShadowCaster"] == {"ui/canvas/sun_shadow_controller.py"}  # one maker
        # … and every consumer: nobody else turns casters into shadows (review P2-4)
        assert calls["compute_scene_shadows"] == {
            "ui/canvas/sun_shadow_controller.py",   # the overlay's recompute
            "core/shade_aggregation.py",            # the heatmap, once per daylight sample
        }
        assert calls["caster_fields"] == {"core/shadow_geometry.py"}  # the ONE unpacking, by type
        assert calls["collect_shadow_casters"] == {
            "ui/canvas/sun_shadow_controller.py",   # the overlay
        }
        assert calls["collect_identified_casters"] == {
            "ui/canvas/sun_shadow_controller.py",   # flattened for the overlay
            "ui/canvas/sun_exposure_snapshot.py",   # the heatmap and the per-plant estimates
        }
        assert calls["IdentifiedCaster"] == {"ui/canvas/sun_shadow_controller.py"}  # one maker
        assert calls["compute_grouped_shadows"] == {"core/shade_aggregation.py"}
        assert calls["GroupedCaster"] == {"core/shade_aggregation.py"}  # base included
        assert calls["shadow_region"] == {
            "ui/canvas/sun_shadow_controller.py",   # the ONE region repair (#444)
        }
        assert calls["item_base_cm"] == {
            "ui/canvas/sun_shadow_controller.py",   # 2D: the caster walk
            "ui/canvas/sun_exposure_snapshot.py",   # 2D: the receiver walk (#641)
            "ui/view3d/snapshot.py",                # 3D: the record walk
        }
        assert calls["standing_parent"] == {
            "ui/canvas/footprints.py",              # inside item_base_cm: the membership half
            "ui/canvas/sun_exposure_snapshot.py",   # which parent a sun receiver stands in
        }
        assert calls["is_solid_soil_parent"] == {"ui/canvas/footprints.py"}  # inside standing_parent
        assert calls["standing_base_cm"] == {"ui/canvas/footprints.py"}  # inside item_base_cm
        assert calls["soil_surface_cm"] == {
            "core/object_height.py",                # inside standing_base_cm
            "core/scene3d/builders/beds.py",        # where the 3D bed meshes put their soil
        }
        assert "parent_bed_id" not in inspect.getsource(sun_shadow_controller)
        assert "parent_bed_id" not in inspect.getsource(sun_heatmap)

    def test_the_overlay_paints_the_raised_shadow(self, canvas: CanvasView) -> None:
        """End to end through the real controller: the overlay's path IS the union of
        the casters with their bases, and its tip lies base / tan α beyond where the
        same plant cast from the ground."""
        garden = Garden(canvas)
        instant = datetime(2026, 6, 21, 18, 0, tzinfo=UTC)  # an evening sun, long shadows
        position = solar_position(BERLIN["latitude"], BERLIN["longitude"], instant)
        assert 5.0 < position.elevation_deg < 20.0
        controller = SunShadowController(garden.scene, lambda: BERLIN)
        controller.set_sim_datetime(instant)
        controller.set_enabled(True)
        overlay = next(i for i in garden.scene.items() if isinstance(i, SunShadowOverlayItem))
        path = overlay.path()
        painted = [(path.elementAt(i).x, path.elementAt(i).y) for i in range(path.elementCount())]
        casters = collect_shadow_casters(garden.scene, at_date=controller.clock.plan_date)
        assert {c.base_cm for c in casters} == {0.0, 38.0}
        expected = compute_scene_shadows(casters, position.elevation_deg, position.azimuth_deg)
        assert set(painted) == {point for polygon in expected for point in polygon}

        direction = shadow_direction_scene(position.azimuth_deg)

        def reach(points: Any) -> float:
            return max(x * direction[0] + y * direction[1] for x, y in points)

        plant = next(c for c in casters if c.base_cm > 0.0)
        tan_a = math.tan(math.radians(position.elevation_deg))
        raised_tip = reach(p for poly in compute_scene_shadows(
            [plant], position.elevation_deg, position.azimuth_deg) for p in poly)
        ground_tip = reach(p for poly in compute_scene_shadows(
            [ShadowCaster(plant.footprint, plant.height_cm)], position.elevation_deg,
            position.azimuth_deg) for p in poly)
        assert raised_tip - ground_tip == pytest.approx(38.0 / tan_a, abs=0.1)
        # What the user sees: the plant's tip now sticks out of the overlay …
        assert reach(painted) == pytest.approx(raised_tip, abs=1e-6)
        # … where, cast from the ground, it never left the bed's own shadow.
        bed = next(c for c in casters if c.base_cm == 0.0)
        bed_tip = reach(p for poly in compute_scene_shadows(
            [bed], position.elevation_deg, position.azimuth_deg) for p in poly)
        assert ground_tip < bed_tip < raised_tip
        controller.set_enabled(False)

    def test_the_overlay_s_key_carries_the_base(self, canvas: CanvasView) -> None:
        """Footprint and height unchanged, only the base differs: still a recompute."""
        garden = Garden(canvas)
        controller = SunShadowController(garden.scene, lambda: BERLIN)
        controller.set_sim_datetime(datetime(2026, 6, 21, 12, 0, tzinfo=UTC))
        controller.set_enabled(True)
        count = controller.recompute_count
        controller.recompute_now()
        assert controller.recompute_count == count  # nothing changed: the key holds
        garden.plant.parent_bed_id = None  # only the BASE changes: footprint and height stay
        controller.recompute_now()
        assert controller.recompute_count == count + 1
        controller.set_enabled(False)

    def test_a_bed_height_change_and_a_re_parent_recompute_the_overlay_through_the_command_stack(
        self, canvas: CanvasView, qtbot: Any
    ) -> None:
        """Neither edit repaints anything — a height is metadata, the link a Python
        attribute — so ``scene.changed`` never fires for them (#173). What reaches
        the overlay is the command stack's ``stack_changed``, wired to
        ``schedule_recompute`` exactly as ``application.py`` does (its connect line
        is pinned by ``test_shadow_overlay.py::test_app_wires_stack_changed_to_sun_controller``).
        Nobody calls ``recompute_now`` here."""
        garden = Garden(canvas)
        instant = datetime(2026, 6, 21, 18, 0, tzinfo=UTC)
        position = solar_position(BERLIN["latitude"], BERLIN["longitude"], instant)
        tan_a = math.tan(math.radians(position.elevation_deg))
        direction = shadow_direction_scene(position.azimuth_deg)
        controller = SunShadowController(garden.scene, lambda: BERLIN)
        controller.set_sim_datetime(instant)
        watch = OverlayWatch(qtbot, garden.scene, controller)
        controller.set_enabled(True)
        garden.commands.stack_changed.connect(controller.schedule_recompute)  # the app's wiring
        overlay = next(i for i in garden.scene.items() if isinstance(i, SunShadowOverlayItem))
        plant_far = max(x * direction[0] + y * direction[1]
                        for x, y in next(c for c in collect_shadow_casters(garden.scene)
                                         if c.height_cm == 60.0).footprint)

        def tip() -> float:
            """How far the overlay reaches beyond the plant's footprint, in cm."""
            path = overlay.path()
            return max(path.elementAt(i).x * direction[0] + path.elementAt(i).y * direction[1]
                       for i in range(path.elementCount())) - plant_far

        settled = watch.settled  # the recompute, its own scene.changed echo, the debounce after it
        count = controller.recompute_count
        settled(count)  # enabling recomputed once; its echo and the items' own are delivered
        assert tip() == pytest.approx((38.0 + 60.0) / tan_a, abs=0.01)

        garden.commands.execute(
            ChangePropertyCommand(garden.bed, "object height", None, 75.0, _set_height))
        settled(count + 1)
        assert tip() == pytest.approx((73.0 + 60.0) / tan_a, abs=0.01)  # the plant rose with its bed

        garden.commands.execute(
            SetParentBedCommand(garden.scene, garden.plant, garden.bed.item_id, None))
        settled(count + 2)
        # unlinked, the plant casts from the ground and ends inside the 75 cm bed's own shadow,
        # which is now the overlay's far edge — about 90 cm short of where the raised tip was
        assert 60.0 / tan_a < tip() < (73.0 + 60.0) / tan_a - 50.0

        garden.commands.undo()  # linked again
        settled(count + 3)
        assert tip() == pytest.approx((73.0 + 60.0) / tan_a, abs=0.01)
        garden.commands.undo()  # the bed is 40 cm again
        settled(count + 4)
        assert tip() == pytest.approx((38.0 + 60.0) / tan_a, abs=0.01)

        # Negative control: without the wiring the same edit goes unseen. ``settled`` has
        # waited for the last recompute's own echo, so nothing is on its way that could
        # carry this edit into the overlay (CI once read 6 == 1 + 4 here: a late echo —
        # ``TestTheOverlaysOwnEcho`` holds that race still).
        garden.commands.stack_changed.disconnect(controller.schedule_recompute)
        delivered = len(watch.changes)
        garden.commands.redo()
        assert not controller._debounce.isActive()  # nothing is scheduled …
        qtbot.wait(2 * controller._debounce.interval())  # longer than a debounce would take
        assert len(watch.changes) == delivered      # … a metadata edit emits no scene.changed …
        assert controller.recompute_count == count + 4  # … and nothing recomputed
        assert tip() == pytest.approx((38.0 + 60.0) / tan_a, abs=0.01)  # the overlay: still 40 cm
        controller.set_enabled(False)
