#!/usr/bin/env python
"""Take the README's pictures from the bundled example plans (#564, #940).

Every picture under ``docs/images/readme/`` comes out of this script, from the app's own
main window on the plans it ships with, so the README can be re-shot after any change to
how the app looks::

    venv/Scripts/python.exe scripts/capture_readme_media.py            # all pictures
    venv/Scripts/python.exe scripts/capture_readme_media.py --only hero,sun-map
    venv/Scripts/python.exe scripts/capture_readme_media.py --list

It needs a real window system and a graphics card (the 3D engine draws nothing under
``QT_QPA_PLATFORM=offscreen``, section 8.10); it is run by hand, never by CI. The window
stays behind the others and takes no focus (``scripts/quiet_windows.py``).

HOW A PICTURE OF THE WINDOW IS TAKEN. The 3D pane is a native window inside the main
window: ``QWidget.grab()`` paints every widget but leaves that pane empty. So the window
is grabbed, and the engine's own frame of the pane is painted into the hole. Both halves
are what the app draws; nothing is retouched. The interface is English, the theme light,
the 3D quality High, and the window is drawn at 1.25 device pixels per pixel so that a
picture stays sharp when a browser shows it at half its width.

The settings and the profile are a temporary copy (``scripts/script_isolation.py``): the
script does not read or change the settings of the person who runs it.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
if __name__ == "__main__":  # run as a script: this checkout's code, and its own profile
    for entry in (str(REPO / "src"), str(REPO / "scripts"), str(REPO)):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    os.environ.setdefault("QT_SCALE_FACTOR", "1.25")
    import script_isolation

    script_isolation.isolate_profile()

from PyQt6.QtCore import QEventLoop, QPoint, QRect, Qt, QTimer  # noqa: E402
from PyQt6.QtGui import QImage, QPainter  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

OUT = REPO / "docs" / "images" / "readme"
EXAMPLES = REPO / "src" / "open_garden_planner" / "resources" / "examples"
#: The window's size in logical pixels. 1.25 device pixels each: a 1920 x 1100 picture.
WINDOW = (1536, 880)
#: The hero's window is lower: a 3:2 plan fills its half, and the picture is 1920 x 1000.
HERO_HEIGHT = 800
#: The sidebar's width in the pictures (the app's default is 450; a user drags it).
SIDEBAR = 330
#: The size of a 3D picture of an example, and of a plan drawing, in device pixels.
RENDER = (1600, 900)
#: The width an example's picture is kept at (three stand side by side in the README).
EXAMPLE_WIDTH = 960
#: How much nearer than "the whole plan with its highest tree" an example is shown:
#: a plan with one tall tree is small in a picture that keeps the tree's top.
CLOSER = {"japanese-garden": 0.7, "wildlife-garden": 0.75, "terraced-house-garden": 0.75,
          "food-forest": 0.85}
#: The width of a picture that stands in a row of three.
PANEL_WIDTH = 960
#: JPEG quality of the pictures. Measured on the hero: 88 keeps the interface's text clean.
QUALITY = 88
#: The widest picture kept. A README column is about 900 px wide; this is twice that.
MAX_WIDTH = 1920


def pump(ms: float) -> None:
    loop = QEventLoop()
    QTimer.singleShot(int(ms), loop.quit)
    loop.exec()


def wait_until(condition: Callable[[], Any], limit_s: float) -> bool:
    started = time.monotonic()
    while time.monotonic() - started < limit_s:
        if condition():
            return True
        pump(20)
    return False


def save(image: QImage, name: str, out: Path, width: int = MAX_WIDTH) -> Path:
    """One picture, at most ``width`` wide, as a JPEG without an alpha channel."""
    if image.width() > width:
        image = image.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
    path = out / f"{name}.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not image.convertToFormat(QImage.Format.Format_RGB888).save(str(path), "JPG", QUALITY):
        raise RuntimeError(f"could not write {path}")
    print(f"  {name}.jpg  {image.width()} x {image.height()}  {path.stat().st_size / 1024:.0f} KiB")
    return path


class Studio:
    """The app's main window, and the ways a picture is taken of it."""

    def __init__(self) -> None:
        from open_garden_planner.app.application import GardenPlannerApp
        from open_garden_planner.app.settings import get_settings
        from open_garden_planner.core.i18n import load_translator
        from open_garden_planner.ui.theme import ThemeMode, apply_theme, refresh_window_theme

        self.app = QApplication.instance() or QApplication(sys.argv)
        settings = get_settings()
        settings.language = "en"
        settings.theme_mode = ThemeMode.LIGHT
        settings.view3d_quality = "high"
        settings.show_welcome_on_startup = False
        settings.agent_api_enabled = False
        load_translator(self.app, "en")
        apply_theme(self.app, ThemeMode.LIGHT)
        # nobody clicks here: no Welcome dialog over the plan, no Unsaved Changes on close
        GardenPlannerApp._show_welcome_dialog = lambda _self: None  # type: ignore[method-assign]
        GardenPlannerApp._confirm_discard_changes = lambda _self: True  # type: ignore[method-assign]
        self.window = GardenPlannerApp()
        self.window.resize(*WINDOW)
        self.window.show()
        refresh_window_theme(self.app, ThemeMode.LIGHT)
        pump(300)

    # ── the plan ─────────────────────────────────────────────────────────────

    def open(self, slug: str, *, hints: bool = False) -> None:
        """The example as the gallery opens it: an untitled copy on its own day."""
        self.window._open_template_file(str(EXAMPLES / f"{slug}.ogp"))
        if not hints:
            self.hide_layer("Hints")
        self.window.canvas_view.fit_in_view()
        pump(200)

    def hide_layer(self, name: str) -> None:
        scene = self.window.canvas_scene
        for layer in scene.layers:
            if layer.name == name:
                layer.visible = False
                scene.update_layer_visibility(layer.id, False)

    def sidebar(self, *open_panels: str, width: int = SIDEBAR) -> None:
        """The sidebar ``width`` wide, with only ``open_panels`` open: the keys of
        the sidebar's accordion ("layers", "constraints", "companion", ...). A panel
        is opened as a click on its title opens it."""
        window = self.window
        accordion = window._sidebar_controller
        accordion.collapse_all()
        for key in accordion.panel_keys():  # also a panel the selection opened by itself
            if accordion.is_open(key) != (key in open_panels):
                accordion._on_title_click(key)
        total = sum(window._main_splitter.sizes())
        window._main_splitter.setSizes([total - width, width])
        pump(700)  # a panel opens with an animation

    def spacing_circles(self, shown: bool) -> None:
        """View > Overlays > Show Spacing Circles: the dashed rings of plants that
        stand closer than their spacing. Off where a picture is about something else."""
        action = self.window._spacing_circles_action
        if action.isChecked() != shown:
            action.trigger()
        pump(100)

    def look_at(self, item: Any, zoom: float) -> None:
        """The canvas at ``zoom`` times its fit-to-plan zoom, centred on ``item``."""
        view = self.window.canvas_view
        view.fit_in_view()
        view.set_zoom(view.zoom_factor * zoom)
        view.centerOn(item.sceneBoundingRect().center())
        pump(300)

    def select(self, name: str) -> Any:
        """The first object whose name contains ``name`` becomes the selection."""
        scene = self.window.canvas_scene
        scene.clearSelection()
        item = next(item for item in scene.items()
                    if name.lower() in str(getattr(item, "name", "") or "").lower())
        item.setSelected(True)
        pump(600)
        return item

    def at(self, moment: datetime) -> None:
        """The plan's clock at a local wall time."""
        self.window._sim_clock.set_datetime(moment)
        pump(100)

    # ── the modes ────────────────────────────────────────────────────────────

    def mode(self, name: str) -> Any:
        from open_garden_planner.ui.view3d.workspace import WorkspaceMode

        workspace = self.window._workspace
        workspace.set_mode(WorkspaceMode(name))
        if name != "plan":
            self.settle()
        pump(200)
        return workspace

    def settle(self, limit_s: float = 120.0) -> None:
        """The 3D pane has built the plan and every plant, and a picture can be taken."""
        workspace = self.window._workspace
        if not wait_until(lambda: workspace.capture.capture_blocker() is None, limit_s):
            raise RuntimeError(f"3D did not settle: {workspace.capture.capture_blocker()}")
        pump(1500)  # plants are forged in the background; the last ones land after this

    # ── the pictures ─────────────────────────────────────────────────────────

    def orbit_shot(self, closer: float = 1.0, *, aspect: float = RENDER[0] / RENDER[1]) -> Any:
        """A camera on the side the plan's stored orbit starts from, as near as shows
        the whole plan in a picture of ``aspect``; ``closer`` times that distance.

        The stored orbit itself stands further off: it keeps the plan in the picture
        all the way round, and a still needs only the one side."""
        from open_garden_planner.core.scene3d.camera import frame_pose
        from open_garden_planner.ui.view3d.quick3d.shots import PerspectiveShot

        tour = next(tour for tour in self.window._project_manager.camera_tours if tour.orbit)
        start = tour.orbit.pose
        bounds = self.window._workspace.controller.plan_bounds()
        pose = frame_pose(bounds, aspect, fov_deg=tour.orbit.fov_deg, yaw_deg=start.yaw_deg,
                          pitch_deg=start.pitch_deg)
        pose = type(pose)(pose.target, pose.distance_cm * closer, pose.yaw_deg, pose.pitch_deg)
        return PerspectiveShot(pose.eye, pose.target_scene, tour.orbit.fov_deg)

    def render(self, shot: Any, size: tuple[int, int] = RENDER) -> QImage:
        """A 3D picture of the open plan from ``shot``, whatever the pane shows."""
        host = self.window._workspace.host
        return host.capture(size, shot, label="readme", fitted_shadows=True)

    def plan_picture(self) -> QImage:
        """The plan's canvas as it is on screen: rulers, scale bar, compass and all."""
        image = self.window.canvas_view.grab().toImage()
        image.setDevicePixelRatio(1.0)
        return image

    def window_picture(self, shot: Any = None) -> QImage:
        """The whole window. With 3D shown, the engine's frame fills the pane: from
        ``shot``, or from where the pane's camera is."""
        window = self.window
        image = window.grab().toImage()
        workspace = window._workspace
        host = workspace.host
        container = getattr(host, "_container", None) if host is not None else None
        if container is not None and container.isVisible():
            ratio = image.devicePixelRatio()
            corner = container.mapTo(window, QPoint(0, 0))
            hole = QRect(round(corner.x() * ratio), round(corner.y() * ratio),
                         round(container.width() * ratio), round(container.height() * ratio))
            frame = host.capture((hole.width(), hole.height()), shot, label="readme",
                                 fitted_shadows=True)
            image.setDevicePixelRatio(1.0)
            painter = QPainter(image)
            painter.drawImage(hole.topLeft(), frame)
            painter.end()
        image.setDevicePixelRatio(1.0)
        return image


