"""Phase 17 L4 "built world complete" (#388) end to end (§8.10).

live items → properties panel / commands → ``snapshot_records`` (with its context
pass) → ``SceneSync`` (production registry) → ``RecordingSink``

A real garden: a house drawn with the HOUSE tool (it makes its ridge), a stepping-stone
path south of it, a lawn with a terrace laid over it and a greenhouse standing on it,
a table and a parasol. Asserted:

1. the roof rows of the properties panel — style, pitch, overhang — are one undo step
   each, mark the plan modified, write nothing for "Automatic"/"Auto", refresh after an
   undo, survive a save and a load with no FILE_VERSION bump, and only a building has
   them; the 3D roof follows each edit;
2. the house's door faces the path, and moving the house along it is still a
   transform only (ADR-059);
3. the lawn's blades are cut out under the terrace and the greenhouse, and the lawn's
   ground tiles stay the painted lawn (its blades are ground detail);
4. a path's width is its width on the ground: the panel sets it in cm up to 5 m, a
   style preset gives a real path width, and the 3D stones follow;
5. an object without a height (the parasol) is BUILT at its illustrative height, casts
   no shadow in 3D and none in the 2D sun study.

Nothing is rendered: the sink is the recording double.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QComboBox, QDoubleSpinBox, QLabel

from open_garden_planner.core import ProjectManager
from open_garden_planner.core import roof_style as rs
from open_garden_planner.core.commands import CreateItemCommand, MoveItemsCommand
from open_garden_planner.core.item_look import MAX_LINE_WIDTH_CM
from open_garden_planner.core.object_height_estimate import ESTIMATED_OBJECT_HEIGHTS_CM
from open_garden_planner.core.object_types import PATH_FENCE_STYLES, ObjectType, PathFenceStyle
from open_garden_planner.core.project import FILE_VERSION
from open_garden_planner.core.scene3d import RecordingSink, SceneSync, pose_points
from open_garden_planner.core.scene3d.builders import production_registry, surfaces
from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.sun_shadow_controller import collect_shadow_casters
from open_garden_planner.ui.panels import PropertiesPanel
from open_garden_planner.ui.view3d.snapshot import snapshot_records


def _field(panel: PropertiesPanel, label_text: str) -> Any:
    form = panel._form_layout
    for row in range(form.rowCount()):
        label = form.itemAt(row, form.ItemRole.LabelRole)
        field = form.itemAt(row, form.ItemRole.FieldRole)
        if label is not None and field is not None and isinstance(label.widget(), QLabel) \
                and label_text in label.widget().text():
            return field.widget()
    return None


class Garden:
    """The story's garden, on a real view."""

    def __init__(self, view: CanvasView, mouse_event: Any) -> None:
        self.view = view
        self.scene = view.scene()
        self.commands = view.command_manager
        layer = self.scene.active_layer.id

        # the lawn first: everything drawn later lies above it
        self.lawn = RectangleItem(600.0, 0.0, 2400.0, 1800.0, object_type=ObjectType.LAWN, layer_id=layer)
        self.commands.execute(CreateItemCommand(self.scene, self.lawn, "lawn"))

        # a house with its ridge, drawn with the HOUSE tool
        before = set(self.scene.items())
        view.set_active_tool(ToolType.HOUSE)
        tool = view.tool_manager.active_tool
        corners = [(1000.0, 800.0), (1900.0, 800.0), (1900.0, 1340.0), (1000.0, 1340.0)]
        for x, y in corners:
            tool.mouse_press(mouse_event, QPointF(x, y))
        tool.mouse_double_click(mouse_event, QPointF(*corners[-1]))
        (self.house,) = [i for i in set(self.scene.items()) - before if isinstance(i, PolygonItem)]

        # a stepping-stone path south of the house (the scene's y is north)
        self.path = PolylineItem([QPointF(200.0, 400.0), QPointF(2800.0, 400.0)],
                                 object_type=ObjectType.PATH, layer_id=layer,
                                 path_fence_style=PathFenceStyle.STEPPING_STONES)
        self.commands.execute(CreateItemCommand(self.scene, self.path, "path"))

        # a terrace laid over the lawn, a greenhouse standing on it
        self.terrace = RectangleItem(2200.0, 1000.0, 400.0, 300.0, object_type=ObjectType.TERRACE_PATIO,
                                     layer_id=layer)
        self.commands.execute(CreateItemCommand(self.scene, self.terrace, "terrace"))
        self.greenhouse = RectangleItem(700.0, 1400.0, 300.0, 200.0, object_type=ObjectType.GREENHOUSE,
                                        layer_id=layer)
        self.commands.execute(CreateItemCommand(self.scene, self.greenhouse, "greenhouse"))

        # a table and a parasol (no height of its own: an illustrative one in 3D)
        self.table = RectangleItem(2300.0, 200.0, 160.0, 90.0, object_type=ObjectType.TABLE_RECTANGULAR,
                                   layer_id=layer)
        self.commands.execute(CreateItemCommand(self.scene, self.table, "table"))
        self.parasol = RectangleItem(2500.0, 200.0, 250.0, 250.0, object_type=ObjectType.PARASOL,
                                     layer_id=layer)
        self.commands.execute(CreateItemCommand(self.scene, self.parasol, "parasol"))

    @staticmethod
    def id(item: Any) -> str:
        return str(item.item_id)


