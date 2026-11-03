"""``render_3d_view`` over the real MCP transport (Phase 17 L6.3, #390, ADR-034 addendum).

A real server and a real client against a stand-in provider: the tool's surface, its
validation, and above all its refusal, which must reach the client as a clean sentence at
once and not as a timeout. The provider's own behaviour on a real workspace and engine is
in ``test_directors_cut.py`` and ``test_directors_cut_render.py``.
"""

from __future__ import annotations

import base64
import json
import threading
import time
from typing import Any

import pytest
from PyQt6.QtCore import QBuffer, QIODevice, Qt
from PyQt6.QtGui import QImage

from open_garden_planner.ui.view3d.workspace_capture import BLOCKERS, CaptureRefused
from tests.agent_api_helpers import start_server
from tests.integration.test_agent_api_render import _drive, _providers


def png(width: int, height: int) -> bytes:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.darkGreen)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def answer(shot: Any, size: tuple[int, int]) -> dict[str, Any]:
    return {
        "png_bytes": png(*size), "image_width_px": size[0], "image_height_px": size[1],
        "eye": shot[0] if shot else (1.0, 2.0, 3.0), "target": shot[1] if shot else (4.0, 5.0, 6.0),
        "fov_deg": shot[2] if shot else 40.0, "plan_date": "2026-06-21", "time_of_day": "15:00",
        "sun_elevation_deg": 54.0, "sun_azimuth_deg": 227.0, "weather": "clear",
        "quality_preset": "high", "roofs_hidden": False, "overlays": [],
    }


class Stand:
    """The provider: records what it was asked, and answers or refuses."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, tuple[int, int]]] = []
        self.refuse: str | None = None

    def __call__(self, shot: Any, size: tuple[int, int]) -> dict[str, Any]:
        self.calls.append((shot, size))
        if self.refuse is not None:
            raise CaptureRefused(self.refuse)
        return answer(shot, size)


def call(canvas: Any, qtbot: Any, stand: Stand | None, arguments: dict[str, Any]) -> dict[str, Any]:
    from dataclasses import replace

    server, _ = start_server(replace(_providers(canvas.scene()), render_3d=stand))
    result: dict[str, Any] = {}

    async def body(session: Any) -> None:
        tools = await session.list_tools()
        result["tools"] = {tool.name: tool for tool in tools.tools}
        started = time.monotonic()
        result["call"] = await session.call_tool("render_3d_view", arguments)
        result["seconds"] = time.monotonic() - started

    threading.Thread(target=_drive, args=(server, body, result), name="mcp-test-client").start()
    try:
        qtbot.waitUntil(lambda: result.get("done", False), timeout=15000)
        assert result.get("error") is None, result.get("error")
    finally:
        server.stop()
    return result


def picture(result: dict[str, Any]) -> tuple[QImage, dict[str, Any]]:
    call_result = result["call"]
    assert call_result.isError is not True, call_result.content
    assert call_result.structuredContent is None
    image_block, text_block = call_result.content
    assert image_block.type == "image" and image_block.mimeType == "image/png"
    image = QImage.fromData(base64.b64decode(image_block.data))
    return image, json.loads(text_block.text)


def test_the_tool_is_there_needs_no_token_and_says_what_it_shows(canvas: Any, qtbot: Any) -> None:
    """Read-only: registered without any token, and the owner's view when no camera is named."""
    stand = Stand()
    result = call(canvas, qtbot, stand, {})
    assert "render_3d_view" in result["tools"]
    image, meta = picture(result)
    assert stand.calls == [(None, (1280, 720))]
    assert (image.width(), image.height()) == (1280, 720)
    assert meta["image_width_px"] == 1280 and meta["image_height_px"] == 720
    assert meta["plan_date"] == "2026-06-21" and meta["time_of_day"] == "15:00"
    assert meta["sun_elevation_deg"] == 54.0 and meta["weather"] == "clear"
    assert meta["roofs_hidden"] is False and meta["overlays"] == []
    assert "png_bytes" not in meta


