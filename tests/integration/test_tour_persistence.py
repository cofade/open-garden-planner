"""Camera tours kept in the plan file, end to end (issue #737, ADR-072 addendum).

A tour is made with the Camera Tour dialog's own controls, kept in the plan under a name,
written by the real serializer, read back by the real loader and flown again. What is
pinned: the tour survives save and reopen and flies the same frames; saving, changing,
renaming and deleting are ONE undo step each (counted, not just "undo works"); the plan
owns its tours (another plan does not inherit them, Save As, a template and a new season
keep them); a file may not take the load down with a hostile tour; and a file with tours
still opens in the last release that did not know them.

The engine is the workspace tests' recording host (``Rig`` of ``test_directors_cut.py``):
what is decided around a picture is the subject here, not its pixels. The model, its
reader and the commands alone: ``tests/unit/test_camera_tours.py``.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import date, time
from pathlib import Path
from typing import Any

import pytest
from PyQt6.QtCore import QDate, QTime
from PyQt6.QtWidgets import QInputDialog, QMessageBox

from open_garden_planner.agent_api.mapping import plan_summary_from_snapshot
from open_garden_planner.core.camera_path import CameraKey, frame_count, tour_frames
from open_garden_planner.core.camera_tours import (
    MAX_TOUR_KEYS,
    MAX_TOURS,
    PLAN_KEY,
    SavedTour,
    dump_tours,
)
from open_garden_planner.core.plan_io import PlanValidationError, validate_plan_data
from open_garden_planner.core.project import FILE_VERSION, ProjectData, ProjectManager
from open_garden_planner.core.scene3d.camera import CameraPose
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.view3d.tour_dialog import TourDialog
from tests.integration.test_directors_cut import Rig
from tests.integration.test_view3d_workspace import build_app3d, first_pass
from tests.unit.test_camera_tours import HOSTILE, ORBIT_BEFORE_EASING, flight, held, orbit

REPO = Path(__file__).resolve().parents[2]
#: The last release whose loader does not know ``camera_tours``. Fixed: "the previous
#: release" of the issue stays this one, whatever is released later.
LAST_RELEASE_WITHOUT_TOURS = "v1.37.9"


class TourRig(Rig):
    """The capturing rig with the plan's keeper beside it, wired the way the app wires it
    (``GardenPlannerApp``: ``stack_changed`` → ``mark_dirty``, ``capture.connect_tours``).
    ``test_the_app_keeps_tours...`` below is the same journey in the real window."""

    def __init__(self, view: CanvasView, qtbot: Any, folder: Path) -> None:
        super().__init__(view, qtbot, folder)
        self.plan = ProjectManager()
        self.commands.stack_changed.connect(self.plan.mark_dirty)
        self.workspace.capture.connect_tours(self.plan, self.commands)

    def dialog(self) -> TourDialog:
        self.open_3d()
        capture = self.workspace.capture
        capture.tour_action.trigger()
        assert capture.dialog is not None and capture.dialog.isVisible()
        return capture.dialog

    def turn(self) -> None:
        """Another view: the orbit camera turned and settled."""
        self.workspace.camera.orbit(35.0, 4.0)
        self.workspace.camera.snap()

    def save(self, path: Path) -> None:
        self.plan.save(self.scene, path)

    def new_plan(self) -> None:
        """What ``GardenPlannerApp._new_project_document`` does to these three."""
        self.scene.clear()
        self.commands.clear()
        self.plan.new_project()
        self.settle()

    def open_plan(self, path: Path) -> None:
        """What ``GardenPlannerApp._load_project_file`` does to these three."""
        self.plan.load(self.scene, path)
        self.commands.clear()
        self.settle()


@pytest.fixture()
def rig(canvas: CanvasView, qtbot: Any, tmp_path: Path) -> TourRig:
    return TourRig(canvas, qtbot, tmp_path)


def fly(rig: TourRig, dialog: TourDialog, views: int = 3) -> None:
    """A keyframe tour through ``views`` views, made with the dialog's own buttons."""
    dialog.motion_combo.setCurrentIndex(dialog.motion_combo.findData("path"))
    for _ in range(views):
        dialog.add_key_button.click()
        rig.turn()


def typing(monkeypatch: pytest.MonkeyPatch, name: str, accepted: bool = True) -> None:
    """What the user types into the name dialog (and whether they press OK)."""
    monkeypatch.setattr(QInputDialog, "getText", lambda *_a, **_k: (name, accepted))


def answering(monkeypatch: pytest.MonkeyPatch, button: QMessageBox.StandardButton) -> list[str]:
    """What the user answers to the dialog's question; returns the questions asked."""
    asked: list[str] = []

    def answer(box: QMessageBox) -> int:
        asked.append(box.text())
        return int(button.value)

    monkeypatch.setattr(QMessageBox, "exec", answer)
    return asked


def offered(dialog: TourDialog) -> list[str]:
    """The saved tours the combo offers (its first entry is the unsaved draft)."""
    return [dialog.tour_combo.itemText(index) for index in range(1, dialog.tour_combo.count())]


def choose(dialog: TourDialog, name: str | None) -> None:
    combo = dialog.tour_combo
    combo.setCurrentIndex(combo.findText(name) if name is not None else 0)