class Pipeline:
    """snapshot → sync → sink with the production registry."""

    def __init__(self, scene: Any) -> None:
        self.scene = scene
        self.sink = RecordingSink()
        self.sync = SceneSync(self.sink, production_registry(), validate=True)

    def tick(self) -> list[tuple[str, str | None]]:
        self.sink.clear_calls()
        self.sync.apply(snapshot_records(self.scene))
        assert self.sync.failures == {}
        return self.sink.ops()

    def part(self, item: Any, name: str) -> Any:
        (part,) = [p for p in self.sink.item(Garden.id(item)).parts if p.name == name]
        return part

    def posed(self, item: Any, name: str) -> np.ndarray:
        held = self.sink.item(Garden.id(item))
        return pose_points(held.transform, self.part(item, name).mesh.positions)


@pytest.fixture
def garden(canvas: CanvasView, mouse_event: Any) -> Garden:
    return Garden(canvas, mouse_event)


# ── 1. the roof rows ─────────────────────────────────────────────────────────


def _ridge_length(roof: np.ndarray) -> float:
    """How long the roof's top line runs (scene east-west: the house's ridge)."""
    top = roof[roof[:, 2] >= roof[:, 2].max() - 0.5]
    return float(np.ptp(top[:, 0]))


def test_the_roof_rows_edit_the_3d_roof_one_undo_step_each(garden: Garden) -> None:
    pipeline = Pipeline(garden.scene)
    pipeline.tick()
    gable = pipeline.posed(garden.house, "roof")
    assert _ridge_length(gable) > 900.0  # automatic: a gable along the live ridge, eaves to eaves

    panel = PropertiesPanel(command_manager=garden.commands)
    panel.set_selected_items([garden.house])
    style = _field(panel, "Roof style")
    pitch = _field(panel, "Roof pitch")
    overhang = _field(panel, "Roof overhang")
    assert isinstance(style, QComboBox) and isinstance(pitch, QDoubleSpinBox)
    assert isinstance(overhang, QDoubleSpinBox)
    assert style.currentData() is None and pitch.value() == 0.0 and overhang.value() == -1.0
    assert (pitch.specialValueText(), overhang.specialValueText()) == ("Auto", "Auto")

    changes: list[bool] = []
    garden.commands.stack_changed.connect(lambda: changes.append(True))

    # a hip roof: every eave slopes, the ridge is shorter than the house
    style.setCurrentIndex(style.findData(rs.HIP))
    assert garden.house.metadata[rs.STYLE_KEY] == rs.HIP and len(changes) == 1
    pipeline.tick()
    assert pipeline.sync.records[Garden.id(garden.house)].params["roof_style"] == rs.HIP
    hip = pipeline.posed(garden.house, "roof")
    assert _ridge_length(hip) < 900.0 - 540.0 + 1.0
    assert float(hip[:, 2].max()) == pytest.approx(float(gable[:, 2].max()))  # top = height

    # a steeper pitch lowers the eaves (a hip's walls end at its eaves) under the same top
    eaves_before = float(pipeline.posed(garden.house, "walls")[:, 2].max())
    pitch.setValue(50.0)
    assert garden.house.metadata[rs.PITCH_KEY] == 50.0 and len(changes) == 2
    pipeline.tick()
    assert float(pipeline.posed(garden.house, "walls")[:, 2].max()) < eaves_before - 5.0
    assert float(pipeline.posed(garden.house, "roof")[:, 2].max()) == pytest.approx(float(gable[:, 2].max()))

    # no overhang: the roof ends at the walls
    overhang.setValue(0.0)
    assert garden.house.metadata[rs.OVERHANG_KEY] == 0.0 and len(changes) == 3
    pipeline.tick()
    roof = pipeline.posed(garden.house, "roof")
    assert float(np.ptp(roof[:, 0])) == pytest.approx(900.0, abs=0.5)

    # "Auto" removes the key, it does not store a value
    overhang.setValue(-1.0)
    assert rs.OVERHANG_KEY not in garden.house.metadata and len(changes) == 4

    # each edit is ONE undo step; the panel shows the value after an undo
    garden.commands.undo()
    panel.set_selected_items([garden.house])
    assert garden.house.metadata[rs.OVERHANG_KEY] == 0.0 and overhang.value() == 0.0
    for _ in range(3):
        garden.commands.undo()
    panel.set_selected_items([garden.house])
    assert not {rs.STYLE_KEY, rs.PITCH_KEY, rs.OVERHANG_KEY} & set(garden.house.metadata)
    assert style.currentData() is None and pitch.value() == 0.0 and overhang.value() == -1.0
    pipeline.tick()
    assert _ridge_length(pipeline.posed(garden.house, "roof")) == pytest.approx(_ridge_length(gable))


