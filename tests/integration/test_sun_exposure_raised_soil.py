"""A plant that stands on a raised bed is not shaded by the bed (US-F3 x the base rule).

Measured on v1.30.1 before this was written: a tomato in a 40 cm raised bed in the open,
Berlin, 21 June — **0.0 hours of sun**, a "too little sun" record and a warning badge;
16.5 hours for the same tomato on open ground. The per-plant estimate samples the ground
point under the plant and left out only the plant's own solid; the bed is a solid too,
and its footprint covers that point all day. So every plant in every raised bed warned.

The rule (one, and it existed): a plant that stands on a parent's SOIL — linked to a
visible raised bed or container and its centre inside it, ``footprints.item_base_cm`` —
is not shaded by that parent. Everything else shades it as at ground level.

Through the real main window, the real worker and the real coordinator.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.core.commands import (
    ChangePropertyCommand,
    CreateItemCommand,
    DeleteItemsCommand,
    SetParentBedCommand,
)
from open_garden_planner.core.object_height import METADATA_KEY
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.shade_aggregation import SAMPLE_STEP_MINUTES
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.sun_exposure_snapshot import collect_exposure_snapshot
from open_garden_planner.ui.theme import ThemeMode, apply_theme, is_dark_theme

DAY = date(2026, 6, 21)
BERLIN = {"latitude": 52.52, "longitude": 13.405}
ONE_SAMPLE_H = SAMPLE_STEP_MINUTES / 60.0
TOMATO = {"common_name": "Tomato", "scientific_name": "Solanum lycopersicum",
          "max_spread_cm": 60, "max_height_cm": 180, "sun_requirement": "full_sun",
          "permaculture_layer": "herbaceous"}


class Plot:
    """The real main window on a 24 m x 24 m plan in Berlin on 21 June."""

    def __init__(self, window: GardenPlannerApp, qtbot: Any) -> None:
        self.window, self.qtbot = window, qtbot
        self.scene = window.canvas_scene
        self.commands = window.canvas_view.command_manager
        self.scene.resize_canvas(2400.0, 2400.0)
        window._project_manager.set_location(dict(BERLIN))
        window._sim_clock.set_date(DAY)

    def tomato(self, name: str, x: float, y: float, radius: float = 30.0) -> CircleItem:
        item = CircleItem(x, y, radius, ObjectType.PERENNIAL, name=name,
                          layer_id=self.scene.active_layer.id,
                          metadata={"plant_species": dict(TOMATO), METADATA_KEY: 180.0})
        self.commands.execute(CreateItemCommand(self.scene, item, "plant"))   # auto-parents
        return item

    def bed(self, x: float, y: float, height: float = 40.0) -> RectangleItem:
        item = RectangleItem(x, y, 200.0, 120.0, object_type=ObjectType.RAISED_BED,
                             layer_id=self.scene.active_layer.id, metadata={METADATA_KEY: height})
        self.commands.execute(CreateItemCommand(self.scene, item, "bed"))
        return item

    def wall(self, x1: float, x2: float, y: float, height: float = 300.0) -> PolylineItem:
        item = PolylineItem([QPointF(x1, y), QPointF(x2, y)], object_type=ObjectType.WALL,
                            layer_id=self.scene.active_layer.id)
        item.metadata[METADATA_KEY] = height
        self.commands.execute(CreateItemCommand(self.scene, item, "wall"))
        return item

    def compute(self) -> None:
        window, qtbot = self.window, self.qtbot
        with qtbot.waitSignal(window._sun_heatmap.finished, timeout=60000) as blocker:
            window._on_heatmap_requested()
        assert blocker.args == [True]
        coordinator = window.sun_exposure_coordinator
        qtbot.waitUntil(lambda: bool(coordinator.evaluations) and any(
            e.hours is not None for e in coordinator.evaluations.values()), timeout=10000)
        qtbot.wait(150)   # the coordinator's 60 ms refresh after the last signal

    def hours(self, item: Any) -> float | None:
        return self.window.sun_exposure_coordinator.evaluations[str(item.item_id)].hours

    def warned(self, item: Any) -> bool:
        records = [r for r in self.window.diagnostics_panel.records if r.kind == "sun_mismatch"
                   and r.details.get("receiver_id") == str(item.item_id)]
        badge = getattr(item, "_sun_badge", None)
        assert bool(records) == bool(badge is not None and badge.isVisible()), "record and badge agree"
        return bool(records)

    def stands_on(self, item: Any) -> str | None:
        snapshot = collect_exposure_snapshot(self.scene, dict(BERLIN), DAY)
        (receiver,) = [r for r in snapshot.receivers if r.item_id == str(item.item_id)]
        return receiver.stands_on


@pytest.fixture()
def plot(qtbot, monkeypatch: pytest.MonkeyPatch) -> Any:
    previous = ThemeMode.DARK if is_dark_theme() else ThemeMode.LIGHT
    window = GardenPlannerApp()
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_confirm_discard_changes", lambda: True)
    yield Plot(window, qtbot)
    window._sun_heatmap.shutdown()
    apply_theme(QApplication.instance(), previous)


def test_a_tomato_on_a_raised_bed_gets_the_sun_of_a_tomato_on_open_ground(plot: Plot) -> None:
    open_ground = plot.tomato("open ground", 400.0, 400.0)
    bed = plot.bed(1000.0, 400.0)
    on_bed = plot.tomato("on the bed", 1100.0, 460.0)
    assert on_bed.parent_bed_id == bed.item_id, "created inside the bed: linked by the command"
    assert plot.stands_on(on_bed) == str(bed.item_id) and plot.stands_on(open_ground) is None

    plot.compute()
    assert plot.hours(open_ground) == 16.5, "the reference: Berlin, 21 June, nothing in the way"
    assert plot.hours(on_bed) == pytest.approx(16.5, abs=ONE_SAMPLE_H)
    assert not plot.warned(on_bed) and not plot.warned(open_ground)


def test_the_bed_is_spared_and_nothing_else_is(plot: Plot) -> None:
    """A 3 m wall 60 cm south of the bed takes the midday sun from the tomato on the bed
    exactly as it takes it from the same tomato at the same place once the bed is gone:
    everything but its own bed shades the plant as at ground level."""
    bed = plot.bed(1000.0, 400.0)
    on_bed = plot.tomato("on the bed", 1100.0, 460.0)
    plot.wall(900.0, 1300.0, 340.0)
    assert plot.stands_on(on_bed) == str(bed.item_id)

    plot.compute()
    shaded = plot.hours(on_bed)
    assert shaded is not None and 2.0 < shaded < 16.5 - 3.0, (
        f"hours of midday sun are gone, not all of the day: {shaded}")

    plot.commands.execute(DeleteItemsCommand(plot.scene, [bed]))     # the same plant, on the ground
    plot.qtbot.waitUntil(lambda: plot.window._sun_heatmap.exposure_reason == "stale", timeout=2000)
    assert plot.stands_on(on_bed) is None
    plot.compute()
    assert plot.hours(on_bed) == shaded, "the wall's share is the same with and without the bed"


def test_a_plant_on_the_ground_next_to_the_bed_is_still_shaded_by_the_bed(plot: Plot) -> None:
    bed = plot.bed(1000.0, 400.0)                              # y 400 … 520
    beside = plot.tomato("north of the bed", 1100.0, 530.0, radius=5.0)   # 10 cm off its edge
    far = plot.tomato("far away", 400.0, 1800.0, radius=5.0)
    assert beside.parent_bed_id is None and plot.stands_on(beside) is None
    assert bed.item_id is not None

    plot.compute()
    assert plot.hours(far) == 16.5
    near = plot.hours(beside)
    assert near is not None and near <= 16.5 - 4 * ONE_SAMPLE_H, (
        f"a 40 cm bed takes sun from the ground 15 cm north of it: {near} h")


def test_a_plant_in_the_bed_without_a_link_stands_on_the_ground_inside_it(plot: Plot) -> None:
    """The stated limit, pinned so that it is a decision: the base rule lifts a plant only
    when it is LINKED to the bed. An unlinked plant inside the bed's outline stands on the
    ground, inside the bed's solid — 0 hours, and the same plant linked: a day of sun."""
    bed = plot.bed(1000.0, 400.0)
    plant = plot.tomato("in the bed", 1100.0, 460.0)
    plot.commands.execute(SetParentBedCommand(plot.scene, plant, bed.item_id, None))
    assert plant.parent_bed_id is None and plot.stands_on(plant) is None
    plot.compute()
    assert plot.hours(plant) == 0.0 and plot.warned(plant)

    plot.commands.execute(SetParentBedCommand(plot.scene, plant, None, bed.item_id))
    plot.qtbot.waitUntil(lambda: plot.window._sun_heatmap.exposure_reason == "stale", timeout=2000)
    plot.compute()
    assert plot.hours(plant) == pytest.approx(16.5, abs=ONE_SAMPLE_H) and not plot.warned(plant)


