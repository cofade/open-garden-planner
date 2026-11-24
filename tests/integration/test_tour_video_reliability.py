"""Recording delivery and tour controls at their real UI boundaries (#889-#896)."""

from __future__ import annotations

import struct
from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest
from PyQt6.QtCore import QLocale, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QMessageBox

from open_garden_planner.core import i18n
from open_garden_planner.core.camera_path import MIN_DURATION_S, HeldCamera, TourSpec, tour_frames
from open_garden_planner.core.mp4_stream import Mp4Error, read_stream
from open_garden_planner.core.unit_preference import get_unit_preference
from open_garden_planner.core.units import UnitSystem
from open_garden_planner.ui.number_fields import install_decimal_marks
from open_garden_planner.ui.view3d import video_writer
from open_garden_planner.ui.view3d.video_writer import Mp4Writer
from tests.integration.test_tour_persistence import TourRig, choose
from tests.unit.test_camera_tours import orbit
from tests.unit.test_mp4_stream import MEDIA_FOUNDATION_SPS, mp4, samples_of


@pytest.mark.parametrize("failure", [struct.error("bad table"), MemoryError("no memory")])
def test_unexpected_tagging_errors_deliver_the_intact_untagged_render(
        qtbot, tmp_path: Path, monkeypatch, caplog, failure: Exception) -> None:
    writer = Mp4Writer(tmp_path / "tour.mp4", (1280, 720), 30)
    original = mp4(samples_of(MEDIA_FOUNDATION_SPS))
    writer.part_path.write_bytes(original)

    def fail(*_args):
        raise failure

    monkeypatch.setattr(video_writer, "tag_colour", fail)
    outcome = []
    writer.finished.connect(lambda ok, text: outcome.append((ok, text)))
    writer._close(True)
    qtbot.waitUntil(lambda: bool(outcome), timeout=5000)
    assert outcome == [(True, "")]
    assert writer.path.read_bytes() == original
    assert read_stream(writer.path).samples == 6
    assert "untagged" in caplog.text and str(writer.path) in caplog.text
    assert not writer.part_path.exists() and not list(tmp_path.glob("*.tmp.mp4"))


@pytest.mark.parametrize("failure", [None, Mp4Error("a sample runs past its chunk")])
def test_a_broken_render_is_kept_and_never_replaces_the_users_video(
        qtbot, tmp_path: Path, monkeypatch, failure: Exception | None) -> None:
    writer = Mp4Writer(tmp_path / "tour.mp4", (1280, 720), 30)
    writer.path.write_bytes(b"the earlier good video")
    part = mp4(samples_of(MEDIA_FOUNDATION_SPS))
    writer.part_path.write_bytes(part if failure else part[:-100])
    if failure:
        def fail(*_args):
            raise failure
        monkeypatch.setattr(video_writer, "tag_colour", fail)
    outcome = []
    writer.finished.connect(lambda ok, text: outcome.append((ok, text)))
    writer._close(True)
    qtbot.waitUntil(lambda: bool(outcome), timeout=5000)
    assert outcome[0][0] is False
    assert str(writer.part_path) in outcome[0][1]
    assert writer.path.read_bytes() == b"the earlier good video"
    assert writer.part_path.exists() and not list(tmp_path.glob("*.tmp.mp4"))


def test_a_held_temporary_copy_cannot_mask_a_structural_error_and_promote_bad_video(
        qtbot, tmp_path, monkeypatch) -> None:
    """A scanner's cleanup error must not turn a malformed NAL into an optional-tag failure."""
    writer = Mp4Writer(tmp_path / "tour.mp4", (1280, 720), 30)
    writer.path.write_bytes(b"GOOD VIDEO")
    bad = bytearray(mp4(samples_of(MEDIA_FOUNDATION_SPS)))
    struct.pack_into(">I", bad, bad.index(b"mdat") + 4, 0xFFFFFFFF)
    writer.part_path.write_bytes(bad)
    # The structural failure is in the samples, not in the tables read before tagging.
    assert read_stream(writer.part_path, read_samples=False).samples == 6
    unlink = Path.unlink

    def held(path, *args, **kwargs):
        if path.name.endswith(".tmp.mp4"):
            raise PermissionError("scanner holds the temporary file")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", held)
    outcome = []
    writer.finished.connect(lambda ok, text: outcome.append((ok, text)))
    writer._close(True)
    qtbot.waitUntil(lambda: bool(outcome), timeout=5000)
    assert outcome[0][0] is False
    assert str(writer.part_path) in outcome[0][1]
    assert writer.path.read_bytes() == b"GOOD VIDEO"
    assert writer.part_path.read_bytes() == bad


