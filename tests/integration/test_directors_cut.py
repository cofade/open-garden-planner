"""The director's cut in the workspace (Phase 17 L6, #390, ADR-072) — the default tier.

The engine is replaced at the workspace's seam (a host that records, ``FakeHost`` of the
workspace's own tests): what is pinned here is every decision around a picture. What a
real engine answers is in ``test_directors_cut_render.py``.

End to end: ``3D ▸ Capture ▸ Photo Mode``, a click, ``Save Photo``; a tour from its dialog
through the clock to its writer; the refusals an agent gets instead of a timeout.
"""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from time import monotonic
from typing import Any

import pytest
from PyQt6.QtCore import QDate, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QImage
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QMessageBox, QPushButton

from open_garden_planner.core.camera_path import (
    CameraKey,
    HeldCamera,
    TourSpec,
    frame_count,
    path_eyes,
)
from open_garden_planner.core.scene3d.photo import DEFAULT_BLUR, NO_PHOTO, PhotoSettings
from open_garden_planner.core.sim_clock import SimClock
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.view3d.quick3d.lifecycle import HostStateError
from open_garden_planner.ui.view3d.quick3d.shots import PerspectiveShot
from open_garden_planner.ui.view3d.tour_dialog import ASK_DISCARD_AFTER_S
from open_garden_planner.ui.view3d.tour_recorder import SETTLE_LIMIT_S, TourRecorder, TourResult
from open_garden_planner.ui.view3d.video_writer import NullWriter, VideoError
from open_garden_planner.ui.view3d.workspace import WorkspaceMode
from open_garden_planner.ui.view3d.workspace_capture import (
    BLOCKERS,
    PHOTO_SIZES,
    CaptureRefused,
    WorkspaceCaptureCoordinator,
    photo_size,
)
from tests.integration.quick3d_render_support import EU_DST
from tests.integration.test_view3d_workspace_widget import Bench, FakeHost


class CapturingHost(FakeHost):
    """The workspace's stand-in host, with the capture path recorded."""

    def __init__(self, prefer_software: bool) -> None:
        super().__init__(prefer_software)
        self.pictures: list[dict[str, Any]] = []
        self.photos: list[PhotoSettings] = []
        self.capture_error: Exception | None = None
        self.sessions: list[str] = []

    def set_photo(self, settings: PhotoSettings) -> None:
        self.photos.append(settings)

    def begin_captures(self) -> None:
        self.sessions.append("begin")

    def end_captures(self) -> None:
        self.sessions.append("end")

    def device_pixel_ratio(self) -> float:
        return 1.0

    def scene_property(self, name: str) -> Any:
        return False

    def capture(self, size: tuple[int, int], shot: Any = None, *, wind_time_s: float | None = None,
                photo: Any = None, label: str = "") -> QImage:
        if self.capture_error is not None:
            raise self.capture_error
        self.pictures.append({"size": size, "shot": shot, "wind": wind_time_s, "photo": photo,
                              "label": label})
        image = QImage(size[0], size[1], QImage.Format.Format_RGBX8888)
        image.fill(Qt.GlobalColor.darkGreen)
        return image

    def pick(self, _x: float, _y: float) -> Any:
        self.frames_taken.append("pick")
        return self.pick_answer

    pick_answer: Any = None


class Hit:
    item_id = "x"
    part_index = 0
    point = (150.0, 250.0, 40.0)
    behind = ()


class Rig(Bench):
    """A window with the workspace in 3D on the capturing host."""

    def _factory(self, prefer_software: bool) -> tuple[Any, Any]:
        from open_garden_planner.core.scene3d import RecordingSink

        self.factory_calls.append(prefer_software)
        host, sink = CapturingHost(prefer_software), RecordingSink()
        self.hosts.append(host)
        self.sinks.append(sink)
        return host, sink

    def open_3d(self) -> None:
        self.workspace.set_mode(WorkspaceMode.VIEW3D)
        self.settle(150)
        self.host.health_now.frames_presented = 3
        self.workspace._poll_health()
        self.qtbot.waitUntil(lambda: self.workspace.capture.capture_blocker() is None, timeout=5000)

    def click(self, x: float = 50.0, y: float = 60.0) -> None:
        """A left click into the 3D view, through the view's own event filter."""
        from PyQt6.QtCore import QEvent, QPointF
        from PyQt6.QtGui import QMouseEvent

        orbit = self.workspace._input
        for kind, buttons in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
                              (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)):
            event = QMouseEvent(kind, QPointF(x, y), QPointF(x, y), Qt.MouseButton.LeftButton,
                                buttons, Qt.KeyboardModifier.NoModifier)
            orbit.eventFilter(None, event)


@pytest.fixture()
def rig(canvas: CanvasView, qtbot: Any, tmp_path: Path) -> Rig:
    return Rig(canvas, qtbot, tmp_path)


# ── photo mode ───────────────────────────────────────────────────────────────


def test_the_actions_wait_for_the_engine_and_the_menu_names_them(rig: Rig) -> None:
    capture = rig.workspace.capture
    assert not capture.photo_action.isEnabled() and not capture.tour_action.isEnabled()
    rig.open_3d()
    assert capture.photo_action.isEnabled() and capture.tour_action.isEnabled()
    assert rig.host.frames_taken == [], "opening the actions takes no frame"


def test_photo_mode_on_shows_its_row_and_off_is_the_view_again(rig: Rig) -> None:
    rig.open_3d()
    capture, host = rig.workspace.capture, rig.host
    assert capture._row is not None and not capture._row.isVisible()
    capture.photo_action.trigger()
    assert capture.photo_mode and capture._row.isVisible()
    capture.set_settings(PhotoSettings(exposure_ev=1.0, vignette=0.4, grade="golden"))
    assert host.photos[-1].grade == "golden"
    capture.photo_action.trigger()
    assert not capture.photo_mode and not capture._row.isVisible()
    assert host.photos[-1] == NO_PHOTO
    capture.photo_action.trigger()
    assert host.photos[-1].grade == "golden", "the settings wait for the next time"


def test_the_sliders_and_the_combo_are_the_settings(rig: Rig) -> None:
    rig.open_3d()
    capture, host = rig.workspace.capture, rig.host
    capture.set_photo_mode(True)
    capture._exposure.setValue(15)
    capture._vignette.setValue(50)
    capture._grade_combo.setCurrentIndex(capture._grade_combo.findData("film"))
    assert host.photos[-1] == PhotoSettings(exposure_ev=1.5, vignette=0.5, grade="film")


def test_the_blur_slider_works_before_any_click_by_focusing_what_the_camera_looks_at(rig: Rig) -> None:
    """Manual test of #390: the slider did nothing until the view was clicked, because there is
    no depth of field without a focused point. The first blur now brings the camera's target."""
    rig.open_3d()
    capture, host = rig.workspace.capture, rig.host
    capture.set_photo_mode(True)
    assert capture.settings.focus_scene is None, "no blur, nothing to focus"
    target = tuple(float(v) for v in rig.workspace._camera_now()[1])
    capture._blur.setValue(60)
    shown = host.photos[-1]
    assert shown.blur == 0.6 and shown.focus_scene == target and shown.depth_of_field
    assert "m" in capture._focus_label.text() and "Click" not in capture._focus_label.text()
    capture.set_settings(PhotoSettings(blur=0.6, focus_scene=(1.0, 2.0, 3.0)))
    capture._blur.setValue(80)
    assert host.photos[-1].focus_scene == (1.0, 2.0, 3.0), "a focus that was chosen stays"


def test_photo_mode_back_on_focuses_the_blur_it_kept(rig: Rig) -> None:
    rig.open_3d()
    capture, host = rig.workspace.capture, rig.host
    capture.set_photo_mode(True)
    capture._blur.setValue(70)
    capture.set_photo_mode(False)
    assert capture.settings.focus_scene is None and capture.settings.blur == 0.7
    capture.set_photo_mode(True)
    assert host.photos[-1].depth_of_field, "the slider still says 70 and the picture must too"


def test_in_photo_mode_a_click_sets_the_focus_and_selects_nothing(rig: Rig, qtbot: Any) -> None:
    """A click is the camera's while photo mode is on: the canvas's selection stays."""
    bed = rig.bed(100.0, 100.0)
    rig.open_3d()
    capture, host = rig.workspace.capture, rig.host
    capture.set_photo_mode(True)
    host.pick_answer = Hit()
    Hit.item_id = str(bed.item_id)
    rig.click()
    assert host.photos[-1].focus_scene == Hit.point
    assert host.photos[-1].blur == DEFAULT_BLUR, "a focus gets a blur to be seen by"
    assert capture._blur.value() == round(DEFAULT_BLUR * 100)
    assert "m" in capture._focus_label.text()
    assert not rig.scene.selectedItems()


def test_a_click_outside_photo_mode_selects_as_ever(rig: Rig) -> None:
    bed = rig.bed(100.0, 100.0)
    rig.open_3d()
    rig.host.pick_answer = Hit()
    Hit.item_id = str(bed.item_id)
    rig.click()
    assert bed in rig.scene.selectedItems()
    assert rig.host.photos == []