def test_where_a_plant_stands_is_part_of_what_an_estimate_was_computed_for(plot: Plot) -> None:
    """The snapshot an estimate belongs to carries the base and the soil parent: lowering
    the bed to the ground changes neither a footprint nor a height of the plant, and the
    estimate must still go stale."""
    bed = plot.bed(1000.0, 400.0)
    plant = plot.tomato("on the bed", 1100.0, 460.0)
    plot.compute()
    assert plot.window._sun_heatmap.exposure_reason == "ready"
    before = collect_exposure_snapshot(plot.scene, dict(BERLIN), DAY)
    (caster,) = [c for c in before.casters if c.item_id == str(plant.item_id)]
    assert caster.base_cm == 38.0

    def set_height(item: Any, value: Any) -> None:
        item.metadata[METADATA_KEY] = value

    plot.commands.execute(ChangePropertyCommand(bed, "object height", 40.0, 2.0, set_height))
    after = collect_exposure_snapshot(plot.scene, dict(BERLIN), DAY)
    (lowered,) = [c for c in after.casters if c.item_id == str(plant.item_id)]
    assert lowered.base_cm == 0.0 and lowered.footprints == caster.footprints
    assert lowered.height_cm == caster.height_cm, "only where it STANDS changed"
    plot.qtbot.waitUntil(lambda: plot.window._sun_heatmap.exposure_reason == "stale", timeout=2000)


