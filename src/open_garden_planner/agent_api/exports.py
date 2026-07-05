"""File-producing tools for the Agent API (US-D1.4): save_plan, export_pdf, export_dxf, export_csv.

Unlike ``queries.py``/``diagnostics.py`` (deliberately Qt-free), this module
touches Qt (``CanvasScene``) and the filesystem — it writes real files to disk
by calling the exact same services the GUI's File > Export/Save menu already
calls (``PdfReportService``, ``DxfExportService``, ``ExportService``,
``ShoppingListService``, ``ProjectManager.save``). Each ``*_file`` function
must run on the Qt main thread (marshaled via ``MainThreadBridge.run_on_main``,
same as the other providers).

Path handling: with no dialog available to an agent caller, ``resolve_export_path``
picks a default location via the same ``app/paths.py`` chokepoint (the #199/#204
data-loss fix) the GUI dialogs use — next to the currently open project, or
``<Documents>/Open Garden Planner`` if nothing is open yet. An explicit path is
honored as given (suffix forced, parent directory must already exist) — this
server is loopback-only (ADR-033): a local MCP client already has the same
filesystem access as the OS user account, so path sandboxing beyond "parent
must exist" would not add real protection, only avoid a typo silently creating
a surprise directory tree.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from open_garden_planner.app.paths import default_dialog_dir, default_save_path
from open_garden_planner.services.dxf_service import DxfExportService
from open_garden_planner.services.export_service import ExportService
from open_garden_planner.services.pdf_report_service import PdfReportOptions, PdfReportService
from open_garden_planner.services.shopping_list_service import ShoppingListService

if TYPE_CHECKING:
    from open_garden_planner.core.project import ProjectManager
    from open_garden_planner.services.soil_service import SoilService
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

CsvKind = Literal["shopping_list", "harvest"]
PaperSize = Literal["A4", "A3", "Letter", "Legal"]
Orientation = Literal["landscape", "portrait"]


def resolve_export_path(
    requested: str | None,
    *,
    default_filename: str | None = None,
    suffix: str,
    project_manager: ProjectManager,
) -> Path:
    """Resolve a file-producing tool's target path — no dialog available to pick one.

    ``requested is None`` -> the same default location the GUI's export dialogs
    open in (``default_save_path``: next to the current project, or
    ``<Documents>/Open Garden Planner``), named ``default_filename`` (required
    in this branch). A given path is expanded and, if relative, resolved
    against that same default directory; either way ``suffix`` is
    force-applied (mirrors every ``_on_export_*`` handler's own
    ``.with_suffix()`` call) and the parent directory must already exist —
    mirrors what a save dialog would allow, and avoids silently creating an
    arbitrary directory tree from a typo'd path.
    """
    if requested is None:
        if default_filename is None:
            raise ValueError("default_filename is required when requested is None.")
        path = Path(default_save_path(default_filename, project_manager.current_file))
    else:
        path = Path(requested).expanduser()
        if not path.is_absolute():
            path = default_dialog_dir(project_manager.current_file) / path
    path = path.with_suffix(suffix)
    if not path.parent.is_dir():
        raise ValueError(f"Parent directory does not exist: {path.parent}")
    return path


def save_plan_file(
    scene: CanvasScene,
    project_manager: ProjectManager,
    soil_service: SoilService,
    file_path: str | None,
) -> dict[str, Any]:
    """Save the live plan to ``.ogp`` — ``ProjectManager.save``, Save / Save As semantics.

    ``file_path is None`` requires a project already open (``current_file``
    set) — mirrors the GUI, where a brand-new project always needs an explicit
    Save-As dialog interaction before a filename exists; this tool won't
    silently invent one. Not overwrite-safe: an explicit ``file_path`` pointing
    at an unrelated existing file is overwritten without the confirmation a
    ``QFileDialog`` would give a human — acceptable only under the loopback
    trust model (ADR-033), same as every other file-producing tool here.

    Mirrors ``application._save_to_file`` exactly, including pruning stale
    shopping-list price entries (issue #178) before writing, so an agent-saved
    ``.ogp`` doesn't drift from what the GUI would have produced.
    """
    previous_file_path = project_manager.current_file
    if file_path is None:
        if previous_file_path is None:
            raise ValueError(
                "No file is currently open — pass file_path to save as a new file."
            )
        resolved = previous_file_path
    else:
        resolved = resolve_export_path(file_path, suffix=".ogp", project_manager=project_manager)
    ShoppingListService(scene, soil_service, project_manager).prune_stale_prices()
    project_manager.save(scene, resolved)
    final_path = project_manager.current_file
    if final_path is None:
        raise RuntimeError("ProjectManager.save() did not set current_file.")
    return {
        "file_path": str(final_path),
        "format": "ogp",
        "row_count": None,
        "previous_file_path": (
            str(previous_file_path)
            if previous_file_path is not None and previous_file_path != final_path
            else None
        ),
    }


def export_pdf_file(
    scene: CanvasScene,
    project_manager: ProjectManager,
    file_path: str | None,
    paper_size: PaperSize,
    orientation: Orientation,
) -> dict[str, Any]:
    """Render the full garden PDF report — same pipeline as File > Export PDF Report."""
    resolved = resolve_export_path(
        file_path,
        default_filename=project_manager.project_name + ".pdf",
        suffix=".pdf",
        project_manager=project_manager,
    )
    opts = PdfReportOptions(
        paper_size=paper_size,
        orientation=orientation,
        project_name=project_manager.project_name,
    )
    PdfReportService.generate(scene, opts, resolved)
    return {"file_path": str(resolved), "format": "pdf", "row_count": None, "previous_file_path": None}


def export_dxf_file(
    scene: CanvasScene,
    project_manager: ProjectManager,
    file_path: str | None,
) -> dict[str, Any]:
    """Export the plan to DXF — same pipeline as File > Export as DXF."""
    resolved = resolve_export_path(
        file_path,
        default_filename=project_manager.project_name + ".dxf",
        suffix=".dxf",
        project_manager=project_manager,
    )
    DxfExportService.export(scene, resolved)
    return {"file_path": str(resolved), "format": "dxf", "row_count": None, "previous_file_path": None}


def export_csv_file(
    scene: CanvasScene,
    project_manager: ProjectManager,
    soil_service: SoilService,
    kind: CsvKind,
    file_path: str | None,
) -> dict[str, Any]:
    """Export a CSV — shopping list or garden-wide harvest totals.

    Same underlying data + writer as the shopping-list dialog's CSV export and
    the Harvest dashboard's CSV export, respectively.
    """
    if kind == "shopping_list":
        default_filename = project_manager.project_name + "_shopping_list.csv"
    elif kind == "harvest":
        default_filename = project_manager.project_name + "_harvest.csv"
    else:
        raise ValueError(f"Unknown csv kind: {kind!r}")

    resolved = resolve_export_path(
        file_path,
        default_filename=default_filename,
        suffix=".csv",
        project_manager=project_manager,
    )
    if kind == "shopping_list":
        items = ShoppingListService(scene, soil_service, project_manager).build()
        row_count = ExportService.export_shopping_list_to_csv(items, resolved)
    else:
        row_count = ExportService.export_harvest_to_csv(project_manager.harvest_logs, resolved)
    return {
        "file_path": str(resolved),
        "format": "csv",
        "row_count": row_count,
        "previous_file_path": None,
    }
