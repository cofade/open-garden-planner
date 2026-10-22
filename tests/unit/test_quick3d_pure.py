"""The engine package's engine-free modules: look, shots, materials, Qt messages (L1.2).

These carry every decision of the engine package that is not a Qt call — which
is why they are separate modules: the default (GPU-less) run covers them, and
the render tier only has to prove that the engine does what they say.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from open_garden_planner.core.scene3d import (
    MATERIAL_KINDS,
    Material,
    MeshPart,
    SunState,
    prism_mesh,
)
from open_garden_planner.core.scene3d.look import look_for
from open_garden_planner.ui.view3d.quick3d.look import (
    COLOR_PROPERTIES,
    LINEAR_COLOR_PROPERTIES,
    NEUTRAL_DAY,
    engine_hex,
    engine_linear,
    engine_srgb,
    scene_properties,
    sky_longitude,
    sky_properties,
)
from open_garden_planner.ui.view3d.quick3d.materials import (
    PART_COMPONENTS,
    WHITE,
    part_tint,
    tint_uniform,
)
from open_garden_planner.ui.view3d.quick3d.qt_messages import (
    QtMessages,
    classify,
    graphics_adapter,
    graphics_info,
)
from open_garden_planner.ui.view3d.quick3d.shots import (
    PerspectiveShot,
    TopDownShot,
    top_down_pixel,
)
from tests.integration.quick3d_render_support import isolated_env

#: What the L0 spike measured, frozen when L1.10 deleted it (its provenance field says how).
SPIKE = json.loads((Path(__file__).resolve().parents[1] / "data" / "l0_spike_reference.json")
                   .read_text(encoding="utf-8"))

SRC = Path(__file__).resolve().parents[2] / "src"
SQUARE = ((-50.0, -50.0), (50.0, -50.0), (50.0, 50.0), (-50.0, 50.0))


# ── look ─────────────────────────────────────────────────────────────────────


class TestLook:
    """``quick3d/look.py`` is a MAPPING (L1.4): the look itself — rig, presets,
    ``look_for`` — is ``core/scene3d/look.py``, tested in ``test_scene3d_look.py``."""

    def test_the_neutral_day_is_the_cores_and_the_spikes_noon_rig(self) -> None:
        """What a host shows before anyone hands it a look is measured, not invented:
        the L0 spike's noon anchor (frozen when L1.10 deleted the spike)."""
        from open_garden_planner.core.scene3d import look as core_look

        noon = SPIKE["rig"]["anchors"]["NOON"]
        assert NEUTRAL_DAY is core_look.NEUTRAL_DAY
        properties = scene_properties(NEUTRAL_DAY)
        assert [properties["sunColor"], properties["sunBrightness"]] == noon["sun"]
        assert properties["exposure"] == noon["look"]["exposure"]
        assert properties["probeExposure"] == noon["look"]["probe"]
        assert properties["meadowColor"] == SPIKE["rig"]["meadow_albedo"]
        assert NEUTRAL_DAY.fog_color == NEUTRAL_DAY.plain_sky == SPIKE["rig"]["noon_fog"]
        assert properties["fogColor"] == properties["skyColor"] == engine_srgb(NEUTRAL_DAY.fog_linear)

    def test_the_mapping_holds_plain_values_only(self) -> None:
        for elevation, preset in ((60.0, "high"), (3.0, "low"), (-20.0, "ultra"), (15.0, "medium")):
            properties = scene_properties(look_for(SunState(elevation, 200.0), preset))
            for name, value in properties.items():
                if name in LINEAR_COLOR_PROPERTIES:
                    assert isinstance(value, tuple) and len(value) == 3, name
                    assert all(isinstance(channel, float) and 0.0 <= channel <= 1.0
                               for channel in value), (name, value)
                    continue
                assert isinstance(value, (str, float, int, bool)), (name, value)
                if name in COLOR_PROPERTIES:
                    assert isinstance(value, str) and len(value) == 7 and value[0] == "#", name
            assert set(properties) >= COLOR_PROPERTIES | LINEAR_COLOR_PROPERTIES
        assert not COLOR_PROPERTIES & LINEAR_COLOR_PROPERTIES

    def test_the_mapping_follows_the_look(self) -> None:
        look = look_for(SunState(-8.0, 320.0), "low")
        properties = scene_properties(look)
        assert properties["sunColor"] == look.mood.sun_color == "#8ea4d6"
        assert properties["exposure"] == 2.4 and properties["saturation"] == 0.6
        assert (properties["shadowFactor"], properties["pcfFactor"]) == (25.0, 8.0)
        assert (properties["shadowMapQuality"], properties["shadowCascades"],
                properties["softShadows"], properties["shadowBias"]) == ("very_high", 1, "pcf4", 15.0)
        assert (properties["antialiasing"], properties["ambientOcclusion"], properties["glow"],
                properties["fog"], properties["reflections"]) == ("msaa", False, False, True, False)
        assert properties["antialiasingQuality"] == "high", "low: 4x MSAA (fix round 1, #529)"
        assert properties["fillColor"] == engine_srgb(look.fill_linear)
        assert properties["skyColor"] == properties["fogColor"] == engine_srgb(look.fog_linear)

    @pytest.mark.parametrize("linear", [0.0, 1e-5, 0.0005, 0.0015, 0.0044, 0.02, 0.2, 0.44, 0.9, 1.0])
    def test_the_engines_own_linearisation_gives_the_looks_linear_value_back(self, linear: float) -> None:
        """A colour PROPERTY is linearised by Qt Quick 3D with a polynomial (measured in
        L1.4 — ``quick3d/look.py``); ``engine_srgb`` is its inverse, so what the shader
        computes with is the linear value the look derived."""
        srgb = engine_srgb((linear, linear, linear))
        assert all(0.0 <= channel <= 1.0 for channel in srgb)
        assert engine_linear(srgb[0]) == pytest.approx(linear, abs=1e-12)

    def test_a_dark_colour_is_where_the_srgb_curve_would_have_been_wrong(self) -> None:
        """The night fog's green channel, linear 0.0014: the sRGB curve encodes it as
        code 5, which the ENGINE reads as 0.0005 — a third. Bright colours agree."""
        from open_garden_planner.core.scene3d.color import srgb_channel_to_linear

        night = look_for(SunState(-10.0, 0.0), "high")
        green = night.fog_linear[1]
        assert green == pytest.approx(0.00142, abs=2e-5)
        naive = int(night.fog_color[3:5], 16) / 255.0          # the sRGB curve's code
        assert engine_linear(naive) < green / 2.5
        assert engine_linear(engine_srgb(night.fog_linear)[1]) == pytest.approx(green, rel=1e-9)
        assert engine_hex(night.fog_linear) == "#060912" and night.fog_color == "#03050e"
        for bright in (0.2, 0.5, 0.9):                         # within one 8-bit code up here
            exact = srgb_channel_to_linear(bright)
            assert abs(engine_srgb((exact,) * 3)[0] - bright) * 255.0 < 1.0

    def test_the_scene_files_defaults_are_the_engine_colours_of_the_neutral_day(self) -> None:
        assert engine_hex(NEUTRAL_DAY.fog_linear) == "#8f9ca8"
        assert engine_hex(NEUTRAL_DAY.fill_linear) == "#56657c", "half L1.2's #778bab (FILL_OF_SKY)"

    def test_no_property_of_the_mapping_could_aim_the_light(self) -> None:
        """Truth: where the sun stands is the pipeline's (``Quick3DSink.set_sun``). The
        look's mapping has no direction in it, by day or by night."""
        for elevation in (40.0, -10.0):
            names = set(scene_properties(look_for(SunState(elevation, 100.0), "high")))
            assert not any("rotation" in name.lower() or "sunup" in name.lower()
                           or "direction" in name.lower() or "travel" in name.lower()
                           for name in names), names

    @pytest.mark.parametrize("azimuth", [0.0, 90.0, 180.0, 270.0, 301.5, 359.5])
    def test_the_sky_longitude_is_the_measured_convention(self, azimuth: float) -> None:
        """``sunLongitude = azimuth + 90°`` — the spike's sky probe; the L1.4 render tier
        measures it again in pixels. Against the spike's own function's answers (frozen)."""
        spike_longitude = SPIKE["sky_longitude"][repr(azimuth)]
        assert sky_longitude(azimuth) == spike_longitude == (azimuth + 90.0) % 360.0

    def test_the_sky_inputs_are_the_spikes(self) -> None:
        """Day and night, against what ``GardenSpike.qml``'s ``rebuildSky`` sets."""
        day = sky_properties(look_for(SunState(12.0, 250.0), "high").sky)
        assert day == {
            "sunLatitude": 12.0, "sunLongitude": 340.0,
            "skyTopColor": day["skyTopColor"], "skyHorizonColor": day["skyHorizonColor"],
            "groundHorizonColor": day["skyHorizonColor"], "groundBottomColor": "#3c4d2e",
            "sunColor": day["sunColor"], "skyEnergy": 1.0, "groundEnergy": 1.0,
            "groundCurve": 0.1, "sunEnergy": 1.0}
        night = sky_properties(look_for(SunState(-30.0, 10.0), "high").sky)
        # the night ground hemisphere at the sky's energy, 0.25 — the spike's 0.15 left a
        # dark line at the night horizon (L1.4 round 5; ``SkySpec.ground_energy``)
        assert (night["sunLatitude"], night["groundBottomColor"], night["skyEnergy"],
                night["groundEnergy"], night["sunEnergy"]) == (-6.0, "#0a0f14", 0.25, 0.25, 0.0)
        spike = "\n".join(SPIKE["qml"]["sky_inputs"])   # GardenSpike.qml's lines, frozen
        for line in ('data.groundBottomColor = root.night ? "#0a0f14" : "#3c4d2e"',
                     "data.groundHorizonColor = root.skyHorizon",
                     "data.skyEnergy = root.night ? 0.25 : 1.0",
                     "data.groundEnergy = root.night ? 0.15 : 1.0",   # the one we left
                     "data.groundCurve = 0.1", "data.sunEnergy = root.night ? 0.0 : 1.0"):
            assert line in spike, line