# ── the shots ────────────────────────────────────────────────────────────────


def shot_hero(studio: Studio, out: Path) -> None:
    """The first thing a visitor sees: one garden, drawn and standing, side by side."""
    studio.window.resize(WINDOW[0], HERO_HEIGHT)
    studio.open("family-garden")
    studio.spacing_circles(False)
    studio.sidebar("layers")
    studio.mode("split")
    studio.window.canvas_view.fit_in_view()
    pump(400)
    save(studio.window_picture(studio.orbit_shot(0.8, aspect=1.35)), "hero", out)
    studio.spacing_circles(True)
    studio.window.resize(*WINDOW)
    pump(300)


def shot_examples(studio: Studio, out: Path) -> None:
    """Every bundled example from the start of its stored orbit, on its own day."""
    from open_garden_planner.services.example_library import bundled_examples

    studio.sidebar()
    studio.spacing_circles(True)
    for entry in bundled_examples("en"):
        studio.open(entry.path.stem)
        studio.mode("3d")
        slug = entry.path.stem
        save(studio.render(studio.orbit_shot(CLOSER.get(slug, 0.9))), f"examples/{slug}", out,
             EXAMPLE_WIDTH)


def shot_shadows(studio: Studio, out: Path) -> None:
    """One garden's shadows in the morning, at midday and in the evening of 21 June."""
    studio.open("family-garden")
    studio.spacing_circles(False)
    studio.sidebar()
    studio.mode("plan")
    studio.window.canvas_view.fit_in_view()
    for hour in (8, 13, 18):
        studio.at(datetime(2026, 6, 21, hour, 0))
        save(studio.plan_picture(), f"shadows-{hour:02d}00", out, PANEL_WIDTH)
    studio.spacing_circles(True)


