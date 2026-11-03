"""The atmosphere sky chosen in the real main window (Phase 17 L7, #391, §8.10).

A real ``GardenPlannerApp``; its 3D engine is replaced at the documented seam
(``Workspace.engine_factory``) by the workspace tests' recording host. The user opens
the 3D view (the painted sky, the default), picks Edit → Preferences → 3D View → Sky →
"Atmosphere with clouds" and saves, turns the weather to Overcast and back in the 3D
strip, and goes back to the painted sky. The test asserts the SKIES handed to the
engine: the same sky (sun, colours, cloud, twilight) drawn by another model, built at
once, and nothing else touched — no look change, no geometry, no camera, no frame.

The cloud noise volume is made on a worker (about a second of numpy) before the
atmosphere is asked for; here the worker answers at once
(``look_controller._make_cloud_noise``), the volume itself is
``test_scene3d_cloud_noise.py``'s. The pixels are ``test_view3d_looks_render.py``'s
(``OGP_RENDER3D=1``): every board gate on both sky models.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from open_garden_planner.core.scene3d.weather import living_look
from open_garden_planner.ui.dialogs.preferences_dialog import PreferencesDialog
from open_garden_planner.ui.view3d import look_controller
from tests.integration.test_view3d_looks import (  # noqa: F401 - pytest fixtures
    BERLIN,
    PLAN,
    VIEW3D,
    _preferences,
    _settle,
    app3d,
    look_settings,
)


@pytest.fixture
def quick_noise(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []

    def make() -> bytes:
        calls.append(1)
        return b"volume"

    monkeypatch.setattr(look_controller, "_make_cloud_noise", make)
    return calls


def _weather_actions(window: Any) -> dict[str, Any]:
    button = window._workspace.living.button
    assert button is not None and button.isVisible(), "the Weather button is in the 3D strip"
    menu = button.menu()
    assert menu is not None
    return {action.text(): action for action in menu.actions() if action.text()}


def test_choosing_the_atmosphere_redraws_the_same_sky_and_touches_nothing_else(
        app3d, qtbot, monkeypatch, quick_noise) -> None:  # noqa: F811 - the fixture
    window, engines = app3d
    workspace = window._workspace
    window._project_manager.set_location(dict(BERLIN))
    workspace.set_mode(VIEW3D)
    qtbot.waitUntil(lambda: bool(engines.hosts) and bool(engines.host.skies), timeout=5000)
    _settle(qtbot)
    host, sink, look, controller = engines.host, engines.sink, workspace.look, workspace.controller
    assert look is not None and controller is not None
    sun = controller.sync.sun
    assert [sky.model for sky in host.skies] == ["painted"] * len(host.skies), "the default"
    assert quick_noise == [], "no cloud volume is made for the painted sky"
    builds, framed, looks = controller.sync.build_count, workspace.camera.pose, len(host.looks)
    sink.clear_calls()

    # ── Edit → Preferences → 3D View → Sky: "Atmosphere with clouds" → Save ──
    skies = len(host.skies)
    _preferences(window, monkeypatch, sky_model="atmosphere")
    assert look.sky_model == "atmosphere"
    assert window._workspace.look is look
    qtbot.waitUntil(lambda: len(host.skies) > skies and host.skies[-1].model == "atmosphere",
                    timeout=5000)
    assert quick_noise == [1], "the volume is made once, off the GUI thread"
    clear = living_look(sun, look.preset, "clear")
    assert host.skies[skies:] == [replace(clear.sky, model="atmosphere")], (
        "ONE build, at once: the same sun, colours and twilight, drawn by the atmosphere")
    # the look carries its sky, so it is sent again — differing in the model alone
    assert host.looks[looks:] == [replace(clear, sky=replace(clear.sky, model="atmosphere"))]
    shown = PreferencesDialog(window)
    qtbot.addWidget(shown)
    assert shown._view3d_sky_combo.currentData() == "atmosphere", "the dialog shows what is stored"
    assert shown._view3d_sky_combo.currentText() == shown.tr("Atmosphere with clouds")

    # ── the 3D strip's Weather → Overcast and back: its cloud IS the atmosphere's ──
    actions = _weather_actions(window)
    skies = len(host.skies)
    actions["Overcast"].trigger()
    overcast = living_look(sun, look.preset, "overcast")
    assert host.skies[skies:] == [replace(overcast.sky, model="atmosphere")]
    assert host.skies[-1].cloud == overcast.sky.cloud > 0.0
    actions["Clear"].trigger()
    assert host.skies[-1] == replace(clear.sky, model="atmosphere")

    # ── hiding and showing the view: the atmosphere stays, nothing is rebuilt ──
    skies = len(host.skies)
    workspace.set_mode(PLAN)
    workspace.set_mode(VIEW3D)
    _settle(qtbot)
    assert len(host.skies) == skies

    # ── back to the painted sky: at once, and the volume is not made again ──
    _preferences(window, monkeypatch, sky_model="painted")
    assert host.skies[-1] == clear.sky and host.skies[-1].model == "painted"
    _preferences(window, monkeypatch, sky_model="atmosphere")
    assert host.skies[-1].model == "atmosphere" and quick_noise == [1]

    # ── and nothing but skies happened ──
    assert sink.ops() == [], "no pipeline call: the sky is the engine's alone"
    assert controller.sync.build_count == builds, "not one builder ran"
    assert workspace.camera.pose is framed, "no camera move"
    assert host.frames_taken == []
    assert window.close() is True
    assert workspace.look is None


def test_compatibility_mode_draws_no_atmosphere_and_makes_no_volume(
        app3d, qtbot, tmp_path, quick_noise, look_settings) -> None:  # noqa: F811 - the fixtures
    """A software adapter has no sky at all (FR-3D-LOOK-05): the chosen atmosphere changes
    nothing there — no sky, no worker (the workspace starts in compatibility mode the way
    the init guard decides it, as ``test_view3d_looks.py`` does)."""
    from open_garden_planner.ui.view3d.init_guard import Init3DGuard

    window, engines = app3d
    look_settings.view3d_sky_model = "atmosphere"
    workspace = window._workspace
    Init3DGuard(tmp_path / "compat", is_running=lambda _pid: False).use_software_next_time()
    workspace._guard = Init3DGuard(tmp_path / "compat", is_running=lambda _pid: False)
    window._project_manager.set_location(dict(BERLIN))
    workspace.set_mode(VIEW3D)
    qtbot.waitUntil(lambda: bool(engines.hosts) and bool(engines.host.looks), timeout=5000)
    _settle(qtbot)
    look = workspace.look
    assert engines.modes == [True] and look is not None and look.software
    assert engines.host.skies == [] and quick_noise == []
    assert look.sky_model == "atmosphere" and look.sky_model_shown == "painted"