# ── shots ────────────────────────────────────────────────────────────────────


class TestShots:
    def test_top_down_puts_east_right_and_north_up(self) -> None:
        shot = TopDownShot(center=(0.0, 0.0), px_per_cm=0.5)
        size = (320, 240)
        assert top_down_pixel(0.0, 0.0, shot, size) == (160.0, 120.0)
        east = top_down_pixel(100.0, 0.0, shot, size)
        north = top_down_pixel(0.0, 100.0, shot, size)
        assert east == (210.0, 120.0)   # +East → to the right
        assert north == (160.0, 70.0)   # +North → UP the image (smaller row)

    def test_the_centre_and_the_scale_are_honoured(self) -> None:
        shot = TopDownShot(center=(1200.0, 800.0), px_per_cm=0.25)
        assert top_down_pixel(1200.0, 800.0, shot, (640, 360)) == (320.0, 180.0)
        assert top_down_pixel(1600.0, 400.0, shot, (640, 360)) == (420.0, 280.0)

    @pytest.mark.parametrize("ratio", [1.0, 1.25, 1.5, 2.0])
    def test_device_pixels_scale_with_the_display(self, ratio: float) -> None:
        """A grab is in DEVICE pixels: at a 150 % display it is 1.5x the logical size, and a
        prediction made in logical pixels pointed at the wrong place (spike, ``--iou``)."""
        shot = TopDownShot(center=(0.0, 0.0), px_per_cm=0.5)
        size = (round(320 * ratio), round(240 * ratio))
        x, y = top_down_pixel(100.0, 60.0, shot, size, device_pixel_ratio=ratio)
        assert (x, y) == pytest.approx((size[0] / 2 + 50.0 * ratio, size[1] / 2 - 30.0 * ratio))

    @pytest.mark.parametrize("make", [
        lambda: TopDownShot((0.0, 0.0), 0.0), lambda: TopDownShot((0.0, 0.0), -1.0),
        lambda: TopDownShot((math.nan, 0.0), 1.0),
        lambda: PerspectiveShot((0.0, 0.0, 100.0), (0.0, 0.0, 100.0)),
        lambda: PerspectiveShot((0.0, 0.0, 100.0), (0.0, 0.0, 0.0), fov_deg=0.0),
        lambda: PerspectiveShot((0.0, 0.0, 100.0), (0.0, 0.0, 0.0), fov_deg=180.0),
        lambda: PerspectiveShot((0.0, math.inf, 100.0), (0.0, 0.0, 0.0)),
    ])
    def test_a_shot_that_cannot_be_rendered_is_refused(self, make: object) -> None:
        with pytest.raises(ValueError):
            make()  # type: ignore[operator]

    def test_a_perspective_shot_defaults_to_the_spikes_field_of_view(self) -> None:
        assert PerspectiveShot((0.0, -500.0, 300.0), (0.0, 0.0, 50.0)).fov_deg == 40.0


