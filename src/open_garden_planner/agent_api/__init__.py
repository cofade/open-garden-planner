"""Agent API: an opt-in, loopback-only MCP server embedded in the app.

Lets AI agents (Claude, Cursor, any MCP client) read the garden plan currently
open in Open Garden Planner. See Package D / epic #237. This spike (US-D1.1)
exposes a single read tool over MCP streamable-HTTP.

``AgentApiServer``/``build_server`` are imported lazily so merely importing this
package never pulls in ``mcp``/``uvicorn``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from open_garden_planner.agent_api.bridge import MainThreadBridge
from open_garden_planner.agent_api.diagnostics import diagnostics_from_records
from open_garden_planner.agent_api.mapping import plan_summary_from_snapshot
from open_garden_planner.agent_api.providers import AgentProviders
from open_garden_planner.agent_api.schema import (
    Diagnostic,
    Measurement,
    ObjectDetail,
    ObjectRef,
    PlanSummary,
)

if TYPE_CHECKING:
    from open_garden_planner.agent_api.server import (
        AgentApiServer,
        PortInUseError,
        build_server,
    )

__all__ = [
    "AgentApiServer",
    "AgentProviders",
    "Diagnostic",
    "MainThreadBridge",
    "Measurement",
    "ObjectDetail",
    "ObjectRef",
    "PlanSummary",
    "PortInUseError",
    "build_server",
    "diagnostics_from_records",
    "plan_summary_from_snapshot",
]

_LAZY = {"AgentApiServer", "PortInUseError", "build_server"}


def __getattr__(name: str) -> Any:
    """Lazily expose server symbols without forcing ``mcp``/``uvicorn`` at import."""
    if name in _LAZY:
        from open_garden_planner.agent_api import server as _server

        return getattr(_server, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