def test_an_early_tagging_io_error_cannot_promote_malformed_samples(
        qtbot, tmp_path, monkeypatch) -> None:
    """A copy can fail before the tagger reaches the bad NAL: metadata is not sufficient."""
    from open_garden_planner.core import mp4_stream

    writer = Mp4Writer(tmp_path / "tour.mp4", (1280, 720), 30)
    writer.path.write_bytes(b"GOOD VIDEO")
    bad = bytearray(mp4(samples_of(MEDIA_FOUNDATION_SPS)))
    struct.pack_into(">I", bad, bad.index(b"mdat") + 4, 0xFFFFFFFF)
    writer.part_path.write_bytes(bad)

    def full_disk(*_args):
        raise OSError("disk full before samples were copied")

    monkeypatch.setattr(mp4_stream, "_copy", full_disk)
    outcome = []
    writer.finished.connect(lambda ok, text: outcome.append((ok, text)))
    writer._close(True)
    qtbot.waitUntil(lambda: bool(outcome), timeout=5000)
    assert outcome[0][0] is False
    assert str(writer.part_path) in outcome[0][1]
    assert writer.path.read_bytes() == b"GOOD VIDEO"
    assert writer.part_path.read_bytes() == bad


def test_closing_during_tagging_names_the_eventual_destination_and_the_retained_part(
        canvas, qtbot, tmp_path, monkeypatch) -> None:
    rig = TourRig(canvas, qtbot, tmp_path)
    rig.open_3d()
    capture = rig.workspace.capture
    writer = Mp4Writer(tmp_path / "tour.mp4", (1280, 720), 30)
    data = mp4(samples_of(MEDIA_FOUNDATION_SPS))
    entered, release = Event(), Event()
    tag = video_writer.tag_colour

    def slow_tag(*args):
        entered.set()
        assert release.wait(5), "test did not release the worker"
        return tag(*args)

    # The real recorder/coordinator and delivery worker; only encoding and the render
    # engine are replaced so the race is controlled by events, never a disk's speed.
    monkeypatch.setattr(writer, "start", lambda: writer.part_path.write_bytes(data))
    monkeypatch.setattr(writer, "write", lambda _image: True)
    monkeypatch.setattr(writer, "finish", lambda: writer._close(True))
    monkeypatch.setattr(video_writer, "tag_colour", slow_tag)
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _parent, _title, text: warned.append(text))
    recorder = capture.start_tour(
        TourSpec(HeldCamera(capture.camera_key()), MIN_DURATION_S), (64, 36), writer)
    try:
        qtbot.waitUntil(entered.is_set, timeout=5000)
        assert writer._delivery is not None and not recorder.running
        capture.shutdown(timeout_s=0.01)
        assert len(warned) == 1
        assert str(writer.path) in warned[0] and str(writer.part_path) in warned[0]
        assert "unfinished output" not in warned[0]
    finally:
        release.set()
        qtbot.waitUntil(lambda: capture._recorder is None, timeout=5000)
    assert read_stream(writer.path).samples == 6 and not writer.part_path.exists()


def test_a_recorded_tour_never_holds_the_lawns_colour_and_gives_the_hold_back(
        canvas, qtbot, tmp_path, monkeypatch) -> None:
    """SEASON PLAYBACK holds a lawn's colour while the date keeps changing; the date steps
    of a recording come 4 frames apart, and every frame must show the plan date's lawns."""
    rig = TourRig(canvas, qtbot, tmp_path)
    rig.open_3d()
    capture = rig.workspace.capture
    controller = rig.workspace.controller
    writer = Mp4Writer(tmp_path / "tour.mp4", (1280, 720), 30)
    data = mp4(samples_of(MEDIA_FOUNDATION_SPS))
    monkeypatch.setattr(writer, "start", lambda: writer.part_path.write_bytes(data))
    monkeypatch.setattr(writer, "write", lambda _image: True)
    monkeypatch.setattr(writer, "finish", lambda: writer._close(True))
    assert controller.hold_season is True
    capture.start_tour(TourSpec(HeldCamera(capture.camera_key()), MIN_DURATION_S), (64, 36), writer)
    assert controller.hold_season is False
    qtbot.waitUntil(lambda: capture._recorder is None, timeout=20000)
    assert controller.hold_season is True