# ── materials ────────────────────────────────────────────────────────────────


class TestMaterials:
    def test_every_material_kind_has_a_part_component(self) -> None:
        assert frozenset(PART_COMPONENTS) == MATERIAL_KINDS
        assert len(set(PART_COMPONENTS.values())) == len(PART_COMPONENTS)

    def test_only_a_tinted_part_takes_the_items_colour(self) -> None:
        material = Material("SHED", fill_rgba=(200, 30, 30, 90))
        mesh = prism_mesh([SQUARE], 10.0)
        assert part_tint(MeshPart(mesh, tinted=True), material) == (200, 30, 30, 255)
        assert part_tint(MeshPart(mesh, tinted=False), material) == WHITE

    def test_the_shader_tint_is_exactly_the_materials_linear_tint(self) -> None:
        material = Material("SHED", fill_rgba=(200, 30, 188, 255))
        assert tint_uniform(material.tint_rgba) == material.tint_linear()[:3]
        assert tint_uniform(WHITE) == (1.0, 1.0, 1.0)


# ── Qt messages ──────────────────────────────────────────────────────────────

# Measured in the spike: renaming one function in water.frag (senior review, 6f0c4f4).
SHADER_PARSE = ("QSpirvCompiler: Failed to parse shader: ERROR: 0:120: "
                "'qt_sampleGlossyRenamed' : no matching overloaded function found")
