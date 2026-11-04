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
from open_garden_planner.core.object_height import (
    METADATA_KEY,
    effective_height_cm,
)
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.shade_aggregation import SAMPLE_STEP_MINUTES
from open_garden_planner.ui.canvas.footprints import holds_plants
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
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
        window._sun_toolbar._heatmap_button.setChecked(True)
        readiness = window._live_sun_map.ensure_current()
        qtbot.waitUntil(readiness.done, timeout=60000)
        readiness.result()
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

    def elevation(self, item: Any) -> float:
        snapshot = collect_exposure_snapshot(self.scene, dict(BERLIN), DAY)
        (receiver,) = [r for r in snapshot.receivers if r.item_id == str(item.item_id)]
        return receiver.elevation_cm


@pytest.fixture()
def plot(qtbot, monkeypatch: pytest.MonkeyPatch) -> Any:
    previous = ThemeMode.DARK if is_dark_theme() else ThemeMode.LIGHT
    prev_stylesheet = QApplication.instance().styleSheet() if QApplication.instance() else ""
    window = GardenPlannerApp()
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_confirm_discard_changes", lambda: True)
    yield Plot(window, qtbot)
    window._sun_heatmap.shutdown()
    apply_theme(QApplication.instance(), previous)
    if not prev_stylesheet and QApplication.instance():
        QApplication.instance().setStyleSheet("")


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
    on_ground_hours = plot.hours(on_bed)
    assert on_ground_hours is not None
    assert on_ground_hours < shaded, "on ground without bed the plant gets less sun than when elevated (#641)"
    assert on_ground_hours == pytest.approx(11.5, abs=ONE_SAMPLE_H)
    assert shaded == pytest.approx(12.0, abs=ONE_SAMPLE_H)


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


def test_a_plant_in_the_bed_without_a_link_gets_the_sun_of_the_bed(plot: Plot) -> None:
    """A plant inside a bed's outline reads the bed's real sun whether or not the link
    was made (#481).

    The link is bookkeeping and follows only some edit paths (#443), so a bed drawn
    around an existing plant, or a plant moved in with the arrow keys, has no link. The
    estimate no longer trusts the link alone: every soil solid whose outline contains
    the plant's point is left out of its shade, exactly like a linked plant's parent
    (ADR-056 addendum). Before #481 this read 0 hours and warned.
    """
    bed = plot.bed(1000.0, 400.0)
    plant = plot.tomato("in the bed", 1100.0, 460.0)
    plot.commands.execute(SetParentBedCommand(plot.scene, plant, bed.item_id, None))
    assert plant.parent_bed_id is None and plot.stands_on(plant) is None
    plot.compute()
    assert plot.hours(plant) == pytest.approx(16.5, abs=ONE_SAMPLE_H) and not plot.warned(plant)

    plot.commands.execute(SetParentBedCommand(plot.scene, plant, None, bed.item_id))
    plot.qtbot.waitUntil(lambda: plot.window._sun_heatmap.exposure_reason == "stale", timeout=2000)
    plot.compute()
    assert plot.hours(plant) == pytest.approx(16.5, abs=ONE_SAMPLE_H) and not plot.warned(plant)


def test_a_soil_solid_spared_for_the_plant_inside_it_still_shades_the_ground_beside_it(
    plot: Plot,
) -> None:
    """The containment spare is per RECEIVER, not a hole in the bed's shadow (#481).

    Before #481 the only spared parent was the linked one; now every soil solid whose
    outline contains a receiver's point is spared for that receiver alone. A plant one
    step outside the bed - on its shadow side - must still lose sun to it, or the fix
    would have punched a hole in every bed's shadow.
    """
    bed = plot.bed(1000.0, 400.0)                       # y 400 … 520, 40 cm high
    inside = plot.tomato("in the bed", 1100.0, 460.0)    # then detached: no link at all
    plot.commands.execute(SetParentBedCommand(plot.scene, inside, bed.item_id, None))
    north = plot.tomato("north of the bed", 1100.0, 535.0, radius=5.0)
    south = plot.tomato("south of the bed", 1100.0, 385.0, radius=5.0)
    assert inside.parent_bed_id is None and north.parent_bed_id is None
    assert south.parent_bed_id is None
    plot.compute()
    assert plot.hours(inside) == pytest.approx(16.5, abs=ONE_SAMPLE_H)
    assert plot.hours(north) is not None and plot.hours(north) < 16.5 - 4 * ONE_SAMPLE_H
    assert plot.hours(south) is not None and plot.hours(south) < 16.5 - 4 * ONE_SAMPLE_H


