"""The "Camera Tour" dialog of the 3D workspace (Phase 17 L6.2, #390, ADR-071).

Not modal while the tour is being set up: the user orbits the view behind it and adds the
view as a key. While a recording runs it IS modal, because the recording drives the sim
clock and nothing else should (a new plant takes its planting date from that clock); so does a
preview of a time-lapse. A preview that leaves the clock alone stays out of the way.

What the dialog asks is two independent things and a format: how the CAMERA moves, what
the CLOCK does meanwhile (a time-lapse), and how the result is saved. The keys live in the
coordinator's session, not in the plan: closing the dialog keeps them, closing the app
does not (the plan stays free of 3D data; a follow-up issue may keep tours in the file).
"""

from __future__ import annotations

import logging
from datetime import date, time
from pathlib import Path
from typing import TYPE_CHECKING, Final

from PyQt6.QtCore import QDate, Qt, QTime
from PyQt6.QtGui import QCloseEvent, QImage, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.core.camera_path import (
    DEFAULT_FPS,
    FRAME_RATES,
    MAX_DURATION_S,
    MIN_DURATION_S,
    CameraKey,
    CameraMotion,
    CameraPath,
    DroneOrbit,
    HeldCamera,
    TourSpec,
    frame_count,
)
from open_garden_planner.core.plain_text import log_text
from open_garden_planner.core.scene3d.camera import FOV_DEG

from .tour_recorder import TourRecorder, TourResult, translated_failure
from .video_writer import FrameSink, Mp4Writer, NullWriter, PngSequenceWriter, VideoError
from .workspace_capture import CaptureRefused

if TYPE_CHECKING:
    from .workspace_capture import WorkspaceCaptureCoordinator

_LOG: Final = logging.getLogger(__name__)

#: A tour's sizes: all 16:9 and all HD, because an untagged stream below HD would be
#: played with the wrong colours (``core/video_yuv.py``).
TOUR_SIZES: Final = ((1280, 720), (1920, 1080), (2560, 1440), (3840, 2160))
DEFAULT_SIZE: Final = (1920, 1080)
#: A preview is small: it shows how the tour moves, not how it looks at full size.
PREVIEW_SIZE: Final = (640, 360)
DEFAULT_DURATION_S: Final = 12.0
#: What a time-lapse covers until the user says otherwise: from first light to dusk, and
#: from the first leaves to the last harvest.
DEFAULT_DAY: Final = (time(6, 0), time(21, 0))
DEFAULT_SEASON: Final = ((3, 1), (10, 31))