def shot_sun_map(studio: Studio, out: Path) -> None:
    """The hours-of-sun map with its key, under the Plan & Sun controls."""
    studio.open("wildlife-garden")
    studio.spacing_circles(False)
    studio.sidebar()
    studio.mode("plan")
    studio.window.canvas_view.fit_in_view()
    window = studio.window
    window._sun_toolbar._heatmap_button.click()
    if not wait_until(lambda: window._sun_heatmap.legend_key() is not None, 120.0):
        raise RuntimeError("the hours-of-sun map did not appear")
    pump(500)
    save(studio.window_picture(), "sun-map", out)
    window._sun_toolbar._heatmap_button.click()
    studio.spacing_circles(True)


def shot_layers(studio: Studio, out: Path) -> None:
    """The food forest's seven planting layers in the Layers panel."""
    studio.open("food-forest")
    studio.sidebar("layers")
    studio.mode("plan")
    studio.window.canvas_view.fit_in_view()
    pump(300)
    save(studio.window_picture(), "layers", out)


def shot_cad(studio: Studio, out: Path) -> None:
    """Guide lines and dimension constraints in the cottage garden."""
    studio.open("cottage-garden")
    studio.sidebar("constraints")
    studio.mode("plan")
    studio.window.canvas_view.fit_in_view()
    pump(300)
    save(studio.window_picture(), "cad", out)