@pytest.mark.parametrize("fov", [0.0, 180.0])
def test_loading_a_plan_skips_an_unflyable_orbit_and_still_offers_the_good_tour(
        canvas, qtbot, tmp_path, fov) -> None:
    import json

    rig = TourRig(canvas, qtbot, tmp_path)
    rig.bed()
    path = tmp_path / "garden.ogp"
    rig.save(path)
    plan = json.loads(path.read_text("utf-8"))
    good = orbit("Good")
    bad = good.to_dict()
    bad["name"] = "Bad"
    bad["orbit"]["fov_deg"] = fov
    plan["camera_tours"] = [bad, good.to_dict()]
    path.write_text(json.dumps(plan), encoding="utf-8")
    rig.open_plan(path)
    dialog = rig.dialog()
    assert rig.plan.last_load_skipped_tours_count == 1
    assert dialog.tour_combo.findText("Bad") == -1
    choose(dialog, "Good")
    assert list(tour_frames(dialog.spec())) == list(tour_frames(good.spec()))
    assert rig.plan.camera_tours == (good,) and not rig.plan.is_dirty


@pytest.mark.parametrize(("language", "system", "mark"), [
    ("de", "en_US", ","), ("en", "de_DE", "."),
])
@pytest.mark.parametrize("unit_system", [UnitSystem.METRIC, UnitSystem.IMPERIAL])
def test_tour_fields_follow_the_ui_locale_and_keep_machine_values_when_saved(
        canvas, qtbot, qapp, tmp_path, monkeypatch, language, system, mark, unit_system) -> None:
    import json

    monkeypatch.setattr(i18n, "_system_locale", lambda: QLocale(system))
    i18n.load_translator(qapp, language)
    install_decimal_marks(qapp)
    get_unit_preference().set_system(unit_system)
    try:
        rig = TourRig(canvas, qtbot, tmp_path)
        dialog = rig.dialog()
        for field in (dialog.pitch_spin, dialog.duration_spin):
            field.setFocus()
            qtbot.wait(1)
            editor = field.lineEdit()
            editor.selectAll()
            # The other convention's mark must also work when pasted.
            qapp.clipboard().setText("21.5" if mark == "," else "21,5")
            QTest.keyClick(editor, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
            field.interpretText()
            assert field.value() == 21.5
            assert f"21{mark}5" in field.text()
        assert dialog.time_from.displayFormat() == dialog.time_to.displayFormat() == "HH:mm"
        assert dialog.date_from.displayFormat() == dialog.date_to.displayFormat() == "yyyy-MM-dd"
        assert dialog.date_from.calendarWidget().firstDayOfWeek() == Qt.DayOfWeek.Monday
        dialog.motion_combo.setCurrentIndex(dialog.motion_combo.findData("path"))
        dialog.add_key_button.click()
        rig.turn()
        dialog.add_key_button.click()
        # Non-integral camera distances exercise the locale AND the unit formatter.
        key = replace(dialog.keys[0], eye=(1234.5, -2345.6, 3456.7))
        dialog._keys[0] = key
        dialog._show_keys()
        row = dialog.keys_list.item(0).text()
        if unit_system == UnitSystem.METRIC:
            assert f"12{mark}35 m" in row
        else:
            assert "40' 6\"" in row
        assert dialog.save_tour_as("Locale")
        path = tmp_path / "locale.ogp"
        rig.save(path)
        saved = json.loads(path.read_text("utf-8"))["camera_tours"][0]
        assert saved["duration_s"] == 21.5 and saved["keys"][0]["eye"] == list(key.eye)
        rig.open_plan(path)
        choose(dialog, "Locale")
        assert dialog.keys[0] == key and dialog.duration_spin.value() == 21.5
        dialog.close()
    finally:
        get_unit_preference().set_system(UnitSystem.METRIC)
        i18n.load_translator(qapp, "en")
