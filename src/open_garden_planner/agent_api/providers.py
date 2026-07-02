"""Provider bundle injected into the Agent API server (Qt-free).

The server thread must never touch Qt directly. Instead the GUI passes a bundle
of callables that each already hop to the Qt main thread (via
:class:`~open_garden_planner.agent_api.bridge.MainThreadBridge`) and return plain
data. Bundling them keeps :func:`~open_garden_planner.agent_api.server.build_server`
stable as the surface grows: US-D1.2 needs ``snapshot`` + ``diagnostics``; US-D1.3
adds ``render``; later stories add exports/save (D1.4) and write ops (D2) as new
fields.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


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
    """

    snapshot: Callable[[], dict[str, Any]]
    diagnostics: Callable[[], list[dict[str, Any]]]
    render: Callable[
        [tuple[float, float, float, float] | None, list[str] | None, int],
        dict[str, Any],
    ]