def test_a_wall_around_a_plant_still_shades_it(plot: Plot) -> None:
    """Only a SOIL solid is spared, not anything that contains the point (#481).

    The negative control for the containment rule: a 3 m wall drawn as a closed box
    round a plant stands between it and the sun (a wall is not a soil container, so
    ``is_solid_soil_parent`` is False and the plant is not spared). Sparing by
    containment alone would call this plant sunny.
    """
    box = PolygonItem([QPointF(900.0, 300.0), QPointF(1300.0, 300.0),
                       QPointF(1300.0, 700.0), QPointF(900.0, 700.0)],
                      object_type=ObjectType.WALL, layer_id=plot.scene.active_layer.id,
                      metadata={METADATA_KEY: 300.0})
    plot.commands.execute(CreateItemCommand(plot.scene, box, "wall"))
    inside = plot.tomato("inside the wall", 1100.0, 500.0)
    plot.compute()
    assert plot.hours(inside) is not None and plot.hours(inside) < 16.5 - 4 * ONE_SAMPLE_H


def test_the_walk_marks_exactly_the_soil_solids_as_able_to_hold_plants(plot: Plot) -> None:
    """The drift guard for #481: the walk's flag IS ``is_solid_soil_parent``, for every
    caster — so a kind the predicate learns about is spared without a second list to
    keep in step (the gap #621 found for cold frames and pots began as such a list).
    """
    bed = plot.bed(1000.0, 400.0)
    plot.tomato("on the bed", 1100.0, 460.0)
    container = CircleItem(1600.0, 400.0, 40.0, ObjectType.CONTAINER_ROUND,
                           layer_id=plot.scene.active_layer.id)
    container.metadata[METADATA_KEY] = 50.0
    plot.commands.execute(CreateItemCommand(plot.scene, container, "pot"))
    plot.tomato("in the pot", 1600.0, 400.0, radius=10.0)
    trellis = PolygonItem([QPointF(400.0, 900.0), QPointF(700.0, 900.0),
                           QPointF(700.0, 1100.0), QPointF(400.0, 1100.0)],
                          object_type=ObjectType.TRELLIS, layer_id=plot.scene.active_layer.id,
                          metadata={METADATA_KEY: 180.0})
    plot.commands.execute(CreateItemCommand(plot.scene, trellis, "trellis"))
    plot.wall(100.0, 300.0, 2000.0)

    snapshot = collect_exposure_snapshot(plot.scene, dict(BERLIN), DAY)
    by_id = {str(item.item_id): item for item in plot.scene.items()
             if hasattr(item, "item_id")}
    checked = 0
    for caster in snapshot.casters:
        item = by_id[caster.item_id]
        expected = holds_plants(item)
        assert caster.holds_plants is expected, item.object_type
        checked += 1
    assert checked >= 4
    assert {by_id[c.item_id].object_type for c in snapshot.casters if c.holds_plants} == {
        ObjectType.RAISED_BED, ObjectType.CONTAINER_ROUND}
    assert bed.item_id is not None


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