# Measured on the L1.2 dev box (monitor asleep), Qt 6.11, on EVERY run that opens a window.
MONITOR = '"Unable to open monitor interface to \\\\\\\\.\\\\DISPLAY1:" "Unknown error 0xe0000225."'


class TestClassify:
    @pytest.mark.parametrize(("kind", "text"), [
        ("warning", SHADER_PARSE),
        ("warning", "Failed to build graphics pipeline state"),
        ("warning", "file:///x/Garden.qml:231:13: Unable to assign [undefined] to QObject*"),
        ("warning", "qrc:/x.qml:12: ReferenceError: groundColor is not defined"),
        ("warning", "QQmlComponent: Component is not ready"),
        ("warning", "Failed to load shader file water.frag"),
        ("critical", "anything a Qt module reports as critical"),
        ("fatal", "anything fatal"),
    ])
    def test_shader_and_qml_failures_are_errors(self, kind: str, text: str) -> None:
        assert classify(kind, text) == "error"

    @pytest.mark.parametrize(("kind", "text", "expected"), [
        ("warning", "QStandardPaths: XDG_RUNTIME_DIR not set, defaulting to '/tmp/runtime-root'",
         "warning"),
        ("info", "Using RHI backend OpenGL", "info"),
        ("debug", "Adapter 0: 'NVIDIA GeForce RTX 4070' (vendor 0x10DE device 0x2786 flags 0x0)",
         "info"),
    ])
    def test_other_messages_are_not_errors(self, kind: str, text: str, expected: str) -> None:
        assert classify(kind, text) == expected

    @pytest.mark.parametrize("kind", ["debug", "info"])
    @pytest.mark.parametrize("text", [
        SHADER_PARSE,
        "Failed to compile fragment shader",
        "file:///x/Garden.qml:231:13: Unable to assign [undefined] to QObject*",
        "qt.rhi.general: shader cache: failed to open, error 2",
        "file:///x/Garden.qml:40: TypeError: Cannot read property 'x' of null",
    ])
    def test_the_level_decides_first(self, kind: str, text: str) -> None:
        """Review P2-3: the error patterns used to run over debug and info lines too. The
        self-test switches ``qt.rhi.general`` debug output on — so the WORDING of a Qt
        debug line could have failed a release. Only a warning is promoted by its text."""
        assert classify(kind, text) == "info"
        assert classify(kind, text, "qt.rhi.general") == "info"
        assert classify("warning", text) == "error", "the same text as a warning IS an error"

    @pytest.mark.parametrize(("kind", "text", "category", "expected"), [
        # an image a widget could not load — "Failed to load" alone used to be an error
        ("warning", "QPixmap::scaled: Pixmap is a null pixmap", "", "warning"),
        ("warning", "Failed to load image file:///x/icon.png", "", "warning"),
        ("warning", "QFont::setPointSize: Point size <= 0 (-1), must be greater than 0", "", "warning"),
        # a word of JavaScript without a QML location says nothing about the scene file
        ("warning", "TypeError: something somewhere", "", "warning"),
        ("warning", "ReferenceError: x is not defined", "", "warning"),
        # QtWebEngine forwards a web page's console: category "js", or the prefix "js: "
        ("warning", "Uncaught TypeError: map.fitBounds is not a function", "js", "info"),
        ("warning", "js: Uncaught ReferenceError: L is not defined", "", "info"),
        ("critical", "Uncaught (in promise) Error: tiles failed to load", "js", "info"),
        ("warning", "js: https://tile.example/1/2/3.png Failed to load shader of the page", "", "info"),
    ])
    def test_messages_of_the_rest_of_the_process_are_not_engine_errors(
            self, kind: str, text: str, category: str, expected: str) -> None:
        """Review round 2, P2-1/2: the recorder listens to the WHOLE process, and its
        error rules matched a pixmap a widget could not load and the JavaScript console
        of the satellite-map page. Each error rule now names a shader, a pipeline or a
        QML location; a web page's console is never a statement about the 3D frame."""
        assert classify(kind, text, category) == expected

    def test_the_error_rules_still_catch_what_they_are_for(self) -> None:
        """The other direction of the tightening: nothing a shader or the scene file can
        say got lost with the bare words."""
        for text in (
            SHADER_PARSE,
            "Failed to compile fragment shader",
            "Failed to link shader program: error X",
            "Failed to create graphics pipeline",
            "ERROR: :12: 'foo' : undeclared identifier in water.frag:12",
            "file:///x/Garden.qml:231:13: Unable to assign [undefined] to QObject*",
            "file:///x/Garden.qml:40: TypeError: Cannot read property 'x' of null",
            "file:///x/Garden.qml:12: ReferenceError: groundColor is not defined",
            "QQmlComponent: Component is not ready",
            "file:///x/Garden.qml:7 Foo is not a type",
            'Cannot assign to non-existent property "castsShadows"',
        ):
            assert classify("warning", text) == "error", text

    def test_a_debug_line_is_recorded_as_information_only(self) -> None:
        qt = QtMessages()
        qt.add("debug", SHADER_PARSE, "qt.rhi.general")
        assert qt.clean and qt.errors == [] and qt.report()["counts"]["info"] == 1

    def test_the_sleeping_monitor_warning_is_the_environment(self) -> None:
        assert classify("warning", MONITOR, "qt.qpa.screen") == "environment"

    def test_the_stale_dpr_warning_is_the_environment(self) -> None:
        """#537: a transient Windows QPA race seen once in ~20 gate runs — a warning
        about the frame's device-pixel-ratio cache, not about the frame."""
        text = "The cached device pixel ratio value was stale on window expose."
        assert classify("warning", text, "") == "environment"

    def test_the_environment_list_is_exact_not_a_category_pass(self) -> None:
        """An allow-list that is wider than what was measured is a hole: another message
        of that category, the same text from another category, and an ERROR in that
        category all keep their class."""
        assert classify("warning", "another screen problem", "qt.qpa.screen") == "warning"
        assert classify("warning", MONITOR, "qt.quick3d") == "warning"
        assert classify("critical", MONITOR, "qt.qpa.screen") == "error"
        assert classify("warning", MONITOR + " Failed to compile shader", "qt.qpa.screen") == "error"