def test_a_camera_of_its_own_reaches_the_provider_unchanged(canvas: Any, qtbot: Any) -> None:
    stand = Stand()
    result = call(canvas, qtbot, stand, {
        "eye_x": 100.0, "eye_y": -200.0, "eye_z": 300.0, "target_x": 400.0, "target_y": 500.0,
        "target_z": 60.0, "fov_deg": 55.0, "image_width_px": 512, "image_height_px": 256})
    assert stand.calls == [(((100.0, -200.0, 300.0), (400.0, 500.0, 60.0), 55.0), (512, 256))]
    _image, meta = picture(result)
    assert meta["eye"] == [100.0, -200.0, 300.0] and meta["fov_deg"] == 55.0


@pytest.mark.parametrize(("asked", "got"), [((50, 50), (128, 128)), ((9000, 9000), (2048, 2048)),
                                            ((1000, 300), (1000, 300))])
def test_the_picture_size_is_clamped_like_the_canvas_render(
        canvas: Any, qtbot: Any, asked: tuple[int, int], got: tuple[int, int]) -> None:
    stand = Stand()
    call(canvas, qtbot, stand, {"image_width_px": asked[0], "image_height_px": asked[1]})
    assert stand.calls[0][1] == got


@pytest.mark.parametrize("code", sorted(BLOCKERS))
def test_a_refusal_is_a_clean_sentence_at_once_never_a_timeout(canvas: Any, qtbot: Any, code: str) -> None:
    """The issue's words: a clean "warming up" refusal instead of a 5 s timeout."""
    stand = Stand()
    stand.refuse = code
    result = call(canvas, qtbot, stand, {})
    outcome = result["call"]
    assert outcome.isError is True
    text = outcome.content[0].text
    assert BLOCKERS[code] in text
    assert "Nothing was changed" in text
    assert result["seconds"] < 2.0, "it says so at once"


@pytest.mark.parametrize("arguments", [
    {"eye_x": 1.0},                                                 # half a camera
    {"eye_x": 1.0, "eye_y": 2.0, "eye_z": 3.0},                     # an eye without a target
    {"target_x": 1.0, "target_y": 2.0, "target_z": 3.0},
    {"eye_x": 1.0, "eye_y": 2.0, "eye_z": 3.0, "target_x": 1.0, "target_y": 2.0, "target_z": 3.0},
    {"eye_x": 1e9, "eye_y": 2.0, "eye_z": 3.0, "target_x": 0.0, "target_y": 0.0, "target_z": 0.0},
    {"eye_x": float("nan"), "eye_y": 2.0, "eye_z": 3.0, "target_x": 0.0, "target_y": 0.0,
     "target_z": 0.0},
    {"eye_x": 1.0, "eye_y": 2.0, "eye_z": 3.0, "target_x": 0.0, "target_y": 0.0, "target_z": 0.0,
     "fov_deg": 170.0},
    {"eye_x": 1.0, "eye_y": 2.0, "eye_z": 3.0, "target_x": 0.0, "target_y": 0.0, "target_z": 0.0,
     "fov_deg": 1.0},
])
def test_a_camera_that_cannot_be_is_refused_before_the_main_thread_is_asked(
        canvas: Any, qtbot: Any, arguments: dict[str, Any]) -> None:
    stand = Stand()
    result = call(canvas, qtbot, stand, arguments)
    assert result["call"].isError is True
    assert stand.calls == []


def test_a_server_without_a_3d_view_says_so(canvas: Any, qtbot: Any) -> None:
    result = call(canvas, qtbot, None, {})
    assert result["call"].isError is True
    assert "no 3D view" in result["call"].content[0].text


def test_the_tools_description_tells_an_agent_what_to_do(canvas: Any, qtbot: Any) -> None:
    result = call(canvas, qtbot, Stand(), {})
    description = result["tools"]["render_3d_view"].description
    assert "Read-only" in description and "never moves" in description
    assert "open 3D or Split" in description


def test_the_application_builds_its_provider_with_the_tool(qtbot: Any) -> None:
    """The one production provider graph has it: a tool wired only in tests is no tool."""
    from open_garden_planner.app.application import GardenPlannerApp

    window = GardenPlannerApp()
    qtbot.addWidget(window)
    providers = window._agent_host._build_agent_providers()
    assert providers.render_3d is not None
    with pytest.raises(CaptureRefused) as refused:
        providers.render_3d(None, (640, 360))   # no 3D view was ever opened in this window
    assert refused.value.code == "not_open"
    assert window._workspace.host is None, "and it built none"