def test_cold_frame_spares_contained_plant_and_shades_exterior(plot: Plot) -> None:
    """A plant inside a COLD_FRAME reads full-sun hours; outside on shadow side is shaded (#621)."""
    cf = RectangleItem(1000.0, 400.0, 200.0, 120.0, object_type=ObjectType.COLD_FRAME,
                       layer_id=plot.scene.active_layer.id)
    plot.commands.execute(CreateItemCommand(plot.scene, cf, "cold frame"))
    inside = plot.tomato("in cold frame", 1100.0, 460.0)
    north = plot.tomato("north of cold frame", 1100.0, 535.0, radius=5.0)

    plot.compute()
    assert plot.hours(inside) == pytest.approx(16.5, abs=ONE_SAMPLE_H)
    assert not plot.warned(inside), "full-sun plant inside cold frame has no sun mismatch (#621)"
    assert plot.hours(north) is not None and plot.hours(north) < 16.5 - 4 * ONE_SAMPLE_H


def test_planter_pot_and_greenhouse_spare_contained_plants(plot: Plot) -> None:
    """Plants inside PLANTER_POT and GREENHOUSE get open-ground sun (#621)."""
    pot = CircleItem(1600.0, 1800.0, 40.0, ObjectType.PLANTER_POT,
                     layer_id=plot.scene.active_layer.id)
    plot.commands.execute(CreateItemCommand(plot.scene, pot, "planter pot"))
    in_pot = plot.tomato("in pot", 1600.0, 1800.0, radius=10.0)

    gh = RectangleItem(400.0, 1000.0, 300.0, 200.0, object_type=ObjectType.GREENHOUSE,
                       layer_id=plot.scene.active_layer.id)
    plot.commands.execute(CreateItemCommand(plot.scene, gh, "greenhouse"))
    in_gh = plot.tomato("in greenhouse", 550.0, 1100.0, radius=20.0)

    plot.compute()
    assert plot.hours(in_pot) == pytest.approx(16.5, abs=ONE_SAMPLE_H)
    assert not plot.warned(in_pot)
    assert plot.hours(in_gh) == pytest.approx(16.5, abs=ONE_SAMPLE_H)
    assert not plot.warned(in_gh)


def test_plant_holders_drift_guard() -> None:
    """Every placeable object kind with a default height that holds plants is covered (#621)."""
    class MockItem:
        def __init__(self, object_type: ObjectType) -> None:
            self.object_type = object_type
            self.metadata: dict[str, Any] = {}

    holders = {
        ot for ot in ObjectType
        if effective_height_cm(ot, {}) is not None
        and effective_height_cm(ot, {}) > 0
        and holds_plants(MockItem(ot))
    }
    assert holders == {
        ObjectType.RAISED_BED,
        ObjectType.CONTAINER,
        ObjectType.CONTAINER_ROUND,
        ObjectType.WALL_PLANTER,
        ObjectType.COLD_FRAME,
        ObjectType.PLANTER_POT,
        ObjectType.GREENHOUSE,
    }



def test_elevated_plant_clears_fence_shadow_and_receives_sun(plot: Plot) -> None:
    """A plant elevated in a raised bed clears a fence's shadow and gets more sun (#641)."""
    # Fence 120 cm high at y = 400
    _fence = plot.wall(100.0, 900.0, 400.0, height=120.0)

    # Raised bed 50 cm high at (200, 430), plant inside at (300, 445)
    # Soil elevation is 50 - 2 = 48 cm
    bed = plot.bed(200.0, 430.0, height=50.0)
    in_bed = plot.tomato("in bed", 300.0, 445.0, radius=10.0)

    # Control plant on open ground at identical y distance (445.0) from the fence
    on_ground = plot.tomato("on ground", 600.0, 445.0, radius=10.0)

    assert plot.stands_on(in_bed) == str(bed.item_id)
    assert plot.elevation(in_bed) == 48.0
    assert plot.stands_on(on_ground) is None
    assert plot.elevation(on_ground) == 0.0

    plot.compute()
    elevated_h = plot.hours(in_bed)
    ground_h = plot.hours(on_ground)
    assert elevated_h is not None and ground_h is not None
    assert elevated_h >= ground_h + 1.0, f"elevated ({elevated_h}h) must exceed ground ({ground_h}h) by >= 1h"
