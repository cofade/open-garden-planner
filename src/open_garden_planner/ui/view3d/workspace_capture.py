"""Director's cut of the 3D workspace: photo mode, camera tours, pictures for an agent
(Phase 17 L6, #390, ADR-072).

All three take their pictures the same way — ``Quick3DHost.capture``, the scene's second
View3D — so a photo, a frame of a video and an agent's picture cannot disagree, and none of
them moves anything the user is looking at. This module decides WHEN a picture may be
taken and what happens to it; ``core/camera_path.py`` knows where a tour goes,
``tour_recorder.py`` how it is rendered, ``video_writer.py`` where its frames go and
``tour_dialog.py`` how the user asks for one.

These are the workspace's only frames besides a click and a growth jump (ADR-060 decision
17, addendum L6): each is someone's own action — the "Save Photo" button, a tour the user
started, an agent's request — and none is taken by a timer of the view's steady state. A
frame of a tour IS paced by a timer, one the user started and can stop.

Photo mode changes how pictures are developed, never what stands in the garden
(``core/scene3d/photo.py``). While it is on, a click in the view sets the focus instead of
selecting: the click is the camera's, and selection has its 2D side.

A tour can be kept in the plan under a name (issue #737, ``core/camera_tours.py``). The plan
owns the list (``ProjectManager.camera_tours``); this coordinator is the dialog's way to it,
and every edit it makes is ONE command on the undo stack (``connect_tours``).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime
from datetime import time as day_time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from PyQt6.QtCore import QBuffer, QCoreApplication, QIODevice, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QImage
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QToolButton,
    QWidget,
)

from open_garden_planner.core.camera_path import (
    CameraKey,
    HeldCamera,
    TourFrame,
    TourSpec,
    path_eyes,
)
from open_garden_planner.core.camera_tours import SavedTour
from open_garden_planner.core.commands import (
    DeleteCameraTourCommand,
    RenameCameraTourCommand,
    SaveCameraTourCommand,
)
from open_garden_planner.core.plain_text import log_text
from open_garden_planner.core.scene3d.photo import (
    DEFAULT_BLUR,
    EXPOSURE_EV_RANGE,
    GRADES,
    NO_GRADE,
    NO_PHOTO,
    PhotoSettings,
)

if TYPE_CHECKING:
    from .tour_dialog import TourDialog
    from .tour_recorder import TourRecorder, TourResult
    from .video_writer import FrameSink

__all__ = ["BLOCKERS", "PHOTO_SIZES", "CaptureRefused", "WorkspaceCaptureCoordinator",
           "grade_names", "photo_size"]

_LOG: Final = logging.getLogger(__name__)

#: What a photo can be saved at, by key. ``window``: what the view shows, in device pixels.
PHOTO_SIZES: Final = {"window": None, "1080p": (1920, 1080), "1440p": (2560, 1440),
                      "4k": (3840, 2160)}
#: Why no picture can be taken now — ``capture_blocker``'s answers, and their sentences for
#: an agent (English: the MCP surface's language, ADR-034).
BLOCKERS: Final = {
    "not_open": "The 3D view is not open, so there is nothing to render. Ask the user to "
                "switch to 3D or Split (View > Workspace), then call this again. Nothing was "
                "changed.",
    "warming_up": "The 3D view is still warming up (building the plan, its plants or its "
                  "ground). Call this again in a few seconds. Nothing was changed.",
    "recording": "The user is recording a camera tour in the 3D view: the plan's date and "
                 "time are moving. Call this again when it is finished. Nothing was changed.",
    "unavailable": "3D is not available on this computer (no graphics device, or the view "
                   "could not start). Nothing was changed.",
}
_SLIDER_STEPS: Final = 100
_EV_STEPS_PER_STOP: Final = 10


def _tr(text: str) -> str:
    return QCoreApplication.translate("Workspace", text)


def _point(values: Any) -> tuple[float, float, float]:
    east, north, up = values
    return (float(east), float(north), float(up))


def grade_names() -> dict[str, str]:
    """``photo.GRADES`` as the combo names them (translated)."""
    return {NO_GRADE: _tr("No Grade"), "golden": _tr("Golden Hour"), "crisp": _tr("Crisp Day"),
            "cool": _tr("Cool Morning"), "film": _tr("Soft Film"), "mono": _tr("Black and White")}


def photo_size_names() -> dict[str, str]:
    return {"window": _tr("View Size"), "1080p": _tr("Full HD (1920 x 1080)"),
            "1440p": _tr("QHD (2560 x 1440)"), "4k": _tr("4K (3840 x 2160)")}


def photo_size(key: str, view_size: tuple[float, float], ratio: float) -> tuple[int, int]:
    """The picture a size key means: for ``window`` what the view shows in device pixels."""
    size = PHOTO_SIZES[key]
    if size is not None:
        return size
    return (max(16, round(view_size[0] * ratio)), max(16, round(view_size[1] * ratio)))


class CaptureRefused(RuntimeError):
    """No picture can be taken now. ``code``: a key of ``BLOCKERS``; the text is that
    sentence, ready for an agent."""

    def __init__(self, code: str) -> None:
        super().__init__(BLOCKERS[code])
        self.code = code


class WorkspaceCaptureCoordinator(QObject):
    """Photo mode, the tours and the agent's pictures (module docstring)."""

    #: A tour is about to drive the sim clock: whoever else plays it must stop.
    clock_wanted = pyqtSignal()
    #: Photo mode went on or off.
    photo_mode_changed = pyqtSignal(bool)
    #: The plan's saved tours changed: one was saved, renamed or deleted, an undo or a
    #: redo put the list back, or another plan came with its own.
    tours_changed = pyqtSignal()

    def __init__(self, get_host: Callable[[], Any], get_controller: Callable[[], Any],
                 get_look: Callable[[], Any], get_clock: Callable[[], Any],
                 get_camera: Callable[[], Any], get_camera_now: Callable[[], tuple[Any, Any, float]],
                 forge_pending: Callable[[], int], is_pane_showing: Callable[[], bool],
                 view_state: Callable[[], str], ground_point: Callable[[float, float], Any],
                 default_path: Callable[[str], str], fly_path: Callable[[Any], None],
                 is_walking: Callable[[], bool], parent: QWidget,
                 aim_lamps: Callable[[Any], None] | None = None) -> None:
        super().__init__(parent)
        self._get_host = get_host
        self._get_controller = get_controller
        self._get_look = get_look
        self._get_clock = get_clock
        self._get_camera = get_camera
        self._get_camera_now = get_camera_now
        self._forge_pending = forge_pending
        self._is_pane_showing = is_pane_showing
        self._view_state = view_state
        self._ground_point = ground_point
        self._is_walking = is_walking
        self.default_path = default_path
        self._fly_path = fly_path
        #: The garden lights that light follow a picture's own camera target (#687;
        #: ``WorkspaceLivingCoordinator.aim_lamps``); None gives the view's back.
        self._aim_lamps: Callable[[Any], None] = aim_lamps or (lambda _target: None)
        self._parent = parent
        self._settings: PhotoSettings = NO_PHOTO
        self._photo_on = False
        self._focus_pending = False
        self._recorder: TourRecorder | None = None
        self._clock_hold: datetime | None = None
        self._tour_holds_utc = False
        self._tour_utc_time: day_time | None = None
        self._tour_size: tuple[int, int] = (16, 16)
        self._tour_still = False   # a held camera's tour fits its shadows (#734)
        self._dialog: TourDialog | None = None
        #: Where the plan's saved tours live (a ``ProjectManager``) and the undo stack
        #: their edits go through (``connect_tours``). None: tours cannot be kept.
        self._tour_plan: Any = None
        self._tour_commands: Any = None
        #: A dialog whose engine stopped while its file was still closing. It is not the
        #: session's any more; it is forgotten when it really closes.
        self._dialog_closing: TourDialog | None = None
        #: The engine is there: the Tour action follows it and the closing-dialog latch.
        self._engine_enabled = False
        self._row: QWidget | None = None
        self._size_combo: QComboBox | None = None
        self._grade_combo: QComboBox | None = None
        self._exposure: QSlider | None = None
        self._vignette: QSlider | None = None
        self._blur: QSlider | None = None
        self._focus_label: QLabel | None = None
        self._button: QToolButton | None = None
        self.photo_action = QAction(_tr("P&hoto Mode"), parent)
        self.photo_action.setCheckable(True)
        self.photo_action.setEnabled(False)
        self.photo_action.setStatusTip(_tr("Develop the view like a photo and save it, up to 4K"))
        self.photo_action.setToolTip(_tr(
            "Exposure, colour grade, vignette and a click to set the focus. Changes how the "
            "picture looks, never what stands in the garden."))
        self.photo_action.triggered.connect(lambda checked=False: self.set_photo_mode(bool(checked)))
        self.tour_action = QAction(_tr("Camera &Tour..."), parent)
        self.tour_action.setEnabled(False)
        self.tour_action.setStatusTip(_tr(
            "Fly a camera through the garden and save it as a video or a PNG sequence"))
        self.tour_action.triggered.connect(self.open_tour_dialog)

    # ── the controls ─────────────────────────────────────────────────────────

    def build_controls(self, strip: QWidget, layout: Any) -> QToolButton:
        """The "Capture" button with its menu, added to the 3D pane's strip."""
        button = QToolButton(strip)
        button.setText(_tr("Capture"))
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setProperty("menuChevron", True)   # its arrow beside the text (ui/theme.py)
        menu = QMenu(button)
        menu.addAction(self.photo_action)
        menu.addAction(self.tour_action)
        button.setMenu(menu)
        layout.addWidget(button)
        self._button = button
        return button

    def build_photo_row(self, parent: QWidget, layout: Any) -> QWidget:
        """Photo mode's controls: one more line of the pane's notices, hidden until it is on
        (nothing overlays the 3D view, ADR-060)."""
        row = QWidget(parent)
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)

        def slider(name: str, low: int, high: int, value: int, tip: str) -> QSlider:
            label = QLabel(name, row)
            label.setTextFormat(Qt.TextFormat.PlainText)
            line.addWidget(label)
            widget = QSlider(Qt.Orientation.Horizontal, row)
            widget.setRange(low, high)
            widget.setValue(value)
            widget.setFixedWidth(90)
            widget.setToolTip(tip)
            widget.valueChanged.connect(self._on_controls_changed)
            line.addWidget(widget)
            return widget

        low_ev, high_ev = EXPOSURE_EV_RANGE
        self._exposure = slider(_tr("Exposure"), round(low_ev * _EV_STEPS_PER_STOP),
                                round(high_ev * _EV_STEPS_PER_STOP), 0,
                                _tr("Brighter or darker, in photographers' stops"))
        self._vignette = slider(_tr("Vignette"), 0, _SLIDER_STEPS, 0,
                                _tr("Darken the corners of the picture"))
        self._blur = slider(_tr("Blur"), 0, _SLIDER_STEPS, 0,
                            _tr("How far out of focus everything else goes. Click the view to "
                                "choose what stays sharp."))
        grade = QComboBox(row)
        names = grade_names()
        for key in GRADES:
            grade.addItem(names[key], key)
        grade.setToolTip(_tr("A colour grade for the whole picture"))
        grade.currentIndexChanged.connect(self._on_controls_changed)
        line.addWidget(grade)
        self._grade_combo = grade
        focus = QLabel(_tr("Click the view to set the focus"), row)
        focus.setTextFormat(Qt.TextFormat.PlainText)
        line.addWidget(focus)
        self._focus_label = focus
        line.addStretch(1)
        size = QComboBox(row)
        sizes = photo_size_names()
        for key in PHOTO_SIZES:
            size.addItem(sizes[key], key)
        size.setCurrentIndex(size.findData("4k"))
        size.setToolTip(_tr("The size of the saved picture. The other sizes keep the view's "
                            "height in the picture and show more or less at the sides."))
        line.addWidget(size)
        self._size_combo = size
        save = QPushButton(_tr("Save Photo..."), row)
        save.clicked.connect(self.save_photo)
        line.addWidget(save)
        row.hide()
        layout.addWidget(row)
        self._row = row
        return row

    def set_enabled(self, enabled: bool) -> None:
        """The engine is there (or gone): the actions follow."""
        # if the settings wait for the new plan's framing, they must not outlive the engine
        self._focus_pending = False
        self._engine_enabled = bool(enabled)
        self.photo_action.setEnabled(enabled)
        self.tour_action.setEnabled(enabled and self._dialog_closing is None)
        if not enabled:
            self.cancel_recording()
            self.set_photo_mode(False)
            dialog = self._dialog
            if dialog is not None:
                # A dialog the user closed stays for the session (an unsaved tour lives in it);
                # one the engine stops is the old engine's and is forgotten when it has
                # really closed. Otherwise a Tour action could open a twin beside it.
                dialog.close_for_shutdown()
                still_open = dialog.isVisible()
                dialog.hide()
                self._dialog = None
                if still_open:
                    self._dialog_closing = dialog

    def document_changed(self) -> None:
        """Another plan: a recording stops, and the focused point was a point of the old one.

        The new plan's camera is not framed until its first pass reaches the engine, so the
        focus is not re-established here. ``document_shown`` does that, once the camera is in
        place; until then the view is the view, and the label says what is happening."""
        self.cancel_recording()
        if self._dialog is not None:
            self._dialog.document_changed()   # #737: its draft was a path through the old plan
        if self._photo_on or self._settings.focus_scene is not None:
            self._settings = replace(self._settings, focus_scene=None)
            self._focus_pending = True
            if self._photo_on:
                self._apply(NO_PHOTO)
            self._say_focus()

    def document_shown(self) -> None:
        """The new document's first pass is in the engine and its camera is framed: give the
        blur kept from the old plan the point of the new one (or keep no point with no blur)."""
        if not self._focus_pending:
            return
        self._focus_pending = False
        self.set_settings(self._settings)
        self._say_focus()   # with photo mode off the label was still the pending sentence

    # ── photo mode ───────────────────────────────────────────────────────────

    @property
    def photo_mode(self) -> bool:
        return self._photo_on

    @property
    def photo_row_open(self) -> bool:
        """Its controls have a line of the pane's notices (``_refresh_notices``)."""
        return self._row is not None and not self._row.isHidden()

    @property
    def settings(self) -> PhotoSettings:
        """The photo settings the controls say."""
        return self._settings

    def set_photo_mode(self, on: bool) -> None:
        """Turn photo mode on or off. Off, the view is the view again; the settings wait
        for the next time, except the focused point, which was only true of this view."""
        on = bool(on)
        self.photo_action.setChecked(on)
        if on == self._photo_on:
            return
        self._photo_on = on
        if self._row is not None:
            self._row.setVisible(on)
        if not on:
            self._settings = replace(self._settings, focus_scene=None)
            self._say_focus()
            self._apply(NO_PHOTO)
        else:
            self.set_settings(self._settings)   # the blur kept from last time gets a point again
        self.photo_mode_changed.emit(on)

    def set_settings(self, settings: PhotoSettings) -> None:
        """What the controls do; a test's way in.

        THE one place the invariant "blur above 0 in photo mode implies a focused point"
        is enforced: ``_on_controls_changed``, ``set_photo_mode``, ``_focus_on`` and the
        new plan's ``document_shown`` all come through here. Without a point Qt has no
        depth to measure from, so the blur slider did nothing until the view was clicked
        (manual test of #390).

        While a new plan's framing is pending, settings are stored and applied later:
        focusing them on the old camera now would pin the blur to the plan that is going
        away."""
        self._settings = settings
        self._sync_blur_slider(settings.blur)
        if self._focus_pending:
            return
        if self._photo_on:
            settings = self._with_a_focus(settings)
            self._settings = settings
            self._apply(settings)
            self._say_focus()

    def _sync_blur_slider(self, blur: float) -> None:
        """The slider says what the settings say, when one changed the other."""
        slider = self._blur
        if slider is None:
            return
        value = round(blur * _SLIDER_STEPS)
        if slider.value() == value:
            return
        slider.blockSignals(True)
        slider.setValue(value)
        slider.blockSignals(False)

    def _apply(self, settings: PhotoSettings) -> None:
        host = self._get_host()
        if host is None:
            return
        try:
            host.set_photo(settings)
        except Exception as error:  # noqa: BLE001 - a dead engine must not take the app down
            _LOG.error("Photo mode: the engine refused the settings (%s: %s)",
                       type(error).__name__, log_text(error))

    def _on_controls_changed(self, *_arguments: object) -> None:
        if self._exposure is None or self._vignette is None or self._blur is None:
            return
        grade = self._grade_combo.currentData() if self._grade_combo is not None else NO_GRADE
        settings = replace(
            self._settings,
            exposure_ev=self._exposure.value() / _EV_STEPS_PER_STOP,
            vignette=self._vignette.value() / _SLIDER_STEPS,
            blur=self._blur.value() / _SLIDER_STEPS,
            grade=str(grade or NO_GRADE))
        self.set_settings(settings)   # it adds the focus a blur needs, applies it and says so

    def _with_a_focus(self, settings: PhotoSettings) -> PhotoSettings:
        """``settings``, with a point in focus if there is blur and none was picked.

        Walking aims 100 cm ahead of the eye, into mid-air (``walk.py``
        ``LOOK_DISTANCE_CM``): that point is behind the walker after a few steps, so the
        ground point under the view's centre is used instead. A camera that cannot answer
        at all gives up the blur rather than a setting that cannot be applied."""
        if settings.blur <= 0.0 or settings.focus_scene is not None:
            return settings
        point = self._focus_default()
        if point is None:
            return replace(settings, blur=0.0)
        return replace(settings, focus_scene=point)

    def _focus_default(self) -> tuple[float, float, float] | None:
        """Where a blur focuses when nothing was clicked: the ground under the walker, or
        what the camera looks at."""
        if self._is_walking():
            host = self._get_host()
            size = host.view_size() if host is not None else None
            if size is not None:
                ground = self._ground_point(size[0] / 2.0, size[1] / 2.0)
                if ground is not None:
                    return (float(ground[0]), float(ground[1]), 0.0)
        target = self._get_camera_now()[1]
        return _point(target)

    def _say_focus(self) -> None:
        label = self._focus_label
        if label is None:
            return
        if self._focus_pending:
            label.setText(_tr("The focus moves to the new plan when it is shown"))
            return
        point = self._settings.focus_scene
        if point is None:
            label.setText(_tr("Click the view to set the focus"))
            return
        eye = self._get_camera_now()[0]
        label.setText(_tr("Focus {distance:.1f} m away").format(
            distance=math.dist(eye, point) / 100.0))

    def take_click(self, hit: object) -> bool:
        """A click in the view (``OrbitInput.picked``): photo mode takes it for the focus.
        A miss (the ground, the sky) is for ``take_ground_click``. True: it was ours."""
        if not self._photo_on:
            return False
        point = getattr(hit, "point", None)
        if point is not None:
            self._focus_on(_point(point))
        return True

    def take_ground_click(self, x: float, y: float) -> bool:
        """A click that hit no item: the point on the ground under it, if the ray meets the
        ground at all (the sky does not)."""
        if not self._photo_on:
            return False
        point = self._ground_point(x, y)
        if point is not None:
            self._focus_on((float(point[0]), float(point[1]), 0.0))
        return True

    def _focus_on(self, point: tuple[float, float, float]) -> None:
        self._focus_pending = False   # a click is the user's own point, valid now
        settings = replace(self._settings, focus_scene=point)
        if settings.blur <= 0.0 and self._blur is not None:
            # a focus with nothing out of focus would do nothing: give it a blur to start with
            settings = replace(settings, blur=DEFAULT_BLUR)
            self._settings = settings
            self._blur.blockSignals(True)
            self._blur.setValue(round(DEFAULT_BLUR * _SLIDER_STEPS))
            self._blur.blockSignals(False)
        self.set_settings(settings)
        self._say_focus()

    def save_photo(self) -> None:
        """The "Save Photo" button: ask where, render, save. Says what went wrong."""
        from .quick3d.lifecycle import HostStateError

        host = self._get_host()
        if host is None:
            return
        name = "garden-photo.png"
        path, _ = QFileDialog.getSaveFileName(
            self._parent, _tr("Save Photo"), self.default_path(name),
            _tr("PNG image (*.png);;JPEG image (*.jpg)"))
        if not path:
            return
        key = str(self._size_combo.currentData()) if self._size_combo is not None else "4k"
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            saved = self.write_photo(Path(path), key)
        except (HostStateError, CaptureRefused):
            self._warn(_tr("The 3D view is not visible right now. Bring it back and try again."))
            return
        except Exception as error:  # noqa: BLE001 - a failed picture must not take the app down
            _LOG.error("Photo mode: the picture failed (%s: %s)", type(error).__name__,
                       log_text(error))
            self._warn(_tr("The picture could not be made: {error}").format(error=error))
            return
        finally:
            QApplication.restoreOverrideCursor()
        if not saved:
            self._warn(_tr("The picture could not be saved to {path}.").format(path=path))

    def write_photo(self, path: Path, size_key: str = "4k") -> bool:
        """Render the view at a size key and write it; False when the file could not be
        written. ``HostStateError`` when no frame can be had right now, ``CaptureRefused``
        when there is no view."""
        host = self._get_host()
        if host is None:
            raise CaptureRefused("not_open")
        ratio = float(host.device_pixel_ratio())
        size = photo_size(size_key, host.view_size(), ratio)
        # #734: a photo's camera holds still, so its shadow map is fitted to the casters
        image = host.capture(size, label="photo", fitted_shadows=True)
        self._describe(image)
        return bool(image.save(str(path)))

    def _describe(self, image: QImage) -> None:
        """What the picture shows, inside the file: the plan's date is a claim (truth gate
        "Date"), and a photo leaves the app without the app around it."""
        clock = self._get_clock()
        image.setText("Software", "Open Garden Planner")
        if clock is not None:
            image.setText("Creation Time", clock.wall.isoformat(timespec="minutes"))

    def _warn(self, text: str) -> None:
        QMessageBox.warning(self._parent, _tr("Capture"), text)

    # ── camera tours ─────────────────────────────────────────────────────────

    def open_tour_dialog(self) -> None:
        if self._dialog_closing is not None:
            return   # the engine stopped; that dialog is closing its file, not a session
        if self._dialog is None:
            from .tour_dialog import TourDialog

            self._dialog = TourDialog(self, self._parent)
            dialog = self._dialog
            dialog.closed.connect(lambda dialog=dialog: self._on_dialog_closed(dialog))
        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()

    def _on_dialog_closed(self, dialog: Any) -> None:
        """The engine stopped this dialog: forget it once it has really closed. A dialog the
        user closed is kept - a tour that was not saved in the plan lives in the dialog."""
        if self._dialog_closing is dialog:
            self._dialog_closing = None
            if self._engine_enabled:
                self.tour_action.setEnabled(True)

    @property
    def dialog(self) -> TourDialog | None:
        return self._dialog

    # ── tours kept in the plan (#737) ────────────────────────────────────────

    def connect_tours(self, project_manager: Any, command_manager: Any) -> None:
        """Where the plan keeps its tours, and the undo stack every edit of them goes
        through. Without this call the dialog offers no saved tours."""
        self._tour_plan, self._tour_commands = project_manager, command_manager
        project_manager.camera_tours_changed.connect(self._on_plan_tours_changed)

    def _on_plan_tours_changed(self, _tours: object) -> None:
        self.tours_changed.emit()

    @property
    def tours_connected(self) -> bool:
        return self._tour_plan is not None and self._tour_commands is not None

    def saved_tours(self) -> tuple[SavedTour, ...]:
        """The plan's saved tours, in the order they were saved."""
        if self._tour_plan is None:
            return ()
        tours: tuple[SavedTour, ...] = self._tour_plan.camera_tours
        return tours

    def save_tour(self, tour: SavedTour) -> None:
        """Keep ``tour`` in the plan, in place of one of its name if there is one. One
        undo step."""
        self._tour_commands.execute(SaveCameraTourCommand(self._tour_plan, tour))

    def rename_tour(self, name: str, new_name: str) -> None:
        """One undo step. ``ValueError``: no such tour, or the new name is taken."""
        self._tour_commands.execute(RenameCameraTourCommand(self._tour_plan, name, new_name))

    def delete_tour(self, name: str) -> None:
        """One undo step. ``ValueError``: no such tour."""
        self._tour_commands.execute(DeleteCameraTourCommand(self._tour_plan, name))

    @property
    def recording(self) -> bool:
        return self._recorder is not None

    def camera_key(self) -> CameraKey:
        """The view's camera as a tour's key (walking: the walker's eye)."""
        eye, target, fov = self._get_camera_now()
        return CameraKey(_point(eye), _point(target), float(fov))

    def orbit_pose(self) -> Any:
        """Where a drone orbit starts: the orbit camera's own pose."""
        camera = self._get_camera()
        return camera.pose

    def plan_date(self) -> date:
        clock = self._get_clock()
        return clock.plan_date if clock is not None else date.today()

    def reduced_motion(self) -> bool:
        """Whether the look asks for reduced motion (the system setting or Preferences)."""
        look = self._get_look()
        return bool(look is not None and look.reduced_motion)

    def owner_plan_date(self) -> date | None:
        """The plan date an agent must see while a tour is moving the clock: the owner's,
        not the frame's."""
        moment = self._clock_hold
        return moment.date() if moment is not None else None

    def start_tour(self, spec: TourSpec, size: tuple[int, int], writer: FrameSink, *,
                   realtime: bool = False) -> TourRecorder:
        """Render ``spec`` at ``size`` into ``writer``. The caller connects the recorder's
        signals before the first frame, which comes with the next pass of the event loop.
        ``CaptureRefused`` when no picture can be taken now; ``VideoError`` when the writer
        cannot start: nothing moved then."""
        blocker = self.capture_blocker()
        if blocker is not None:
            raise CaptureRefused(blocker)
        host, clock, look = self._get_host(), self._get_clock(), self._get_look()
        from .tour_recorder import TourRecorder

        self._tour_size = size
        # #734: a held camera's frames (a time-lapse) fit the shadow map like a picture; a
        # moving camera's keep the view's stable fit — a fitted map would crawl with it
        self._tour_still = isinstance(spec.motion, HeldCamera)
        recorder = TourRecorder(spec, writer, self._tour_frame, self._tour_clock,
                                self._tour_settled, realtime=realtime,
                                view_showing=self._is_pane_showing, parent=self)
        recorder.start()   # raises before anything moved
        host.begin_captures()
        self.clock_wanted.emit()
        # ONE hold, and only a tour that moves the clock takes it (issue #730). A tour
        # with no date and no time range is a flight: it never writes the clock, so it
        # must never put a snapshot back over a change the owner made meanwhile.
        self._clock_hold = None
        self._tour_utc_time = None
        self._tour_holds_utc = spec.date_range is not None and spec.time_range is None
        if spec.date_range is not None or spec.time_range is not None:
            self._clock_hold = clock.wall if clock is not None else None
        if look is not None:
            look.hold_preset(True)   # a recording view presents little: not a slow machine
        recorder.finished.connect(self._on_tour_finished)
        self._recorder = recorder
        if not realtime:   # a preview shows how the tour moves, and does not wait for leaves
            self._fly_path(path_eyes(spec))
        return recorder

    def _tour_frame(self, frame: TourFrame) -> QImage:
        """A tour's picture of one frame: from the frame's camera, on the frame's wind."""
        from .quick3d.shots import PerspectiveShot

        key = frame.key
        self._aim_lamps(key.target)   # its lamps, not the view's (#687)
        image: QImage = self._get_host().capture(
            self._tour_size, PerspectiveShot(key.eye, key.target, key.fov_deg),
            wind_time_s=frame.wind_time_s, label=f"tour{frame.index}",
            fitted_shadows=self._tour_still)
        return image

    def _tour_clock(self, day: date | None, moment: day_time | None) -> None:
        """Move the clock for one frame.

        A tour that sweeps the year holds the UTC time, not the wall time (issue #732).
        The sun is computed from ``SimClock.utc``: holding the wall time across a DST
        change moves the sun by an hour, which read as a 24-level brightness step in the
        video. The wall reading is still what is written (ADR-053: user-facing writers
        hand wall readings); it is derived through the zone from the held UTC instant by
        ``SimClock.set_utc_time_on``, so the repeated autumn hour's ``fold`` is right; a
        local date with no exact instant gets the nearest reading on that date, at most a
        minute away, so the date range the dialog promised holds."""
        clock = self._get_clock()
        if clock is None:
            return
        if day is not None:
            clock.set_date(day)
            if self._tour_holds_utc:
                if self._tour_utc_time is None:
                    # The first frame shows the date the dialog says at the time the owner's
                    # clock had; THAT instant is what the rest of the year holds.
                    self._tour_utc_time = clock.utc.time()
                else:
                    clock.set_utc_time_on(day, self._tour_utc_time)
        if moment is not None:
            clock.set_time_of_day(moment)

    def _tour_settled(self) -> bool:
        """Everything that follows from the frame's date and time has happened."""
        controller = self._get_controller()
        if controller is None:
            return True
        if not controller.idle or controller.capturing or self._forge_pending() > 0:
            return False
        look = self._get_look()
        if look is not None:
            look.settle_sky()   # the sky of this very moment, not of when the sun rests
        return True

    def cancel_recording(self) -> None:
        if self._recorder is not None:
            self._recorder.cancel()

    def _on_tour_finished(self, result: TourResult) -> None:
        recorder, self._recorder = self._recorder, None
        if recorder is not None:
            recorder.deleteLater()
        moment = self._clock_hold
        self._tour_utc_time = None
        self._tour_holds_utc = False
        try:
            try:
                self._aim_lamps(None)   # the view's own lamps again (#687)
                self._fly_path(None)
                host = self._get_host()
                if host is not None:
                    host.end_captures()   # its render targets go; a 4K tour holds about 600 MB
            except Exception as error:  # noqa: BLE001 - a dead engine must not keep the owner's clock
                _LOG.error("Camera tour: could not let go of the engine (%s: %s)",
                           type(error).__name__, log_text(error))
            clock = self._get_clock()
            if clock is not None and moment is not None:
                clock.set_datetime(moment)   # the owner's date and time, as they were
        except Exception as error:  # noqa: BLE001 - one listener must not skip the rest
            _LOG.error("Camera tour: could not put the clock back (%s: %s)",
                       type(error).__name__, log_text(error))
        finally:
            self._clock_hold = None   # only after the clock is the owner's again
            look = self._get_look()
            if look is not None:
                look.hold_preset(False)
        _LOG.info("Camera tour: ok=%s cancelled=%s frames=%d unsettled=%d", result.ok,
                  result.cancelled, result.frames, result.unsettled)

    def shutdown(self, timeout_s: float = 2.5) -> None:
        """The window is closing: end a recording and wait for its file to close.

        ``closeEvent`` runs while Qt's event loop can still deliver the writer's finish,
        so a bounded nested loop here is what turns "the app went away" into a closed
        file instead of a ``.part.mp4`` left beside the user's video (issue #731). If the
        encoder does not close in time, the path is reported: the file may stay, and the
        user is told where."""
        recorder = self._recorder
        if recorder is None:
            return
        from PyQt6.QtCore import QEventLoop, QTimer

        # A modal dialog would sit in front of the close and could not be answered.
        dialog, self._dialog = self._dialog, None
        self._dialog_closing = None
        if dialog is not None:
            dialog.close_for_shutdown()
            dialog.hide()   # a visible modal dialog would sit under the warning below
        recorder.abort_now()
        if self._recorder is None:   # a preview's writer finished synchronously
            return
        loop = QEventLoop()
        recorder.finished.connect(lambda _result: loop.quit())
        limit = QTimer(loop)
        limit.setSingleShot(True)
        limit.timeout.connect(loop.quit)
        limit.start(max(1, int(timeout_s * 1000.0)))
        loop.exec()
        if self._recorder is not None:
            path = recorder.output_path()
            _LOG.warning("Camera tour: the file had not closed when the window went; "
                         "its unfinished output may stay at %s", path)
            QMessageBox.warning(
                self._parent, _tr("Camera Tour"),
                _tr("The recording could not be closed before the window went. "
                    "Its unfinished output may stay at {path}.").format(path=path))

    # ── pictures for an agent ────────────────────────────────────────────────

    def capture_blocker(self) -> str | None:
        """Why no picture can be taken now — a key of ``BLOCKERS`` — or None. Never waits:
        it is what stands between an agent and a timeout."""
        state = self._view_state()
        if state in ("unavailable", "failed"):
            return "unavailable"
        host = self._get_host()
        if host is None or state == "not_started" or not self._is_pane_showing():
            return "not_open"
        if self._recorder is not None:
            return "recording"
        controller = self._get_controller()
        if (state != "running" or controller is None or not controller.idle
                or controller.capturing or self._forge_pending() > 0):
            return "warming_up"
        return None

    def agent_picture(self, size: tuple[int, int], shot: Any = None) -> dict[str, Any]:
        """A picture for an agent, as PNG bytes and what it shows (``render_3d_view``). The
        view's look without photo mode's development: an agent asks what the plan looks like.
        ``CaptureRefused`` instead of a timeout. Reads, and changes nothing."""
        from .quick3d.lifecycle import HostStateError

        blocker = self.capture_blocker()
        if blocker is not None:
            raise CaptureRefused(blocker)
        host = self._get_host()
        if shot is not None:
            self._aim_lamps(shot.target)   # its own lamps, not the view's (#687)
        try:
            image = host.capture(size, shot, photo=NO_PHOTO, label="agent",
                                 fitted_shadows=True)   # a still picture (#734)
        except HostStateError as error:   # resized or hidden a moment ago: "not now"
            _LOG.info("render_3d_view: no frame right now (%s)", log_text(error))
            raise CaptureRefused("warming_up") from error
        finally:
            if shot is not None:
                self._aim_lamps(None)
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        png = bytes(buffer.data())
        buffer.close()
        eye, target, fov = (shot.eye, shot.target, shot.fov_deg) if shot is not None else \
            self._get_camera_now()
        clock, controller, look = self._get_clock(), self._get_controller(), self._get_look()
        sun = controller.sync.sun if controller is not None else None
        return {
            "png_bytes": png,
            "image_width_px": image.width(),
            "image_height_px": image.height(),
            "eye": _point(eye),
            "target": _point(target),
            "fov_deg": float(fov),
            "plan_date": clock.plan_date.isoformat() if clock is not None else None,
            "time_of_day": clock.time_of_day.isoformat("minutes") if clock is not None else None,
            "sun_elevation_deg": float(sun.elevation_deg) if sun is not None else None,
            "sun_azimuth_deg": float(sun.azimuth_deg) if sun is not None else None,
            "weather": look.weather if look is not None else None,
            "quality_preset": look.preset if look is not None else None,
            "roofs_hidden": bool(host.scene_property("roofsHidden")),
            "overlays": [layer for layer, prop in (("shade", "shadeVisible"), ("drape", "drapeVisible"),
                                                   ("lines", "linesVisible"))
                         if host.scene_property(prop)],
        }