class TourDialog(QDialog):
    """Set up a tour, preview it, record it (module docstring)."""

    def __init__(self, capture: WorkspaceCaptureCoordinator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._capture = capture
        self._keys: list[CameraKey] = []
        self._recorder: TourRecorder | None = None
        self._recording = False
        self._modal = False
        self._close_when_stopped = False
        self._output: Path | None = None
        self.setWindowTitle(self.tr("Camera Tour"))
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        root = QVBoxLayout(self)
        root.addWidget(self._build_camera())
        root.addWidget(self._build_time())
        root.addWidget(self._build_output())
        self._thumbnail = QLabel(self)
        self._thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumbnail.setMinimumHeight(0)
        root.addWidget(self._thumbnail)
        self._progress = QProgressBar(self)
        self._progress.hide()
        root.addWidget(self._progress)
        self._status = QLabel("", self)
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        self._status.setWordWrap(True)
        root.addWidget(self._status)
        root.addLayout(self._build_buttons())
        self._sync_controls()

    # ── building ─────────────────────────────────────────────────────────────

    def _build_camera(self) -> QWidget:
        group = QGroupBox(self.tr("Camera"), self)
        layout = QVBoxLayout(group)
        self.motion_combo = QComboBox(group)
        self.motion_combo.addItem(self.tr("Drone Orbit Around the Plan"), "orbit")
        self.motion_combo.addItem(self.tr("Fly Through My Keyframes"), "path")
        self.motion_combo.addItem(self.tr("Keep the Current View"), "hold")
        self.motion_combo.currentIndexChanged.connect(self._sync_controls)
        layout.addWidget(self.motion_combo)
        self._motion_pages = QStackedWidget(group)
        # the orbit
        orbit = QWidget(group)
        orbit_form = QFormLayout(orbit)
        orbit_form.setContentsMargins(0, 0, 0, 0)
        self.turns_spin = QSpinBox(orbit)
        self.turns_spin.setRange(1, 4)
        orbit_form.addRow(self.tr("Turns:"), self.turns_spin)
        self.clockwise_check = QCheckBox(self.tr("Clockwise"), orbit)
        self.clockwise_check.setChecked(True)
        orbit_form.addRow("", self.clockwise_check)
        hint = QLabel(self.tr("Starts where the view is now, at the same distance and height."),
                      orbit)
        hint.setWordWrap(True)
        orbit_form.addRow(hint)
        self._motion_pages.addWidget(orbit)
        # the keys
        keys = QWidget(group)
        keys_layout = QGridLayout(keys)
        keys_layout.setContentsMargins(0, 0, 0, 0)
        self.keys_list = QListWidget(keys)
        self.keys_list.setMaximumHeight(110)
        keys_layout.addWidget(self.keys_list, 0, 0, 3, 1)
        self.add_key_button = QPushButton(self.tr("Add Current View"), keys)
        self.add_key_button.clicked.connect(self.add_key)
        keys_layout.addWidget(self.add_key_button, 0, 1)
        self.remove_key_button = QPushButton(self.tr("Remove"), keys)
        self.remove_key_button.clicked.connect(self._remove_key)
        keys_layout.addWidget(self.remove_key_button, 1, 1)
        self.loop_check = QCheckBox(self.tr("Fly back to the start"), keys)
        keys_layout.addWidget(self.loop_check, 2, 1)
        self._motion_pages.addWidget(keys)
        # the held view
        held = QLabel(self.tr("The camera stays where the view is now. Good for a time-lapse."),
                      group)
        held.setWordWrap(True)
        self._motion_pages.addWidget(held)
        layout.addWidget(self._motion_pages)
        return group

    def _build_time(self) -> QWidget:
        group = QGroupBox(self.tr("Time"), self)
        layout = QVBoxLayout(group)
        self.time_combo = QComboBox(group)
        self.time_combo.addItem(self.tr("Stay at the Plan's Date and Time"), "none")
        self.time_combo.addItem(self.tr("Time-Lapse of a Day"), "day")
        self.time_combo.addItem(self.tr("Time-Lapse Through the Year"), "year")
        self.time_combo.currentIndexChanged.connect(self._sync_controls)
        layout.addWidget(self.time_combo)
        self._time_pages = QStackedWidget(group)
        self._time_pages.addWidget(QWidget(group))
        day = QWidget(group)
        day_form = QHBoxLayout(day)
        day_form.setContentsMargins(0, 0, 0, 0)
        self.time_from = QTimeEdit(QTime(DEFAULT_DAY[0].hour, DEFAULT_DAY[0].minute), day)
        self.time_to = QTimeEdit(QTime(DEFAULT_DAY[1].hour, DEFAULT_DAY[1].minute), day)
        day_form.addWidget(QLabel(self.tr("From:"), day))
        day_form.addWidget(self.time_from)
        day_form.addWidget(QLabel(self.tr("To:"), day))
        day_form.addWidget(self.time_to)
        day_form.addStretch(1)
        self._time_pages.addWidget(day)
        year = QWidget(group)
        year_form = QHBoxLayout(year)
        year_form.setContentsMargins(0, 0, 0, 0)
        self.date_from = QDateEdit(year)
        self.date_from.setCalendarPopup(True)
        self.date_to = QDateEdit(year)
        self.date_to.setCalendarPopup(True)
        year_form.addWidget(QLabel(self.tr("From:"), year))
        year_form.addWidget(self.date_from)
        year_form.addWidget(QLabel(self.tr("To:"), year))
        year_form.addWidget(self.date_to)
        year_form.addStretch(1)
        self._time_pages.addWidget(year)
        layout.addWidget(self._time_pages)
        self.time_from.timeChanged.connect(self._sync_controls)
        self.time_to.timeChanged.connect(self._sync_controls)
        self.date_from.dateChanged.connect(self._sync_controls)
        self.date_to.dateChanged.connect(self._sync_controls)
        return group

    def _build_output(self) -> QWidget:
        group = QGroupBox(self.tr("Picture"), self)
        form = QFormLayout(group)
        self.duration_spin = QDoubleSpinBox(group)
        self.duration_spin.setRange(MIN_DURATION_S, MAX_DURATION_S)
        self.duration_spin.setDecimals(1)
        self.duration_spin.setSuffix(self.tr(" s"))
        self.duration_spin.setValue(DEFAULT_DURATION_S)
        form.addRow(self.tr("Duration:"), self.duration_spin)
        self.fps_combo = QComboBox(group)
        for rate in FRAME_RATES:
            self.fps_combo.addItem(self.tr("{rate} frames per second").format(rate=rate), rate)
        self.fps_combo.setCurrentIndex(self.fps_combo.findData(DEFAULT_FPS))
        form.addRow(self.tr("Frame rate:"), self.fps_combo)
        self.size_combo = QComboBox(group)
        for width, height in TOUR_SIZES:
            self.size_combo.addItem(f"{width} x {height}")
        self.size_combo.setCurrentIndex(TOUR_SIZES.index(DEFAULT_SIZE))
        form.addRow(self.tr("Size:"), self.size_combo)
        return group

    def _build_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.preview_button = QPushButton(self.tr("Preview"), self)
        self.preview_button.setToolTip(self.tr(
            "Play the tour small and in real time, here in this window. Saves nothing."))
        self.preview_button.clicked.connect(self.preview)
        row.addWidget(self.preview_button)
        row.addStretch(1)
        self.video_button = QPushButton(self.tr("Save Video..."), self)
        self.video_button.clicked.connect(self._ask_video)
        row.addWidget(self.video_button)
        self.png_button = QPushButton(self.tr("Save PNG Sequence..."), self)
        self.png_button.clicked.connect(self._ask_png)
        row.addWidget(self.png_button)
        self.cancel_button = QPushButton(self.tr("Cancel"), self)
        self.cancel_button.clicked.connect(self._cancel)
        self.cancel_button.hide()
        row.addWidget(self.cancel_button)
        self.close_button = QPushButton(self.tr("Close"), self)
        self.close_button.clicked.connect(self.close)
        row.addWidget(self.close_button)
        return row

    # ── the keys ─────────────────────────────────────────────────────────────

    @property
    def keys(self) -> tuple[CameraKey, ...]:
        return tuple(self._keys)

    def add_key(self) -> None:
        """The view's camera as the next key."""
        key = self._capture.camera_key()
        self._keys.append(key)
        self.keys_list.addItem(self.tr("View {number}: from {east:.1f} / {north:.1f} m, "
                                       "{height:.1f} m high").format(
            number=len(self._keys), east=key.eye[0] / 100.0, north=key.eye[1] / 100.0,
            height=key.eye[2] / 100.0))
        self._sync_controls()

    def _remove_key(self) -> None:
        row = self.keys_list.currentRow()
        if 0 <= row < len(self._keys):
            del self._keys[row]
            self.keys_list.takeItem(row)
        self._sync_controls()

    # ── what the user asked for ──────────────────────────────────────────────

    def motion(self) -> CameraMotion | None:
        """The camera's movement as the controls say; None: it cannot be made yet."""
        kind = self.motion_combo.currentData()
        if kind == "path":
            try:
                return CameraPath(self._keys, closed=self.loop_check.isChecked())
            except ValueError:
                return None
        if kind == "hold":
            return HeldCamera(self._capture.camera_key())
        return DroneOrbit(self._capture.orbit_pose(), fov_deg=FOV_DEG,
                          turns=float(self.turns_spin.value()),
                          clockwise=self.clockwise_check.isChecked())

    def spec(self) -> TourSpec | None:
        """The tour as the controls say. None: its keys are missing, or a range runs backwards."""
        motion = self.motion()
        if motion is None:
            return None
        kind = self.time_combo.currentData()
        date_range = time_range = None
        if kind == "day":
            start, end = self.time_from.time(), self.time_to.time()
            time_range = (time(start.hour(), start.minute()), time(end.hour(), end.minute()))
        elif kind == "year":
            start_day, end_day = self.date_from.date(), self.date_to.date()
            date_range = (date(start_day.year(), start_day.month(), start_day.day()),
                          date(end_day.year(), end_day.month(), end_day.day()))
        try:
            return TourSpec(motion, float(self.duration_spin.value()),
                            int(self.fps_combo.currentData()),
                            date_range=date_range, time_range=time_range,
                            wind=not self._reduced_motion())
        except ValueError:
            return None

    def _reduced_motion(self) -> bool:
        look = self._capture._get_look()
        return bool(look is not None and look.reduced_motion)

    def _sync_controls(self, *_arguments: object) -> None:
        self._motion_pages.setCurrentIndex(self.motion_combo.currentIndex())
        self._time_pages.setCurrentIndex(self.time_combo.currentIndex())
        self.remove_key_button.setEnabled(bool(self._keys))
        ready = self.spec() is not None and self._recorder is None
        for button in (self.preview_button, self.video_button, self.png_button):
            button.setEnabled(ready)

    def showEvent(self, event: object) -> None:  # noqa: N802 - Qt's name
        """The year the plan date is in, whenever the dialog opens and no year was chosen."""
        if not self._recording and not self.date_from.property("chosen"):
            year = self._capture.plan_date().year
            self.date_from.setDate(QDate(year, *DEFAULT_SEASON[0]))
            self.date_to.setDate(QDate(year, *DEFAULT_SEASON[1]))
            self.date_from.setProperty("chosen", True)
        self._sync_controls()
        super().showEvent(event)  # type: ignore[arg-type]

    # ── running ──────────────────────────────────────────────────────────────

    def preview(self) -> None:
        self._run(NullWriter(self), PREVIEW_SIZE, realtime=True)

    def _ask_video(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Save Video"), self._capture.default_path("garden-tour.mp4"),
            self.tr("MP4 video (*.mp4)"))
        if path:
            self.record_video(Path(path))

    def _ask_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Save PNG Sequence"), self._capture.default_path("garden-tour"),
            self.tr("Folder for the frames (*)"))
        if path:
            self.record_png(Path(path))

    def _size(self) -> tuple[int, int]:
        return TOUR_SIZES[self.size_combo.currentIndex()]

    def record_video(self, path: Path) -> None:
        spec = self.spec()
        if spec is not None:
            self._output = path
            self._run(Mp4Writer(path, self._size(), spec.fps, self), self._size())

    def record_png(self, folder: Path) -> None:
        self._output = folder
        self._run(PngSequenceWriter(folder, self), self._size())

    def _run(self, writer: FrameSink, size: tuple[int, int], *, realtime: bool = False) -> None:
        spec = self.spec()
        if spec is None or self._recorder is not None:
            return
        try:
            recorder = self._capture.start_tour(spec, size, writer, realtime=realtime)
        except CaptureRefused as refused:   # its own text is English: it is an agent's sentence
            self._status.setText(self._refusal(refused.code))
            return
        except VideoError as error:
            self._status.setText(str(error))
            return
        self._recorder = recorder
        self._recording = not realtime
        self._modal = self._recording or spec.date_range is not None or spec.time_range is not None
        recorder.progress.connect(self._on_progress)
        recorder.paused_changed.connect(self._on_paused)
        recorder.finishing.connect(self._on_finishing)
        recorder.finished.connect(self._on_finished)
        self._progress.setRange(0, frame_count(spec))
        self._progress.setValue(0)
        self._progress.show()
        self._status.setText(self.tr("Rendering…") if not realtime else "")
        self.cancel_button.show()
        self.close_button.setEnabled(False)
        if self._modal:
            self.setWindowModality(Qt.WindowModality.ApplicationModal)
            # a window's modality takes effect when it is shown
            self.hide()
            self.show()
        self._sync_controls()

    def _on_progress(self, done: int, total: int, image: QImage) -> None:
        self._progress.setValue(done)
        self._thumbnail.setPixmap(QPixmap.fromImage(image))
        if self._recording:
            self._status.setText(self.tr("Frame {done} of {total}").format(done=done, total=total))

    def _refusal(self, code: str) -> str:
        """Why no tour can start, in the user's language (``workspace_capture.BLOCKERS``)."""
        return {
            "not_open": self.tr("Open the 3D view first: switch to 3D or Split."),
            "recording": self.tr("A recording is already running."),
            "unavailable": self.tr("3D is not available on this computer."),
        }.get(code, self.tr("The 3D view is still building. Try again in a moment."))

    def _on_finishing(self) -> None:
        self.cancel_button.setEnabled(False)
        if self._recording:
            self._status.setText(self.tr("Finishing the file…"))

    def _on_paused(self, paused: bool) -> None:
        if paused:
            self._status.setText(self.tr(
                "Waiting: the 3D view is not visible. The recording goes on when it is back."))

    def _cancel(self) -> None:
        if self._recorder is not None and self._recorder.cancel():
            self.cancel_button.setEnabled(False)
            self._status.setText(self.tr("Stopping…"))

    def _on_finished(self, result: TourResult) -> None:
        recording = self._recording
        self._recorder = None
        self._recording = False
        self._progress.hide()
        self.cancel_button.hide()
        self.cancel_button.setEnabled(True)
        self.close_button.setEnabled(True)
        if self._modal:
            self._modal = False
            self.hide()
            self.setWindowModality(Qt.WindowModality.NonModal)
            self.show()
        self._status.setText(self._say(result, recording))
        self._sync_controls()
        closing, self._close_when_stopped = self._close_when_stopped, False
        if closing and result.cancelled:   # a finished file's outcome stays to be read
            self.close()

    def _say(self, result: TourResult, recording: bool) -> str:
        if result.cancelled:
            return self.tr("Cancelled.")
        if not result.ok:
            _LOG.error("Camera tour failed: %s", log_text(result.message))
            return translated_failure(result.message)
        if not recording:
            return ""
        done = self.tr("Saved {frames} frames to {path}.").format(
            frames=result.frames, path=self._output)
        if result.unsettled:
            done += " " + self.tr("{count} frames were rendered before the 3D view had caught "
                                  "up with their date.").format(count=result.unsettled)
        return done

    def reject(self) -> None:
        """Esc: a running preview or recording stops, and the dialog stays to say how that
        ended. Hiding it would leave a modal recording running behind nothing at all."""
        if self._recorder is not None:
            self._cancel()
            return
        super().reject()

    def closeEvent(self, event: QCloseEvent | None) -> None:  # noqa: N802 - Qt's name
        """A running preview or recording stops first, and then the dialog closes."""
        if self._recorder is not None:
            self._close_when_stopped = True
            self._cancel()
            if event is not None:
                event.ignore()
            return
        super().closeEvent(event)