class TestRecorder:
    def test_counts_keeps_and_logs_only_what_matters(self) -> None:
        logged: list[dict[str, object]] = []
        qt = QtMessages(lambda phase, **fields: logged.append({"phase": phase, **fields}))
        qt.add("info", "Using RHI backend OpenGL")
        qt.add("warning", "QStandardPaths: XDG_RUNTIME_DIR not set")
        qt.add("warning", MONITOR, "qt.qpa.screen")
        qt.add("warning", SHADER_PARSE, "qt.shadertools")
        report = qt.report()
        assert report["counts"] == {"error": 1, "warning": 1, "environment": 1, "info": 1}
        assert qt.errors == [f"warning: qt.shadertools: {SHADER_PARSE}"]
        assert qt.warnings == ["warning: QStandardPaths: XDG_RUNTIME_DIR not set"]
        assert [entry["level"] for entry in logged] == ["warning", "environment", "error"]
        assert not qt.clean

    def test_a_run_with_only_information_and_environment_is_clean(self) -> None:
        qt = QtMessages()
        qt.add("debug", "Adapter 0: 'x' (vendor 0x1 device 0x2 flags 0x0)", "qt.rhi.general")
        qt.add("warning", MONITOR, "qt.qpa.screen")
        assert qt.clean and qt.report()["counts"]["environment"] == 1

    def test_the_recorder_is_bounded(self) -> None:
        qt = QtMessages()
        for k in range(1000):
            qt.add("warning", f"noise {k}")
        assert qt.report()["counts"]["warning"] == 1000
        assert len(qt.report()["warnings"]) == 30 and len(qt.warnings) == 100

    def test_it_never_raises_inside_qts_handler(self) -> None:
        def broken_log(*_args: object, **_fields: object) -> None:
            raise OSError("log closed")

        qt = QtMessages(broken_log)
        qt.add("warning", "a message after the log was closed")  # must not raise
        assert qt.report()["counts"]["warning"] == 1


