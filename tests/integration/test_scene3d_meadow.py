"""A lawn given the WILDFLOWER fill becomes a flower meadow in 3D (#940) — end to end (§8.10).

live lawn → the properties panel's fill pattern (one undo step) → ``snapshot_records``
→ ``SceneSync`` (production registry) → ``RecordingSink``

Asserted:

1. choosing "Wildflower Meadow" for a lawn writes the pattern into its record — and
   only then: the record of a lawn with any other fill is what it was before #940;
2. the meadow is built: the blades' part (tinted, taller) and the flower heads' part
   (untinted), both under the blades' name; undo gives back the plain lawn, mesh for
   mesh, and the item's 2D picture is the one the fill pattern paints;
3. no other kind with the WILDFLOWER fill changes its record (a terrace keeps the
   pattern it always carried; every other kind carries none).

Nothing is rendered: the sink is the recording double.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from PyQt6.QtWidgets import QComboBox, QLabel

from open_garden_planner.core.commands import CreateItemCommand
from open_garden_planner.core.fill_patterns import FillPattern, create_pattern_brush
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.scene3d import RecordingSink, SceneSync
from open_garden_planner.core.scene3d.builders import production_registry, surfaces
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
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


def _lawn(canvas: CanvasView) -> RectangleItem:
    lawn = RectangleItem(0.0, 0.0, 800.0, 600.0, object_type=ObjectType.LAWN,
                         layer_id=canvas.scene().active_layer.id)
    canvas.command_manager.execute(CreateItemCommand(canvas.scene(), lawn, "lawn"))
    return lawn


def _fill(item: Any, pattern: FillPattern) -> None:
    """A fill pattern as the properties panel gives it: the attribute and its brush."""
    item.fill_pattern = pattern
    item.setBrush(create_pattern_brush(pattern, item.fill_color))


def _parts(sync: SceneSync, sink: RecordingSink, scene: Any, item: Any) -> tuple[Any, ...]:
    sync.apply(snapshot_records(scene))
    assert sync.failures == {}
    return tuple(sink.item(str(item.item_id)).parts)


def test_a_lawn_given_the_wildflower_fill_is_a_meadow_and_undo_gives_the_lawn_back(
        canvas: CanvasView) -> None:
    scene = canvas.scene()
    lawn = _lawn(canvas)
    item_id = str(lawn.item_id)
    sink = RecordingSink()
    sync = SceneSync(sink, production_registry(), validate=True)
    plain_record = snapshot_records(scene)[item_id]
    assert "surface_pattern" not in plain_record.params   # a lawn's GRASS fill: no pattern param
    (plain,) = _parts(sync, sink, scene, lawn)
    assert plain.tinted and plain.name == surfaces.LAWN_BLADES

    panel = PropertiesPanel(command_manager=canvas.command_manager)
    panel.set_selected_items([lawn])
    combo = _field(panel, "Fill Pattern")
    assert isinstance(combo, QComboBox)
    changes: list[bool] = []
    canvas.command_manager.stack_changed.connect(lambda: changes.append(True))
    combo.setCurrentIndex(combo.findData(FillPattern.WILDFLOWER))
    assert lawn.fill_pattern is FillPattern.WILDFLOWER and len(changes) == 1   # one undo step

    record = snapshot_records(scene)[item_id]
    assert record.params["surface_pattern"] == "WILDFLOWER" and surfaces.is_meadow(record)
    assert record.material.pattern == "WILDFLOWER"     # what the ground bake paints, as before
    blades, flowers = _parts(sync, sink, scene, lawn)
    assert (blades.name, flowers.name) == (surfaces.LAWN_BLADES, surfaces.LAWN_BLADES)
    assert blades.tinted and not flowers.tinted and flowers.material_kind == "grass"
    assert float(np.median(blades.mesh.positions[:, 2])) > 2.0 * float(np.median(plain.mesh.positions[:, 2]))
    assert lawn.brush() == create_pattern_brush(FillPattern.WILDFLOWER, lawn.fill_color)   # the 2D picture

    canvas.command_manager.undo()
    assert lawn.fill_pattern is FillPattern.GRASS
    assert snapshot_records(scene)[item_id] == plain_record
    (again,) = _parts(sync, sink, scene, lawn)
    assert again == plain


@pytest.mark.parametrize("kind", [ObjectType.GARDEN_BED, ObjectType.GENERIC_RECTANGLE,
                                  ObjectType.HEDGE_POLYGON, ObjectType.TERRACE_PATIO,
                                  ObjectType.DRIVEWAY, ObjectType.POND_POOL])
def test_another_kind_with_the_wildflower_fill_keeps_its_record(canvas: CanvasView, kind: ObjectType) -> None:
    scene = canvas.scene()
    item = RectangleItem(0.0, 0.0, 500.0, 400.0, object_type=kind, layer_id=scene.active_layer.id)
    canvas.command_manager.execute(CreateItemCommand(scene, item, "item"))
    _fill(item, FillPattern.SOLID)
    solid = snapshot_records(scene)[str(item.item_id)]
    _fill(item, FillPattern.WILDFLOWER)
    flowered = snapshot_records(scene)[str(item.item_id)]
    if kind in (ObjectType.TERRACE_PATIO, ObjectType.DRIVEWAY):   # their relief always read the pattern (L4.2)
        assert flowered.params["surface_pattern"] == "WILDFLOWER"
        assert not surfaces.is_meadow(flowered)
    else:
        assert "surface_pattern" not in flowered.params
        assert flowered.params == solid.params
