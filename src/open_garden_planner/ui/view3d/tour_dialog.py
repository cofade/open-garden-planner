"""The "Camera Tour" dialog of the 3D workspace (Phase 17 L6.2, #390, ADR-072).

Not modal while the tour is being set up: the user orbits the view behind it and adds the
view as a key. While a recording runs it IS modal, because the recording drives the sim
clock and nothing else should (a new plant takes its planting date from that clock); so does a
preview of a time-lapse. A preview that leaves the clock alone stays out of the way.

What the dialog asks is two independent things and a format: how the CAMERA moves, what
the CLOCK does meanwhile (a time-lapse), and how the result is saved.

The controls are a DRAFT. It lives in the dialog: closing the dialog keeps it, closing the
app or opening another plan does not. "Save Tour" keeps it in the plan under a name
(issue #737, ``core/camera_tours.py``): the plan owns the list, every save, rename and
delete is one undo step (``WorkspaceCaptureCoordinator.save_tour`` and its neighbours), and
choosing a saved tour puts it back into the controls. A saved orbit or held view carries the
view it started from, so it plays the same next week; "Use Current View" lets it go.

An orbit's tilt is ONE value, ``_orbit_pitch`` (#807): the tilt control shows and edits it,
a saved tour brings its own (exactly, not the control's rounding), and "Use Current View"
puts the view's tilt into it. A new orbit starts from the view's place and distance at
``DEFAULT_ORBIT_PITCH_DEG``, eases in and out, and lasts ``ORBIT_SECONDS_PER_TURN`` a turn
until the user sets a duration (``default_duration_s``).
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import date, time
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, Final

from PyQt6.QtCore import QDate, Qt, QTime, pyqtSignal
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
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
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
    clamp_orbit_pitch,
    frame_count,
    orbit_pitch_range,
)
from open_garden_planner.core.camera_tours import (
    DEFAULT_DURATION_S,
    DEFAULT_ORBIT_PITCH_DEG,
    DEFAULT_SIZE,
    MAX_TOUR_KEYS,
    MAX_TOURS,
    ORBIT_TURNS,
    TOUR_SIZES,
    SavedTour,
    clean_tour_name,
    default_duration_s,
    find_tour,
)
from open_garden_planner.core.measurement_display import length_text
from open_garden_planner.core.plain_text import log_text
from open_garden_planner.core.scene3d.camera import (
    FOV_DEG,
    MAX_PITCH_DEG,
    MIN_PITCH_DEG,
    CameraPose,
)
from open_garden_planner.ui.date_fields import as_date_field, as_time_field
from open_garden_planner.ui.units_notifier import units_notifier

from .tour_recorder import TourRecorder, TourResult, translated_failure
from .video_writer import (
    DEFAULT_VIDEO_QUALITY,
    FrameSink,
    Mp4Writer,
    NullWriter,
    PngSequenceWriter,
    VideoError,
)
from .workspace_capture import CaptureRefused

if TYPE_CHECKING:
    from .workspace_capture import WorkspaceCaptureCoordinator

_LOG: Final = logging.getLogger(__name__)
#: Window frame, title bar and the gap under a run's frame, in pixels.
_FRAME_CHROME_PX: Final = 48
#: A run's frame is never shown smaller than this, however short the screen.
_MIN_FRAME_PX: Final = 96

__all__ = ["ASK_DISCARD_AFTER_S", "DEFAULT_DAY", "DEFAULT_DURATION_S", "DEFAULT_SEASON",
           "DEFAULT_SIZE", "PREVIEW_SIZE", "TOUR_SIZES", "TourDialog"]

#: A preview is small: it shows how the tour moves, not how it looks at full size.
PREVIEW_SIZE: Final = (640, 360)
#: What a time-lapse covers until the user says otherwise: from first light to dusk, and
#: from the first leaves to the last harvest.
DEFAULT_DAY: Final = (time(6, 0), time(21, 0))
DEFAULT_SEASON: Final = ((3, 1), (10, 31))
#: A recording that has run this long is worth a question before Esc or X throws it away.
ASK_DISCARD_AFTER_S: Final = 10.0


class TourDialog(QDialog):
    """Set up a tour, preview it, record it (module docstring)."""

    #: The dialog closed for good: the coordinator drops it when the ENGINE stopped it;
    #: a user's Close keeps it, because the tour's keys live here for the session.
    closed = pyqtSignal()

    def __init__(self, capture: WorkspaceCaptureCoordinator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._capture = capture
        self._keys: list[CameraKey] = []
        #: The saved tour the controls came from (its name), or None: an unsaved draft.
        self._bound: str | None = None
        #: The view a saved orbit starts from and the view a saved held camera keeps.
        #: None: the view as it is when the tour starts.
        self._orbit_start: tuple[CameraPose, float] | None = None
        self._held_view: CameraKey | None = None
        #: The orbit's tilt (module docstring): what the tilt control shows, exactly.
        self._orbit_pitch = DEFAULT_ORBIT_PITCH_DEG
        self._setting_pitch = False
        #: True once the user set a duration: the default follows the camera until then.
        self._duration_chosen = False
        self._setting_duration = False
        #: What the status line last said about a saved tour; it goes when the controls
        #: are changed, so that "Saved" never stands beside an edit that is not saved.
        self._tour_note = ""
        self._recorder: TourRecorder | None = None
        self._recording = False
        self._finishing = False
        self._modal = False
        self._close_when_stopped = False
        self._output: Path | None = None
        self._run_started_at: float | None = None
        self._sink_kind = "preview"
        self._programmatic_close = False
        #: True once the user edited the year: the defaults follow the plan date until then.
        self._dates_chosen = False
        self._setting_dates = False
        self.setWindowTitle(self.tr("Camera Tour"))
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        root = QVBoxLayout(self)
        root.addWidget(self._build_tours())
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
        capture.tours_changed.connect(self._refresh_tours)
        self._refresh_tours()
        # Enter in a field starts nothing: no button of this window is the default (#796).
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
            button.setDefault(False)
        self._height_without_frame = 0

    # ── building ─────────────────────────────────────────────────────────────

    def _build_tours(self) -> QWidget:
        """The plan's saved tours: choose one, keep the controls as one, rename, delete."""
        group = QGroupBox(self.tr("Tours in This Plan"), self)
        layout = QVBoxLayout(group)
        self.tour_combo = QComboBox(group)
        self.tour_combo.setToolTip(self.tr(
            "The tours kept in this plan. They are saved with the plan file."))
        self.tour_combo.currentIndexChanged.connect(self._on_tour_chosen)
        layout.addWidget(self.tour_combo)
        row = QHBoxLayout()
        self.save_tour_button = QPushButton(self.tr("Save Tour"), group)
        self.save_tour_button.clicked.connect(self.save_tour)
        self.save_tour_as_button = QPushButton(self.tr("Save Tour As..."), group)
        self.save_tour_as_button.clicked.connect(self._ask_save_as)
        self.rename_tour_button = QPushButton(self.tr("Rename..."), group)
        self.rename_tour_button.clicked.connect(self._ask_rename)
        self.delete_tour_button = QPushButton(self.tr("Delete"), group)
        self.delete_tour_button.clicked.connect(self.delete_tour)
        for button in (self.save_tour_button, self.save_tour_as_button,
                       self.rename_tour_button, self.delete_tour_button):
            button.setAutoDefault(False)   # Enter in a field must not save or delete a tour
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        group.setVisible(self._capture.tours_connected)
        return group

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
        self.turns_spin.setRange(*ORBIT_TURNS)
        self.turns_spin.valueChanged.connect(self._sync_controls)
        orbit_form.addRow(self.tr("Turns:"), self.turns_spin)
        self.clockwise_check = QCheckBox(self.tr("Clockwise"), orbit)
        self.clockwise_check.setChecked(True)
        self.clockwise_check.toggled.connect(self._sync_controls)
        orbit_form.addRow("", self.clockwise_check)
        self.pitch_spin = QDoubleSpinBox(orbit)
        self.pitch_spin.setDecimals(1)
        self.pitch_spin.setSingleStep(1.0)
        self.pitch_spin.setRange(MIN_PITCH_DEG, MAX_PITCH_DEG)
        self.pitch_spin.setSuffix(self.tr(" °"))
        self.pitch_spin.setValue(self._orbit_pitch)
        self.pitch_spin.setToolTip(self.tr(
            "How steeply the camera looks down at the garden. A low tilt shows the horizon "
            "and the sky; a high one looks down into the beds."))
        self.pitch_spin.valueChanged.connect(self._pitch_edited)
        orbit_form.addRow(self.tr("Camera tilt:"), self.pitch_spin)
        self.ease_check = QCheckBox(self.tr("Start and stop smoothly"), orbit)
        self.ease_check.setChecked(True)
        self.ease_check.setToolTip(self.tr(
            "The camera speeds up gently at the start and slows down to a stop at the end. "
            "Turn it off for a video that plays in a loop: then the end leads straight back "
            "into the start."))
        self.ease_check.toggled.connect(self._sync_controls)
        orbit_form.addRow("", self.ease_check)
        self._orbit_hint = QLabel(orbit)
        self._orbit_hint.setWordWrap(True)
        orbit_form.addRow(self._orbit_hint)
        self.orbit_view_button = QPushButton(self.tr("Use Current View"), orbit)
        self.orbit_view_button.setAutoDefault(False)
        self.orbit_view_button.setToolTip(self.tr(
            "Start the orbit exactly where the 3D view is now, with the view's own tilt."))
        self.orbit_view_button.clicked.connect(self._use_current_view)
        orbit_row = QHBoxLayout()
        orbit_row.addWidget(self.orbit_view_button)
        orbit_row.addStretch(1)
        orbit_form.addRow(orbit_row)
        self._motion_pages.addWidget(orbit)
        # the keys
        keys = QWidget(group)
        keys_layout = QGridLayout(keys)
        keys_layout.setContentsMargins(0, 0, 0, 0)
        self.keys_list = QListWidget(keys)
        units_notifier().changed.connect(self._show_keys)
        self.keys_list.setMaximumHeight(110)
        keys_layout.addWidget(self.keys_list, 0, 0, 3, 1)
        self.add_key_button = QPushButton(self.tr("Add Current View"), keys)
        self.add_key_button.clicked.connect(self.add_key)
        keys_layout.addWidget(self.add_key_button, 0, 1)
        self.remove_key_button = QPushButton(self.tr("Remove"), keys)
        self.remove_key_button.clicked.connect(self._remove_key)
        keys_layout.addWidget(self.remove_key_button, 1, 1)
        self.loop_check = QCheckBox(self.tr("Fly back to the start"), keys)
        self.loop_check.toggled.connect(self._sync_controls)
        keys_layout.addWidget(self.loop_check, 2, 1)
        self._motion_pages.addWidget(keys)
        # the held view
        held = QWidget(group)
        held_layout = QVBoxLayout(held)
        held_layout.setContentsMargins(0, 0, 0, 0)
        self._held_hint = QLabel(held)
        self._held_hint.setWordWrap(True)
        held_layout.addWidget(self._held_hint)
        self.held_view_button = QPushButton(self.tr("Use Current View"), held)
        self.held_view_button.setAutoDefault(False)
        self.held_view_button.clicked.connect(self._use_current_view)
        held_layout.addWidget(self.held_view_button, 0, Qt.AlignmentFlag.AlignLeft)
        held_layout.addStretch(1)
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
        self.time_from = as_time_field(
            QTimeEdit(QTime(DEFAULT_DAY[0].hour, DEFAULT_DAY[0].minute), day))
        self.time_to = as_time_field(
            QTimeEdit(QTime(DEFAULT_DAY[1].hour, DEFAULT_DAY[1].minute), day))
        day_form.addWidget(QLabel(self.tr("From:"), day))
        day_form.addWidget(self.time_from)
        day_form.addWidget(QLabel(self.tr("To:"), day))
        day_form.addWidget(self.time_to)
        day_form.addStretch(1)
        self._time_pages.addWidget(day)
        year = QWidget(group)
        year_form = QHBoxLayout(year)
        year_form.setContentsMargins(0, 0, 0, 0)
        self.date_from = as_date_field(QDateEdit(year))
        self.date_to = as_date_field(QDateEdit(year))
        year_form.addWidget(QLabel(self.tr("From:"), year))
        year_form.addWidget(self.date_from)
        year_form.addWidget(QLabel(self.tr("To:"), year))
        year_form.addWidget(self.date_to)
        year_form.addStretch(1)
        self._time_pages.addWidget(year)
        layout.addWidget(self._time_pages)
        self.time_from.timeChanged.connect(self._sync_controls)
        self.time_to.timeChanged.connect(self._sync_controls)
        self.date_from.dateChanged.connect(self._dates_changed)
        self.date_to.dateChanged.connect(self._dates_changed)
        return group

    def _dates_changed(self, *_arguments: object) -> None:
        """The year is the user's from now on: a later plan date must not overwrite it."""
        if not self._setting_dates:
            self._dates_chosen = True
        self._sync_controls()

    def _build_output(self) -> QWidget:
        group = QGroupBox(self.tr("Picture"), self)
        form = QFormLayout(group)
        self.duration_spin = QDoubleSpinBox(group)
        self.duration_spin.setRange(MIN_DURATION_S, MAX_DURATION_S)
        self.duration_spin.setDecimals(1)
        self.duration_spin.setSuffix(self.tr(" s"))
        self.duration_spin.setValue(DEFAULT_DURATION_S)
        self.duration_spin.setToolTip(self.tr(
            "How long the video lasts. A drone orbit takes 30 s a turn until you set a "
            "length here."))
        self.duration_spin.valueChanged.connect(self._duration_edited)
        form.addRow(self.tr("Duration:"), self.duration_spin)
        self.fps_combo = QComboBox(group)
        for rate in FRAME_RATES:
            self.fps_combo.addItem(self.tr("{rate} frames per second").format(rate=rate), rate)
        self.fps_combo.setCurrentIndex(self.fps_combo.findData(DEFAULT_FPS))
        self.fps_combo.currentIndexChanged.connect(self._sync_controls)
        form.addRow(self.tr("Frame rate:"), self.fps_combo)
        self.size_combo = QComboBox(group)
        for width, height in TOUR_SIZES:
            self.size_combo.addItem(f"{width} x {height}")
        self.size_combo.setCurrentIndex(TOUR_SIZES.index(DEFAULT_SIZE))
        self.size_combo.currentIndexChanged.connect(self._sync_controls)
        form.addRow(self.tr("Size:"), self.size_combo)
        # How the video is encoded: not part of a saved tour, like the look (#807)
        self.quality_combo = QComboBox(group)
        self.quality_combo.addItem(self.tr("Standard"), "standard")
        self.quality_combo.addItem(self.tr("Best, for Publishing"), "best")
        self.quality_combo.setCurrentIndex(self.quality_combo.findData(DEFAULT_VIDEO_QUALITY))
        self.quality_combo.setToolTip(self.tr(
            "How much detail the video keeps. Best keeps nearly every leaf and makes a larger "
            "file: use it for a video you publish. Only for Save Video: a PNG sequence keeps "
            "every detail."))
        form.addRow(self.tr("Video quality:"), self.quality_combo)
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
        """The view's camera as the next key (a tour has at most ``MAX_TOUR_KEYS``)."""
        if len(self._keys) >= MAX_TOUR_KEYS:
            return
        key = self._capture.camera_key()
        self._keys.append(key)
        self.keys_list.addItem(self._key_text(len(self._keys), key))
        self._sync_controls()

    def _key_text(self, number: int, key: CameraKey) -> str:
        return self.tr("View {number}: from {east} / {north}, "
                       "{height} high").format(
            number=number, east=length_text(key.eye[0]),
            north=length_text(key.eye[1]),
            height=length_text(key.eye[2]))

    def _show_keys(self) -> None:
        """The list says what the keys are (a saved tour or another plan came)."""
        self.keys_list.clear()
        for number, key in enumerate(self._keys, start=1):
            self.keys_list.addItem(self._key_text(number, key))

    def _remove_key(self) -> None:
        row = self.keys_list.currentRow()
        if 0 <= row < len(self._keys):
            del self._keys[row]
            self._show_keys()   # the views after it are numbered anew
            self.keys_list.setCurrentRow(min(row, len(self._keys) - 1))
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
            return HeldCamera(self._held())
        return self._orbit()

    def _orbit(self) -> DroneOrbit:
        """The orbit as the controls say: from a saved tour's view, or from the view's place
        and distance now, at the tilt (``_orbit_pitch``). A saved tour's tilt is flown as it
        was saved; the view's distance can change behind the dialog, so the tilt of an orbit
        from the view is kept above the ground for the distance it has now."""
        if self._orbit_start is not None:
            start, fov = self._orbit_start
            pitch = self._orbit_pitch
        else:
            start, fov = self._capture.orbit_pose(), FOV_DEG
            pitch = clamp_orbit_pitch(self._orbit_pitch, start.distance_cm)
        pose = CameraPose(start.target, start.distance_cm, start.yaw_deg, pitch)
        return DroneOrbit(pose, fov_deg=fov, turns=float(self.turns_spin.value()),
                          clockwise=self.clockwise_check.isChecked(),
                          ease=self.ease_check.isChecked())

    def _orbit_distance(self) -> float:
        start = self._orbit_start
        return start[0].distance_cm if start is not None else self._capture.orbit_pose().distance_cm

    def _pitch_edited(self, value: float) -> None:
        """The user set the tilt: it is the orbit's, kept above the ground."""
        if self._setting_pitch:   # the control is being shown the tilt, not changing it
            return
        self._orbit_pitch = clamp_orbit_pitch(value, self._orbit_distance())
        self._sync_controls()

    def _show_pitch(self) -> None:
        """The tilt control shows the tilt the orbit flies: a saved tour's own (its range
        widened to hold it, so showing it never changes it), or ``_orbit_pitch`` kept above
        the ground at the view's distance now."""
        low, high = orbit_pitch_range(self._orbit_distance())
        if self._orbit_start is not None:
            shown = self._orbit_pitch
            low, high = min(low, shown), max(high, shown)
        else:
            shown = min(max(self._orbit_pitch, low), high)
        self._setting_pitch = True
        try:
            self.pitch_spin.setRange(low, high)
            self.pitch_spin.setValue(shown)
        finally:
            self._setting_pitch = False

    def _duration_edited(self, *_arguments: object) -> None:
        """The length is the user's from now on: the camera's default no longer moves it."""
        if self._setting_duration:   # the default moving it, from inside ``_sync_controls``
            return
        self._duration_chosen = True
        self._sync_controls()

    def _follow_default_duration(self) -> None:
        if self._duration_chosen:
            return
        seconds = default_duration_s(str(self.motion_combo.currentData()), self.turns_spin.value(),
                                     str(self.time_combo.currentData()))
        if self.duration_spin.value() != seconds:
            self._setting_duration = True
            try:
                self.duration_spin.setValue(seconds)
            finally:
                self._setting_duration = False

    def _held(self) -> CameraKey:
        return self._held_view or self._capture.camera_key()

    def _ranges(self) -> tuple[tuple[date, date] | None, tuple[time, time] | None]:
        """What the clock does: (the stretch of the year, the stretch of the day)."""
        kind = self.time_combo.currentData()
        if kind == "day":
            start, end = self.time_from.time(), self.time_to.time()
            return None, (time(start.hour(), start.minute()), time(end.hour(), end.minute()))
        if kind == "year":
            start_day, end_day = self.date_from.date(), self.date_to.date()
            return (date(start_day.year(), start_day.month(), start_day.day()),
                    date(end_day.year(), end_day.month(), end_day.day())), None
        return None, None

    def spec(self) -> TourSpec | None:
        """The tour as the controls say. None: its keys are missing, or a range runs backwards."""
        motion = self.motion()
        if motion is None:
            return None
        date_range, time_range = self._ranges()
        try:
            return TourSpec(motion, float(self.duration_spin.value()),
                            int(self.fps_combo.currentData()),
                            date_range=date_range, time_range=time_range,
                            wind=not self._reduced_motion())
        except ValueError:
            return None

    def _reduced_motion(self) -> bool:
        return self._capture.reduced_motion()

    def _sync_controls(self, *_arguments: object) -> None:
        self._motion_pages.setCurrentIndex(self.motion_combo.currentIndex())
        self._time_pages.setCurrentIndex(self.time_combo.currentIndex())
        self.remove_key_button.setEnabled(bool(self._keys))
        self.add_key_button.setEnabled(len(self._keys) < MAX_TOUR_KEYS)
        self._follow_default_duration()
        self._show_pitch()
        self._orbit_hint.setText(
            self.tr("Starts at the view saved with this tour.") if self._orbit_start is not None
            else self.tr("Starts where the view is now, at the same distance, with the tilt "
                         "set here."))
        self._held_hint.setText(
            self.tr("The camera stays at the view saved with this tour. Good for a time-lapse.")
            if self._held_view is not None
            else self.tr("The camera stays where the view is now. Good for a time-lapse."))
        self.held_view_button.setVisible(self._held_view is not None)
        idle = self._recorder is None
        ready = self.spec() is not None and idle
        for button in (self.preview_button, self.video_button, self.png_button):
            button.setEnabled(ready)
        # the saved tours: only what would do something is offered
        self.tour_combo.setEnabled(idle)
        self.save_tour_as_button.setEnabled(ready)
        self.save_tour_button.setEnabled(ready and self._bound is not None and self._modified())
        self.rename_tour_button.setEnabled(idle and self._bound is not None)
        self.delete_tour_button.setEnabled(idle and self._bound is not None)
        if self._tour_note and self.save_tour_button.isEnabled():
            if self._status.text() == self._tour_note:
                self._status.setText("")
            self._tour_note = ""

    # ── tours kept in the plan (#737) ────────────────────────────────────────

    @property
    def bound_tour(self) -> str | None:
        """The name of the saved tour the controls came from. None: an unsaved draft."""
        return self._bound

    @property
    def starts_at_saved_view(self) -> bool:
        """The orbit or held camera starts at a saved tour's view, not at the view now."""
        kind = self.motion_combo.currentData()
        return ((kind == "orbit" and self._orbit_start is not None)
                or (kind == "hold" and self._held_view is not None))

    def _draft(self, name: str) -> SavedTour | None:
        """The controls as a tour of that name. None: they are no tour yet (``spec``)."""
        kind = str(self.motion_combo.currentData())
        date_range, time_range = self._ranges()
        try:
            return SavedTour(
                name=name, motion=kind, keys=tuple(self._keys),
                closed=self.loop_check.isChecked(),
                orbit=self._orbit() if kind == "orbit" else None,
                held=self._held() if kind == "hold" else None,
                date_range=date_range, time_range=time_range,
                duration_s=float(self.duration_spin.value()),
                fps=int(self.fps_combo.currentData()), size=self._size())
        except ValueError:
            return None

    def _uses_the_view(self) -> bool:
        """The tour starts from wherever the view is when it starts, not from a saved view."""
        kind = self.motion_combo.currentData()
        return ((kind == "orbit" and self._orbit_start is None)
                or (kind == "hold" and self._held_view is None))

    def _modified(self) -> bool:
        """The controls are not the saved tour they came from any more."""
        if self._bound is None:
            return False
        saved = find_tour(self._capture.saved_tours(), self._bound)
        return saved is None or self._uses_the_view() or self._draft(saved.name) != saved

    def _draft_is_unsaved(self) -> bool:
        """Choosing another tour would lose work: a saved tour's changes, or keyframes
        that are in no saved tour. An orbit or a held view costs one click to make again
        and is not asked about."""
        if self._bound is not None:
            return self._modified()
        if not self._keys:
            return False
        draft = self._draft("draft")
        return draft is None or all(replace(tour, name=draft.name) != draft
                                    for tour in self._capture.saved_tours())

    def _refresh_tours(self) -> None:
        """The combo names the plan's tours (they changed, or the dialog is new)."""
        tours = self._capture.saved_tours()
        bound = find_tour(tours, self._bound) if self._bound is not None else None
        self._bound = bound.name if bound is not None else None
        combo = self.tour_combo
        combo.blockSignals(True)
        try:
            combo.clear()
            combo.addItem(self.tr("Unsaved Tour"), None)
            for tour in tours:
                combo.addItem(tour.name, tour.name)
            combo.setCurrentIndex(self._bound_index())
        finally:
            combo.blockSignals(False)
        self._sync_controls()

    def _bound_index(self) -> int:
        return max(0, self.tour_combo.findData(self._bound)) if self._bound is not None else 0

    def _on_tour_chosen(self, index: int) -> None:
        """The combo: a saved tour goes into the controls; "Unsaved Tour" lets go of the
        saved one and keeps the controls, as a copy to go on from."""
        name = self.tour_combo.itemData(index)
        if name == self._bound:
            return
        if name is None:
            self._bound = None
            self._sync_controls()
            return
        tour = find_tour(self._capture.saved_tours(), str(name))
        if tour is None or (self._draft_is_unsaved() and not self._ask(
                self.tr("Discard the changes to the current tour?"),
                QMessageBox.StandardButton.Discard)):
            self.tour_combo.blockSignals(True)
            self.tour_combo.setCurrentIndex(self._bound_index())
            self.tour_combo.blockSignals(False)
            return
        self._show(tour)

    def _show(self, tour: SavedTour) -> None:
        """A saved tour into the controls."""
        self._bound = tour.name
        self._keys = list(tour.keys)
        self._show_keys()
        self._orbit_start = self._held_view = None
        self._pin(tour)
        self.loop_check.setChecked(tour.closed)
        self._duration_chosen = True   # the tour's length, not the camera's default
        self.motion_combo.setCurrentIndex(self.motion_combo.findData(tour.motion))
        if tour.orbit is not None:
            self.turns_spin.setValue(int(tour.orbit.turns))
            self.clockwise_check.setChecked(tour.orbit.clockwise)
            self.ease_check.setChecked(tour.orbit.ease)   # absent in an older file: no easing
        kind = "year" if tour.date_range else "day" if tour.time_range else "none"
        self.time_combo.setCurrentIndex(self.time_combo.findData(kind))
        if tour.time_range is not None:
            self.time_from.setTime(QTime(tour.time_range[0].hour, tour.time_range[0].minute))
            self.time_to.setTime(QTime(tour.time_range[1].hour, tour.time_range[1].minute))
        if tour.date_range is not None:
            first, last = tour.date_range
            self.date_from.setDate(QDate(first.year, first.month, first.day))
            self.date_to.setDate(QDate(last.year, last.month, last.day))
            self._dates_chosen = True   # the tour's year, not the plan's
        self.duration_spin.setValue(tour.duration_s)
        self.fps_combo.setCurrentIndex(self.fps_combo.findData(tour.fps))
        self.size_combo.setCurrentIndex(TOUR_SIZES.index(tour.size))
        self._status.setText("")
        self._sync_controls()

    def _pin(self, tour: SavedTour) -> None:
        """The controls are this saved tour: its view, not wherever the view is now."""
        if tour.orbit is not None:
            self._orbit_start = (tour.orbit.pose, tour.orbit.fov_deg)
            self._orbit_pitch = tour.orbit.pose.pitch_deg   # exactly, whatever the control shows
        if tour.held is not None:
            self._held_view = tour.held

    def _use_current_view(self) -> None:
        """Let go of the saved view: the orbit or the held camera starts at the view again.
        The orbit takes the view's tilt too, so its first frame is the view."""
        if self.motion_combo.currentData() == "hold":
            self._held_view = None
        else:
            self._orbit_start = None
            pose = self._capture.orbit_pose()
            self._orbit_pitch = clamp_orbit_pitch(pose.pitch_deg, pose.distance_cm)
        self._sync_controls()

    def _keep(self, name: str) -> bool:
        """The controls into the plan as the tour of that name: ONE undo step."""
        tour = self._draft(name)
        if tour is None or self._recorder is not None or not self._capture.tours_connected:
            return False
        self._bound = tour.name   # before the list comes back (``_refresh_tours``)
        self._pin(tour)
        self._capture.save_tour(tour)
        self._note(self.tr("Saved the tour '{name}' in the plan.").format(name=tour.name))
        return True

    def _note(self, text: str) -> None:
        self._tour_note = text
        self._status.setText(text)

    def save_tour(self) -> bool:
        """"Save Tour": the controls replace the saved tour they came from."""
        return self._bound is not None and self._keep(self._bound)

    def save_tour_as(self, name: str) -> bool:
        """"Save Tour As": keep the controls under ``name``. A name the plan already has
        is asked about first; False when nothing was saved."""
        name = clean_tour_name(name)
        if not name or self._draft(name) is None:
            return False
        tours = self._capture.saved_tours()
        existing = find_tour(tours, name)
        own = self._bound is not None and name.casefold() == self._bound.casefold()
        if existing is None and len(tours) >= MAX_TOURS:
            self._note(self.tr(
                "A plan keeps at most {count} tours. Delete one first.").format(count=MAX_TOURS))
            return False
        if existing is not None and not own and not self._ask(
                self.tr("A tour named '{name}' already exists. Replace it?").format(
                    name=existing.name), QMessageBox.StandardButton.Yes):
            return False
        return self._keep(name)

    def rename_tour(self, new_name: str) -> bool:
        """"Rename": the saved tour the controls came from gets another name."""
        name = clean_tour_name(new_name)
        if self._bound is None or not name or name == self._bound or self._recorder is not None:
            return False
        other = find_tour(self._capture.saved_tours(), name)
        if other is not None and other.name.casefold() != self._bound.casefold():
            self._note(self.tr("A tour named '{name}' already exists.").format(name=other.name))
            return False
        old, self._bound = self._bound, name
        self._capture.rename_tour(old, name)
        self._status.setText("")
        return True

    def delete_tour(self) -> bool:
        """"Delete": the saved tour goes; the controls stay, as an unsaved draft."""
        if self._bound is None or self._recorder is not None:
            return False
        name, self._bound = self._bound, None
        self._capture.delete_tour(name)
        self._note(self.tr("Deleted the tour '{name}'. Undo brings it back.").format(name=name))
        return True

    def _ask_save_as(self) -> None:
        name, accepted = QInputDialog.getText(
            self, self.tr("Save Tour As"), self.tr("Name of the tour:"), text=self._bound or "")
        if accepted:
            self.save_tour_as(name)

    def _ask_rename(self) -> None:
        name, accepted = QInputDialog.getText(
            self, self.tr("Rename Tour"), self.tr("Name of the tour:"), text=self._bound or "")
        if accepted:
            self.rename_tour(name)

    def _ask(self, question: str, accept: QMessageBox.StandardButton) -> bool:
        """A question that may name a tour. The name can come from a plan file, so the
        text is shown as text (``core/plain_text.py``)."""
        box = QMessageBox(QMessageBox.Icon.Question, self.tr("Camera Tour"), question,
                          accept | QMessageBox.StandardButton.Cancel, self)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        return box.exec() == accept

    def document_changed(self) -> None:
        """Another plan: the draft was a path through the old one, and so were its views.
        The new plan's own tours arrive with ``tours_changed``."""
        self._bound = None
        self._keys.clear()
        self._show_keys()
        self._orbit_start = self._held_view = None
        self._dates_chosen = False   # the year follows the new plan's date again
        if self._tour_note and self._status.text() == self._tour_note:
            self._status.setText("")   # "Saved the tour ..." was said of the old plan
        self._tour_note = ""
        self._refresh_tours()

    def showEvent(self, event: object) -> None:  # noqa: N802 - Qt's name
        """The year the plan date is in, whenever the dialog opens and the user chose none."""
        self._programmatic_close = False
        if not self._recording and not self._dates_chosen:
            year = self._capture.plan_date().year
            self._setting_dates = True
            try:
                self.date_from.setDate(QDate(year, *DEFAULT_SEASON[0]))
                self.date_to.setDate(QDate(year, *DEFAULT_SEASON[1]))
            finally:
                self._setting_dates = False
        self._refresh_tours()
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
            self._run(Mp4Writer(path, self._size(), spec.fps, self,
                                quality=str(self.quality_combo.currentData())), self._size())

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
        self._finishing = False
        self._run_started_at = monotonic()
        self._sink_kind = ("preview" if isinstance(writer, NullWriter)
                           else "mp4" if isinstance(writer, Mp4Writer) else "png")
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
        current = self._thumbnail.pixmap()
        if current is None or current.isNull():
            self._height_without_frame = self.sizeHint().height()
        pixmap = QPixmap.fromImage(image)
        height = self._frame_height(pixmap.height())
        if 0 < height < pixmap.height():
            pixmap = pixmap.scaledToHeight(height, Qt.TransformationMode.SmoothTransformation)
        self._thumbnail.setPixmap(pixmap)
        if self._recording:
            self._status.setText(self.tr("Frame {done} of {total}").format(done=done, total=total))

    def _frame_height(self, frame_height: int) -> int:
        """How tall a run's frame is shown here: whole where the screen has room, smaller
        on a short screen, so the buttons below it stay on the screen (#796)."""
        screen = self.screen()
        if screen is None:
            return frame_height
        room = (screen.availableGeometry().height() - self._height_without_frame
                - _FRAME_CHROME_PX)
        return max(_MIN_FRAME_PX, min(frame_height, room))

    def _drop_frame(self) -> None:
        """A finished run's last frame goes: the window is as tall as it was before."""
        current = self._thumbnail.pixmap()
        if current is None or current.isNull():
            return
        self._thumbnail.clear()
        layout = self.layout()
        if layout is not None:
            layout.activate()
        self.resize(self.width(), self.sizeHint().height())

    def _refusal(self, code: str) -> str:
        """Why no tour can start, in the user's language (``workspace_capture.BLOCKERS``)."""
        return {
            "not_open": self.tr("Open the 3D view first: switch to 3D or Split."),
            "recording": self.tr("A recording is already running."),
            "unavailable": self.tr("3D is not available on this computer."),
        }.get(code, self.tr("The 3D view is still building. Try again in a moment."))

    def _on_finishing(self) -> None:
        self._finishing = True
        self.cancel_button.setEnabled(False)
        if self._recording:
            self._status.setText(self.tr("Finishing the file…"))

    def _on_paused(self, paused: bool) -> None:
        if paused:
            self._status.setText(self.tr(
                "Waiting: the 3D view is not visible. The recording goes on when it is back."))
            return
        # Back: the wait is over, so the wait's sentence must go. Only a running
        # recording has a status of its own (its frame count); a preview has none.
        if self._recorder is None or self._finishing:
            return
        self._status.setText(self.tr("Rendering…") if self._recording else "")

    def _cancel(self) -> None:
        if self._recorder is not None and self._recorder.cancel():
            self.cancel_button.setEnabled(False)
            self._status.setText(self.tr("Stopping…"))

    def _on_finished(self, result: TourResult) -> None:
        recording = self._recording
        programmatic = self._programmatic_close
        self._recorder = None
        self._recording = False
        self._finishing = False
        self._run_started_at = None
        self._programmatic_close = False
        self._progress.hide()
        self.cancel_button.hide()
        self.cancel_button.setEnabled(True)
        self.close_button.setEnabled(True)
        if self._modal:
            self._modal = False
            self.hide()
            self.setWindowModality(Qt.WindowModality.NonModal)
            if not programmatic:   # a shutdown hid it: do not flash it back
                self.show()
        self._status.setText(self._say(result, recording))
        self._sync_controls()
        self._drop_frame()
        closing, self._close_when_stopped = self._close_when_stopped, False
        if closing and (result.cancelled or result.ok or programmatic):
            self.close()   # a programmatic teardown cannot wait for a failure's reason

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

    def _confirm_discard(self) -> bool:
        """True when a running recording may be thrown away.

        Esc or X used to discard an MP4 at once, however long it had been rendering
        (issue #731). A short run is not worth a question; a long one is. A programmatic
        close (the engine is going) cannot ask; a file already being closed cannot be
        stopped; and a PNG sequence's written frames stay, so its question says that."""
        if (self._programmatic_close or not self._recording or self._recorder is None
                or not self._recorder.running):
            return True
        elapsed = monotonic() - self._run_started_at if self._run_started_at else 0.0
        if elapsed < ASK_DISCARD_AFTER_S:
            return True
        if self._sink_kind == "png":
            question = self.tr(
                "Stop the render? The frames already written to {path} stay.").format(
                    path=self._output)
            stop = QMessageBox.StandardButton.Yes
        else:
            question = self.tr(
                "Stop the recording? It has been running for {seconds:.0f} s, and the "
                "video is not saved yet.").format(seconds=elapsed)
            stop = QMessageBox.StandardButton.Discard
        answer = QMessageBox.question(
            self, self.tr("Camera Tour"), question,
            stop | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        return answer == stop

    def close_for_shutdown(self) -> None:
        """The engine is going: close without asking, and stop what this dialog started."""
        self._programmatic_close = True
        self.close()

    def reject(self) -> None:
        """Esc: a running preview or recording stops, and the dialog stays to say how that
        ended. Hiding it would leave a modal recording running behind nothing at all."""
        if self._recorder is not None:
            if not self._confirm_discard():
                return
            self._cancel()
            return
        super().reject()

    def closeEvent(self, event: QCloseEvent | None) -> None:  # noqa: N802 - Qt's name
        """A running preview or recording stops first, and then the dialog closes."""
        if self._recorder is not None:
            if not self._confirm_discard():
                if event is not None:
                    event.ignore()
                return
            self._close_when_stopped = True
            self._cancel()
            if event is not None:
                event.ignore()
            return
        super().closeEvent(event)
        if event is None or event.isAccepted():
            self.closed.emit()