class TestWhichThreadDelivered:
    """Review round 2, P1-C: the recorder may only be installed where every message
    arrives on the thread that created it — it counts the ones that did not, so the
    render tier can assert the claim instead of assuming it."""

    def test_messages_on_the_recorders_own_thread_are_not_counted(self) -> None:
        qt = QtMessages()
        qt.add("warning", "on the thread that renders")
        assert qt.other_threads == 0 and qt.report()["other_threads"] == 0

    def test_a_message_from_another_thread_is_counted_and_still_recorded(self) -> None:
        import threading

        qt = QtMessages()
        worker = threading.Thread(target=qt.add, args=("warning", SHADER_PARSE, "qt.shadertools"))
        worker.start()
        worker.join(10)
        qt.add("debug", "back on the creating thread")
        assert qt.other_threads == 1 and qt.report()["other_threads"] == 1
        assert len(qt.errors) == 1, "counted AND recorded: an error is an error on any thread"


def test_the_logging_sink_of_the_live_watch_is_gone() -> None:
    """Nothing of the live message watch is left to be picked up again (review round 2):
    a Python Qt message handler beside a shown window deadlocks the process."""
    from open_garden_planner.ui.view3d.quick3d import qt_messages

    assert not hasattr(qt_messages, "logging_sink")
    source = Path(qt_messages.__file__).read_text(encoding="utf-8")
    assert "import logging" not in source


class TestGraphicsInfo:
    """Review P2-4: the debug rule was switched on and never off again."""

    @staticmethod
    def _rhi_debug() -> bool:
        from PyQt6.QtCore import QLoggingCategory

        return bool(QLoggingCategory("qt.rhi.general").isDebugEnabled())

    def test_the_rule_is_on_inside_the_block_and_off_after(self, qtbot) -> None:  # noqa: ARG002
        assert not self._rhi_debug()
        with graphics_info():
            assert self._rhi_debug()
        assert not self._rhi_debug()

    def test_the_rule_is_cleared_when_the_block_raises(self, qtbot) -> None:  # noqa: ARG002
        with pytest.raises(RuntimeError), graphics_info():
            raise RuntimeError("the render failed")
        assert not self._rhi_debug()

    def test_blocks_nest_and_the_outermost_one_switches(self, qtbot) -> None:  # noqa: ARG002
        """The render driver records a whole run while ``render_records`` records one
        frame: the inner block must not switch the outer one's rule off."""
        with graphics_info():
            with graphics_info():
                assert self._rhi_debug()
            assert self._rhi_debug(), "the inner block switched the outer rule off"
        assert not self._rhi_debug()