def test_a_click_on_the_ground_focuses_on_the_ground_and_the_sky_changes_nothing(
        rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    rig.open_3d()
    capture, host = rig.workspace.capture, rig.host
    capture.set_photo_mode(True)
    host.pick_answer = None
    monkeypatch.setattr(capture, "_ground_point", lambda _x, _y: (10.0, 20.0))
    rig.click()
    assert host.photos[-1].focus_scene == (10.0, 20.0, 0.0)
    before = len(host.photos)
    monkeypatch.setattr(capture, "_ground_point", lambda _x, _y: None)
    rig.click()
    assert len(host.photos) == before


def test_the_focus_goes_with_the_document_and_with_photo_mode(rig: Rig) -> None:
    rig.open_3d()
    capture = rig.workspace.capture
    capture.set_photo_mode(True)
    capture.set_settings(PhotoSettings(blur=0.5, focus_scene=(1.0, 2.0, 3.0)))
    rig.workspace.document_changed()
    assert capture.settings.focus_scene is None
    capture.set_settings(PhotoSettings(blur=0.5, focus_scene=(1.0, 2.0, 3.0)))
    capture.set_photo_mode(False)
    assert capture.settings.focus_scene is None


@pytest.mark.parametrize("key", PHOTO_SIZES)
def test_a_photo_is_saved_at_the_size_it_asks_for(rig: Rig, tmp_path: Path, key: str) -> None:
    rig.open_3d()
    capture, host = rig.workspace.capture, rig.host
    path = tmp_path / f"{key}.png"
    assert capture.write_photo(path, key)
    expected = PHOTO_SIZES[key] or (round(host.size[0]), round(host.size[1]))
    assert host.pictures[-1]["size"] == expected
    assert host.pictures[-1]["shot"] is None, "the view's own camera"
    assert QImage(str(path)).size().width() == expected[0]


def test_a_saved_photo_says_what_date_it_shows(rig: Rig, tmp_path: Path) -> None:
    rig.open_3d()
    rig.clock.set_datetime(datetime(2026, 6, 21, 15, 0))
    path = tmp_path / "photo.png"
    rig.workspace.capture.write_photo(path, "1080p")
    assert QImage(str(path)).text("Creation Time") == "2026-06-21T15:00"


def test_a_picture_is_taken_at_the_views_preset_and_never_changes_it(rig: Rig, tmp_path: Path,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR-072 addendum (#735): a saved picture uses the view's preset. Raising it for the
    capture's own frame would preview one thing and save another, and the machine that
    dropped to Low is exactly the one that cannot afford the raise. The quality setting is
    the user's lever."""
    rig.open_3d()
    workspace, capture, host = rig.workspace, rig.workspace.capture, rig.host
    look = workspace._look
    assert look is not None
    before = look.preset
    holds: list[bool] = []
    monkeypatch.setattr(look, "hold_preset", holds.append)
    assert capture.write_photo(tmp_path / "picture.png", "4k")
    assert look.preset == before, "the preset the view runs is the preset the picture uses"
    assert holds == [], "a still is one frame: it holds nothing and raises nothing"
    assert host.pictures[-1]["size"] == (3840, 2160)


def test_the_window_size_follows_the_display_scale() -> None:
    assert photo_size("window", (800.0, 450.0), 1.25) == (1000, 562)
    assert photo_size("4k", (800.0, 450.0), 1.25) == (3840, 2160)


def test_a_view_that_gives_no_frame_is_a_sentence_and_no_crash(rig: Rig, monkeypatch: pytest.MonkeyPatch,
                                                               tmp_path: Path) -> None:
    rig.open_3d()
    capture, host = rig.workspace.capture, rig.host
    warnings: list[str] = []
    monkeypatch.setattr(capture, "_warn", warnings.append)
    monkeypatch.setattr("open_garden_planner.ui.view3d.workspace_capture.QFileDialog.getSaveFileName",
                        lambda *_a, **_k: (str(tmp_path / "x.png"), ""))
    host.capture_error = HostStateError("minimised")
    capture.save_photo()
    assert warnings and not (tmp_path / "x.png").exists()
    host.capture_error = RuntimeError("the engine says no")
    capture.save_photo()
    assert "the engine says no" in warnings[-1]


# ── the agent's picture ──────────────────────────────────────────────────────


def test_every_refusal_is_a_key_with_a_sentence_and_changes_nothing(rig: Rig) -> None:
    capture = rig.workspace.capture
    # 3D never opened: nothing was built for this, and nothing is built by it
    assert capture.capture_blocker() == "not_open"
    with pytest.raises(CaptureRefused) as refused:
        capture.agent_picture((640, 360))
    assert refused.value.code == "not_open" and str(refused.value) == BLOCKERS["not_open"]
    assert rig.hosts == [], "a refused picture builds no engine"
    assert rig.workspace.mode is WorkspaceMode.PLAN, "and switches no view"


def test_warming_up_is_refused_until_the_first_frame_and_the_pipeline_are_through(rig: Rig) -> None:
    rig.bed(100.0, 100.0)
    rig.workspace.set_mode(WorkspaceMode.VIEW3D)
    capture = rig.workspace.capture
    assert capture.capture_blocker() == "warming_up"
    rig.settle(150)
    assert capture.capture_blocker() == "warming_up", "no frame was presented yet"
    rig.host.health_now.frames_presented = 3
    rig.workspace._poll_health()
    assert capture.capture_blocker() is None
    # an edit is on its way: the picture would not show it yet
    rig.bed(300.0, 300.0)
    assert capture.capture_blocker() == "warming_up"
    rig.settle(150)
    assert capture.capture_blocker() is None


def test_a_hidden_view_is_not_open(rig: Rig) -> None:
    rig.open_3d()
    rig.workspace.set_mode(WorkspaceMode.PLAN)
    assert rig.workspace.capture.capture_blocker() == "not_open"
    rig.workspace.set_mode(WorkspaceMode.SPLIT)
    rig.settle(150)
    rig.qtbot.waitUntil(lambda: rig.workspace.capture.capture_blocker() is None, timeout=5000)


def test_the_agents_picture_is_read_only_and_undeveloped(rig: Rig) -> None:
    """The contract: PNG bytes and what they show; no development; nothing moved, nothing
    undoable, nothing dirty — and photo mode's settings left as they were."""
    rig.open_3d()
    capture, host = rig.workspace.capture, rig.host
    capture.set_photo_mode(True)
    capture.set_settings(PhotoSettings(exposure_ev=1.0))
    rig.clock.set_datetime(datetime(2026, 6, 21, 15, 0))
    rig.settle(150)
    rig.qtbot.waitUntil(lambda: capture.capture_blocker() is None, timeout=5000)
    photos, cameras = len(host.photos), len(host.cameras)
    undo = rig.commands.can_undo
    pose = rig.workspace.camera.pose
    shot = PerspectiveShot((1.0, 2.0, 300.0), (4.0, 5.0, 6.0), 50.0)
    answer = capture.agent_picture((640, 360), shot)
    assert answer["png_bytes"].startswith(b"\x89PNG")
    assert (answer["image_width_px"], answer["image_height_px"]) == (640, 360)
    assert answer["eye"] == (1.0, 2.0, 300.0) and answer["target"] == (4.0, 5.0, 6.0)
    assert answer["fov_deg"] == 50.0
    assert answer["plan_date"] == "2026-06-21" and answer["time_of_day"] == "15:00"
    assert host.pictures[-1]["photo"] == NO_PHOTO and host.pictures[-1]["shot"] is shot
    assert len(host.photos) == photos, "no setting was changed for it"
    assert len(host.cameras) == cameras, "the workspace moved no camera for it"
    assert rig.workspace.camera.pose == pose and rig.commands.can_undo == undo
    assert capture.settings.exposure_ev == 1.0


def test_the_owners_view_is_what_an_agent_gets_when_it_names_no_camera(rig: Rig) -> None:
    rig.open_3d()
    answer = rig.workspace.capture.agent_picture((640, 360))
    pose = rig.workspace.camera.pose
    assert answer["eye"] == pytest.approx(pose.eye)
    assert answer["target"] == pytest.approx(pose.target_scene)
    assert rig.host.pictures[-1]["shot"] is None


def test_a_frame_that_cannot_be_had_right_now_is_warming_up_not_an_error(rig: Rig) -> None:
    rig.open_3d()
    rig.host.capture_error = HostStateError("mid-resize")
    with pytest.raises(CaptureRefused) as refused:
        rig.workspace.capture.agent_picture((640, 360))
    assert refused.value.code == "warming_up"


def test_a_recording_refuses_the_agent(rig: Rig, qtbot: Any) -> None:
    rig.open_3d()
    capture = rig.workspace.capture
    spec = TourSpec(HeldCamera(capture.camera_key()), 1.0, 24)
    outcome: list[TourResult] = []
    recorder = capture.start_tour(spec, (64, 36), NullWriter())
    recorder.finished.connect(outcome.append)
    assert capture.capture_blocker() == "recording"
    qtbot.waitUntil(lambda: bool(outcome), timeout=20000)
    assert capture.capture_blocker() is None


# ── a tour ───────────────────────────────────────────────────────────────────


def run_tour(rig: Rig, spec: TourSpec, writer: Any = None, size: tuple[int, int] = (64, 36),
             **arguments: Any) -> TourResult:
    outcome: list[TourResult] = []
    recorder = rig.workspace.capture.start_tour(spec, size, writer or NullWriter(), **arguments)
    recorder.finished.connect(outcome.append)
    rig.qtbot.waitUntil(lambda: bool(outcome), timeout=60000)
    return outcome[0]


def test_a_recording_gives_the_plants_its_flight_and_takes_it_back_and_a_preview_does_not(
        rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    rig.open_3d()
    capture = rig.workspace.capture
    flights: list[Any] = []
    monkeypatch.setattr(capture, "_fly_path", flights.append)
    key = CameraKey((0.0, 0.0, 500.0), (10.0, 10.0, 0.0))
    spec = TourSpec(HeldCamera(key), 1.0, 24)
    assert run_tour(rig, spec).ok
    assert flights[0] == path_eyes(spec) and flights[-1] is None and len(flights) == 2
    flights.clear()
    assert run_tour(rig, spec, realtime=True).ok
    assert flights == [None], "a preview shows how a tour moves, and does not wait for leaves"


def test_the_flight_reaches_the_forge_and_its_work_starts(
        rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    class Forge:
        pending_count = 3
        flights: list[Any] = []

        def fly_path(self, eyes: Any) -> None:
            self.flights.append(eyes)

        def step(self, max_items: int = 1) -> list[str]:
            return []

    rig.open_3d()
    workspace = rig.workspace
    assert workspace._forge_worker is None, "no forge on this bench unless it is put there"
    workspace._fly_path(((0.0, 0.0, 500.0),))   # and without one it is nothing to worry about
    forge = Forge()
    monkeypatch.setattr(workspace, "_forge_worker", forge)
    eyes = ((0.0, 0.0, 500.0),)
    workspace._fly_path(eyes)
    assert forge.flights == [eyes]
    assert workspace._forge_timer.isActive(), "the plants of the flight are forged from now on"
    workspace._forge_timer.stop()


def test_a_tour_renders_every_frame_from_its_own_camera_without_moving_the_view(rig: Rig) -> None:
    rig.open_3d()
    host = rig.host
    first = CameraKey((0.0, 0.0, 500.0), (10.0, 10.0, 0.0))
    spec = TourSpec(HeldCamera(first), 1.0, 24)
    pose, cameras = rig.workspace.camera.pose, len(host.cameras)
    result = run_tour(rig, spec)
    assert result.ok and result.frames == frame_count(spec) == 24 and result.unsettled == 0
    assert len(host.pictures) == 24
    assert all(picture["shot"].eye == first.eye for picture in host.pictures)
    assert all(picture["size"] == (64, 36) for picture in host.pictures)
    assert host.pictures[1]["wind"] > host.pictures[0]["wind"]
    assert rig.workspace.camera.pose == pose and len(host.cameras) == cameras
    assert host.sessions == ["begin", "end"], "the capture view rests again after it"


def test_a_time_lapse_moves_the_clock_frame_by_frame_and_puts_it_back(rig: Rig) -> None:
    rig.open_3d()
    capture, clock = rig.workspace.capture, rig.clock
    before = datetime(2026, 6, 21, 15, 0)
    clock.set_datetime(before)
    rig.settle(150)
    rig.qtbot.waitUntil(lambda: capture.capture_blocker() is None, timeout=5000)
    seen: list[tuple[date, time]] = []
    original = rig.host.capture

    def noting(*arguments: Any, **keywords: Any) -> QImage:
        seen.append((clock.plan_date, clock.time_of_day))
        return original(*arguments, **keywords)

    rig.host.capture = noting  # type: ignore[method-assign]
    spec = TourSpec(HeldCamera(capture.camera_key()), 1.0, 24,
                    date_range=(date(2026, 3, 1), date(2026, 3, 24)),
                    time_range=(time(8, 0), time(20, 0)))
    assert run_tour(rig, spec).ok
    assert seen[0] == (date(2026, 3, 1), time(8, 0))
    assert seen[-1] == (date(2026, 3, 24), time(20, 0))
    assert [moment[0] for moment in seen] == sorted(moment[0] for moment in seen)
    assert clock.wall == before, "the owner's date and time, as they were"


def test_a_tour_stops_whoever_else_plays_the_clock_and_holds_the_automatic_preset(rig: Rig) -> None:
    rig.open_3d()
    capture = rig.workspace.capture
    asked: list[bool] = []
    capture.clock_wanted.connect(lambda: asked.append(True))
    run_tour(rig, TourSpec(HeldCamera(capture.camera_key()), 1.0, 24))
    assert asked == [True]
    assert rig.workspace.look._preset_held is False, "and lets it go"


def test_a_cancelled_tour_says_so_and_puts_the_clock_back(rig: Rig) -> None:
    rig.open_3d()
    capture, clock = rig.workspace.capture, rig.clock
    before = clock.wall
    spec = TourSpec(HeldCamera(capture.camera_key()), 10.0, 30, time_range=(time(6, 0), time(21, 0)))
    outcome: list[TourResult] = []
    recorder = capture.start_tour(spec, (64, 36), NullWriter())
    recorder.finished.connect(outcome.append)
    recorder.progress.connect(lambda done, _total, _image: capture.cancel_recording() if done >= 3 else None)
    rig.qtbot.waitUntil(lambda: bool(outcome), timeout=30000)
    assert outcome[0].cancelled and not outcome[0].ok
    assert outcome[0].frames < frame_count(spec)
    assert clock.wall == before


def test_a_new_document_or_the_engine_going_ends_a_recording(rig: Rig, qtbot: Any) -> None:
    rig.open_3d()
    capture = rig.workspace.capture
    spec = TourSpec(HeldCamera(capture.camera_key()), 60.0, 30)
    outcome: list[TourResult] = []
    recorder = capture.start_tour(spec, (64, 36), NullWriter())
    recorder.finished.connect(outcome.append)
    rig.workspace.document_changed()
    qtbot.waitUntil(lambda: bool(outcome), timeout=20000)
    assert outcome[0].cancelled
    assert capture.capture_blocker() != "recording"


def test_a_writer_that_cannot_start_moves_nothing(rig: Rig) -> None:
    rig.open_3d()
    capture, clock = rig.workspace.capture, rig.clock

    class Broken(NullWriter):
        def start(self) -> None:
            raise VideoError("no encoder")

    before = clock.wall
    sessions = list(rig.host.sessions)
    with pytest.raises(VideoError):
        capture.start_tour(TourSpec(HeldCamera(capture.camera_key()), 1.0, 24), (64, 36), Broken())
    assert not capture.recording and clock.wall == before and rig.host.sessions == sessions


def test_a_tour_cannot_start_without_a_view(rig: Rig) -> None:
    rig.open_3d()
    capture = rig.workspace.capture
    spec = TourSpec(HeldCamera(capture.camera_key()), 1.0, 24)
    rig.workspace.set_mode(WorkspaceMode.PLAN)
    with pytest.raises(CaptureRefused) as refused:
        capture.start_tour(spec, (64, 36), NullWriter())
    assert refused.value.code == "not_open"


# ── the recorder alone: its waits, its pause, its failures ───────────────────


class Sink(QObject):
    finished = pyqtSignal(bool, str)

    def __init__(self, refuse_first: int = 0) -> None:
        super().__init__()
        self.refuse = refuse_first
        self.frames = 0
        self.ended: list[str] = []
        self.fail_at: int | None = None

    def start(self) -> None:
        pass

    def write(self, _image: QImage) -> bool:
        if self.fail_at is not None and self.frames == self.fail_at:
            raise VideoError("the disk is full")
        if self.refuse > 0:
            self.refuse -= 1
            return False
        self.frames += 1
        return True

    def finish(self) -> None:
        self.ended.append("finish")
        self.finished.emit(True, "")

    def abort(self) -> None:
        self.ended.append("abort")
        self.finished.emit(False, "")


def recorder(writer: Any, *, capture: Any = None, settled: Any = None, seconds: float = 1.0,
             **arguments: Any) -> tuple[TourRecorder, list[TourResult]]:
    key = CameraKey((0.0, 0.0, 500.0), (10.0, 10.0, 0.0))
    image = QImage(16, 16, QImage.Format.Format_RGBX8888)
    made = TourRecorder(TourSpec(HeldCamera(key), seconds, 24), writer,
                        capture or (lambda _frame: image), lambda _day, _moment: None,
                        settled or (lambda: True), **arguments)
    outcome: list[TourResult] = []
    made.finished.connect(outcome.append)
    return made, outcome


def test_a_full_writer_is_offered_the_same_frame_again(qtbot: Any) -> None:
    sink = Sink(refuse_first=5)
    calls: list[int] = []
    image = QImage(16, 16, QImage.Format.Format_RGBX8888)

    def capture(frame: Any) -> QImage:
        calls.append(frame.index)
        return image

    made, outcome = recorder(sink, capture=capture)
    made.start()
    qtbot.waitUntil(lambda: bool(outcome), timeout=10000)
    assert sink.frames == 24
    assert calls == list(range(24)), "rendered once each, in order, none skipped or repeated"


def test_a_frame_waits_for_the_pipeline_to_settle(qtbot: Any) -> None:
    answers = [False] * 20 + [True] * 1000
    made, outcome = recorder(Sink(), settled=lambda: answers.pop(0))
    made.start()
    qtbot.waitUntil(lambda: bool(outcome), timeout=10000)
    assert outcome[0].unsettled == 0 and len(answers) < 1000


def test_the_first_frame_may_wait_longer_for_the_plants_of_the_whole_flight(
        qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """The forge is at work on everything the flight passes close by; later frames only on what
    a day has changed. Rendered too early, a video opens on coarse leaves that pop in later."""
    monkeypatch.setattr("open_garden_planner.ui.view3d.tour_recorder.SETTLE_LIMIT_S", 0.05)
    ready_at = monotonic() + 0.25
    made, outcome = recorder(Sink(), settled=lambda: monotonic() > ready_at)
    made.start()
    qtbot.waitUntil(lambda: bool(outcome), timeout=10000)
    assert outcome[0].ok and outcome[0].unsettled == 0


def test_cancel_while_the_file_closes_changes_nothing_and_the_truth_is_reported(qtbot: Any) -> None:
    """The file was still written over the earlier one, and the result said "Cancelled."."""
    class Closing(Sink):
        def finish(self) -> None:
            self.ended.append("finish")   # the encoder's flush takes its time

    sink = Closing()
    made, outcome = recorder(sink)
    last_call: list[bool] = []
    made.finishing.connect(lambda: last_call.append(True))
    made.start()
    qtbot.waitUntil(lambda: sink.ended == ["finish"], timeout=10000)
    assert last_call == [True], "the dialog hears that it is too late"
    assert made.cancel() is False
    sink.finished.emit(True, "")
    assert outcome[0].ok and not outcome[0].cancelled


def test_a_hidden_view_is_said_at_once_and_counted_as_nothing(qtbot: Any) -> None:
    """Every retry behind a hidden view counted one frame as rendered too early, and nothing was
    said until the limit had passed: 3 minutes on the first frame. The guard is NOT dead (#738
    said it could go): a hidden pane's controller stays paused with its records dirty, so
    ``settled`` never becomes true and, without it, the first sentence waits out
    ``SETTLE_LIMIT_S``."""
    from open_garden_planner.ui.view3d.tour_recorder import SETTLE_LIMIT_S

    assert SETTLE_LIMIT_S >= 20.0, "the premise: a wait that must not happen"
    showing = {"now": False}
    made, outcome = recorder(Sink(), settled=lambda: showing["now"],
                             view_showing=lambda: showing["now"])
    paused: list[bool] = []
    made.paused_changed.connect(paused.append)
    made.start()
    # The settle limit is 20 s: a pause inside this wait cannot be a settle timeout, so
    # the hidden-view guard is what said it.
    qtbot.waitUntil(lambda: paused == [True], timeout=1000)
    qtbot.wait(600)
    showing["now"] = True
    qtbot.waitUntil(lambda: bool(outcome), timeout=10000)
    assert paused == [True, False] and outcome[0].frames == 24
    assert outcome[0].unsettled == 0


def test_a_frame_taken_too_early_counts_once_however_often_it_was_tried(
        qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("open_garden_planner.ui.view3d.tour_recorder.SETTLE_LIMIT_S", 0.0)
    image = QImage(16, 16, QImage.Format.Format_RGBX8888)
    refused = {"left": 3}

    def capture(_frame: Any) -> QImage:
        if refused["left"]:
            refused["left"] -= 1
            raise HostStateError("hidden")
        return image

    made, outcome = recorder(Sink(), capture=capture, settled=lambda: False, seconds=1.0)
    made.start()
    qtbot.waitUntil(lambda: bool(outcome), timeout=10000)
    assert outcome[0].unsettled == 24, "one per frame, not one per try"


def test_a_pipeline_that_never_settles_cannot_hold_a_recording_for_ever(
        qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("open_garden_planner.ui.view3d.tour_recorder.SETTLE_LIMIT_S", 0.0)
    assert SETTLE_LIMIT_S > 0.0
    made, outcome = recorder(Sink(), settled=lambda: False)
    made.start()
    qtbot.waitUntil(lambda: bool(outcome), timeout=10000)
    assert outcome[0].ok and outcome[0].frames == 24
    assert outcome[0].unsettled == 24, "and the result counts them"


def test_a_view_that_gives_no_frame_pauses_it_and_it_goes_on_without_a_gap(qtbot: Any) -> None:
    image = QImage(16, 16, QImage.Format.Format_RGBX8888)
    refusals = [True, True]
    indices: list[int] = []

    def capture(frame: Any) -> QImage:
        if frame.index == 3 and refusals:
            refusals.pop()
            raise HostStateError("minimised")
        indices.append(frame.index)
        return image

    pauses: list[bool] = []
    sink = Sink()
    made, outcome = recorder(sink, capture=capture)
    made.paused_changed.connect(pauses.append)
    made.start()
    qtbot.waitUntil(lambda: bool(outcome), timeout=20000)
    assert pauses == [True, False]
    assert indices == list(range(24)) and sink.frames == 24
    assert outcome[0].ok


def test_a_writer_that_fails_ends_it_with_the_reason_and_aborts(qtbot: Any) -> None:
    sink = Sink()
    sink.fail_at = 2
    made, outcome = recorder(sink)
    made.start()
    qtbot.waitUntil(lambda: bool(outcome), timeout=10000)
    assert not outcome[0].ok and "disk is full" in outcome[0].message
    assert sink.ended == ["abort"]


def test_an_engine_that_fails_ends_it_with_the_reason(qtbot: Any) -> None:
    def capture(_frame: Any) -> QImage:
        raise RuntimeError("device lost")

    sink = Sink()
    made, outcome = recorder(sink, capture=capture)
    made.start()
    qtbot.waitUntil(lambda: bool(outcome), timeout=10000)
    assert not outcome[0].ok and "device lost" in outcome[0].message
    assert sink.ended == ["abort"]


def test_a_preview_follows_the_wall_clock_and_skips_what_it_is_late_for(qtbot: Any) -> None:
    """A slow machine previews fewer frames over the same time, and always reaches the end."""
    import time as stopwatch

    image = QImage(16, 16, QImage.Format.Format_RGBX8888)
    indices: list[int] = []

    def slow(frame: Any) -> QImage:
        indices.append(frame.index)
        stopwatch.sleep(0.06)
        return image

    made, outcome = recorder(Sink(), capture=slow, realtime=True)
    made.start()
    qtbot.waitUntil(lambda: bool(outcome), timeout=10000)
    assert len(indices) < 24
    assert indices == sorted(indices)
    assert outcome[0].ok


# ── the dialog ───────────────────────────────────────────────────────────────


def dialog_of(rig: Rig) -> Any:
    rig.open_3d()
    capture = rig.workspace.capture
    capture.tour_action.trigger()
    dialog = capture.dialog
    assert dialog is not None and dialog.isVisible()
    return dialog


def test_a_keyframe_path_needs_two_views(rig: Rig) -> None:
    dialog = dialog_of(rig)
    dialog.motion_combo.setCurrentIndex(dialog.motion_combo.findData("path"))
    assert not dialog.video_button.isEnabled() and dialog.spec() is None
    dialog.add_key()
    assert dialog.spec() is None
    rig.workspace.camera.orbit(30.0, 5.0)
    rig.workspace.camera.snap()
    dialog.add_key()
    assert len(dialog.keys) == 2 and dialog.keys_list.count() == 2
    assert dialog.video_button.isEnabled() and dialog.spec() is not None
    dialog.keys_list.setCurrentRow(0)
    dialog.remove_key_button.click()
    assert len(dialog.keys) == 1 and dialog.spec() is None
    dialog.close()


def test_the_dialog_starts_with_a_size_a_frame_rate_and_a_tour_it_can_record(rig: Rig) -> None:
    """A combo cannot find a tuple among its data: the size started as "nothing", and the
    first Save Video raised (found by the end-to-end test below)."""
    dialog = dialog_of(rig)
    assert dialog._size() == (1920, 1080)
    assert dialog.fps_combo.currentData() == 30
    assert dialog.video_button.isEnabled()
    dialog.close()


def test_the_orbit_and_the_held_view_need_no_keys(rig: Rig) -> None:
    dialog = dialog_of(rig)
    assert dialog.motion_combo.currentData() == "orbit" and dialog.spec() is not None
    assert dialog.spec().motion.closed
    dialog.motion_combo.setCurrentIndex(dialog.motion_combo.findData("hold"))
    assert dialog.spec().motion.at(0.5) == dialog.spec().motion.at(0.0)
    dialog.close()


def test_a_time_lapse_range_that_runs_backwards_cannot_be_recorded(rig: Rig) -> None:
    dialog = dialog_of(rig)
    dialog.time_combo.setCurrentIndex(dialog.time_combo.findData("day"))
    from PyQt6.QtCore import QTime

    dialog.time_from.setTime(QTime(20, 0))
    dialog.time_to.setTime(QTime(8, 0))
    assert dialog.spec() is None
    dialog.time_to.setTime(QTime(21, 0))
    assert dialog.spec().time_range == (time(20, 0), time(21, 0))
    dialog.close()


def test_the_year_of_the_time_lapse_is_the_plans(rig: Rig) -> None:
    rig.clock.set_date(date(2031, 7, 1))
    dialog = dialog_of(rig)
    dialog.time_combo.setCurrentIndex(dialog.time_combo.findData("year"))
    assert dialog.spec().date_range == (date(2031, 3, 1), date(2031, 10, 31))
    dialog.close()


def test_the_default_year_follows_the_plan_until_the_user_chooses_one(rig: Rig) -> None:
    """#738: the year was stamped "chosen" on the first show, so a later plan date never
    reached the dialog's defaults again."""
    rig.clock.set_date(date(2031, 7, 1))
    dialog = dialog_of(rig)
    dialog.time_combo.setCurrentIndex(dialog.time_combo.findData("year"))
    assert dialog.date_from.date().year() == 2031
    dialog.hide()
    rig.clock.set_date(date(2033, 7, 1))
    dialog.show()
    assert dialog.date_from.date().year() == 2033, "the plan's year, while the user chose none"
    dialog.date_from.setDate(QDate(2032, 3, 1))
    dialog.hide()
    rig.clock.set_date(date(2035, 7, 1))
    dialog.show()
    assert dialog.date_from.date().year() == 2032, "a year the user chose is theirs"
    dialog.close()


def test_a_paused_preview_stops_saying_it_waits_when_the_view_comes_back(rig: Rig) -> None:
    """#738: only a recording overwrote the paused sentence, so a preview kept saying
    "Waiting: the 3D view is not visible." after the view was back."""
    dialog = dialog_of(rig)
    dialog.duration_spin.setValue(60.0)
    dialog.preview()
    dialog._on_paused(True)
    assert "Waiting" in dialog._status.text()
    dialog._on_paused(False)
    assert dialog._status.text() == "", "a preview has nothing to say once it is moving again"
    dialog.close()


def test_a_clock_that_refuses_at_the_end_of_a_tour_still_lets_the_preset_go(rig: Rig) -> None:
    """#738: a raising clock listener used to skip ``hold_preset(False)``, and automatic
    quality stayed paused for the rest of the session."""
    from open_garden_planner.ui.view3d.tour_recorder import TourResult

    class Clock:
        def set_datetime(self, _moment: Any) -> None:
            raise RuntimeError("a listener refused the write")

    class Look:
        def __init__(self) -> None:
            self.holds: list[bool] = []

        def hold_preset(self, held: bool) -> None:
            self.holds.append(held)

    look = Look()
    capture = WorkspaceCaptureCoordinator(
        get_host=lambda: None, get_controller=lambda: None, get_look=lambda: look,
        get_clock=Clock, get_camera=lambda: None,
        get_camera_now=lambda: ((0.0, 0.0, 500.0), (0.0, 0.0, 0.0), 40.0),
        forge_pending=lambda: 0, is_pane_showing=lambda: True, view_state=lambda: "running",
        ground_point=lambda _x, _y: None, default_path=str, fly_path=lambda _eyes: None,
        is_walking=lambda: False, parent=rig.window)
    capture._clock_hold = datetime(2026, 6, 21, 12, 0)
    capture._on_tour_finished(TourResult(ok=True, cancelled=False, frames=3))
    assert capture._clock_hold is None, "the hold is not left behind for the next picture"
    assert look.holds == [False], "the automatic preset measures again"


def test_stopping_the_engine_forgets_the_tour_dialog_once_it_really_closed(
        rig: Rig, qtbot: Any, tmp_path: Path) -> None:
    """#738: the coordinator dropped its reference before the dialog had closed, so a Tour
    action after an engine restart opened a second dialog while the first was still
    finishing its file. Only an engine stop forgets it: a user's Close keeps the keys."""
    dialog = dialog_of(rig)
    dialog.duration_spin.setValue(60.0)
    dialog.record_png(tmp_path / "tour")
    capture = rig.workspace.capture
    assert capture.dialog is dialog and capture.recording
    capture.set_enabled(False)   # the engine is going
    assert not capture.tour_action.isEnabled()
    assert capture.dialog is None, "the old engine's dialog is not the session's any more"
    qtbot.waitUntil(lambda: capture._dialog_closing is None, timeout=30000)
    assert not dialog.isVisible(), "and no hidden dialog is left behind"


def test_a_tour_says_at_once_when_the_pane_goes_hidden(rig: Rig, qtbot: Any) -> None:
    """#738 review: the hidden-view guard is only as good as the workspace's wiring of it.
    Delete ``view_showing=`` from ``start_tour`` and a hidden pane's tour waits out the
    settle limit (180 s on the first frame) before it says anything."""
    rig.open_3d()
    capture = rig.workspace.capture
    key = CameraKey((0.0, 0.0, 500.0), (10.0, 10.0, 0.0))
    recorder = capture.start_tour(TourSpec(HeldCamera(key), 60.0, 24), (64, 36), NullWriter())
    paused: list[bool] = []
    recorder.paused_changed.connect(paused.append)
    try:
        rig.workspace.set_mode(WorkspaceMode.PLAN)
        qtbot.waitUntil(lambda: paused == [True], timeout=1000)
    finally:
        capture.cancel_recording()
        qtbot.waitUntil(lambda: not capture.recording, timeout=20000)


def test_the_tour_action_waits_for_an_engine_stopped_dialog_to_close(
        rig: Rig, qtbot: Any, tmp_path: Path) -> None:
    """#738 review: while the engine-stopped dialog finishes its file the Tour action must
    not be a dead click, and it must not open a twin either."""
    dialog = dialog_of(rig)
    dialog.duration_spin.setValue(60.0)
    dialog.record_png(tmp_path / "tour")
    capture = rig.workspace.capture
    capture.set_enabled(False)   # the engine is going; its file is still closing
    assert capture._dialog_closing is not None, "a recording closes its file asynchronously"
    capture.set_enabled(True)    # a new engine, the old dialog is not done yet
    assert not capture.tour_action.isEnabled(), "a click would do nothing: say so by the action"
    capture.tour_action.trigger()
    assert capture.dialog is None, "no twin beside the closing dialog"
    qtbot.waitUntil(lambda: capture._dialog_closing is None, timeout=30000)
    assert capture.tour_action.isEnabled()
    capture.tour_action.trigger()
    assert capture.dialog is not None and capture.dialog is not dialog
    capture.dialog.close()


def test_closing_the_tour_dialog_keeps_the_keys_for_the_next_open(rig: Rig) -> None:
    """#738: the module's contract is that closing the dialog keeps its keys (only closing
    the app loses them). Forgetting every closed dialog broke that on Close and X while Esc
    kept them."""
    dialog = dialog_of(rig)
    dialog.add_key()
    dialog.add_key()
    dialog.close()
    assert not dialog.isVisible()
    rig.workspace.capture.tour_action.trigger()
    assert rig.workspace.capture.dialog is dialog, "the same dialog, not a fresh one"
    assert len(dialog.keys) == 2, "the user's keyframes are the session's"
    dialog.close()


def test_reduced_motion_holds_the_wind_in_a_tour(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = dialog_of(rig)
    assert dialog.spec().wind
    rig.workspace.look.set_reduced_motion(True)
    assert not dialog.spec().wind
    dialog.close()


def test_recording_from_the_dialog_end_to_end(rig: Rig, qtbot: Any, tmp_path: Path) -> None:
    """Dialog → a real PNG sequence on disk → what it says afterwards → the dialog free again."""
    dialog = dialog_of(rig)
    dialog.duration_spin.setValue(1.0)
    dialog.fps_combo.setCurrentIndex(dialog.fps_combo.findData(24))
    dialog.size_combo.setCurrentIndex(0)
    folder = tmp_path / "tour"
    dialog.record_png(folder)
    assert dialog.isModal() or dialog.windowModality() == Qt.WindowModality.ApplicationModal
    assert not dialog.video_button.isEnabled(), "one recording at a time"
    assert dialog.cancel_button.isVisible()
    qtbot.waitUntil(lambda: dialog._recorder is None, timeout=60000)
    assert len(list(folder.glob("frame_*.png"))) == 24
    assert str(folder) in dialog._status.text()
    assert dialog.video_button.isEnabled() and not dialog.cancel_button.isVisible()
    assert dialog.windowModality() == Qt.WindowModality.NonModal
    dialog.close()


def test_a_preview_saves_nothing_and_stays_small(rig: Rig, qtbot: Any, tmp_path: Path) -> None:
    dialog = dialog_of(rig)
    dialog.duration_spin.setValue(1.0)
    dialog.preview()
    assert dialog.windowModality() == Qt.WindowModality.NonModal
    qtbot.waitUntil(lambda: dialog._recorder is None, timeout=30000)
    assert {picture["size"] for picture in rig.host.pictures} == {(640, 360)}
    dialog.close()


def test_closing_the_dialog_stops_what_it_started(rig: Rig, qtbot: Any) -> None:
    dialog = dialog_of(rig)
    dialog.duration_spin.setValue(60.0)
    dialog.preview()
    capture = rig.workspace.capture
    assert capture.recording
    dialog.close()
    qtbot.waitUntil(lambda: not capture.recording, timeout=20000)


def test_closing_the_dialog_during_a_recording_stops_it_first_and_then_closes(
        rig: Rig, qtbot: Any, tmp_path: Path) -> None:
    dialog = dialog_of(rig)
    dialog.duration_spin.setValue(60.0)
    dialog.record_png(tmp_path / "tour")
    capture = rig.workspace.capture
    assert capture.recording
    dialog.close()
    assert dialog.isVisible(), "a modal recording does not run on behind nothing"
    qtbot.waitUntil(lambda: not capture.recording, timeout=20000)
    qtbot.waitUntil(lambda: not dialog.isVisible(), timeout=5000)
    assert dialog.windowModality() == Qt.WindowModality.NonModal


def test_esc_cancels_a_recording_and_the_dialog_stays_to_say_so(
        rig: Rig, qtbot: Any, tmp_path: Path) -> None:
    """``QDialog.reject`` hides without a close event: the recording ran on with the clock moving,
    the main window live again, and its end told to a hidden dialog."""
    dialog = dialog_of(rig)
    dialog.duration_spin.setValue(60.0)
    clock = rig.workspace.capture._get_clock()
    before = clock.wall
    dialog.record_png(tmp_path / "tour")
    capture = rig.workspace.capture
    QTest.keyClick(dialog, Qt.Key.Key_Escape)
    assert dialog.isVisible()
    qtbot.waitUntil(lambda: not capture.recording, timeout=20000)
    assert dialog.isVisible() and dialog._status.text() == "Cancelled."
    assert clock.wall == before
    QTest.keyClick(dialog, Qt.Key.Key_Escape)
    assert not dialog.isVisible(), "and with nothing running Esc closes it as ever"


def test_a_preview_of_a_time_lapse_is_modal_because_new_plants_read_that_clock(
        rig: Rig, qtbot: Any) -> None:
    dialog = dialog_of(rig)
    dialog.duration_spin.setValue(1.0)
    dialog.time_combo.setCurrentIndex(dialog.time_combo.findData("year"))
    dialog.preview()
    assert dialog.windowModality() == Qt.WindowModality.ApplicationModal
    qtbot.waitUntil(lambda: dialog._recorder is None, timeout=30000)
    assert dialog.windowModality() == Qt.WindowModality.NonModal and dialog.isVisible()
    dialog.close()


def test_a_date_range_that_runs_backwards_disables_the_buttons_at_once(rig: Rig) -> None:
    dialog = dialog_of(rig)
    dialog.time_combo.setCurrentIndex(dialog.time_combo.findData("year"))
    assert dialog.video_button.isEnabled()
    dialog.date_to.setDate(dialog.date_from.date().addDays(-5))
    assert not dialog.video_button.isEnabled() and not dialog.png_button.isEnabled()
    dialog.close()


def test_a_tour_refused_for_now_says_so_in_the_users_language(rig: Rig) -> None:
    dialog = dialog_of(rig)
    rig.bed(300.0, 300.0)   # an edit is on its way: the view is warming up
    dialog.preview()
    assert not rig.workspace.capture.recording
    assert "still building" in dialog._status.text()
    dialog.close()


def test_a_tour_refused_for_good_does_not_say_try_again(rig: Rig) -> None:
    dialog = dialog_of(rig)
    rig.workspace.set_mode(WorkspaceMode.PLAN)
    dialog.preview()
    assert "Open the 3D view" in dialog._status.text()
    for code, words in (("recording", "already running"), ("unavailable", "not available"),
                        ("warming_up", "still building")):
        assert words in dialog._refusal(code), code
    dialog.close()


def test_the_end_of_an_engine_ends_a_recording_and_gives_the_clock_back(
        rig: Rig, qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    rig.open_3d()
    capture = rig.workspace.capture
    clock = capture._get_clock()
    before = clock.wall
    outcome: list[Any] = []
    capture.start_tour(TourSpec(HeldCamera(capture.camera_key()), 60.0, 30, time_range=(time(6, 0), time(21, 0))),
                       (64, 36), NullWriter()).finished.connect(outcome.append)
    capture.set_enabled(False)
    qtbot.waitUntil(lambda: bool(outcome), timeout=10000)
    assert outcome[0].cancelled and clock.wall == before


def test_a_recording_holds_the_preset_and_lets_go_of_it(
        rig: Rig, qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    rig.open_3d()
    capture = rig.workspace.capture
    held: list[bool] = []
    monkeypatch.setattr(capture._get_look(), "hold_preset", held.append)
    run_tour(rig, TourSpec(HeldCamera(capture.camera_key()), 1.0, 24))
    assert held == [True, False]


def test_a_failed_writer_gives_the_clock_back_too(rig: Rig, qtbot: Any) -> None:
    rig.open_3d()
    capture = rig.workspace.capture
    clock = capture._get_clock()
    before = clock.wall
    sink = Sink()
    sink.fail_at = 3
    result = run_tour(rig, TourSpec(HeldCamera(capture.camera_key()), 1.0, 24,
                                    time_range=(time(6, 0), time(21, 0))), writer=sink)
    assert not result.ok and "disk is full" in result.message
    assert clock.wall == before


def test_a_failing_engine_cannot_keep_the_owners_clock(
        rig: Rig, qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    rig.open_3d()
    capture = rig.workspace.capture
    clock = capture._get_clock()
    before = clock.wall

    def dead() -> None:
        raise RuntimeError("wrapped C/C++ object has been deleted")

    monkeypatch.setattr(rig.host, "end_captures", dead)
    run_tour(rig, TourSpec(HeldCamera(capture.camera_key()), 1.0, 24,
                           time_range=(time(6, 0), time(21, 0))))
    assert clock.wall == before and not capture.recording


def test_photo_modes_controls_survive_a_pass_of_the_pipeline(rig: Rig) -> None:
    """They live in the notices' part of the strip, which a pass hid when it had nothing to say:
    photo mode stayed on, with Save Photo gone, until it was toggled."""
    rig.open_3d()
    capture = rig.workspace.capture
    workspace = rig.workspace
    capture.set_photo_mode(True)
    assert capture._row.isVisible()
    workspace._refresh_notices()
    assert capture._row.isVisible(), "a pass with no notice to show"
    capture.set_photo_mode(False)
    assert not workspace._pane.notices.isVisible(), "and off, nothing is left open for it"


def test_shutting_down_with_a_tour_running_is_clean(rig: Rig) -> None:
    rig.open_3d()
    capture = rig.workspace.capture
    capture.start_tour(TourSpec(HeldCamera(capture.camera_key()), 60.0, 30), (64, 36), NullWriter())
    rig.workspace.shutdown()
    assert not capture.photo_action.isEnabled()
    assert rig.host.closed


def test_the_buttons_have_their_words(rig: Rig) -> None:
    dialog = dialog_of(rig)
    texts = {button.text() for button in dialog.findChildren(QPushButton)}
    assert {"Preview", "Save Video...", "Save PNG Sequence...", "Close"} <= texts
    dialog.close()


# ── capture-session integrity (#745, #730, #731, #732) ──────────────────────


def test_a_blur_set_without_a_focus_focuses_what_the_camera_looks_at(rig: Rig) -> None:
    rig.open_3d()
    capture = rig.workspace.capture
    capture.set_photo_mode(True)
    capture.set_settings(PhotoSettings(blur=0.6))
    target = capture._get_camera_now()[1]
    assert capture.settings.focus_scene == (float(target[0]), float(target[1]), float(target[2]))
    assert rig.host.photos[-1].focus_scene == capture.settings.focus_scene
    assert "Click" not in capture._focus_label.text()


def test_a_new_plan_gives_the_kept_blur_the_new_cameras_focus(
        rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    rig.open_3d()
    capture = rig.workspace.capture
    capture.set_photo_mode(True)
    capture.set_settings(PhotoSettings(blur=0.6, focus_scene=(1.0, 2.0, 3.0)))
    rig.workspace.document_changed()
    assert capture.settings.focus_scene is None and capture._focus_pending
    assert "new plan" in capture._focus_label.text(), "the label says why it is waiting"
    moved = (1500.0, 1200.0, 0.0)
    monkeypatch.setattr(capture, "_get_camera_now",
                        lambda: ((0.0, 0.0, 500.0), moved, 40.0))
    rig.workspace._controller.document_shown.emit()   # the engine's first pass: the real seam
    assert capture.settings.blur == 0.6 and capture.settings.focus_scene == moved
    assert capture._blur.value() == 60
    assert rig.host.photos[-1].focus_scene == moved
    assert "Click" not in capture._focus_label.text()


def test_a_blur_while_walking_focuses_the_ground_under_the_view_centre(
        rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    rig.open_3d()
    capture = rig.workspace.capture
    asked: list[tuple[float, float]] = []

    def ground(x: float, y: float) -> tuple[float, float]:
        asked.append((x, y))
        return (123.0, 456.0)

    monkeypatch.setattr(capture, "_is_walking", lambda: True)
    monkeypatch.setattr(capture, "_ground_point", ground)
    capture.set_photo_mode(True)
    capture.set_settings(PhotoSettings(blur=0.6))
    assert asked == [(rig.host.size[0] / 2.0, rig.host.size[1] / 2.0)]
    assert capture.settings.focus_scene == (123.0, 456.0, 0.0), (
        "mid-air 100 cm ahead is behind the walker after a few steps")


def test_a_flight_preview_leaves_a_date_set_during_it_alone(rig: Rig) -> None:
    rig.open_3d()
    capture, clock = rig.workspace.capture, rig.clock
    clock.set_datetime(datetime(2026, 6, 21, 15, 0))
    rig.qtbot.waitUntil(lambda: capture.capture_blocker() is None, timeout=5000)
    spec = TourSpec(HeldCamera(capture.camera_key()), 1.0, 24)   # no range: never writes the clock
    outcome: list[TourResult] = []
    recorder = capture.start_tour(spec, (64, 36), NullWriter(), realtime=True)
    recorder.finished.connect(outcome.append)
    assert capture.owner_plan_date() is None, "a flight holds nothing"
    wanted = datetime(2031, 7, 1, 9, 30)
    clock.set_datetime(wanted)
    rig.qtbot.waitUntil(lambda: bool(outcome), timeout=30000)
    assert outcome[0].ok and clock.wall == wanted


def test_a_time_lapse_holds_the_owners_date_for_agent_reads(rig: Rig) -> None:
    rig.open_3d()
    capture, clock = rig.workspace.capture, rig.clock
    clock.set_datetime(datetime(2026, 6, 21, 15, 0))
    rig.qtbot.waitUntil(lambda: capture.capture_blocker() is None, timeout=5000)
    seen: list[Any] = []
    outcome: list[TourResult] = []
    spec = TourSpec(HeldCamera(capture.camera_key()), 1.0, 24,
                    date_range=(date(2026, 3, 1), date(2026, 10, 31)))
    recorder = capture.start_tour(spec, (64, 36), NullWriter())
    recorder.progress.connect(lambda *_arguments: seen.append(capture.owner_plan_date()))
    recorder.finished.connect(outcome.append)
    rig.qtbot.waitUntil(lambda: bool(outcome), timeout=60000)
    assert outcome[0].ok
    assert set(seen) == {date(2026, 6, 21)}, "the owner's day, not each frame's"


def test_a_frame_waits_for_the_pipeline_before_it_is_captured(rig: Rig) -> None:
    """``_tour_settled`` is what a recording's frame waits for: an idle controller that is
    not capturing, and an empty forge. A predicate that always says True would render
    every frame before its date had reached the engine (#738)."""

    class Controller:
        idle = False
        capturing = False

    class Look:
        def __init__(self) -> None:
            self.settled = 0

        def settle_sky(self) -> None:
            self.settled += 1

    controller, look = Controller(), Look()

    def make(pending: Any, ctrl: Any) -> WorkspaceCaptureCoordinator:
        return WorkspaceCaptureCoordinator(
            get_host=lambda: None, get_controller=lambda: ctrl, get_look=lambda: look,
            get_clock=lambda: None, get_camera=lambda: None,
            get_camera_now=lambda: ((0.0, 0.0, 500.0), (0.0, 0.0, 0.0), 40.0),
            forge_pending=pending, is_pane_showing=lambda: True, view_state=lambda: "running",
            ground_point=lambda _x, _y: None, default_path=str, fly_path=lambda _eyes: None,
            is_walking=lambda: False, parent=rig.window)

    pending = {"n": 0}
    capture = make(lambda: pending["n"], controller)
    assert capture._tour_settled() is False, "the controller is not idle yet"
    controller.idle = True
    pending["n"] = 1
    assert capture._tour_settled() is False, "the forge is still building"
    pending["n"] = 0
    controller.capturing = True
    assert capture._tour_settled() is False, "a capture is in flight"
    controller.capturing = False
    assert capture._tour_settled() is True
    assert look.settled == 1, "the frame's own sky is built, not one the sun left behind"
    assert make(lambda: 0, None)._tour_settled() is True, "no controller: nothing to wait for"

def test_a_years_time_lapse_holds_utc_across_both_clock_changes(rig: Rig) -> None:
    """The sun is a function of UTC: a wall time held across a DST change moves it by an
    hour, which the owner saw as a 24-level step in the year video (#732)."""
    clock = SimClock(datetime(2026, 6, 21, 15, 0), tz=EU_DST)
    capture = WorkspaceCaptureCoordinator(
        get_host=lambda: None, get_controller=lambda: None, get_look=lambda: None,
        get_clock=lambda: clock, get_camera=lambda: None,
        get_camera_now=lambda: ((0.0, 0.0, 500.0), (0.0, 0.0, 0.0), 40.0),
        forge_pending=lambda: 0, is_pane_showing=lambda: True, view_state=lambda: "running",
        ground_point=lambda _x, _y: None, default_path=str, fly_path=lambda _eyes: None,
        is_walking=lambda: False, parent=rig.window)
    capture._tour_holds_utc = True
    days = [date(2026, 3, 1), date(2026, 3, 28), date(2026, 3, 30),
            date(2026, 10, 24), date(2026, 10, 26), date(2026, 10, 31)]
    moments = []
    for day in days:
        capture._tour_clock(day, None)
        moments.append((clock.plan_date, clock.utc.time(), clock.time_of_day))
    assert [moment[0] for moment in moments] == days, "the dialog's dates are kept"
    assert {moment[1] for moment in moments} == {time(14, 0)}, moments
    assert [moment[2] for moment in moments] == [
        time(15, 0), time(15, 0), time(16, 0), time(16, 0), time(15, 0), time(15, 0)]


def test_a_years_time_lapse_holds_utc_through_the_repeated_autumn_hour(rig: Rig) -> None:
    """A 03:30 start on the autumn change day used to land in the repeated hour and be
    resolved as the summer occurrence: a one-hour sun jump. The fold is part of the
    reading, not an afterthought (issue #732, senior review)."""
    clock = SimClock(datetime(2026, 10, 24, 3, 30), tz=EU_DST)
    capture = WorkspaceCaptureCoordinator(
        get_host=lambda: None, get_controller=lambda: None, get_look=lambda: None,
        get_clock=lambda: clock, get_camera=lambda: None,
        get_camera_now=lambda: ((0.0, 0.0, 500.0), (0.0, 0.0, 0.0), 40.0),
        forge_pending=lambda: 0, is_pane_showing=lambda: True, view_state=lambda: "running",
        ground_point=lambda _x, _y: None, default_path=str, fly_path=lambda _eyes: None,
        is_walking=lambda: False, parent=rig.window)
    capture._tour_holds_utc = True
    moments = []
    for day in (date(2026, 10, 24), date(2026, 10, 25), date(2026, 10, 25),
                date(2026, 10, 26)):
        capture._tour_clock(day, None)
        moments.append((clock.plan_date, clock.utc.time(), clock.time_of_day))
    assert [moment[0] for moment in moments] == [
        date(2026, 10, 24), date(2026, 10, 25), date(2026, 10, 25), date(2026, 10, 26)]
    assert {moment[1] for moment in moments} == {time(1, 30)}, moments
    assert moments[0][2] == time(3, 30)
    assert moments[1][2] == time(2, 30), "the repeated hour's second occurrence"
    assert moments[2][2] == time(2, 30), "a repeated date must not flip the occurrence"


def test_a_year_time_lapse_repeating_a_change_day_keeps_the_instant(rig: Rig) -> None:
    """A real tour has several frames on one date (8 date steps per second of video). The
    fold must hold for every one of them, not only the first (#732, senior review)."""
    from open_garden_planner.core.camera_path import tour_frames

    clock = SimClock(datetime(2026, 10, 1, 3, 30), tz=EU_DST)
    capture = WorkspaceCaptureCoordinator(
        get_host=lambda: None, get_controller=lambda: None, get_look=lambda: None,
        get_clock=lambda: clock, get_camera=lambda: None,
        get_camera_now=lambda: ((0.0, 0.0, 500.0), (0.0, 0.0, 0.0), 40.0),
        forge_pending=lambda: 0, is_pane_showing=lambda: True, view_state=lambda: "running",
        ground_point=lambda _x, _y: None, default_path=str, fly_path=lambda _eyes: None,
        is_walking=lambda: False, parent=rig.window)
    capture._tour_holds_utc = True
    spec = TourSpec(HeldCamera(CameraKey((0.0, 0.0, 500.0), (0.0, 0.0, 0.0))),
                    12.0, 24, date_range=(date(2026, 10, 1), date(2026, 10, 31)))
    moments = []
    for frame in tour_frames(spec):
        assert frame.plan_date is not None
        capture._tour_clock(frame.plan_date, frame.time_of_day)
        moments.append(clock.utc.time())
    assert len(moments) == 288 and len(set(moments)) == 1, sorted(set(moments))


class _FakeRecorder:
    def __init__(self) -> None:
        self.cancelled = 0
        self.running = True

    def cancel(self) -> bool:
        self.cancelled += 1
        return True


def test_esc_asks_before_discarding_a_long_recording(
        rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = dialog_of(rig)
    recorder = _FakeRecorder()
    dialog._recorder = recorder
    dialog._recording = True
    dialog._run_started_at = monotonic() - ASK_DISCARD_AFTER_S - 1.0
    asked: list[str] = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda _parent, _title, text, *_a, **_k:
                        asked.append(text) or QMessageBox.StandardButton.Cancel)
    dialog.reject()
    assert asked and recorder.cancelled == 0, "Cancel keeps the render running"
    assert dialog.isVisible()
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *_a, **_k: QMessageBox.StandardButton.Discard)
    dialog.reject()
    assert recorder.cancelled == 1
    dialog._recorder = None
    dialog._recording = False
    dialog.close()


def test_closing_the_dialog_asks_too(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = dialog_of(rig)
    recorder = _FakeRecorder()
    dialog._recorder = recorder
    dialog._recording = True
    dialog._run_started_at = monotonic() - ASK_DISCARD_AFTER_S - 1.0
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *_a, **_k: QMessageBox.StandardButton.Cancel)
    event = QCloseEvent()
    dialog.closeEvent(event)
    assert not event.isAccepted() and recorder.cancelled == 0 and dialog.isVisible()
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *_a, **_k: QMessageBox.StandardButton.Discard)
    event = QCloseEvent()
    dialog.closeEvent(event)
    assert recorder.cancelled == 1 and not event.isAccepted(), "closes when it has stopped"
    dialog._recorder = None
    dialog._recording = False
    dialog.close()


def test_closing_the_app_during_a_recording_closes_its_file(
        rig: Rig, qtbot: Any, tmp_path: Path) -> None:
    from open_garden_planner.ui.view3d.video_writer import Mp4Writer, best_codec

    if best_codec() is None:
        pytest.skip("this system has no MP4 encoder")
    rig.open_3d()
    capture = rig.workspace.capture
    writer = Mp4Writer(tmp_path / "tour.mp4", (128, 72), 24)
    outcome: list[TourResult] = []
    recorder = capture.start_tour(
        TourSpec(HeldCamera(capture.camera_key()), 60.0, 24), (128, 72), writer)
    recorder.finished.connect(outcome.append)
    qtbot.waitUntil(lambda: writer.frames_sent >= 1, timeout=30000)
    part = writer.part_path
    assert part.exists()
    rig.workspace.shutdown()
    assert outcome and outcome[-1].cancelled
    assert not part.exists(), "the app's close does not leave a .part.mp4 behind"
    assert not capture.recording


def test_an_agent_uses_the_owners_date_while_a_tour_moves_the_clock(
        qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from open_garden_planner.app.application import GardenPlannerApp

    monkeypatch.setattr(GardenPlannerApp, "_show_welcome_dialog", lambda *_a, **_k: None)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *_a, **_k: QMessageBox.StandardButton.Discard)
    app = GardenPlannerApp()
    qtbot.addWidget(app)
    try:
        capture = app._workspace.capture
        capture._clock_hold = datetime(2026, 5, 1, 15, 0)
        app._sim_clock.set_datetime(datetime(2026, 9, 9, 12, 0))
        snapshot = app._agent_host._agent_snapshot()
        assert snapshot["agent_meta"]["as_of_date"] == "2026-05-01"
        created = app._agent_host._do_agent_create_object(
            "TREE", 400.0, 300.0, None, None, 40.0, "Owner's tree", None)
        from uuid import UUID

        item = app.canvas_scene.find_item_by_id(UUID(created["item_id"]))
        assert item.metadata["plant_instance"]["planting_date"] == "2026-05-01"
        # the same held date decides `present`: this plant is not planted yet on 1 May,
        # but it is on the frame the tour is rendering (9 September)
        item.metadata["plant_instance"]["planting_date"] = "2026-06-01"
        from open_garden_planner.agent_api import queries

        held = app._agent_host._agent_snapshot()
        tree = next(obj for obj in queries.list_objects(held)
                    if obj.item_id == created["item_id"])
        assert tree.present is False and tree.as_of_date == "2026-05-01"
        capture._clock_hold = None
        later = app._agent_host._agent_snapshot()
        tree = next(obj for obj in queries.list_objects(later)
                    if obj.item_id == created["item_id"])
        assert tree.present is True and tree.as_of_date == "2026-09-09"
    finally:
        app._workspace.capture._clock_hold = None
        app._stop_agent_api()
        app.close()


def test_a_setting_change_while_the_new_plan_is_framing_waits_for_the_camera(
        rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    rig.open_3d()
    capture = rig.workspace.capture
    capture.set_photo_mode(True)
    capture.set_settings(PhotoSettings(blur=0.6, focus_scene=(1.0, 2.0, 3.0)))
    rig.workspace.document_changed()
    monkeypatch.setattr(capture, "_get_camera_now",
                        lambda: ((0.0, 0.0, 500.0), (900.0, 800.0, 0.0), 40.0))
    capture.set_settings(PhotoSettings(blur=0.7))   # the user moves the slider meanwhile
    assert capture.settings.blur == 0.7 and capture.settings.focus_scene is None
    rig.workspace._controller.document_shown.emit()
    assert capture.settings.focus_scene == (900.0, 800.0, 0.0)
    assert rig.host.photos[-1].focus_scene == capture.settings.focus_scene


def test_an_engine_teardown_closes_the_dialog_without_asking(
        rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = dialog_of(rig)
    recorder = _FakeRecorder()
    dialog._recorder = recorder
    dialog._recording = True
    dialog._run_started_at = monotonic() - ASK_DISCARD_AFTER_S - 1.0
    asked: list[str] = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda _parent, _title, text, *_a, **_k: asked.append(text)
                        or QMessageBox.StandardButton.Cancel)
    dialog.close_for_shutdown()
    assert not asked, "the engine is going: no question can be answered usefully"
    assert recorder.cancelled == 1
    dialog._recorder = None
    dialog._recording = False
    dialog.close()


def test_a_writer_that_never_closes_is_named_on_exit(
        rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    class Stuck(QObject):
        finished = pyqtSignal(object)

        def __init__(self) -> None:
            super().__init__()
            self.path = Path("C:/tmp/tour.part.mp4")

        def abort_now(self) -> None:
            pass

        def output_path(self) -> Path:
            return self.path

    capture = rig.workspace.capture
    stuck = Stuck()
    capture._recorder = stuck
    warned: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda _parent, _title, text, *_a, **_k: warned.append(text))
    capture.shutdown(timeout_s=0.05)
    assert warned and str(stuck.path) in warned[0]
    assert capture._recorder is stuck
    capture._recorder = None


def test_the_app_close_hands_the_capture_its_shutdown(
        qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from open_garden_planner.app.application import GardenPlannerApp

    monkeypatch.setattr(GardenPlannerApp, "_show_welcome_dialog", lambda *_a, **_k: None)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *_a, **_k: QMessageBox.StandardButton.Discard)
    app = GardenPlannerApp()
    qtbot.addWidget(app)
    calls: list[str] = []
    monkeypatch.setattr(app._workspace.capture, "shutdown",
                        lambda *_a, **_k: calls.append("capture"))
    try:
        event = QCloseEvent()
        app.closeEvent(event)
        assert "capture" in calls, "the main window's close waits for a recording's file"
        assert event.isAccepted()
    finally:
        app._stop_agent_api()


def test_a_preview_never_asks_before_cancelling(
        rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = dialog_of(rig)
    recorder = _FakeRecorder()
    dialog._recorder = recorder
    dialog._recording = False
    asked: list[str] = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *_a, **_k: asked.append("asked")
                        or QMessageBox.StandardButton.Cancel)
    dialog.reject()
    assert not asked and recorder.cancelled == 1
    dialog._recorder = None
    dialog.close()


def test_a_finishing_recording_cannot_be_asked_to_discard(
        rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = dialog_of(rig)
    recorder = _FakeRecorder()
    recorder.running = False
    dialog._recorder = recorder
    dialog._recording = True
    dialog._run_started_at = monotonic() - ASK_DISCARD_AFTER_S - 1.0
    asked: list[str] = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *_a, **_k: asked.append("asked")
                        or QMessageBox.StandardButton.Cancel)
    dialog.reject()
    assert not asked, "the file is already closing; a question cannot stop it"
    dialog._recorder = None
    dialog._recording = False
    dialog.close()


def test_a_png_sequence_says_its_frames_stay(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = dialog_of(rig)
    recorder = _FakeRecorder()
    dialog._recorder = recorder
    dialog._recording = True
    dialog._sink_kind = "png"
    dialog._output = Path("C:/tmp/tour-frames")
    dialog._run_started_at = monotonic() - ASK_DISCARD_AFTER_S - 1.0
    asked: list[str] = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda _parent, _title, text, *_a, **_k: asked.append(text)
                        or QMessageBox.StandardButton.Yes)
    dialog.reject()
    assert asked and "frames already written" in asked[0]
    assert "video is not saved" not in asked[0]
    assert recorder.cancelled == 1
    dialog._recorder = None
    dialog._recording = False
    dialog.close()


def test_the_engine_going_closes_the_dialog_without_a_question(rig: Rig) -> None:
    dialog = dialog_of(rig)
    capture = rig.workspace.capture
    capture._dialog = dialog
    capture.set_enabled(False)
    assert capture._dialog is None and not dialog.isVisible()
    dialog.close()


def test_a_spring_tour_holds_utc_across_the_gap(rig: Rig) -> None:
    clock = SimClock(datetime(2026, 3, 28, 3, 30), tz=EU_DST)
    capture = WorkspaceCaptureCoordinator(
        get_host=lambda: None, get_controller=lambda: None, get_look=lambda: None,
        get_clock=lambda: clock, get_camera=lambda: None,
        get_camera_now=lambda: ((0.0, 0.0, 500.0), (0.0, 0.0, 0.0), 40.0),
        forge_pending=lambda: 0, is_pane_showing=lambda: True, view_state=lambda: "running",
        ground_point=lambda _x, _y: None, default_path=str, fly_path=lambda _eyes: None,
        is_walking=lambda: False, parent=rig.window)
    capture._tour_holds_utc = True
    moments = []
    for day in (date(2026, 3, 28), date(2026, 3, 29), date(2026, 3, 30)):
        capture._tour_clock(day, None)
        moments.append((clock.plan_date, clock.utc.time(), clock.time_of_day))
    assert [moment[0] for moment in moments] == [
        date(2026, 3, 28), date(2026, 3, 29), date(2026, 3, 30)]
    assert {moment[1] for moment in moments} == {time(2, 30)}, moments
    assert [moment[2] for moment in moments] == [
        time(3, 30), time(4, 30), time(4, 30)]


def test_a_tour_started_near_midnight_keeps_its_dates(rig: Rig) -> None:
    """The 23-hour spring day has no reading at the held UTC time; the clock takes the
    nearest one on that date (23:59), so the date range holds and the sun moves a minute."""
    clock = SimClock(datetime(2026, 3, 1, 23, 0), tz=EU_DST)
    capture = WorkspaceCaptureCoordinator(
        get_host=lambda: None, get_controller=lambda: None, get_look=lambda: None,
        get_clock=lambda: clock, get_camera=lambda: None,
        get_camera_now=lambda: ((0.0, 0.0, 500.0), (0.0, 0.0, 0.0), 40.0),
        forge_pending=lambda: 0, is_pane_showing=lambda: True, view_state=lambda: "running",
        ground_point=lambda _x, _y: None, default_path=str, fly_path=lambda _eyes: None,
        is_walking=lambda: False, parent=rig.window)
    capture._tour_holds_utc = True
    moments = []
    for day in (date(2026, 3, 1), date(2026, 3, 28), date(2026, 3, 29),
                date(2026, 3, 30)):
        capture._tour_clock(day, None)
        moments.append((clock.plan_date, clock.utc.time(), clock.time_of_day))
    assert [moment[0] for moment in moments] == [
        date(2026, 3, 1), date(2026, 3, 28), date(2026, 3, 29), date(2026, 3, 30)]
    assert {moment[1] for moment in moments} <= {time(22, 0), time(21, 59)}, moments
    assert moments[2][2] == time(23, 59), "the 23-hour day's nearest reading"
    assert moments[3][2] == time(0, 0), "an exact instant on the adjacent UTC date"


def test_the_window_close_asks_then_stops_and_waits(
        rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = dialog_of(rig)
    recorder = _FakeRecorder()
    dialog._recorder = recorder
    dialog._recording = True
    dialog._sink_kind = "mp4"
    dialog._run_started_at = monotonic() - ASK_DISCARD_AFTER_S - 1.0
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *_a, **_k: QMessageBox.StandardButton.Discard)
    event = QCloseEvent()
    dialog.closeEvent(event)
    assert recorder.cancelled == 1
    assert not event.isAccepted(), "the dialog closes when the file has closed"
    assert dialog._close_when_stopped
    dialog._recorder = None
    dialog._recording = False
    dialog.close()


def test_a_programmatic_close_that_failed_does_not_keep_the_dialog(rig: Rig) -> None:
    dialog = dialog_of(rig)
    dialog._programmatic_close = True
    dialog._close_when_stopped = True
    dialog._on_finished(TourResult(ok=False, cancelled=False, frames=1,
                                   message="the writer failed", unsettled=0))
    assert not dialog.isVisible(), "the engine is gone; nothing is left to explain to"


def test_a_tour_started_at_half_past_midnight_keeps_its_exact_instants(rig: Rig) -> None:
    """A local 00:30 is the previous UTC date's 22:30; the exact instant must be used,
    not the nearest sweep (senior review round 4)."""
    clock = SimClock(datetime(2026, 6, 21, 0, 30), tz=EU_DST)
    capture = WorkspaceCaptureCoordinator(
        get_host=lambda: None, get_controller=lambda: None, get_look=lambda: None,
        get_clock=lambda: clock, get_camera=lambda: None,
        get_camera_now=lambda: ((0.0, 0.0, 500.0), (0.0, 0.0, 0.0), 40.0),
        forge_pending=lambda: 0, is_pane_showing=lambda: True, view_state=lambda: "running",
        ground_point=lambda _x, _y: None, default_path=str, fly_path=lambda _eyes: None,
        is_walking=lambda: False, parent=rig.window)
    capture._tour_holds_utc = True
    moments = []
    for day in (date(2026, 6, 21), date(2026, 6, 22), date(2026, 6, 23)):
        capture._tour_clock(day, None)
        moments.append((clock.plan_date, clock.utc.time(), clock.time_of_day))
    assert [moment[0] for moment in moments] == [
        date(2026, 6, 21), date(2026, 6, 22), date(2026, 6, 23)]
    assert {moment[1] for moment in moments} == {time(22, 30)}, moments
    assert [moment[2] for moment in moments] == [time(0, 30)] * 3


def test_a_tour_started_in_the_spring_gap_holds_utc(rig: Rig) -> None:
    """A wall reading inside the skipped 02:00-03:00 hour resolves by PEP 495 to the
    pre-gap offset; the tour holds that UTC instant and the next day reads 03:30."""
    clock = SimClock(datetime(2026, 3, 29, 2, 30), tz=EU_DST)
    capture = WorkspaceCaptureCoordinator(
        get_host=lambda: None, get_controller=lambda: None, get_look=lambda: None,
        get_clock=lambda: clock, get_camera=lambda: None,
        get_camera_now=lambda: ((0.0, 0.0, 500.0), (0.0, 0.0, 0.0), 40.0),
        forge_pending=lambda: 0, is_pane_showing=lambda: True, view_state=lambda: "running",
        ground_point=lambda _x, _y: None, default_path=str, fly_path=lambda _eyes: None,
        is_walking=lambda: False, parent=rig.window)
    capture._tour_holds_utc = True
    moments = []
    for day in (date(2026, 3, 29), date(2026, 3, 30)):
        capture._tour_clock(day, None)
        moments.append((clock.plan_date, clock.utc.time(), clock.time_of_day))
    assert [moment[0] for moment in moments] == [date(2026, 3, 29), date(2026, 3, 30)]
    assert {moment[1] for moment in moments} == {time(1, 30)}, moments
    assert moments[0][2] == time(2, 30) and moments[1][2] == time(3, 30)


def test_the_window_close_of_a_preview_does_not_ask(
        rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = dialog_of(rig)
    recorder = _FakeRecorder()
    dialog._recorder = recorder
    dialog._recording = False
    asked: list[str] = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *_a, **_k: asked.append("asked")
                        or QMessageBox.StandardButton.Cancel)
    event = QCloseEvent()
    dialog.closeEvent(event)
    assert not asked and recorder.cancelled == 1
    assert not event.isAccepted()
    dialog._recorder = None
    dialog.close()


def test_the_window_close_of_a_png_sequence_says_frames_stay(
        rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = dialog_of(rig)
    recorder = _FakeRecorder()
    dialog._recorder = recorder
    dialog._recording = True
    dialog._sink_kind = "png"
    dialog._output = Path("C:/tmp/tour-frames")
    dialog._run_started_at = monotonic() - ASK_DISCARD_AFTER_S - 1.0
    asked: list[str] = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda _parent, _title, text, *_a, **_k: asked.append(text)
                        or QMessageBox.StandardButton.Yes)
    event = QCloseEvent()
    dialog.closeEvent(event)
    assert asked and "frames already written" in asked[0]
    assert recorder.cancelled == 1 and not event.isAccepted()
    dialog._recorder = None
    dialog.close()