def shot_companions(studio: Studio, out: Path) -> None:
    """A selected tomato in the allotment's greenhouse: its companions and antagonists."""
    studio.open("allotment")
    studio.mode("plan")
    tomato = studio.select("tomato")
    studio.sidebar("companion", width=420)
    studio.look_at(tomato, 2.2)
    save(studio.window_picture(), "companions", out)
    studio.window.canvas_scene.clearSelection()


def shot_evening(studio: Studio, out: Path) -> None:
    """The modern garden a quarter of an hour after sunset: its lamps are on."""
    studio.open("modern-garden")
    studio.sidebar()
    studio.mode("3d")
    studio.at(datetime(2026, 8, 15, 20, 45))
    studio.settle()
    save(studio.render(studio.orbit_shot(0.8)), "evening", out)


SHOTS: dict[str, Callable[[Studio, Path], None]] = {
    "hero": shot_hero,
    "shadows": shot_shadows,
    "sun-map": shot_sun_map,
    "cad": shot_cad,
    "layers": shot_layers,
    "companions": shot_companions,
    "evening": shot_evening,
    "examples": shot_examples,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--only", default="", help="comma-separated shot names")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--list", action="store_true", help="print the shot names and stop")
    arguments = parser.parse_args()
    if arguments.list:
        print("\n".join(SHOTS))
        return 0
    wanted = [name for name in arguments.only.split(",") if name] or list(SHOTS)
    unknown = [name for name in wanted if name not in SHOTS]
    if unknown:
        parser.error(f"unknown shot: {', '.join(unknown)}")
    script_isolation.isolate()
    studio = Studio()
    try:
        for name in wanted:
            print(name)
            SHOTS[name](studio, arguments.out)
    finally:
        studio.window.close()
        pump(300)
    return 0


if __name__ == "__main__":
    sys.exit(main())
