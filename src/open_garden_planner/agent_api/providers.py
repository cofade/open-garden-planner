"""Provider bundle injected into the Agent API server (Qt-free).

The server thread must never touch Qt directly. Instead the GUI passes a bundle
of callables that each already hop to the Qt main thread (via
:class:`~open_garden_planner.agent_api.bridge.MainThreadBridge`) and return plain
data. Bundling them keeps :func:`~open_garden_planner.agent_api.server.build_server`
stable as the surface grows: US-D1.2 needs ``snapshot`` + ``diagnostics``; US-D1.3
adds ``render``; US-D1.4 adds ``save_plan``/``export_pdf``/``export_dxf``/
``export_csv``; later stories add write ops (D2) as new fields.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class AgentProviders:
    """Main-thread-marshaled data sources the MCP tools read from.

    Args:
        snapshot: Returns a read-only ``.ogp``-shaped dict of the live plan
            (``ProjectManager.snapshot_dict``).
        diagnostics: Returns the plan's harvested warning-flag records
            (``ProjectManager.diagnostics_snapshot``).
        render: Renders a PNG of the live plan. Takes an optional region
            (x, y, width, height in scene cm; ``None`` = full canvas), an
            optional layer-name allowlist, and a requested pixel width; returns
            a plain dict with ``png_bytes`` and render metadata
            (``agent_api.render.render_canvas_image``). Unlike ``snapshot``/
            ``diagnostics`` this callable takes parameters — it resolves the
            default region and does the hide/render/encode work in one atomic
            main-thread hop.
        save_plan: Saves the live plan to its ``.ogp`` file (or a new path,
            i.e. Save As). Takes an optional destination path; returns a plain
            dict (``agent_api.exports.save_plan_file``).
        export_pdf: Renders the full garden PDF report. Takes an optional
            destination path, paper size, and orientation; returns a plain
            dict (``agent_api.exports.export_pdf_file``).
        export_dxf: Exports the plan to a DXF drawing. Takes an optional
            destination path; returns a plain dict
            (``agent_api.exports.export_dxf_file``).
        export_csv: Exports a CSV — the shopping list or garden-wide harvest
            totals. Takes the kind and an optional destination path; returns a
            plain dict, including a row count
            (``agent_api.exports.export_csv_file``).
        move_object: **Write (D2).** Moves one object by a relative offset
            (dx, dy in scene cm; +x east, +y north — the canvas is Y-up, so a
            negative dy moves south). Takes ``(item_id, dx, dy)``; runs one
            undoable move command on the main thread and returns a plain
            ``WriteResult``-shaped dict. Raises if the id is unknown.
        delete_object: **Write (D2).** Deletes one object by id. Takes
            ``(item_id,)``; runs one undoable ``DeleteItemsCommand`` on the main
            thread and returns a plain ``WriteResult``-shaped dict. Raises if the
            id is unknown.
    """

    snapshot: Callable[[], dict[str, Any]]
    diagnostics: Callable[[], list[dict[str, Any]]]
    render: Callable[
        [tuple[float, float, float, float] | None, list[str] | None, int],
        dict[str, Any],
    ]
    save_plan: Callable[[str | None], dict[str, Any]]
    export_pdf: Callable[
        [str | None, Literal["A4", "A3", "Letter", "Legal"], Literal["landscape", "portrait"]],
        dict[str, Any],
    ]
    export_dxf: Callable[[str | None], dict[str, Any]]
    export_csv: Callable[[Literal["shopping_list", "harvest"], str | None], dict[str, Any]]
    move_object: Callable[[str, float, float], dict[str, Any]]
    delete_object: Callable[[str], dict[str, Any]]
