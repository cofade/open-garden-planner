"""Agent schema adapter for the shared Qt-free diagnostic converter."""

from dataclasses import asdict
from typing import Any

from open_garden_planner.agent_api.schema import Diagnostic
from open_garden_planner.services.diagnostics import diagnostics_from_records as convert_records


def diagnostics_from_records(records: list[dict[str, Any]], *, kind: str | None = None) -> list[Diagnostic]:
    return [Diagnostic(**asdict(record)) for record in convert_records(records, kind=kind)]