def save_as(dialog: TourDialog, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    typing(monkeypatch, name)
    dialog.save_tour_as_button.click()


# ── save, reopen, the same flight ────────────────────────────────────────────


def test_a_tour_made_in_the_dialog_survives_save_and_reopen_and_flies_the_same_frames(
        rig: TourRig, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dialog = rig.dialog()
    assert offered(dialog) == [] and dialog.bound_tour is None
    assert not dialog.save_tour_button.isEnabled() and not dialog.delete_tour_button.isEnabled()
    fly(rig, dialog)
    dialog.loop_check.setChecked(True)
    dialog.time_combo.setCurrentIndex(dialog.time_combo.findData("year"))
    dialog.date_from.setDate(QDate(2027, 4, 1))
    dialog.date_to.setDate(QDate(2027, 9, 30))
    dialog.duration_spin.setValue(3.0)
    dialog.fps_combo.setCurrentIndex(dialog.fps_combo.findData(24))
    dialog.size_combo.setCurrentIndex(0)
    save_as(dialog, monkeypatch, "  Promo   Flight\n")
    assert rig.commands.undo_depth == 1 and rig.plan.is_dirty
    assert offered(dialog) == ["Promo Flight"] and dialog.bound_tour == "Promo Flight"
    assert dialog.tour_combo.currentText() == "Promo Flight"
    assert "Promo Flight" in dialog._status.text()
    assert not dialog.save_tour_button.isEnabled(), "the controls ARE the saved tour now"
    flown = list(tour_frames(dialog.spec()))
    assert len(flown) == 72 and flown[-1].plan_date == date(2027, 9, 30)

    path = tmp_path / "garden.ogp"
    rig.save(path)
    assert not rig.plan.is_dirty
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["version"] == "1.4"
    assert [tour["name"] for tour in on_disk[PLAN_KEY]] == ["Promo Flight"]
    assert on_disk[PLAN_KEY][0]["size"] == [1280, 720] and len(on_disk[PLAN_KEY][0]["keys"]) == 3

    rig.new_plan()                       # the plan goes ...
    assert rig.plan.camera_tours == () and offered(dialog) == [] and dialog.keys == ()
    rig.open_plan(path)                  # ... and comes back from its file
    assert offered(dialog) == ["Promo Flight"] and dialog.bound_tour is None
    assert rig.commands.undo_depth == 0 and not rig.plan.is_dirty
    choose(dialog, "Promo Flight")
    assert dialog.bound_tour == "Promo Flight" and len(dialog.keys) == 3
    assert dialog.keys_list.count() == 3 and dialog.loop_check.isChecked()
    assert dialog.motion_combo.currentData() == "path"
    assert dialog.time_combo.currentData() == "year" and dialog._size() == (1280, 720)
    assert list(tour_frames(dialog.spec())) == flown, "the same camera, date and wind, frame by frame"
    assert rig.commands.undo_depth == 0 and not rig.plan.is_dirty, "choosing a tour edits nothing"
    assert not dialog.save_tour_button.isEnabled()
    dialog.close()


def test_reopening_the_dialog_offers_the_saved_tours(
        rig: TourRig, monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = rig.dialog()
    save_as(dialog, monkeypatch, "Drone")
    dialog.close()
    rig.workspace.capture.tour_action.trigger()
    assert rig.workspace.capture.dialog is dialog and dialog.isVisible()
    assert offered(dialog) == ["Drone"] and dialog.tour_combo.currentText() == "Drone"
    dialog.close()


def test_a_saved_tour_renders_the_changed_garden_along_the_saved_path(
        rig: TourRig, monkeypatch: pytest.MonkeyPatch, qtbot: Any, tmp_path: Path) -> None:
    """The tour holds a camera and a clock, and nothing of the garden: next week's video is
    next week's garden from last week's path."""
    dialog = rig.dialog()
    fly(rig, dialog)
    dialog.duration_spin.setValue(1.0)
    dialog.fps_combo.setCurrentIndex(dialog.fps_combo.findData(24))
    dialog.size_combo.setCurrentIndex(0)
    save_as(dialog, monkeypatch, "Promo Flight")
    saved = rig.plan.camera_tours[0]
    path = tmp_path / "garden.ogp"
    rig.save(path)

    rig.open_plan(path)
    bed = rig.bed()                      # the garden changes ...
    rig.turn()                           # ... and the view is somewhere else
    rig.settle()
    rig.qtbot.waitUntil(lambda: rig.workspace.capture.capture_blocker() is None, timeout=5000)
    assert str(bed.item_id) in rig.sink.item_ids()
    choose(dialog, "Promo Flight")
    rig.host.pictures.clear()
    dialog.record_png(tmp_path / "frames")
    qtbot.waitUntil(lambda: dialog._recorder is None, timeout=60000)
    expected = list(tour_frames(saved.spec()))
    assert len(rig.host.pictures) == frame_count(saved.spec()) == 24
    assert [(picture["shot"].eye, picture["shot"].target, picture["shot"].fov_deg)
            for picture in rig.host.pictures] == [
                (frame.key.eye, frame.key.target, frame.key.fov_deg) for frame in expected]
    assert {picture["size"] for picture in rig.host.pictures} == {(1280, 720)}
    assert str(bed.item_id) in rig.sink.item_ids(), "what was filmed is the garden as it is now"
    dialog.close()


@pytest.mark.parametrize("motion", ["orbit", "hold"])
def test_a_saved_orbit_or_held_view_plays_from_its_saved_view_until_the_user_lets_it_go(
        rig: TourRig, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, motion: str) -> None:
    """The dialog's orbit "starts where the view is now". Saved like that, the tour would be
    another video every time; it carries its view, and says so."""
    dialog = rig.dialog()
    dialog.motion_combo.setCurrentIndex(dialog.motion_combo.findData(motion))
    button = dialog.orbit_view_button if motion == "orbit" else dialog.held_view_button
    # (#807: the orbit's button is always there - it also takes the view's tilt)
    assert not dialog.starts_at_saved_view and button.isVisible() == (motion == "orbit")
    start = dialog.spec().motion.at(0.0)
    save_as(dialog, monkeypatch, "Saved View")
    assert dialog.starts_at_saved_view and button.isVisible(), \
        "the tour starts at its saved view now, and offers to let go"
    rig.turn()
    assert rig.workspace.capture.camera_key() != start, "the view is somewhere else"
    assert dialog.spec().motion.at(0.0) == start
    assert not dialog.save_tour_button.isEnabled()

    path = tmp_path / "garden.ogp"
    rig.save(path)
    rig.open_plan(path)
    rig.turn()
    choose(dialog, "Saved View")
    assert dialog.motion_combo.currentData() == motion and dialog.starts_at_saved_view
    assert dialog.spec().motion.at(0.0) == start, "after a reopen too"

    depth = rig.commands.undo_depth
    button.click()                       # "Use Current View"
    assert not dialog.starts_at_saved_view and dialog.spec().motion.at(0.0) != start
    assert dialog.save_tour_button.isEnabled() and rig.commands.undo_depth == depth
    now = dialog.spec().motion.at(0.0)
    dialog.save_tour_button.click()
    assert rig.commands.undo_depth == depth + 1
    assert rig.plan.camera_tours[0].spec().motion.at(0.0) == now
    dialog.close()


# ── one undo step each ───────────────────────────────────────────────────────


def test_saving_changing_renaming_and_deleting_a_tour_is_one_undo_step_each(
        rig: TourRig, monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = rig.dialog()
    plan, commands = rig.plan, rig.commands
    fly(rig, dialog)
    assert commands.undo_depth == 0 and not plan.is_dirty, "making a draft edits no plan"

    save_as(dialog, monkeypatch, "Promo Flight")                    # add
    assert commands.undo_depth == 1 and commands.undo_description == "Save camera tour"
    added = plan.camera_tours
    assert [tour.name for tour in added] == ["Promo Flight"] and plan.is_dirty

    plan.mark_clean()
    dialog.duration_spin.setValue(20.0)                             # change a setting ...
    dialog.keys_list.setCurrentRow(1)
    dialog.remove_key_button.click()                                # ... and a keyframe
    assert commands.undo_depth == 1 and not plan.is_dirty, "the controls are a draft until saved"
    assert dialog.save_tour_button.isEnabled()
    dialog.save_tour_button.click()
    assert commands.undo_depth == 2 and plan.is_dirty
    changed = plan.camera_tours
    assert (changed[0].duration_s, len(changed[0].keys)) == (20.0, 2)
    assert not dialog.save_tour_button.isEnabled()

    typing(monkeypatch, "Garden Fly-Through")                       # rename
    dialog.rename_tour_button.click()
    assert commands.undo_depth == 3 and commands.undo_description == "Rename camera tour"
    renamed = plan.camera_tours
    assert [tour.name for tour in renamed] == ["Garden Fly-Through"]
    assert offered(dialog) == ["Garden Fly-Through"] and dialog.bound_tour == "Garden Fly-Through"

    dialog.delete_tour_button.click()                               # delete
    assert commands.undo_depth == 4 and commands.undo_description == "Delete camera tour"
    assert plan.camera_tours == () and offered(dialog) == [] and dialog.bound_tour is None
    assert len(dialog.keys) == 2, "the controls stay, as a draft"

    for expected in (renamed, changed, added, ()):                  # exactly four steps back
        commands.undo()
        assert plan.camera_tours == expected
        assert offered(dialog) == [tour.name for tour in expected]
    assert commands.undo_depth == 0 and commands.redo_depth == 4
    for expected in (added, changed, renamed, ()):                  # and four forward
        commands.redo()
        assert plan.camera_tours == expected
    assert commands.undo_depth == 4 and commands.redo_depth == 0
    dialog.close()


def test_what_changes_nothing_is_no_undo_step(
        rig: TourRig, monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = rig.dialog()
    save_as(dialog, monkeypatch, "Drone")
    fly(rig, dialog, views=2)
    dialog.save_tour_button.click()
    plan, commands = rig.plan, rig.commands
    depth, tours = commands.undo_depth, plan.camera_tours
    assert depth == 2

    typing(monkeypatch, "Other", accepted=False)                    # Cancel in the name dialog
    dialog.save_tour_as_button.click()
    dialog.rename_tour_button.click()
    typing(monkeypatch, "   \n ")                                   # no name at all
    dialog.save_tour_as_button.click()
    dialog.rename_tour_button.click()
    typing(monkeypatch, "Drone")                                    # its own name
    dialog.rename_tour_button.click()
    choose(dialog, None)                                            # the combo, both ways
    choose(dialog, "Drone")
    dialog.close()
    rig.workspace.capture.tour_action.trigger()
    assert (commands.undo_depth, plan.camera_tours) == (depth, tours)
    dialog.close()


def test_a_name_the_plan_already_has_is_asked_about_and_never_kept_twice(
        rig: TourRig, monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = rig.dialog()
    save_as(dialog, monkeypatch, "Drone")
    fly(rig, dialog, views=2)
    save_as(dialog, monkeypatch, "Flight")
    plan, commands = rig.plan, rig.commands
    assert [tour.name for tour in plan.camera_tours] == ["Drone", "Flight"]
    tours = plan.camera_tours

    asked = answering(monkeypatch, QMessageBox.StandardButton.Cancel)
    save_as(dialog, monkeypatch, "DRONE")
    assert asked == ["A tour named 'Drone' already exists. Replace it?"]
    assert (commands.undo_depth, plan.camera_tours) == (2, tours), "Cancel keeps both as they were"

    typing(monkeypatch, "drone")                                    # renaming onto another tour
    dialog.rename_tour_button.click()
    assert "already exists" in dialog._status.text()
    assert (commands.undo_depth, plan.camera_tours) == (2, tours)

    answering(monkeypatch, QMessageBox.StandardButton.Yes)
    save_as(dialog, monkeypatch, "DRONE")
    assert commands.undo_depth == 3
    assert [(tour.name, tour.motion) for tour in plan.camera_tours] == [
        ("DRONE", "path"), ("Flight", "path")], "replaced in its place, under the name typed"
    commands.undo()
    assert plan.camera_tours == tours
    dialog.close()


def test_choosing_another_tour_asks_before_it_throws_a_draft_away(
        rig: TourRig, monkeypatch: pytest.MonkeyPatch) -> None:
    """A wheel turn over the combo must not cost ten hand-placed keyframes."""
    dialog = rig.dialog()
    save_as(dialog, monkeypatch, "Drone")
    choose(dialog, None)
    fly(rig, dialog, views=4)                                       # an unsaved draft
    asked = answering(monkeypatch, QMessageBox.StandardButton.Cancel)
    choose(dialog, "Drone")
    assert asked == ["Discard the changes to the current tour?"]
    assert dialog.tour_combo.currentIndex() == 0 and dialog.bound_tour is None
    assert len(dialog.keys) == 4, "Cancel keeps the draft"

    answering(monkeypatch, QMessageBox.StandardButton.Discard)
    choose(dialog, "Drone")
    assert dialog.bound_tour == "Drone" and dialog.keys == ()
    assert dialog.motion_combo.currentData() == "orbit"

    asked = answering(monkeypatch, QMessageBox.StandardButton.Cancel)
    choose(dialog, None)                                            # letting go loses nothing
    choose(dialog, "Drone")                                         # and nothing was changed
    assert asked == []
    dialog.close()


def test_a_tour_holds_at_most_a_hundred_views_and_a_plan_at_most_fifty_tours(
        rig: TourRig, monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = rig.dialog()
    dialog.motion_combo.setCurrentIndex(dialog.motion_combo.findData("path"))
    key = rig.workspace.capture.camera_key()
    dialog._keys.extend([key] * (MAX_TOUR_KEYS - 1))
    rig.turn()
    dialog.add_key_button.click()
    assert len(dialog.keys) == MAX_TOUR_KEYS and not dialog.add_key_button.isEnabled()
    dialog.add_key()
    assert len(dialog.keys) == MAX_TOUR_KEYS
    assert dialog.save_tour_as_button.isEnabled(), "what the dialog can hold, the plan can keep"

    rig.plan.set_camera_tours(held(f"Tour {number}") for number in range(MAX_TOURS))
    depth = rig.commands.undo_depth
    save_as(dialog, monkeypatch, "One Too Many")
    assert rig.commands.undo_depth == depth and len(rig.plan.camera_tours) == MAX_TOURS
    assert str(MAX_TOURS) in dialog._status.text()
    answering(monkeypatch, QMessageBox.StandardButton.Yes)          # replacing one is not one more
    save_as(dialog, monkeypatch, "tour 7")
    assert rig.commands.undo_depth == depth + 1 and len(rig.plan.camera_tours) == MAX_TOURS
    dialog.close()


def test_the_keyframe_list_numbers_the_views_that_are_left_after_one_is_removed(
        rig: TourRig) -> None:
    """Found on the way (#737): a removed view took its number with it, so a tour of two
    views read "View 1, View 3" — and the same tour, chosen again from the saved ones, read
    "View 1, View 2"."""
    dialog = rig.dialog()
    fly(rig, dialog, views=3)
    dialog.keys_list.setCurrentRow(1)
    dialog.remove_key_button.click()
    assert [dialog.keys_list.item(row).text().split(":")[0]
            for row in range(dialog.keys_list.count())] == ["View 1", "View 2"]
    assert dialog.keys_list.currentRow() == 1, "the next view is selected: Remove again works"
    dialog.close()


# ── the plan owns its tours ──────────────────────────────────────────────────


def test_another_plan_does_not_inherit_tours_or_the_draft(
        rig: TourRig, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dialog = rig.dialog()
    fly(rig, dialog)
    save_as(dialog, monkeypatch, "Tour of A")
    first = tmp_path / "a.ogp"
    rig.save(first)

    rig.new_plan()
    assert rig.plan.camera_tours == () and offered(dialog) == []
    assert dialog.keys == () and dialog.keys_list.count() == 0 and dialog.bound_tour is None
    assert dialog.motion_combo.currentData() == "path" and dialog.spec() is None
    assert not dialog.save_tour_as_button.isEnabled(), "no draft of plan A is left to keep in B"
    dialog.motion_combo.setCurrentIndex(dialog.motion_combo.findData("orbit"))
    save_as(dialog, monkeypatch, "Tour of B")
    second = tmp_path / "b.ogp"
    rig.save(second)
    assert [tour["name"] for tour in json.loads(second.read_text("utf-8"))[PLAN_KEY]] == ["Tour of B"]

    rig.open_plan(first)
    assert offered(dialog) == ["Tour of A"] and dialog.bound_tour is None
    assert not dialog.starts_at_saved_view, "plan B's saved view went with plan B"
    rig.open_plan(second)
    assert offered(dialog) == ["Tour of B"]
    dialog.close()


def test_a_plan_without_the_key_loads_and_a_plan_without_tours_writes_none(
        rig: TourRig, tmp_path: Path) -> None:
    rig.bed()
    path = tmp_path / "plain.ogp"
    rig.save(path)
    written = json.loads(path.read_text("utf-8"))
    assert PLAN_KEY not in written and written["version"] == "1.4"
    rig.plan.set_camera_tours([flight()])
    rig.open_plan(path)
    assert rig.plan.camera_tours == () and rig.plan.last_load_skipped_tours_count == 0
    assert len(rig.scene.items()) >= 1 and not rig.plan.is_dirty


def test_save_as_a_template_and_a_new_season_keep_the_tours(rig: TourRig, tmp_path: Path) -> None:
    rig.bed()
    tours = (flight(), orbit(), held())
    rig.plan.set_camera_tours(tours)
    written = dump_tours(tours)
    rig.save(tmp_path / "garden.ogp")
    rig.save(tmp_path / "copy.ogp")                                 # File ▸ Save As
    rig.plan.save_template(rig.scene, tmp_path / "template.ogp")
    rig.plan.create_new_season(rig.scene, 2027, tmp_path / "garden-2027.ogp")
    for name in ("garden", "copy", "template", "garden-2027"):
        assert json.loads((tmp_path / f"{name}.ogp").read_text("utf-8"))[PLAN_KEY] == written, name
    rig.new_plan()
    rig.plan.load(rig.scene, tmp_path / "template.ogp", as_template=True)
    assert rig.plan.camera_tours == tours and rig.plan.current_file is None


# ── an orbit's ease and tilt (#807) ──────────────────────────────────────────


def test_an_orbit_saved_before_ease_and_tilt_flies_its_old_frames_through_the_dialog(
        rig: TourRig, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A plan written before #807 holds an orbit with no "ease" and a tilt the new control
    shows rounded. Chosen in the dialog it is the even loop it always was, at its own tilt to
    the last bit, frame for frame; nothing reads as changed; saved again, the entry is the
    same."""
    rig.bed()
    path = tmp_path / "older.ogp"
    rig.save(path)
    data = json.loads(path.read_text("utf-8"))
    data[PLAN_KEY] = [ORBIT_BEFORE_EASING]
    path.write_text(json.dumps(data), encoding="utf-8")
    dialog = rig.dialog()
    rig.open_plan(path)
    choose(dialog, "Drone")
    assert dialog.bound_tour == "Drone" and dialog.motion_combo.currentData() == "orbit"
    assert not dialog.ease_check.isChecked()
    assert dialog.pitch_spin.value() == pytest.approx(28.25, abs=0.06), "shown, rounded ..."
    spec = dialog.spec()
    assert spec.motion.pose.pitch_deg == 28.25, "... and flown exactly"
    frames = list(tour_frames(spec))
    pose = spec.motion.pose
    assert len(frames) == 360
    for frame in frames:   # the formula every orbit used before #807
        yaw = pose.yaw_deg + -1.0 * 360.0 * 2.0 * (frame.index / len(frames))
        at = CameraPose(pose.target, pose.distance_cm, yaw, pose.pitch_deg)
        assert frame.key == CameraKey(at.eye, at.target_scene, 40.0)
    assert not dialog.save_tour_button.isEnabled(), "showing it changed nothing"
    assert dialog.duration_spin.value() == 12.0, "its own length, not 30 s a turn"
    rig.save(tmp_path / "again.ogp")
    assert json.loads((tmp_path / "again.ogp").read_text("utf-8"))[PLAN_KEY] == [ORBIT_BEFORE_EASING]
    dialog.close()


def test_an_eased_tilted_orbit_is_kept_and_flown_again_the_same(
        rig: TourRig, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dialog = rig.dialog()
    dialog.pitch_spin.setValue(15.0)
    assert dialog.ease_check.isChecked()
    flown = list(tour_frames(dialog.spec()))
    save_as(dialog, monkeypatch, "Promo Orbit")
    path = tmp_path / "garden.ogp"
    rig.save(path)
    entry = json.loads(path.read_text("utf-8"))[PLAN_KEY][0]
    assert entry["orbit"]["ease"] is True and entry["orbit"]["pitch_deg"] == 15.0
    assert entry["duration_s"] == 30.0
    rig.new_plan()
    rig.turn()
    dialog.pitch_spin.setValue(40.0)    # the draft's tilt moves on ...
    rig.open_plan(path)
    choose(dialog, "Promo Orbit")       # ... and the saved tour brings its own back
    assert dialog.pitch_spin.value() == 15.0 and dialog.ease_check.isChecked()
    assert list(tour_frames(dialog.spec())) == flown
    dialog.ease_check.setChecked(False)
    assert dialog.save_tour_button.isEnabled(), "a changed ease is a change to save"
    dialog.close()


# ── the file format: additive, and the last release still opens it ───────────


def test_the_tours_are_one_additive_key_and_the_file_version_does_not_move(
        rig: TourRig, tmp_path: Path) -> None:
    """Done-when of #737, the part every runner can check: with tours, the file differs
    from the same plan without them by ONE top-level key, and says version 1.4 — the
    version every release since Phase 13 accepts (``_is_newer_file_version``)."""
    rig.bed()
    rig.save(tmp_path / "without.ogp")
    rig.plan.set_camera_tours([flight(), orbit()])
    rig.save(tmp_path / "with.ogp")
    without = json.loads((tmp_path / "without.ogp").read_text("utf-8"))
    with_tours = json.loads((tmp_path / "with.ogp").read_text("utf-8"))
    assert FILE_VERSION == "1.4" == with_tours["version"] == without["version"]
    assert set(with_tours) - set(without) == {"camera_tours"} and set(without) <= set(with_tours)
    for key in without:
        if key != "metadata":   # its "modified" stamp is the only other difference
            assert with_tours[key] == without[key], key
    # a reader that takes the keys it knows and no others gets the same plan from both
    known = {field for field in ProjectData.__dataclass_fields__ if field != "camera_tours"}
    old_reading = ProjectData.from_dict({key: value for key, value in with_tours.items()
                                         if key != PLAN_KEY})
    new_reading = ProjectData.from_dict(with_tours)
    assert all(getattr(old_reading, field) == getattr(new_reading, field) for field in known)


def _previous_release(folder: Path) -> Path | None:
    """The source tree of ``LAST_RELEASE_WITHOUT_TOURS``, or None where the tag cannot be
    had (a shallow CI checkout has no tags)."""
    git = shutil.which("git")
    if git is None:
        return None
    try:
        archive = subprocess.run(
            [git, "archive", "--format=tar", LAST_RELEASE_WITHOUT_TOURS, "src/open_garden_planner"],
            cwd=REPO, capture_output=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if archive.returncode != 0:
        return None
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        tar.extractall(folder, filter="data")
    return folder / "src"


#: Run by the PREVIOUS release's interpreter path: its own loader opens the file, and its
#: own serializer writes it again. Isolated like every script that builds the app (§8.10).
_OLD_RELEASE_OPENS_IT = """
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import script_isolation
script_isolation.isolate_profile()
import open_garden_planner
from PyQt6.QtWidgets import QApplication
application = QApplication([])
script_isolation.isolate()
from open_garden_planner.core.project import FILE_VERSION, ProjectData, ProjectManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import GardenItemMixin
scene = CanvasScene(width_cm=5000, height_cm=3000)
manager = ProjectManager()
manager.load(scene, Path(sys.argv[2]))
names = sorted(item.name for item in scene.items() if isinstance(item, GardenItemMixin))
manager.save(scene, Path(sys.argv[3]))
print("RESULT " + json.dumps({
    "release": open_garden_planner.__version__, "module": open_garden_planner.__file__,
    "file_version": FILE_VERSION, "knows_tours": "camera_tours" in ProjectData.__dataclass_fields__,
    "names": names, "skipped": manager.last_load_skipped_items_count}))
"""


def test_a_file_with_tours_opens_in_the_last_release_that_did_not_know_them(
        rig: TourRig, tmp_path: Path) -> None:
    """Done-when of #737, for real: release v1.37.9's own code loads a plan this build
    wrote with tours in it, and loses nothing but the tours.

    Skipped where the tag is not in the checkout (CI clones shallow); there
    ``test_the_tours_are_one_additive_key...`` above carries the criterion."""
    old_source = _previous_release(tmp_path / "previous")
    if old_source is None:
        pytest.skip(f"the tag {LAST_RELEASE_WITHOUT_TOURS} is not in this checkout")
    rig.bed().name = "Raised bed"
    rig.bed(900.0, 700.0).name = "Second bed"
    rig.plan.set_camera_tours([flight(), orbit(), held()])
    plan, resaved = tmp_path / "with-tours.ogp", tmp_path / "resaved-by-old.ogp"
    rig.save(plan)
    assert len(json.loads(plan.read_text("utf-8"))[PLAN_KEY]) == 3

    env = dict(os.environ, PYTHONPATH=str(old_source), QT_QPA_PLATFORM="offscreen")
    run = subprocess.run(
        [sys.executable, "-c", _OLD_RELEASE_OPENS_IT, str(REPO / "scripts"), str(plan), str(resaved)],
        env=env, cwd=tmp_path, capture_output=True, text=True, timeout=170, check=False)
    assert run.returncode == 0, run.stderr[-3000:]
    result = json.loads(next(line for line in run.stdout.splitlines()
                             if line.startswith("RESULT "))[len("RESULT "):])
    # (its ``__version__`` says 1.37.8: the version is synced in the commit AFTER the tag)
    assert Path(result["module"]).is_relative_to(old_source), "the old code ran, not this checkout"
    assert not result["knows_tours"] and result["file_version"] == "1.4"
    assert result["names"] == ["Raised bed", "Second bed"] and result["skipped"] == 0
    # What "ignores the key" means in full: the old release writes the plan back WITHOUT
    # the tours. That is the degrade of every additive key (architecture contract, row 9).
    again = json.loads(resaved.read_text("utf-8"))
    assert PLAN_KEY not in again and len(again["objects"]) == 2


# ── the trust boundary, through the real loader ──────────────────────────────


def _a_file_can_say(entry: Any) -> bool:
    """Whether the document's numeric boundary lets the entry through (``plan_io``): a NaN,
    an infinity or an integer no float holds refuses the whole file before any tour is
    read, and has its own test below."""
    try:
        validate_plan_data({PLAN_KEY: [entry]})
    except PlanValidationError:
        return False
    return True


def test_hostile_tours_are_skipped_and_the_rest_of_the_plan_loads(
        rig: TourRig, tmp_path: Path) -> None:
    """One probe per class of hostile entry — wrong shapes, numbers that are no camera,
    absurd counts — through ``ProjectManager.load``. None of them may cost the plan."""
    rig.bed()
    rig.bed(900.0, 700.0)
    path = tmp_path / "garden.ogp"
    rig.save(path)
    hostile = [entry for entry in HOSTILE.values() if _a_file_can_say(entry)]
    assert len(hostile) >= 40, "nearly every hostile class reaches the tours' own reader"
    data = json.loads(path.read_text("utf-8"))
    data[PLAN_KEY] = [flight().to_dict(), *hostile, orbit().to_dict(),
                      {**held().to_dict(), "name": "promo flight"}]      # a name twice
    path.write_text(json.dumps(data), encoding="utf-8")

    dialog = rig.dialog()
    rig.new_plan()
    rig.open_plan(path)
    assert rig.plan.camera_tours == (flight(), orbit())
    assert rig.plan.last_load_skipped_tours_count == len(hostile) + 1
    assert rig.plan.last_load_skipped_items_count == 0 and not rig.plan.is_dirty
    assert len([item for item in rig.scene.items() if hasattr(item, "object_type")]) == 2
    assert offered(dialog) == ["Promo Flight", "Drone"]
    choose(dialog, "Promo Flight")
    assert dialog.spec() is not None
    dialog.close()


@pytest.mark.parametrize("value", [{"a": flight().to_dict()}, "tours", 7, [[[]]], [None, None]],
                         ids=["object", "text", "number", "nested-lists", "nulls"])
def test_a_tours_key_of_the_wrong_shape_costs_nothing_but_itself(
        rig: TourRig, tmp_path: Path, value: Any) -> None:
    rig.bed()
    path = tmp_path / "garden.ogp"
    rig.save(path)
    data = json.loads(path.read_text("utf-8"))
    data[PLAN_KEY] = value
    path.write_text(json.dumps(data), encoding="utf-8")
    rig.new_plan()
    rig.open_plan(path)
    assert rig.plan.camera_tours == () and rig.plan.last_load_skipped_tours_count >= 1
    assert len([item for item in rig.scene.items() if hasattr(item, "object_type")]) == 1
    rig.save(path)
    assert PLAN_KEY not in json.loads(path.read_text("utf-8"))


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity", "1e999", "1" + "0" * 400],
                         ids=["nan", "inf", "minus-inf", "1e999", "an-integer-no-float-holds"])
def test_a_number_that_is_not_finite_refuses_the_document_and_keeps_the_open_plan(
        rig: TourRig, tmp_path: Path, token: str) -> None:
    """The document's numeric boundary (``plan_io``, AUD-041) refuses the whole file for a
    NaN anywhere — in a tour too. The plan that is open keeps its tours."""
    bed = rig.bed()
    rig.plan.set_camera_tours([orbit()])
    path = tmp_path / "bad.ogp"
    rig.save(path)
    text = json.dumps({**json.loads(path.read_text("utf-8")), PLAN_KEY: [flight().to_dict()]})
    assert '"fov_deg": 40.0' in text
    path.write_text(text.replace('"fov_deg": 40.0', f'"fov_deg": {token}', 1), encoding="utf-8")
    with pytest.raises(PlanValidationError):
        rig.plan.load(rig.scene, path)
    assert rig.plan.camera_tours == (orbit(),) and bed.scene() is rig.scene


# ── the agent surface and the real window ────────────────────────────────────


def test_an_agents_plan_summary_is_the_same_with_tours_and_does_not_name_them(
        rig: TourRig) -> None:
    """``snapshot_dict`` is the plan as the file holds it, so the tours are in it; the agent
    schema is curated (ADR-031) and names none of them. No new agent tool."""
    rig.bed()
    before = plan_summary_from_snapshot(rig.plan.snapshot_dict(rig.scene)).model_dump()
    rig.plan.set_camera_tours([flight(), orbit()])
    snapshot = rig.plan.snapshot_dict(rig.scene)
    assert snapshot[PLAN_KEY] == dump_tours((flight(), orbit()))
    after = plan_summary_from_snapshot(snapshot).model_dump()
    assert "camera" not in json.dumps(after).lower()
    assert {key: value for key, value in after.items() if key != "is_dirty"} == {
        key: value for key, value in before.items() if key != "is_dirty"}


def test_the_app_keeps_tours_in_the_plan_through_its_own_save_new_and_open(
        qtbot: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The same journey in the real main window: its undo stack, its title's dirty mark,
    its ``_save_to_file``, ``_new_project_document`` and ``_load_project_file``."""
    window, _engines = build_app3d(qtbot, monkeypatch, tmp_path)
    workspace, plan = window._workspace, window._project_manager
    commands = window.canvas_view.command_manager
    assert workspace.capture.tours_connected
    window._view3d_action.trigger()
    first_pass(workspace, qtbot)
    workspace.capture.tour_action.trigger()
    dialog = workspace.capture.dialog
    assert dialog is not None and dialog.isVisible() and dialog.tour_combo.isVisible()

    dialog.time_combo.setCurrentIndex(dialog.time_combo.findData("day"))
    dialog.time_from.setTime(QTime(7, 30))
    dialog.time_to.setTime(QTime(19, 15))
    save_as(dialog, monkeypatch, "Day at the Pond")
    assert commands.undo_depth == 1 and plan.is_dirty and window._undo_action.isEnabled()
    saved = plan.camera_tours
    assert saved[0].time_range == (time(7, 30), time(19, 15)) and saved[0].motion == "orbit"

    path = tmp_path / "garden.ogp"
    window._save_to_file(path)
    assert not plan.is_dirty and plan.current_file == path
    window._new_project_document(width_cm=4000.0, height_cm=2500.0)
    assert plan.camera_tours == () and offered(dialog) == [] and commands.undo_depth == 0
    window._load_project_file(str(path))
    assert plan.camera_tours == saved and offered(dialog) == ["Day at the Pond"]
    assert commands.undo_depth == 0 and not plan.is_dirty

    choose(dialog, "Day at the Pond")
    assert dialog.spec().time_range == (time(7, 30), time(19, 15))
    assert dialog.spec().motion == saved[0].orbit
    dialog.delete_tour_button.click()
    assert plan.camera_tours == () and commands.undo_depth == 1 and plan.is_dirty
    window._undo_action.trigger()
    assert plan.camera_tours == saved and commands.undo_depth == 0
    dialog.close()
    plan.mark_clean()


def test_the_app_says_when_a_file_had_tours_it_could_not_read(
        qtbot: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    window, _engines = build_app3d(qtbot, monkeypatch, tmp_path)
    plan = window._project_manager
    path = tmp_path / "garden.ogp"
    window._save_to_file(path)
    data = json.loads(path.read_text("utf-8"))
    data[PLAN_KEY] = [flight().to_dict(), {"name": "Broken", "motion": "path"}, 5]
    path.write_text(json.dumps(data), encoding="utf-8")
    window._load_project_file(str(path))
    assert plan.camera_tours == (flight(),) and plan.last_load_skipped_tours_count == 2
    assert "2 camera tour(s)" in window.statusBar().currentMessage()
    window._save_to_file(path)
    window._load_project_file(str(path))
    assert plan.last_load_skipped_tours_count == 0
    assert "camera tour" not in window.statusBar().currentMessage()
    plan.mark_clean()


def test_a_saved_tour_is_what_the_model_says_it_is(rig: TourRig,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    """What the dialog keeps is a ``SavedTour`` of exactly its controls: the drift guard
    between the dialog's ``spec()`` and the model's."""
    dialog = rig.dialog()
    fly(rig, dialog)
    dialog.time_combo.setCurrentIndex(dialog.time_combo.findData("day"))
    save_as(dialog, monkeypatch, "Flight")
    saved = rig.plan.camera_tours[0]
    assert isinstance(saved, SavedTour) and saved.keys == dialog.keys
    assert saved.time_range == (time(6, 0), time(21, 0)) and saved.date_range is None
    assert list(tour_frames(saved.spec())) == list(tour_frames(dialog.spec()))
    dialog.close()