@pytest.mark.parametrize(("parent_type", "height", "visible", "in_it"), [
    (ObjectType.RAISED_BED, 40.0, True, True),
    (ObjectType.CONTAINER, 30.0, True, True),
    (ObjectType.GARDEN_BED, 15.0, True, True),       # a mounded bed: a solid
    (ObjectType.GARDEN_BED, None, True, False),      # in the ground: nothing to stand in
    (ObjectType.TRELLIS, 200.0, True, False),        # a linked parent that holds no soil
    (ObjectType.RAISED_BED, 40.0, False, False),     # a hidden parent is not there
])
def test_which_parent_a_plant_stands_in(plot: Plot, parent_type: ObjectType, height: float | None,
                                        visible: bool, in_it: bool) -> None:
    """``footprints.standing_parent`` — the membership half of the base rule, as the sun
    receivers ask it: linked, visible, a soil-capable SOLID, and the centre inside."""
    parent = RectangleItem(1000.0, 400.0, 200.0, 120.0, object_type=parent_type,
                           layer_id=plot.scene.active_layer.id)
    if height is not None:
        parent.metadata[METADATA_KEY] = height
    plot.commands.execute(CreateItemCommand(plot.scene, parent, "parent"))
    plant = plot.tomato("plant", 1100.0, 460.0)
    if plant.parent_bed_id != parent.item_id:
        plot.commands.execute(SetParentBedCommand(plot.scene, plant, plant.parent_bed_id,
                                                  parent.item_id))
    assert plant.parent_bed_id == parent.item_id, "linked in every row: only the parent differs"
    parent.setVisible(visible)
    assert plot.stands_on(plant) == (str(parent.item_id) if in_it else None)
    # … and a linked plant whose centre is OUTSIDE its parent stands in nothing
    plant.setPos(plant.pos() + QPointF(600.0, 0.0))
    assert plant.parent_bed_id == parent.item_id and plot.stands_on(plant) is None


def test_an_edging_two_centimetres_high_lifts_nothing_and_is_spared_all_the_same(plot: Plot) -> None:
    """A raised bed typed 2 cm high has its soil AT the ground (the soil lies 2 cm below a
    bed's rim): the base rule lifts nothing. It is a solid all the same — its footprint
    covers the ground point under its plants — and they stand in it: spared, like the
    40 cm bed. (Asking "is the plant lifted?" instead of "is it in the parent's solid?"
    would have left every plant in such an edging at 0 hours.)"""
    bed = plot.bed(1000.0, 400.0, height=2.0)
    plant = plot.tomato("in the edging", 1100.0, 460.0)
    snapshot = collect_exposure_snapshot(plot.scene, dict(BERLIN), DAY)
    (caster,) = [c for c in snapshot.casters if c.item_id == str(plant.item_id)]
    assert caster.base_cm == 0.0 and plot.stands_on(plant) == str(bed.item_id)
    plot.compute()
    assert plot.hours(plant) == pytest.approx(16.5, abs=ONE_SAMPLE_H) and not plot.warned(plant)