def test_the_roof_survives_a_save_and_a_load(garden: Garden, tmp_path) -> None:
    garden.house.metadata.update({rs.STYLE_KEY: rs.SHED, rs.PITCH_KEY: 20.0, rs.OVERHANG_KEY: 45.0})
    manager = ProjectManager()
    path = tmp_path / "roof.ogp"
    manager.save(garden.scene, path)
    garden.scene.clear()
    manager.load(garden.scene, path)
    (house,) = [i for i in garden.scene.items() if getattr(i, "object_type", None) is ObjectType.HOUSE]
    assert {key: house.metadata[key] for key in (rs.STYLE_KEY, rs.PITCH_KEY, rs.OVERHANG_KEY)} == {
        rs.STYLE_KEY: rs.SHED, rs.PITCH_KEY: 20.0, rs.OVERHANG_KEY: 45.0}
    assert FILE_VERSION == "1.4"  # additive metadata: no bump


@pytest.mark.parametrize("kind", ["TOOL_SHED", "GARAGE_SHED", "TABLE_RECTANGULAR", "LAWN"])
def test_only_a_building_has_roof_rows(qtbot, garden: Garden, kind: str) -> None:  # noqa: ARG001
    item = RectangleItem(0.0, 0.0, 300.0, 200.0, object_type=ObjectType[kind])
    panel = PropertiesPanel(command_manager=garden.commands)
    panel.set_selected_items([item])
    assert (_field(panel, "Roof style") is not None) == (kind in rs.BUILDING_KINDS)


# ── 2. the door faces the path ───────────────────────────────────────────────


def test_the_door_faces_the_path_and_a_move_is_a_transform(garden: Garden) -> None:
    pipeline = Pipeline(garden.scene)
    pipeline.tick()
    house_id = Garden.id(garden.house)
    record = pipeline.sync.records[house_id]
    wall = record.params["door_wall"]
    ring = np.asarray(record.footprints[0])
    middle = (ring[wall] + ring[(wall + 1) % len(ring)]) / 2.0
    posed = pose_points(record.transform, np.array([[middle[0], middle[1], 0.0]]))[0]
    centre = pose_points(record.transform, np.array([[0.0, 0.0, 0.0]]))[0]
    assert posed[1] < centre[1] - 200.0  # the south wall: the path's side

    door = pipeline.posed(garden.house, "facade")
    assert float(door[:, 1].min()) < centre[1] - 260.0  # its panels stand on that wall

    garden.commands.execute(MoveItemsCommand([garden.house], QPointF(300.0, 0.0)))
    ops = [op for op in pipeline.tick() if op[1] == house_id]
    assert ops == [("update_transform", house_id)]  # the door's wall did not change


# ── 3. the lawn is cut out under the terrace and the greenhouse ──────────────


