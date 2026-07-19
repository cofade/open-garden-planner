"""End-to-end integration tests for the Agent API's export/save tools (US-D1.4).

Boots ``AgentApiServer`` in-process against a real scene (mirroring
``test_agent_api_server.py``/``test_agent_api_render.py``'s pattern), drives a
real MCP client, and verifies the file each tool writes is genuinely valid —
not just "no exception raised" — by round-tripping it through the same
libraries the GUI's own export tests use (``ezdxf.readfile``, the PDF magic
header, ``csv.DictReader``).
"""

from __future__ import annotations

import asyncio
import socket
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from open_garden_planner.agent_api import (
    AgentApiServer,
    AgentProviders,
    MainThreadBridge,
)
from open_garden_planner.agent_api.exports import (
    export_csv_file,
    export_dxf_file,
    export_pdf_file,
    save_plan_file,
)
from open_garden_planner.agent_api.render import render_canvas_image
from open_garden_planner.app import paths as paths_module
from open_garden_planner.core import ProjectManager
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.harvest_log import HarvestHistory, HarvestRecord
from open_garden_planner.services.soil_service import SoilService
from open_garden_planner.ui.canvas.items import CircleItem, RectangleItem


@pytest.fixture(autouse=True)
def _redirect_documents_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never touch the real Documents folder — default-path tests stay hermetic."""
    monkeypatch.setattr(paths_module, "get_documents_dir", lambda: tmp_path)


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _providers(
    scene: Any, project_manager: ProjectManager, soil_service: SoilService
) -> AgentProviders:
    bridge = MainThreadBridge()
    return AgentProviders(
        snapshot=lambda: bridge.run_on_main(lambda: project_manager.snapshot_dict(scene)),
        diagnostics=lambda: bridge.run_on_main(
            lambda: project_manager.diagnostics_snapshot(scene)
        ),
        render=lambda region, layers, width_px: bridge.run_on_main(
            lambda: render_canvas_image(scene, region, layers, width_px)
        ),
        save_plan=lambda file_path: bridge.run_on_main(
            lambda: save_plan_file(scene, project_manager, soil_service, file_path)
        ),
        export_pdf=lambda file_path, paper_size, orientation: bridge.run_on_main(
            lambda: export_pdf_file(
                scene, project_manager, file_path, paper_size, orientation
            )
        ),
        export_dxf=lambda file_path: bridge.run_on_main(
            lambda: export_dxf_file(scene, project_manager, file_path)
        ),
        export_csv=lambda kind, file_path: bridge.run_on_main(
            lambda: export_csv_file(scene, project_manager, soil_service, kind, file_path)
        ),
        # Write providers are unused by these export tests.
        move_object=lambda *_a: _unused("move_object"),
        delete_object=lambda *_a: _unused("delete_object"),
    )


def _unused(name: str) -> dict[str, Any]:
    raise AssertionError(f"{name} should not be called in an export test")


def _drive(server: AgentApiServer, body: Callable[[Any], Any], result: dict[str, Any]) -> None:
    """Run an MCP client session against ``server`` and call ``body(session)``."""

    async def run() -> None:
        from mcp import ClientSession

        try:  # SDK renamed it; fall back for the pinned floor (mcp>=1.12)
            from mcp.client.streamable_http import (
                streamable_http_client as http_client,
            )
        except ImportError:
            from mcp.client.streamable_http import (
                streamablehttp_client as http_client,
            )

        async with (
            http_client(server.url) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            await body(session)

    try:
        asyncio.run(run())
    except Exception as exc:  # noqa: BLE001 - surface to the assertion below
        result["error"] = exc
    finally:
        result["done"] = True


def _add_plant(scene: Any, common_name: str, source_id: str) -> CircleItem:
    plant = CircleItem(
        center_x=100, center_y=100, radius=20,
        object_type=ObjectType.PERENNIAL,
        name=common_name,
    )
    plant.metadata["plant_species"] = {"common_name": common_name, "source_id": source_id}
    plant.metadata["plant_instance"] = {"current_spread_cm": 30.0}
    scene.addItem(plant)
    return plant


def _run(
    server: AgentApiServer, qtbot: Any, result: dict[str, Any], body: Callable[[Any], Any]
) -> None:
    """Drive ``body`` against ``server`` and block until done, writing into ``result``.

    ``result`` must be the same dict object ``body`` closes over — mutated in
    place, not replaced, so ``body``'s writes and this function's done/error
    bookkeeping land on one shared object.
    """
    threading.Thread(
        target=_drive, args=(server, body, result), name="mcp-test-client"
    ).start()
    qtbot.waitUntil(lambda: result.get("done", False), timeout=15000)
    assert result.get("error") is None, result.get("error")


# ---------------------------------------------------------------------------
# save_plan
# ---------------------------------------------------------------------------


def test_save_plan_no_file_open_errors(canvas: Any, qtbot: Any) -> None:
    scene = canvas.scene()
    project_manager = ProjectManager()
    soil_service = SoilService(project_manager)
    server = AgentApiServer(_providers(scene, project_manager, soil_service), port=_free_port())
    server.start()

    result: dict[str, Any] = {}

    async def body(session: Any) -> None:
        result["call"] = await session.call_tool("save_plan", {})

    try:
        _run(server, qtbot, result, body)
        assert result["call"].isError is True
    finally:
        server.stop()


def test_save_plan_saves_to_current_file(canvas: Any, qtbot: Any, tmp_path: Path) -> None:
    scene = canvas.scene()
    scene.addItem(RectangleItem(0, 0, 100, 80))
    project_manager = ProjectManager()
    existing = tmp_path / "existing.ogp"
    project_manager.save(scene, existing)
    soil_service = SoilService(project_manager)
    server = AgentApiServer(_providers(scene, project_manager, soil_service), port=_free_port())
    server.start()

    result: dict[str, Any] = {}

    async def body(session: Any) -> None:
        result["call"] = await session.call_tool("save_plan", {})

    try:
        _run(server, qtbot, result, body)
        payload = result["call"].structuredContent
        assert payload["format"] == "ogp"
        assert payload["file_path"] == str(existing)
        assert payload["previous_file_path"] is None
        assert existing.exists()
    finally:
        server.stop()


def test_save_plan_save_as_new_path_reports_previous(
    canvas: Any, qtbot: Any, tmp_path: Path
) -> None:
    scene = canvas.scene()
    project_manager = ProjectManager()
    original = tmp_path / "original.ogp"
    project_manager.save(scene, original)
    soil_service = SoilService(project_manager)
    server = AgentApiServer(_providers(scene, project_manager, soil_service), port=_free_port())
    server.start()

    new_path = tmp_path / "renamed.ogp"

    result: dict[str, Any] = {}

    async def body(session: Any) -> None:
        result["call"] = await session.call_tool("save_plan", {"file_path": str(new_path)})

    try:
        _run(server, qtbot, result, body)
        payload = result["call"].structuredContent
        assert payload["file_path"] == str(new_path)
        assert payload["previous_file_path"] == str(original)
        assert new_path.exists()
        assert project_manager.current_file == new_path
    finally:
        server.stop()


def test_save_plan_first_save_reports_null_previous_file(
    canvas: Any, qtbot: Any, tmp_path: Path
) -> None:
    """A never-saved project's first save-as must report previous_file_path as
    null, not the literal string "None" (regression: previous_file_path started
    as None, and `str(None) if previous_file_path != final_path else None` was
    True for a first save, stringifying None instead of reporting null)."""
    scene = canvas.scene()
    project_manager = ProjectManager()
    assert project_manager.current_file is None
    soil_service = SoilService(project_manager)
    server = AgentApiServer(_providers(scene, project_manager, soil_service), port=_free_port())
    server.start()

    new_path = tmp_path / "first_save.ogp"

    async def body(session: Any) -> None:
        result["call"] = await session.call_tool("save_plan", {"file_path": str(new_path)})

    result: dict[str, Any] = {}
    try:
        _run(server, qtbot, result, body)
        payload = result["call"].structuredContent
        assert payload["file_path"] == str(new_path)
        assert payload["previous_file_path"] is None
        assert new_path.exists()
    finally:
        server.stop()


# ---------------------------------------------------------------------------
# export_pdf
# ---------------------------------------------------------------------------


def test_export_pdf_default_and_explicit_path(canvas: Any, qtbot: Any, tmp_path: Path) -> None:
    scene = canvas.scene()
    scene.addItem(RectangleItem(0, 0, 100, 80))
    project_manager = ProjectManager()
    soil_service = SoilService(project_manager)
    server = AgentApiServer(_providers(scene, project_manager, soil_service), port=_free_port())
    server.start()

    explicit_path = tmp_path / "custom_report.pdf"

    result: dict[str, Any] = {}

    async def body(session: Any) -> None:
        result["default_call"] = await session.call_tool("export_pdf", {})
        result["explicit_call"] = await session.call_tool(
            "export_pdf",
            {
                "file_path": str(explicit_path),
                "paper_size": "Letter",
                "orientation": "portrait",
            },
        )

    try:
        _run(server, qtbot, result, body)

        default_payload = result["default_call"].structuredContent
        assert default_payload["format"] == "pdf"
        default_path = Path(default_payload["file_path"])
        assert default_path.exists()
        assert default_path.read_bytes()[:5] == b"%PDF-"

        explicit_payload = result["explicit_call"].structuredContent
        assert explicit_payload["file_path"] == str(explicit_path)
        assert explicit_path.exists()
        assert explicit_path.read_bytes()[:5] == b"%PDF-"
    finally:
        server.stop()


# ---------------------------------------------------------------------------
# export_dxf
# ---------------------------------------------------------------------------


def test_export_dxf_round_trips(canvas: Any, qtbot: Any, tmp_path: Path) -> None:
    import ezdxf

    scene = canvas.scene()
    scene.addItem(RectangleItem(0, 0, 200, 100))
    project_manager = ProjectManager()
    soil_service = SoilService(project_manager)
    server = AgentApiServer(_providers(scene, project_manager, soil_service), port=_free_port())
    server.start()

    explicit_path = tmp_path / "custom.dxf"
    result: dict[str, Any] = {}

    async def body(session: Any) -> None:
        result["call"] = await session.call_tool(
            "export_dxf", {"file_path": str(explicit_path)}
        )

    try:
        _run(server, qtbot, result, body)
        payload = result["call"].structuredContent
        assert payload["format"] == "dxf"
        assert payload["file_path"] == str(explicit_path)
        doc = ezdxf.readfile(str(explicit_path))
        types = [e.dxftype() for e in doc.modelspace()]
        assert "LWPOLYLINE" in types
    finally:
        server.stop()


# ---------------------------------------------------------------------------
# export_csv
# ---------------------------------------------------------------------------


def test_export_csv_shopping_list(canvas: Any, qtbot: Any) -> None:
    import csv

    scene = canvas.scene()
    _add_plant(scene, "Tomato", "solanum_lycopersicum")
    project_manager = ProjectManager()
    soil_service = SoilService(project_manager)
    server = AgentApiServer(_providers(scene, project_manager, soil_service), port=_free_port())
    server.start()

    result: dict[str, Any] = {}

    async def body(session: Any) -> None:
        result["call"] = await session.call_tool(
            "export_csv", {"kind": "shopping_list"}
        )

    try:
        _run(server, qtbot, result, body)
        payload = result["call"].structuredContent
        assert payload["format"] == "csv"
        assert payload["row_count"] >= 1
        path = Path(payload["file_path"])
        with open(path, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == payload["row_count"]
        assert "Tomato" in {r["name"] for r in rows}
    finally:
        server.stop()


def test_export_csv_harvest(canvas: Any, qtbot: Any) -> None:
    import csv

    scene = canvas.scene()
    project_manager = ProjectManager()
    project_manager.set_harvest_history(
        "plant-1",
        HarvestHistory(
            target_id="plant-1",
            species_key="tomato",
            species_name="Tomato",
            records=[HarvestRecord(date="2026-06-01", quantity=2.5, unit="kg")],
        ),
    )
    soil_service = SoilService(project_manager)
    server = AgentApiServer(_providers(scene, project_manager, soil_service), port=_free_port())
    server.start()

    result: dict[str, Any] = {}

    async def body(session: Any) -> None:
        result["call"] = await session.call_tool("export_csv", {"kind": "harvest"})

    try:
        _run(server, qtbot, result, body)
        payload = result["call"].structuredContent
        assert payload["format"] == "csv"
        assert payload["row_count"] == 1
        path = Path(payload["file_path"])
        with open(path, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 1
        assert rows[0]["species"] == "Tomato"
    finally:
        server.stop()
