"""Analysis menu and controls coordinator for the 3D workspace (Phase 17 L2, issue #583)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Final

from PyQt6.QtCore import QCoreApplication, QTimer
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import QMenu, QToolButton, QWidget

from open_garden_planner.core.measurements import format_length
from open_garden_planner.core.scene3d.drape import DRAPE_LIFT_CM
from open_garden_planner.core.scene3d.pick_oracle import perspective_ray
from open_garden_planner.ui.sun_exposure_text import sun_requirement_label

from .analysis_modes import JUMP_YEARS, DrapeMode
from .sync_controller import TickReport

if TYPE_CHECKING:
    from .analysis_controller import AnalysisController, ProbeResult
    from .growth_jump import GrowthJump
from .workspace_legend import _locale_date, _locale_number
from .workspace_protocols import EngineHost, HeatmapSource, ShadowsSource, SunHoursSource
from .workspace_wipe import WorkspaceWipeCoordinator

_LOG = logging.getLogger(__name__)



#: After the camera stops moving, the Cutaway X-ray runs (ms).
XRAY_DELAY_MS: Final = 150


class WorkspaceAnalysisCoordinator:
    """Coordinates analysis actions, drapes, solar paths, day sweeps, Cutaway, and growth jumps."""

    def __init__(
        self,
        get_host: Callable[[], EngineHost | None],
        get_controller: Callable[[], Any],
        get_clock: Callable[[], Any],
        get_location: Callable[[], Any],
        get_scene: Callable[[], Any],
        get_camera_now: Callable[[], tuple[tuple[float, float, float], tuple[float, float, float], float]],
        get_held_parts: Callable[[], Callable[[Any], tuple[Any, ...]]],
        wipe_coordinator: WorkspaceWipeCoordinator,
        update_legend: Callable[[], None],
        refresh_card: Callable[[], None],
        say_notice: Callable[[str, str], None],
        parent_widget: QWidget,
    ) -> None:
        self._get_host = get_host
        self._get_controller = get_controller
        self._get_clock = get_clock
        self._get_location = get_location
        self._get_scene = get_scene
        self._get_camera_now = get_camera_now
        self._get_held_parts = get_held_parts
        self._wipe = wipe_coordinator
        self._update_legend = update_legend
        self._refresh_card = refresh_card
        self._say = say_notice
        self._parent = parent_widget

        self._analysis: AnalysisController | None = None
        self._jump: GrowthJump | None = None
        self._shadow_source: ShadowsSource | None = None
        self._sun_heatmap: HeatmapSource | None = None
        self._sun_hours: SunHoursSource | None = None

        self._xray_timer = QTimer(parent_widget)
        self._xray_timer.setSingleShot(True)
        self._xray_timer.setInterval(XRAY_DELAY_MS)
        self._xray_timer.timeout.connect(self.run_xray)

        self._analyze_button: QToolButton | None = None
        self._drape_group = QActionGroup(parent_widget)
        self._drape_group.setExclusive(True)
        self._drape_actions: dict[DrapeMode, QAction] = {}
        self._init_actions()

    def _init_actions(self) -> None:
        for mode, text, tip in (
            (DrapeMode.NONE, QCoreApplication.translate("Workspace", "Nothing on the Ground"),
             QCoreApplication.translate("Workspace", "Show the garden in 3D without an analysis on the ground")),
            (DrapeMode.SHADOWS, QCoreApplication.translate("Workspace", "2D Shadows on the Ground"),
             QCoreApplication.translate("Workspace", "Lay the plan's 2D shadows on the 3D ground: the sun study's own answer")),
            (DrapeMode.SUN_HOURS, QCoreApplication.translate("Workspace", "Hours of Sun on the Ground"),
             QCoreApplication.translate("Workspace", "Lay the hours-of-sun map on the 3D ground; click the ground to read it")),
        ):
            action = QAction(text, self._parent)
            action.setCheckable(True)
            action.setStatusTip(tip)
            action.triggered.connect(lambda _checked=False, m=mode: self.set_drape_mode(m))
            self._drape_group.addAction(action)
            self._drape_actions[mode] = action
        self._drape_actions[DrapeMode.NONE].setChecked(True)

        self._sun_path_action = QAction(QCoreApplication.translate("Workspace", "Sun Path and Compass"), self._parent)
        self._sun_path_action.setCheckable(True)
        self._sun_path_action.setStatusTip(
            QCoreApplication.translate("Workspace", "Show where the sun goes today, at both solstices and at the equinox, and a compass")
        )
        self._sun_path_action.triggered.connect(
            lambda checked=False: self.set_sun_path_visible(bool(checked))
        )

        self._sweep_action = QAction(QCoreApplication.translate("Workspace", "Sweep the Day"), self._parent)
        self._sweep_action.setCheckable(True)
        self._sweep_action.setStatusTip(
            QCoreApplication.translate("Workspace", "Play the plan date from sunrise to sunset and watch the hours of sun add up")
        )
        self._sweep_action.triggered.connect(lambda checked=False: self.set_sweeping(bool(checked)))

        self._cutaway_action = QAction(QCoreApplication.translate("Workspace", "Cutaway"), self._parent)
        self._cutaway_action.setCheckable(True)
        self._cutaway_action.setStatusTip(
            QCoreApplication.translate("Workspace", "Take the roofs off and let what stands in front of the selection fade")
        )
        self._cutaway_action.triggered.connect(lambda checked=False: self.set_cutaway(bool(checked)))

        texts = {1: QCoreApplication.translate("Workspace", "+1 Year"), 3: QCoreApplication.translate("Workspace", "+3 Years"), 10: QCoreApplication.translate("Workspace", "+10 Years")}
        self._jump_actions: dict[int, QAction] = {}
        for years in JUMP_YEARS:
            action = QAction(texts[years], self._parent)
            action.setStatusTip(QCoreApplication.translate("Workspace", "Move the plan date forward and compare before and after"))
            action.triggered.connect(lambda _checked=False, y=years: self.jump_years(y))
            self._jump_actions[years] = action

        self._back_action = QAction(QCoreApplication.translate("Workspace", "Back to the Starting Date"), self._parent)
        self._back_action.triggered.connect(lambda _checked=False: self.growth_back())

        for action in self.analysis_actions():
            action.setEnabled(False)

    def analysis_actions(self) -> list[QAction]:
        return [
            *self._drape_actions.values(),
            self._sun_path_action,
            self._sweep_action,
            self._cutaway_action,
            *self._jump_actions.values(),
            self._back_action,
        ]

    @property
    def analysis(self) -> AnalysisController | None:
        return self._analysis

    @property
    def growth(self) -> GrowthJump | None:
        return self._jump

    @property
    def drape_actions(self) -> dict[Any, QAction]:
        return dict(self._drape_actions)

    @property
    def sun_path_action(self) -> QAction:
        return self._sun_path_action

    @property
    def sweep_action(self) -> QAction:
        return self._sweep_action

    @property
    def cutaway_action(self) -> QAction:
        return self._cutaway_action

    @property
    def jump_actions(self) -> dict[int, QAction]:
        return dict(self._jump_actions)

    @property
    def back_action(self) -> QAction:
        return self._back_action

    @property
    def shadow_source(self) -> ShadowsSource | None:
        return self._shadow_source

    @property
    def sun_heatmap(self) -> HeatmapSource | None:
        return self._sun_heatmap

    @property
    def sun_hours(self) -> SunHoursSource | None:
        return self._sun_hours

    def connect_sources(
        self,
        shadows: ShadowsSource | None = None,
        heatmap: HeatmapSource | None = None,
        sun_hours: SunHoursSource | None = None,
    ) -> None:
        self._shadow_source = shadows
        self._sun_heatmap = heatmap
        self._sun_hours = sun_hours
        if self._analysis is not None:
            self._analysis.connect_sources(shadows, heatmap, sun_hours)

    def build_controls(self, pane: Any) -> QToolButton:
        self._analyze_button = QToolButton(pane.strip)
        self._analyze_button.setText(QCoreApplication.translate("Workspace", "Analyze"))
        self._analyze_button.setToolTip(
            QCoreApplication.translate("Workspace", "Sun and shade on the ground, the sun path, a day sweep, Cutaway and growth")
        )
        self._analyze_button.setAutoRaise(True)
        self._analyze_button.setFocusPolicy(QtCoreQtNoFocus())
        self._analyze_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self._analyze_button)
        menu.addSection(QCoreApplication.translate("Workspace", "On the ground"))
        menu.addActions(list(self._drape_actions.values()))
        menu.addSeparator()
        menu.addAction(self._sun_path_action)
        menu.addAction(self._sweep_action)
        menu.addAction(self._cutaway_action)
        menu.addSection(QCoreApplication.translate("Workspace", "Growth"))
        menu.addActions(list(self._jump_actions.values()))
        menu.addAction(self._back_action)
        self._analyze_button.setMenu(menu)
        pane.strip_layout.addWidget(self._analyze_button)

        self._wipe.build_wipe(pane.body)
        pane.body.addWidget(self._wipe.wipe)
        return self._analyze_button

    def wire(self, host: EngineHost, orbit: Any, controller: Any) -> None:
        from .analysis_controller import AnalysisController
        from .compass_glyphs import cardinal_glyphs
        from .growth_jump import GrowthJump

        clock = self._get_clock()
        assert clock is not None
        analysis = AnalysisController(
            host,
            clock,
            self._get_location,
            controller.plan_size,
            glyphs=cardinal_glyphs,
            parent=self._parent,
        )
        analysis.connect_sources(self._shadow_source, self._sun_heatmap, self._sun_hours)
        analysis.changed.connect(self.sync_actions)
        analysis.probe_changed.connect(self._refresh_card)
        orbit.ground_clicked.connect(self.on_ground_clicked)

        jump = GrowthJump(clock, host, self._parent)
        jump.wipe_ready.connect(self._wipe.show_pair)
        jump.changed.connect(self.sync_actions)

        controller.applied.connect(self.on_applied)
        self._analysis, self._jump = analysis, jump

        for action in self.analysis_actions():
            action.setEnabled(True)
        self.sync_actions()

    def unwire(self) -> None:
        self._wipe.close_wipe()
        self._xray_timer.stop()
        analysis, self._analysis = self._analysis, None
        if analysis is not None:
            analysis.shutdown()
            analysis.deleteLater()
        jump, self._jump = self._jump, None
        if jump is not None:
            jump.forget()
            jump.deleteLater()
        for action in self.analysis_actions():
            action.setEnabled(False)
        self._update_legend()

    def on_document_changed(self) -> None:
        self._wipe.close_wipe()
        if self._analysis is not None:
            self._analysis.document_changed()
        if self._jump is not None:
            self._jump.forget()

    def sync_actions(self) -> None:
        analysis, jump = self._analysis, self._jump
        if analysis is not None:
            self._drape_actions[analysis.drape_mode].setChecked(True)
            self._sun_path_action.setChecked(analysis.sun_path_visible)
            self._sweep_action.setChecked(analysis.sweeping)
            self._cutaway_action.setChecked(analysis.cutaway)

        origin = jump.origin if jump is not None else None
        self._back_action.setEnabled(origin is not None)
        if origin is not None:
            self._back_action.setText(
                QCoreApplication.translate("Workspace", "Back to {date}").format(
                    date=_locale_date(origin)
                )
            )
        else:
            self._back_action.setText(
                QCoreApplication.translate("Workspace", "Back to the Starting Date")
            )
        self._update_legend()
        self._refresh_card()

    def set_drape_mode(self, mode: Any) -> None:
        if self._analysis is not None:
            self._analysis.set_drape_mode(mode)
        self.sync_actions()

    def set_sun_path_visible(self, visible: bool) -> None:
        if self._analysis is not None:
            self._analysis.set_sun_path_visible(visible)
        self.sync_actions()

    def set_sweeping(self, on: bool) -> bool:
        analysis = self._analysis
        started = False
        if analysis is not None:
            if on:
                started = analysis.start_sweep()
                if not started:
                    self._say(
                        "sync",
                        QCoreApplication.translate(
                            "Workspace",
                            "There is no daylight to sweep on this date here, or the garden has no location.",
                        ),
                    )
            else:
                analysis.stop_sweep()
        self.sync_actions()
        return started

    def set_cutaway(self, on: bool) -> None:
        if self._analysis is not None:
            self._analysis.set_cutaway(on)
        self.sync_actions()
        self.run_xray()

    def jump_years(self, years: int) -> None:
        if self._jump is None:
            return
        if self._analysis is not None:
            self._analysis.stop_sweep()
        before = self._wipe.wipe.after_image() if self._wipe.is_shown() and self._wipe.wipe is not None else None
        self._wipe.close_wipe()
        self._jump.jump(years, before)

    def growth_back(self) -> None:
        if self._jump is None:
            return
        self._wipe.close_wipe()
        self._jump.back()

    def on_applied(self, report: TickReport) -> None:
        if report.snapshot:
            self.schedule_xray()
        jump, controller = self._jump, self._get_controller()
        if jump is not None and controller is not None:
            jump.on_applied(report.snapshot, controller.pass_date)

    def ground_point(self, x: float, y: float) -> tuple[float, float] | None:
        host = self._get_host()
        if host is None:
            return None
        eye, target, fov = self._get_camera_now()
        try:
            ray = perspective_ray(eye, target, fov, host.view_size(), x, y)
        except (ValueError, ZeroDivisionError):
            return None
        down = ray.direction[2]
        if down >= -1e-9:
            return None
        reach = (DRAPE_LIFT_CM - ray.origin[2]) / down
        return (ray.origin[0] + reach * ray.direction[0], ray.origin[1] + reach * ray.direction[1])

    def on_ground_clicked(self, x: float, y: float) -> None:
        analysis = self._analysis
        if analysis is None or analysis.drape_mode is not DrapeMode.SUN_HOURS:
            return
        point = self.ground_point(x, y)
        if point is not None:
            analysis.probe(*point)
        self._refresh_card()

    def probe_text(self) -> str:
        analysis = self._analysis
        if analysis is None:
            return ""
        probe: ProbeResult | None = analysis.probe_result
        if probe is None:
            if analysis.drape_mode is DrapeMode.SUN_HOURS:
                return QCoreApplication.translate("Workspace", "Click the ground to read its hours of sun.")
            return ""
        if probe.reason == "outside":
            return QCoreApplication.translate("Workspace", "That spot lies outside the hours-of-sun map.")
        if probe.reason == "updating":
            return QCoreApplication.translate("Workspace", "The hours of sun are being updated for the changed plan.")
        if probe.reason == "unavailable":
            return QCoreApplication.translate("Workspace", "The hours of sun could not be computed for the changed plan.")
        if probe.reason != "ok" or probe.minutes is None or probe.band is None:
            return QCoreApplication.translate("Workspace", "The hours of sun are not computed yet for this plan date.")
        return QCoreApplication.translate("Workspace",
            "Ground at {east} east, {north} north: {hours} h of direct sun on {date} — {band}."
        ).format(
            east=format_length(probe.east_cm),
            north=format_length(probe.north_cm),
            hours=_locale_number(probe.minutes / 60.0),
            date=_locale_date(probe.day),
            band=sun_requirement_label(probe.band.value),
        )

    def schedule_xray(self) -> None:
        if self._analysis is not None and self._analysis.cutaway:
            self._xray_timer.start()

    def run_xray(self) -> None:
        from .selection_bridge import selected_record_ids

        analysis, controller, scene = (
            self._analysis,
            self._get_controller(),
            self._get_scene(),
        )
        if analysis is None or controller is None or scene is None:
            return
        try:
            selected = selected_record_ids(scene)
        except RuntimeError:
            return
        eye, _target, _fov = self._get_camera_now()
        parts_of = self._get_held_parts()
        analysis.update_xray(
            eye,
            selected,
            controller.apply_count,
            lambda: (controller.sync.records, parts_of),
        )


def QtCoreQtNoFocus():
    from PyQt6.QtCore import Qt
    return Qt.FocusPolicy.NoFocus