class TestGraphicsAdapter:
    def test_direct3d_names_the_adapter_that_was_chosen(self) -> None:
        """Real lines of Qt 6.11's ``qt.rhi.general`` on the L1.2 dev box."""
        gpu = [
            "debug: qt.rhi.general: Adapter 0: 'NVIDIA GeForce RTX 4070' (vendor 0x10DE device 0x2786 flags 0x0)",
            "debug: qt.rhi.general:   using this adapter",
            "debug: qt.rhi.general: Adapter 1: 'Microsoft Basic Render Driver' (vendor 0x1414 device 0x8C flags 0x2)",
        ]
        warp = [gpu[0], gpu[2], gpu[1]]  # QSG_RHI_PREFER_SOFTWARE_RENDERER=1: the marker follows adapter 1
        assert graphics_adapter(gpu) == "NVIDIA GeForce RTX 4070"
        assert graphics_adapter(warp) == "Microsoft Basic Render Driver"

    def test_opengl_names_the_renderer(self) -> None:
        lines = ["debug: qt.rhi.general: OpenGL VENDOR: Mesa RENDERER: llvmpipe (LLVM 15.0.7, 256 bits) "
                 "VERSION: 4.5 (Core Profile) Mesa 23.2.1"]
        assert graphics_adapter(lines) == "llvmpipe (LLVM 15.0.7, 256 bits)"

    def test_the_last_device_wins(self) -> None:
        """A process may create several devices; the answer is about the latest one."""
        lines = [
            "debug: qt.rhi.general: Adapter 0: 'A' (vendor 0x1 device 0x2 flags 0x0)",
            "debug: qt.rhi.general:   using this adapter",
            "debug: qt.rhi.general: Adapter 0: 'A' (vendor 0x1 device 0x2 flags 0x0)",
            "debug: qt.rhi.general: Adapter 1: 'B' (vendor 0x1 device 0x2 flags 0x2)",
            "debug: qt.rhi.general:   using this adapter",
        ]
        assert graphics_adapter(lines) == "B"

    def test_unknown_stays_unknown(self) -> None:
        assert graphics_adapter([]) is None
        assert graphics_adapter(["debug: qt.rhi.general: Adapter 0: 'A' (vendor 0x1 device 0x2 flags 0x0)"]) is None


_LATE_MESSAGE = textwrap.dedent("""
    import sys
    from pathlib import Path
    from PyQt6.QtCore import QCoreApplication, qWarning
    from open_garden_planner.ui.view3d.quick3d.qt_messages import QtMessages, install, uninstall

    app = QCoreApplication([])
    log_file = (Path(sys.argv[1]) / "render.log").open("w", encoding="utf-8")

    def log(phase, **fields):
        log_file.write(phase + str(fields) + "\\n")

    previous = install(QtMessages(log))
    if sys.argv[2] == "uninstall":
        uninstall(previous)
    log_file.close()
    qWarning("a late Qt message, after the log closed")
    print("survived", flush=True)
""")


@pytest.mark.parametrize("mode", ["uninstall", "closed-log"])
def test_a_late_qt_message_cannot_abort_the_process(tmp_path: Path, mode: str) -> None:
    """The spike reproduced exit 134: the handler wrote to a closed log, raised, and PyQt
    turned the exception into qFatal. The recorder never raises ("closed-log"), and a
    render detaches its handler before its log closes ("uninstall")."""
    env = isolated_env(tmp_path, QT_QPA_PLATFORM="offscreen")
    proc = subprocess.run(  # noqa: S603 - fixed argv, our own code
        [sys.executable, "-c", _LATE_MESSAGE, str(tmp_path), mode],
        env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "survived" in proc.stdout


def test_a_recorder_listens_in_and_then_steps_aside(qtbot) -> None:  # noqa: ARG001
    """A render inside the running app (or inside a test driver's own recorder) must not
    steal messages: whoever listened before still hears every one, and gets its
    handler back afterwards."""
    from PyQt6.QtCore import qInstallMessageHandler, qWarning

    from open_garden_planner.ui.view3d.quick3d.qt_messages import install, uninstall

    seen: list[str] = []

    def outer(_mode: object, _context: object, text: str | None) -> None:
        seen.append(text or "")

    before = qInstallMessageHandler(outer)
    try:
        recorder = QtMessages()
        previous = install(recorder)
        qWarning("inside the render")
        uninstall(previous)
        qWarning("after the render")
    finally:
        qInstallMessageHandler(before)
    assert recorder.warnings == ["warning: inside the render"]
    assert seen == ["inside the render", "after the render"]


def test_nested_recorders_both_hear_an_error(qtbot) -> None:  # noqa: ARG001
    """The render driver records a whole run while ``render_records`` records one frame:
    a shader error inside the frame must reach both."""
    from PyQt6.QtCore import qInstallMessageHandler, qWarning

    from open_garden_planner.ui.view3d.quick3d.qt_messages import install, uninstall

    quiet = qInstallMessageHandler(lambda *_args: None)  # keep the test's stderr clean
    try:
        whole_run, one_frame = QtMessages(), QtMessages()
        first = install(whole_run)
        second = install(one_frame)
        qWarning(SHADER_PARSE)
        uninstall(second)
        uninstall(first)
    finally:
        qInstallMessageHandler(quiet)
    assert len(one_frame.errors) == 1 and len(whole_run.errors) == 1