def test_the_lawn_has_no_blades_under_the_terrace_or_the_greenhouse(garden: Garden) -> None:
    pipeline = Pipeline(garden.scene)
    pipeline.tick()
    blades = pipeline.part(garden.lawn, surfaces.LAWN_BLADES)
    assert blades.ground_detail and not blades.casts_shadow
    roots = pipeline.posed(garden.lawn, surfaces.LAWN_BLADES)[::5, :2]
    assert len(roots) > 1000
    for item in (garden.terrace, garden.greenhouse):
        rect = item.mapRectToScene(item.rect())
        inside = ((roots[:, 0] > rect.left() + 5.0) & (roots[:, 0] < rect.right() - 5.0)
                  & (roots[:, 1] > rect.top() + 5.0) & (roots[:, 1] < rect.bottom() - 5.0))
        assert not inside.any(), item.object_type
    # the lawn is still painted on the ground: it is no solid
    assert Garden.id(garden.lawn) not in pipeline.sync.solid_ids
    assert Garden.id(garden.greenhouse) in pipeline.sync.solid_ids

    # moving the terrace moves its cut-out
    garden.commands.execute(MoveItemsCommand([garden.terrace], QPointF(-800.0, 0.0)))
    pipeline.tick()
    moved = pipeline.posed(garden.lawn, surfaces.LAWN_BLADES)[::5, :2]
    assert ((moved[:, 0] > 2205.0) & (moved[:, 0] < 2595.0)
            & (moved[:, 1] > 1005.0) & (moved[:, 1] < 1295.0)).any()


# ── 4. a path's width is its width on the ground ─────────────────────────────


def test_a_path_s_width_is_set_in_cm_and_the_stones_follow(garden: Garden, tmp_path) -> None:
    assert garden.path.pen().widthF() == PATH_FENCE_STYLES[PathFenceStyle.STEPPING_STONES].stroke_width
    assert garden.path.pen().widthF() >= 60.0  # a path one walks on, not a 6 cm line
    pipeline = Pipeline(garden.scene)
    pipeline.tick()
    narrow = pipeline.posed(garden.path, "stones")

    panel = PropertiesPanel(command_manager=garden.commands)
    panel.set_selected_items([garden.path])
    width = _field(panel, "Stroke Width")
    assert isinstance(width, QDoubleSpinBox)
    assert width.maximum() == MAX_LINE_WIDTH_CM and width.suffix() == " cm"
    width.setValue(150.0)
    assert garden.path.pen().widthF() == 150.0
    pipeline.tick()
    wide = pipeline.posed(garden.path, "stones")
    assert float(np.ptp(wide[:, 1])) > float(np.ptp(narrow[:, 1])) + 40.0  # wider stones
    assert float(np.ptp(wide[:, 1])) <= 150.0

    # and it is the width the plan keeps
    manager = ProjectManager()
    path = tmp_path / "path.ogp"
    manager.save(garden.scene, path)
    garden.scene.clear()
    manager.load(garden.scene, path)
    (loaded,) = [i for i in garden.scene.items() if getattr(i, "object_type", None) is ObjectType.PATH]
    assert loaded.pen().widthF() == 150.0


def test_a_shape_s_outline_keeps_its_pixel_range(garden: Garden) -> None:
    panel = PropertiesPanel(command_manager=garden.commands)
    panel.set_selected_items([garden.terrace])
    width = _field(panel, "Stroke Width")
    assert width.maximum() == 20.0 and width.suffix() == " px"


# ── 5. an object without a height ────────────────────────────────────────────


def test_a_parasol_is_built_at_its_illustrative_height_and_casts_no_shadow(garden: Garden) -> None:
    pipeline = Pipeline(garden.scene)
    pipeline.tick()
    parasol_id = Garden.id(garden.parasol)
    record = pipeline.sync.records[parasol_id]
    assert record.height_cm is None  # the plan holds no height for it
    parts = pipeline.sink.item(parasol_id).parts
    assert parts and not any(part.casts_shadow for part in parts)
    top = max(float(pipeline.posed(garden.parasol, part.name)[:, 2].max()) for part in parts)
    assert top == pytest.approx(ESTIMATED_OBJECT_HEIGHTS_CM["PARASOL"], rel=0.01)
    # the 2D sun study: no caster for it — and the table (a real height) is one
    casters = collect_shadow_casters(garden.scene)
    heights = sorted(round(caster.height_cm) for caster in casters)
    assert ESTIMATED_OBJECT_HEIGHTS_CM["PARASOL"] not in heights
    assert any(part.casts_shadow for part in pipeline.sink.item(Garden.id(garden.table)).parts)
