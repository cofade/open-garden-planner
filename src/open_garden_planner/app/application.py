"""Main application window."""

import contextlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QCloseEvent, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.app.paths import default_dialog_dir, default_save_path
from open_garden_planner.core import (
    ProjectManager,
    calculate_area_and_perimeter,
    format_area,
    format_length,
)
from open_garden_planner.core.plant_renderer import is_plant_type
from open_garden_planner.core.tools import ToolType
from open_garden_planner.services.companion_planting_service import (
    ANTAGONISTIC,
    BENEFICIAL,
    CompanionPlantingService,
)
from open_garden_planner.services.export_service import ExportService
from open_garden_planner.services.soil_service import (
    ALL_PARAMS,
    PARAM_K,
    PARAM_N,
    PARAM_OVERALL,
    PARAM_P,
    PARAM_PH,
    SoilService,
)
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.panels import (
    CompanionPanel,
    ConstraintsPanel,
    CropRotationPanel,
    JournalPanel,
    LayersPanel,
    PestOverviewPanel,
    PlantDatabasePanel,
    PlantSearchPanel,
    PropertiesPanel,
    SmartSymbolsPanel,
)
from open_garden_planner.ui.theme import ThemeMode, apply_theme
from open_garden_planner.ui.views.harvest_view import HarvestView
from open_garden_planner.ui.views.planting_calendar_view import PlantingCalendarView
from open_garden_planner.ui.views.seed_inventory_view import SeedInventoryView
from open_garden_planner.ui.views.tasks_view import TasksView
from open_garden_planner.ui.widgets import (
    CategoryToolbar,
    CollapsiblePanel,
    ConstraintToolbar,
    MainToolbar,
    SidebarController,
    TaskReminderBar,
    UpdateBar,
)

if TYPE_CHECKING:
    from open_garden_planner.agent_api import AgentApiServer

logger = logging.getLogger(__name__)


def _records_equivalent(a: object, b: object) -> bool:
    """True iff two SoilTestRecord instances match field-by-field, ignoring id and date.

    Used by ``_open_soil_test_dialog`` (F12 / F2.6c) to skip ``AddSoilTestCommand``
    when the user clicks OK without changing the entry tab — common after using
    Edit-via-History, which already committed the change via ``EditSoilTestCommand``.
    """
    if a is None or b is None:
        return False
    fields = (
        "ph",
        "n_level", "p_level", "k_level",
        "ca_level", "mg_level", "s_level",
        "n_ppm", "p_ppm", "k_ppm",
        "ca_ppm", "mg_ppm", "s_ppm",
        "notes",
        "mode",
    )
    return all(getattr(a, f, None) == getattr(b, f, None) for f in fields)


def _should_skip_add_after_dialog(
    form_record: object,
    existing_pre_dialog: object,
    latest_after_dialog: object,
) -> bool:
    """Decide whether to skip ``AddSoilTestCommand`` after the soil test dialog closes.

    Two cases must skip the Add:

    1. **No-op outer OK.** The user clicked OK without touching the entry
       tab. The form values therefore equal the originally-shown
       ``existing_pre_dialog`` record — this also covers the
       Edit-via-History flow where an inner ``EditSoilTestCommand`` already
       committed the change but the outer entry tab still displays the
       *pre-edit* values. Comparing against ``latest_after_dialog`` alone
       would miss this case (regression discovered 2026-05-07).

    2. **Form happens to match the current latest.** Defensive: if the
       form ended up identical to whatever record is currently latest
       (e.g. user re-typed the existing values), don't append a duplicate.

    Otherwise return False so the Add proceeds normally.
    """
    if existing_pre_dialog is not None and _records_equivalent(
        form_record, existing_pre_dialog
    ):
        return True
    return latest_after_dialog is not None and _records_equivalent(
        form_record, latest_after_dialog
    )


class GardenPlannerApp(QMainWindow):
    """Main application window for Open Garden Planner.

    Provides the main window with menu bar, status bar, and central widget area.
    """

    def __init__(self) -> None:
        """Initialize the main window."""
        super().__init__()

        self.setMinimumSize(800, 600)

        # Persistent UI state (window geometry, main splitter)
        from open_garden_planner.app.ui_state import UiStateStore
        self._ui_state = UiStateStore()

        # Project manager for save/load
        self._project_manager = ProjectManager(self)
        self._project_manager.project_changed.connect(self._update_window_title)
        self._project_manager.dirty_changed.connect(self._update_window_title)
        self._project_manager.location_changed.connect(self._on_location_changed)
        self._project_manager.crop_rotation_changed.connect(self._on_crop_rotation_changed)
        self._project_manager.season_changed.connect(self._on_season_changed)

        # Set up UI components
        self._setup_menu_bar()
        self._setup_status_bar()
        self._setup_central_widget()
        self._restore_ui_state()

        # Set up auto-save manager
        self._setup_autosave()

        # Preview mode state
        self._preview_mode = False
        self._pre_preview_state: dict | None = None

        # Initial window title
        self._update_window_title()

        # First-launch fallback: maximize. On subsequent launches the persisted
        # geometry from _restore_ui_state() above is honoured instead.
        if not self._geometry_restored:
            self.showMaximized()
        QTimer.singleShot(100, self.canvas_view.fit_in_view)

        # Check for recovery files after UI is fully loaded
        # Then show welcome dialog if enabled
        QTimer.singleShot(500, self._startup_sequence)

        # Check for updates in background (2-second delay so UI is fully ready)
        QTimer.singleShot(2000, self._start_update_check)

        # Agent API (US-D1.1): bridge + opt-in embedded MCP server.
        self._setup_agent_api()

    def _setup_agent_api(self) -> None:
        """Create the main-thread bridge and defer auto-start if the user enabled it."""
        from open_garden_planner.agent_api import MainThreadBridge

        self._agent_bridge = MainThreadBridge(self)
        self._agent_server: AgentApiServer | None = None
        # Auto-start shortly after launch (when enabled in Preferences).
        QTimer.singleShot(1500, self._maybe_start_agent_api)

    def _agent_snapshot(self) -> dict[str, Any]:
        """Read a snapshot of the live plan ON the Qt main thread (for the server)."""
        return self._agent_bridge.run_on_main(
            lambda: self._project_manager.snapshot_dict(self.canvas_scene)
        )

    def _agent_diagnostics(self) -> list[dict[str, Any]]:
        """Harvest the plan's current warnings ON the Qt main thread (for the server)."""
        return self._agent_bridge.run_on_main(
            lambda: self._project_manager.diagnostics_snapshot(self.canvas_scene)
        )

    def _agent_render(
        self,
        region: tuple[float, float, float, float] | None,
        layers: list[str] | None,
        image_width_px: int,
    ) -> dict[str, Any]:
        """Render a PNG of the live plan ON the Qt main thread (for the server)."""
        from open_garden_planner.agent_api.render import render_canvas_image

        return self._agent_bridge.run_on_main(
            lambda: render_canvas_image(self.canvas_scene, region, layers, image_width_px)
        )

    def _agent_save_plan(self, file_path: str | None) -> dict[str, Any]:
        """Save the live plan to disk ON the Qt main thread (for the server)."""
        from open_garden_planner.agent_api.exports import save_plan_file

        return self._agent_bridge.run_on_main(
            lambda: save_plan_file(
                self.canvas_scene, self._project_manager, self._soil_service, file_path
            )
        )

    def _agent_export_pdf(
        self,
        file_path: str | None,
        paper_size: Literal["A4", "A3", "Letter", "Legal"],
        orientation: Literal["landscape", "portrait"],
    ) -> dict[str, Any]:
        """Export the PDF report ON the Qt main thread (for the server)."""
        from open_garden_planner.agent_api.exports import export_pdf_file

        return self._agent_bridge.run_on_main(
            lambda: export_pdf_file(
                self.canvas_scene, self._project_manager, file_path, paper_size, orientation
            )
        )

    def _agent_export_dxf(self, file_path: str | None) -> dict[str, Any]:
        """Export a DXF drawing ON the Qt main thread (for the server)."""
        from open_garden_planner.agent_api.exports import export_dxf_file

        return self._agent_bridge.run_on_main(
            lambda: export_dxf_file(self.canvas_scene, self._project_manager, file_path)
        )

    def _agent_export_csv(
        self, kind: Literal["shopping_list", "harvest"], file_path: str | None
    ) -> dict[str, Any]:
        """Export a shopping-list/harvest CSV ON the Qt main thread (for the server)."""
        from open_garden_planner.agent_api.exports import export_csv_file

        return self._agent_bridge.run_on_main(
            lambda: export_csv_file(
                self.canvas_scene, self._project_manager, self._soil_service, kind, file_path
            )
        )

    def _agent_move_object(self, item_id: str, dx: float, dy: float) -> dict[str, Any]:
        """Move one object by (dx, dy) scene cm ON the Qt main thread (for the server)."""
        return self._agent_bridge.run_on_main(
            lambda: self._do_agent_move_object(item_id, dx, dy)
        )

    def _do_agent_move_object(
        self, item_id: str, dx: float, dy: float
    ) -> dict[str, Any]:
        """Main-thread body of ``move_object``.

        Mirrors what a drag-release does in ``CanvasView`` (invariant #13 means
        "behaves like the GUI's own move", not merely "calls a Command class"):
        a bed/container/trellis carries its contained plants along
        (``_propagate_bed_children_during_drag`` + the multi-item
        ``AlignItemsCommand`` branch at drag-release), and a moved plant has its
        bed membership re-evaluated afterward (``_update_plant_bed_relationships``).
        Skipping either step — the first cut of this tool did — silently
        abandons a bed's plants where they sit, or leaves stale
        parent/child links that soil-mismatch diagnostics then act on.

        Like the GUI, this can be ONE undo step (a lone item, no reparenting)
        or TWO (the move, plus a separate ``SetParentBedCommand`` only when the
        move actually crosses a bed boundary) — never more.

        Refuses (raises) rather than silently violating a geometric
        constraint: ``CanvasView`` runs an iterative solver
        (``_propagate_constraints_during_drag``) to move every item linked to
        the dragged one by a distance/fixed/tangent constraint, computing a
        per-item delta that generally is NOT the dragged item's own delta.
        Replicating that solver for a one-shot agent call is out of scope for
        this tool — moving a constrained item without it would silently leave
        the constraint violated, which is worse than refusing outright.
        """
        from PyQt6.QtCore import QPointF

        from open_garden_planner.core.commands import AlignItemsCommand, MoveItemsCommand

        item = self._resolve_agent_item(item_id)
        delta = QPointF(float(dx), float(dy))

        item_deltas = self._agent_move_item_deltas(item, delta)
        for constrained_item, _ in item_deltas:
            if self._agent_item_constraints(constrained_item):
                raise ValueError(
                    f"{item_id} (or a plant it contains) participates in a "
                    "geometric constraint; move_object doesn't support "
                    "constrained objects yet — remove the constraint first, "
                    "or move it from the app."
                )
        if len(item_deltas) == 1:
            move_cmd = MoveItemsCommand([item], delta)
        else:
            # Matches CanvasView's own wording: the description names the
            # primary item being moved, not every propagated child.
            from PyQt6.QtCore import QCoreApplication

            move_cmd = AlignItemsCommand(
                item_deltas, QCoreApplication.translate("Commands", "Move item")
            )
        self.canvas_view.command_manager.execute(move_cmd)

        reparented, new_parent_bed_id = self._agent_reconcile_bed_membership(item)

        cx, cy = self._agent_item_center(item)
        return {
            "item_id": item_id,
            "action": "move",
            "undo_description": move_cmd.description,
            "x": cx,
            "y": cy,
            "children_moved": len(item_deltas) - 1,
            "bed_membership_changed": reparented,
            "new_parent_bed_id": new_parent_bed_id,
        }

    def _agent_move_item_deltas(
        self, item: Any, delta: Any
    ) -> list[tuple[Any, Any]]:
        """``(item, delta)`` pairs for one move: the item plus every contained
        plant, uniformly offset — the release-time equivalent of
        ``CanvasView._propagate_bed_children_during_drag``. A plain plant/shape
        with no children returns just itself."""
        from open_garden_planner.core.object_types import is_plant_parent_type
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        item_deltas: list[tuple[Any, Any]] = [(item, delta)]
        if isinstance(item, GardenItemMixin) and is_plant_parent_type(item.object_type):
            for child_id in item.child_item_ids:
                child = self.canvas_scene.find_item_by_id(child_id)
                if child is not None:
                    item_deltas.append((child, delta))
        return item_deltas

    def _agent_reconcile_bed_membership(self, item: Any) -> tuple[bool, str | None]:
        """After moving a plant, re-evaluate its bed membership — the
        release-time equivalent of ``CanvasView._update_plant_bed_relationships``.
        Returns ``(changed, new_parent_bed_id)``; a non-plant item or an
        unchanged membership returns ``(False, None)``."""
        from open_garden_planner.core.commands import SetParentBedCommand
        from open_garden_planner.core.plant_renderer import is_plant_type
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        if not isinstance(item, GardenItemMixin) or not is_plant_type(item.object_type):
            return False, None

        plant_center = item.mapToScene(item.boundingRect().center())
        current_parent_id = item.parent_bed_id
        new_bed = self.canvas_scene.find_smallest_bed_containing(plant_center)
        new_parent_id = (
            new_bed.item_id
            if new_bed is not None and isinstance(new_bed, GardenItemMixin)
            else None
        )
        if new_parent_id == current_parent_id:
            return False, None

        cmd = SetParentBedCommand(
            self.canvas_scene, item, current_parent_id, new_parent_id
        )
        self.canvas_view.command_manager.execute(cmd)
        return True, str(new_parent_id) if new_parent_id is not None else None

    def _agent_item_center(self, item: Any) -> tuple[float, float]:
        """The object's centre in scene cm, using the SAME source the read tools do.

        ``get_object``/``list_objects`` report the serialised-geometry centre
        (``agent_api.queries.object_center``); reusing it here keeps a moved
        object's returned x/y identical to what a follow-up read reports —
        ``sceneBoundingRect().center()`` would diverge for a plant showing the
        runtime-only antagonist badge (asymmetric boundingRect, invariant #2).
        Falls back to the bounding-rect centre only if the item can't serialise.
        """
        from open_garden_planner.agent_api import queries

        data = self._project_manager._serialize_item(item)
        if data is not None:
            return queries.object_center(data)
        c = item.sceneBoundingRect().center()
        return c.x(), c.y()

    def _agent_delete_object(self, item_id: str) -> dict[str, Any]:
        """Delete one object ON the Qt main thread (for the server)."""
        return self._agent_bridge.run_on_main(
            lambda: self._do_agent_delete_object(item_id)
        )

    def _do_agent_delete_object(self, item_id: str) -> dict[str, Any]:
        """Main-thread body of ``delete_object``.

        Mirrors ``CanvasView._delete_selected_items``, not just
        ``DeleteItemsCommand`` in isolation: that method also (a) removes any
        constraint referencing the deleted item — left alone, the constraint
        graph would keep a dangling reference to a UUID no longer in the
        scene — and (b) deletes a HOUSE's linked roof ridge (a
        metadata-``ridge_item_id`` association, not a Qt-child or bed
        relationship), which would otherwise be orphaned. Contained plants are
        detached (not deleted) by ``DeleteItemsCommand`` itself, matching the
        GUI's "Keep plants" choice — the only sensible default for a
        single-object programmatic delete, which can't prompt.
        """
        from open_garden_planner.core.commands import DeleteItemsCommand, RemoveConstraintCommand

        item = self._resolve_agent_item(item_id)

        constraints = self._agent_item_constraints(item)
        for constraint in constraints:
            self.canvas_view.command_manager.execute(
                RemoveConstraintCommand(self.canvas_scene.constraint_graph, constraint)
            )

        linked_ridge = self._agent_linked_roof_ridge(item)
        cmd = DeleteItemsCommand(self.canvas_scene, [item, *linked_ridge])
        self.canvas_view.command_manager.execute(cmd)
        return {
            "item_id": item_id,
            "action": "delete",
            "undo_description": cmd.description,
            "linked_items_deleted": len(linked_ridge),
            "constraints_removed": len(constraints),
        }

    def _agent_linked_roof_ridge(self, item: Any) -> list[Any]:
        """A HOUSE's linked ``ROOF_RIDGE`` item, if any — mirroring
        ``CanvasView._delete_selected_items``'s ``ridge_item_id`` expansion so
        deleting a house doesn't orphan its ridge polyline."""
        from uuid import UUID

        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        if not isinstance(item, GardenItemMixin) or item.object_type != ObjectType.HOUSE:
            return []
        ridge_id_str = item.metadata.get("ridge_item_id")
        if not ridge_id_str:
            return []
        try:
            ridge = self.canvas_scene.find_item_by_id(UUID(ridge_id_str))
        except ValueError:
            return []
        return [ridge] if ridge is not None else []

    def _resolve_agent_item(self, item_id: str) -> Any:
        """Look up a scene item by UUID string for a write tool, or raise.

        Raising here surfaces to the agent as a failed tool call (the bridge
        propagates the exception across the main-thread hop).
        """
        from uuid import UUID

        from open_garden_planner.ui.canvas.items.group_item import GroupItem
        from open_garden_planner.ui.canvas.items.journal_pin_item import JournalPinItem

        try:
            uuid = UUID(item_id)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Not a valid object id: {item_id!r}") from exc
        item = self.canvas_scene.find_item_by_id(uuid)
        if item is None:
            raise ValueError(f"No object with id {item_id}")
        if isinstance(item.parentItem(), GroupItem):
            # A group member isn't a top-level object (list_objects/get_object
            # skip it; only a raw snapshot exposes its id nested in the group).
            # The GUI never lets you select a lone member — you move/delete the
            # whole group — and moveBy on a QGraphicsItemGroup child would
            # displace it *within* the group. Address the group by its own id.
            raise ValueError(
                f"{item_id} is a member of a group; move or delete the group "
                "itself (its own id), not an individual member."
            )
        if isinstance(item, JournalPinItem):
            # Journal pins have their own ProjectData-linked delete path
            # (DeleteJournalNoteCommand prunes the note dict; a plain
            # DeleteItemsCommand would remove the pin but silently orphan the
            # note record). Not supported by move_object/delete_object yet.
            raise ValueError(
                f"{item_id} is a journal pin, not a garden object — "
                "move_object/delete_object don't support journal pins yet."
            )
        if self._agent_item_is_locked(item):
            # The GUI enforces layer-lock by clearing ItemIsSelectable/
            # ItemIsMovable, so a locked-layer item can't be dragged, arrow-
            # moved, or deleted at all (every GUI edit works off selectedItems()).
            # The agent resolves by UUID, bypassing selection — so honour the
            # lock explicitly here, the one chokepoint every write tool shares.
            raise ValueError(
                f"{item_id} is on a locked layer; unlock the layer in the app "
                "before editing this object."
            )
        return item

    def _agent_item_is_locked(self, item: Any) -> bool:
        """Whether ``item`` sits on a locked layer (which the GUI makes
        entirely non-interactive)."""
        layer_id = getattr(item, "layer_id", None)
        if layer_id is None:
            return False
        layer = self.canvas_scene.get_layer_by_id(layer_id)
        return bool(layer is not None and layer.locked)

    def _agent_item_constraints(self, item: Any) -> list[Any]:
        """Every constraint (distance/fixed/tangent/…) referencing ``item``."""
        return self.canvas_scene.constraint_graph.get_item_constraints(item.item_id)

    def _maybe_start_agent_api(self) -> None:
        """Start the Agent API server iff it is enabled in settings."""
        from open_garden_planner.app.settings import get_settings

        if get_settings().agent_api_enabled:
            self._start_agent_api()

    def _start_agent_api(self) -> None:
        """Start the embedded MCP server, surfacing failures in the status bar."""
        from open_garden_planner.agent_api import (
            AgentApiServer,
            AgentProviders,
            PortInUseError,
        )
        from open_garden_planner.app.settings import get_settings

        if self._agent_server is not None and self._agent_server.is_running:
            return
        settings = get_settings()
        port = settings.agent_api_port
        providers = AgentProviders(
            snapshot=self._agent_snapshot,
            diagnostics=self._agent_diagnostics,
            render=self._agent_render,
            save_plan=self._agent_save_plan,
            export_pdf=self._agent_export_pdf,
            export_dxf=self._agent_export_dxf,
            export_csv=self._agent_export_csv,
            move_object=self._agent_move_object,
            delete_object=self._agent_delete_object,
        )
        writes_enabled = settings.agent_api_writes_enabled
        # Only read (and thus auto-generate) the token when writes are on, so a
        # user who never enables editing never has a token sitting in settings.
        write_token = settings.agent_api_token if writes_enabled else None
        try:
            server = AgentApiServer(
                providers,
                port=port,
                write_token=write_token,
                writes_enabled=writes_enabled,
            )
            server.start()
        except PortInUseError:
            self._agent_server = None
            self.statusBar().showMessage(
                self.tr("Agent API: port {port} is already in use").format(port=port),
                8000,
            )
            return
        except Exception:
            self._agent_server = None
            logger.exception("Agent API failed to start")
            self.statusBar().showMessage(
                self.tr("Agent API failed to start (see log)"), 8000
            )
            return
        self._agent_server = server
        self.statusBar().showMessage(
            self.tr("Agent API running at {url}").format(url=server.url), 5000
        )

    def _stop_agent_api(self) -> None:
        """Stop the embedded MCP server if it is running."""
        if self._agent_server is not None:
            # Abort any in-flight main-thread hops first so the server thread's
            # tool handler returns at once — otherwise stop()'s join could wait
            # on a queued call the (now tearing-down) main thread won't service.
            self._agent_bridge.abort_pending()
            self._agent_server.stop()
            self._agent_server = None

    def _setup_menu_bar(self) -> None:
        """Set up the menu bar with File, Edit, View, Help menus."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu(self.tr("&File"))
        self._setup_file_menu(file_menu)

        # Edit menu
        edit_menu = menubar.addMenu(self.tr("&Edit"))
        self._setup_edit_menu(edit_menu)

        # View menu
        view_menu = menubar.addMenu(self.tr("&View"))
        self._setup_view_menu(view_menu)

        # Plants menu
        plants_menu = menubar.addMenu(self.tr("&Plants"))
        self._setup_plants_menu(plants_menu)

        # Garden menu (US-12.10a — soil tests; expanded in 12.10b–e)
        garden_menu = menubar.addMenu(self.tr("&Garden"))
        self._setup_garden_menu(garden_menu)

        # Help menu
        help_menu = menubar.addMenu(self.tr("&Help"))
        self._setup_help_menu(help_menu)

    def _setup_file_menu(self, menu: QMenu) -> None:
        """Set up the File menu actions."""
        # New Project
        new_action = QAction(self.tr("&New Project"), self)
        new_action.setShortcut(QKeySequence("Ctrl+N"))
        new_action.setStatusTip(self.tr("Create a new garden project"))
        new_action.triggered.connect(self._on_new_project)
        menu.addAction(new_action)

        # Open Project
        open_action = QAction(self.tr("&Open..."), self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.setStatusTip(self.tr("Open an existing project"))
        open_action.triggered.connect(self._on_open_project)
        menu.addAction(open_action)

        # Open Recent submenu
        self._recent_menu = menu.addMenu(self.tr("Open &Recent"))
        self._recent_menu.aboutToShow.connect(self._populate_recent_menu)

        menu.addSeparator()

        # Save
        save_action = QAction(self.tr("&Save"), self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.setStatusTip(self.tr("Save the current project"))
        save_action.triggered.connect(self._on_save)
        menu.addAction(save_action)

        # Save As
        save_as_action = QAction(self.tr("Save &As..."), self)
        save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_as_action.setStatusTip(self.tr("Save the project with a new name"))
        save_as_action.triggered.connect(self._on_save_as)
        menu.addAction(save_as_action)

        menu.addSeparator()

        # Manage Seasons (US-10.7)
        seasons_action = QAction(self.tr("Manage &Seasons..."), self)
        seasons_action.setStatusTip(self.tr("Create a new season or switch between seasons"))
        seasons_action.triggered.connect(self._on_manage_seasons)
        menu.addAction(seasons_action)

        menu.addSeparator()

        # Import Background Image
        import_image_action = QAction(self.tr("&Import Background Image..."), self)
        import_image_action.setStatusTip(self.tr("Import a background image (satellite photo, etc.)"))
        import_image_action.triggered.connect(self._on_import_background_image)
        menu.addAction(import_image_action)

        # Load Satellite Background (via embedded Google Maps picker)
        load_satellite_action = QAction(self.tr("Load &Satellite Background..."), self)
        _enabled_hint = self.tr(
            "Pick an area on Google Maps and load it as a true-to-scale "
            "satellite background"
        )
        load_satellite_action.setStatusTip(_enabled_hint)
        load_satellite_action.setToolTip(_enabled_hint)
        load_satellite_action.triggered.connect(self._on_load_satellite_background)
        # Disable when API key not configured; explain why in both status bar
        # and tooltip (QMenu defaults to NOT showing action tooltips, so we
        # turn them on with ``setToolTipsVisible`` below).
        from open_garden_planner.services.google_maps_service import (  # noqa: PLC0415
            has_api_key as _has_maps_key,
        )
        if not _has_maps_key():
            load_satellite_action.setEnabled(False)
            _disabled_hint = self.tr(
                "Set OGP_GOOGLE_MAPS_KEY in your .env file to enable "
                "satellite background loading"
            )
            load_satellite_action.setStatusTip(_disabled_hint)
            load_satellite_action.setToolTip(_disabled_hint)
        menu.setToolTipsVisible(True)
        menu.addAction(load_satellite_action)

        # Import DXF
        import_dxf_action = QAction(self.tr("Import &DXF..."), self)
        import_dxf_action.setStatusTip(self.tr("Import a DXF CAD file onto the canvas"))
        import_dxf_action.triggered.connect(self._on_import_dxf)
        menu.addAction(import_dxf_action)

        # Set Garden Location
        location_action = QAction(self.tr("Set Garden &Location..."), self)
        location_action.setStatusTip(self.tr("Set GPS coordinates and frost dates for planting calendar"))
        location_action.triggered.connect(self._on_set_location)
        menu.addAction(location_action)

        menu.addSeparator()

        # Export submenu
        export_menu = menu.addMenu(self.tr("&Export"))

        export_png = QAction(self.tr("Export as &PNG..."), self)
        export_png.setStatusTip(self.tr("Export the plan as a PNG image"))
        export_png.triggered.connect(self._on_export_png)
        export_menu.addAction(export_png)

        export_svg = QAction(self.tr("Export as &SVG..."), self)
        export_svg.setStatusTip(self.tr("Export the plan as an SVG vector file"))
        export_svg.triggered.connect(self._on_export_svg)
        export_menu.addAction(export_svg)

        export_csv = QAction(self.tr("Export Plant List as &CSV..."), self)
        export_csv.setStatusTip(self.tr("Export all plants to a CSV spreadsheet"))
        export_csv.triggered.connect(self._on_export_plant_csv)
        export_menu.addAction(export_csv)

        export_dxf = QAction(self.tr("Export as D&XF..."), self)
        export_dxf.setStatusTip(self.tr("Export the plan as a DXF file for CAD software"))
        export_dxf.triggered.connect(self._on_export_dxf)
        export_menu.addAction(export_dxf)

        export_pdf_report = QAction(self.tr("Export PDF &Report..."), self)
        export_pdf_report.setStatusTip(self.tr("Generate a multi-page PDF report of the garden plan"))
        export_pdf_report.triggered.connect(self._on_export_pdf_report)
        export_menu.addAction(export_pdf_report)

        menu.addSeparator()

        # Print
        print_action = QAction(self.tr("&Print..."), self)
        print_action.setShortcut(QKeySequence("Ctrl+P"))
        print_action.setStatusTip(self.tr("Print the garden plan"))
        print_action.triggered.connect(self._on_print)
        menu.addAction(print_action)

        menu.addSeparator()

        # Exit
        exit_action = QAction(self.tr("E&xit"), self)
        exit_action.setShortcut(QKeySequence("Alt+F4"))
        exit_action.setStatusTip(self.tr("Exit the application"))
        exit_action.triggered.connect(self.close)
        menu.addAction(exit_action)

    def _setup_edit_menu(self, menu: QMenu) -> None:
        """Set up the Edit menu actions."""
        # Undo
        self._undo_action = QAction(self.tr("&Undo"), self)
        self._undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        self._undo_action.setStatusTip(self.tr("Undo the last action"))
        self._undo_action.setEnabled(False)  # Disabled until there's something to undo
        self._undo_action.triggered.connect(self._on_undo)
        menu.addAction(self._undo_action)

        # Redo
        self._redo_action = QAction(self.tr("&Redo"), self)
        self._redo_action.setShortcut(QKeySequence("Ctrl+Y"))
        self._redo_action.setStatusTip(self.tr("Redo the last undone action"))
        self._redo_action.setEnabled(False)  # Disabled until there's something to redo
        self._redo_action.triggered.connect(self._on_redo)
        menu.addAction(self._redo_action)

        menu.addSeparator()

        # Cut
        cut_action = QAction(self.tr("Cu&t"), self)
        cut_action.setShortcut(QKeySequence("Ctrl+X"))
        cut_action.setStatusTip(self.tr("Cut selected objects"))
        cut_action.triggered.connect(self._on_cut)
        menu.addAction(cut_action)

        # Copy
        copy_action = QAction(self.tr("&Copy"), self)
        copy_action.setShortcut(QKeySequence("Ctrl+C"))
        copy_action.setStatusTip(self.tr("Copy selected objects"))
        copy_action.triggered.connect(self._on_copy)
        menu.addAction(copy_action)

        # Paste
        paste_action = QAction(self.tr("&Paste"), self)
        paste_action.setShortcut(QKeySequence("Ctrl+V"))
        paste_action.setStatusTip(self.tr("Paste objects from clipboard"))
        paste_action.triggered.connect(self._on_paste)
        menu.addAction(paste_action)

        # Duplicate
        duplicate_action = QAction(self.tr("D&uplicate"), self)
        duplicate_action.setShortcut(QKeySequence("Ctrl+D"))
        duplicate_action.setStatusTip(self.tr("Duplicate selected objects"))
        duplicate_action.triggered.connect(self._on_duplicate)
        menu.addAction(duplicate_action)

        # Delete
        self._delete_action = QAction(self.tr("&Delete"), self)
        self._delete_action.setShortcut(QKeySequence("Delete"))
        self._delete_action.setStatusTip(self.tr("Delete selected objects"))
        menu.addAction(self._delete_action)

        menu.addSeparator()

        # Select All
        select_all_action = QAction(self.tr("Select &All"), self)
        select_all_action.setShortcut(QKeySequence("Ctrl+A"))
        select_all_action.setStatusTip(self.tr("Select all objects"))
        select_all_action.triggered.connect(self._on_select_all)
        menu.addAction(select_all_action)

        # Find & Replace
        find_replace_action = QAction(self.tr("&Find && Replace…"), self)
        find_replace_action.setShortcut(QKeySequence.StandardKey.Find)
        find_replace_action.setStatusTip(self.tr("Find and replace objects by name, type, layer or species"))
        find_replace_action.triggered.connect(self._on_toggle_find_replace)
        menu.addAction(find_replace_action)

        menu.addSeparator()

        # Align submenu
        align_menu = menu.addMenu(self.tr("Ali&gn && Distribute"))

        align_left = QAction(self.tr("Align &Left"), self)
        align_left.setStatusTip(self.tr("Align selected objects to the left edge"))
        align_left.triggered.connect(self._on_align_left)
        align_menu.addAction(align_left)

        align_right = QAction(self.tr("Align &Right"), self)
        align_right.setStatusTip(self.tr("Align selected objects to the right edge"))
        align_right.triggered.connect(self._on_align_right)
        align_menu.addAction(align_right)

        align_top = QAction(self.tr("Align &Top"), self)
        align_top.setStatusTip(self.tr("Align selected objects to the top edge"))
        align_top.triggered.connect(self._on_align_top)
        align_menu.addAction(align_top)

        align_bottom = QAction(self.tr("Align &Bottom"), self)
        align_bottom.setStatusTip(self.tr("Align selected objects to the bottom edge"))
        align_bottom.triggered.connect(self._on_align_bottom)
        align_menu.addAction(align_bottom)

        align_center_h = QAction(self.tr("Align Center &Horizontally"), self)
        align_center_h.setStatusTip(self.tr("Align selected objects to horizontal center"))
        align_center_h.triggered.connect(self._on_align_center_h)
        align_menu.addAction(align_center_h)

        align_center_v = QAction(self.tr("Align Center &Vertically"), self)
        align_center_v.setStatusTip(self.tr("Align selected objects to vertical center"))
        align_center_v.triggered.connect(self._on_align_center_v)
        align_menu.addAction(align_center_v)

        align_menu.addSeparator()

        dist_h = QAction(self.tr("Distribute &Horizontal"), self)
        dist_h.setStatusTip(self.tr("Distribute selected objects with equal horizontal spacing"))
        dist_h.triggered.connect(self._on_distribute_horizontal)
        align_menu.addAction(dist_h)

        dist_v = QAction(self.tr("Distribute &Vertical"), self)
        dist_v.setStatusTip(self.tr("Distribute selected objects with equal vertical spacing"))
        dist_v.triggered.connect(self._on_distribute_vertical)
        align_menu.addAction(dist_v)

        menu.addSeparator()

        # Canvas Size
        canvas_size_action = QAction(self.tr("Canvas &Size..."), self)
        canvas_size_action.setStatusTip(self.tr("Resize the canvas dimensions"))
        canvas_size_action.triggered.connect(self._on_canvas_size)
        menu.addAction(canvas_size_action)

        menu.addSeparator()

        # Auto-Save submenu
        autosave_menu = menu.addMenu(self.tr("Auto-&Save"))

        # Toggle auto-save
        self._autosave_action = QAction(self.tr("&Enable Auto-Save"), self)
        self._autosave_action.setCheckable(True)
        self._autosave_action.setStatusTip(self.tr("Enable or disable automatic saving"))
        self._autosave_action.triggered.connect(self._on_toggle_autosave)
        autosave_menu.addAction(self._autosave_action)

        autosave_menu.addSeparator()

        # Auto-save interval options
        self._autosave_interval_actions: list[QAction] = []
        intervals = [1, 2, 5, 10, 15, 30]
        for minutes in intervals:
            label = self.tr("{n} minute(s)").format(n=minutes)
            action = QAction(label, self)
            action.setCheckable(True)
            action.setData(minutes)
            action.triggered.connect(lambda _checked, m=minutes: self._on_set_autosave_interval(m))
            autosave_menu.addAction(action)
            self._autosave_interval_actions.append(action)

        # Initialize menu state from settings
        QTimer.singleShot(0, self._update_autosave_menu_state)

        menu.addSeparator()

        # Preferences
        preferences_action = QAction(self.tr("&Preferences..."), self)
        preferences_action.setStatusTip(self.tr("Configure application settings and API keys"))
        preferences_action.triggered.connect(self._on_preferences)
        menu.addAction(preferences_action)

    def _setup_view_menu(self, menu: QMenu) -> None:
        """Set up the View menu actions."""
        # Zoom In
        zoom_in_action = QAction(self.tr("Zoom &In"), self)
        zoom_in_action.setShortcut(QKeySequence("Ctrl++"))
        zoom_in_action.setStatusTip(self.tr("Zoom in on the canvas"))
        zoom_in_action.triggered.connect(self._on_zoom_in)
        menu.addAction(zoom_in_action)

        # Zoom Out
        zoom_out_action = QAction(self.tr("Zoom &Out"), self)
        zoom_out_action.setShortcut(QKeySequence("Ctrl+-"))
        zoom_out_action.setStatusTip(self.tr("Zoom out on the canvas"))
        zoom_out_action.triggered.connect(self._on_zoom_out)
        menu.addAction(zoom_out_action)

        # Fit to Window
        fit_action = QAction(self.tr("&Fit to Window"), self)
        fit_action.setShortcut(QKeySequence("Ctrl+0"))
        fit_action.setStatusTip(self.tr("Fit the entire canvas in the window"))
        fit_action.triggered.connect(self._on_fit_to_window)
        menu.addAction(fit_action)

        menu.addSeparator()

        # Toggle Grid
        self.grid_action = QAction(self.tr("Show &Grid"), self)
        self.grid_action.setShortcut(QKeySequence("G"))
        self.grid_action.setCheckable(True)
        self.grid_action.setChecked(False)
        self.grid_action.setStatusTip(self.tr("Toggle grid visibility"))
        menu.addAction(self.grid_action)

        # Toggle Snap
        self.snap_action = QAction(self.tr("&Snap to Grid"), self)
        self.snap_action.setShortcut(QKeySequence("S"))
        self.snap_action.setCheckable(True)
        self.snap_action.setChecked(True)
        self.snap_action.setStatusTip(self.tr("Toggle snap to grid"))
        menu.addAction(self.snap_action)

        # Toggle Object Snap
        self._object_snap_action = QAction(self.tr("Snap to &Objects"), self)
        self._object_snap_action.setCheckable(True)
        self._object_snap_action.setChecked(True)
        self._object_snap_action.setStatusTip(self.tr("Toggle snap to object edges and centers"))
        self._object_snap_action.triggered.connect(self._on_toggle_object_snap)
        menu.addAction(self._object_snap_action)

        # Toggle Midpoint Snap (Package A - US-A3)
        self._midpoint_snap_action = QAction(self.tr("Snap to &Midpoints"), self)
        self._midpoint_snap_action.setCheckable(True)
        self._midpoint_snap_action.setChecked(True)
        self._midpoint_snap_action.setStatusTip(
            self.tr("Toggle snap to the midpoint of any straight edge")
        )
        self._midpoint_snap_action.triggered.connect(self._on_toggle_midpoint_snap)
        menu.addAction(self._midpoint_snap_action)

        # Toggle Intersection Snap (Package A - US-A3)
        self._intersection_snap_action = QAction(
            self.tr("Snap to &Intersections"), self
        )
        self._intersection_snap_action.setCheckable(True)
        self._intersection_snap_action.setChecked(True)
        self._intersection_snap_action.setStatusTip(
            self.tr("Toggle snap to intersections of straight edges")
        )
        self._intersection_snap_action.triggered.connect(
            self._on_toggle_intersection_snap
        )
        menu.addAction(self._intersection_snap_action)

        # Toggle Nearest Snap (Package B — US-B4). Fallback below the
        # other snap kinds; off by default so it doesn't surprise users.
        self._nearest_snap_action = QAction(self.tr("Snap to &Nearest Point"), self)
        self._nearest_snap_action.setCheckable(True)
        self._nearest_snap_action.setChecked(False)
        self._nearest_snap_action.setStatusTip(
            self.tr("Toggle snap to the closest point on any visible edge or curve")
        )
        self._nearest_snap_action.triggered.connect(self._on_toggle_nearest_snap)
        menu.addAction(self._nearest_snap_action)

        # Toggle Perpendicular Snap (Package B — US-B5). Drops the
        # perpendicular foot from the active tool's anchor onto a
        # hovered edge; off by default.
        self._perpendicular_snap_action = QAction(
            self.tr("Snap &Perpendicular"), self
        )
        self._perpendicular_snap_action.setCheckable(True)
        self._perpendicular_snap_action.setChecked(False)
        self._perpendicular_snap_action.setStatusTip(
            self.tr(
                "Toggle snap to the perpendicular foot from the last "
                "drawn point onto the nearest edge"
            )
        )
        self._perpendicular_snap_action.triggered.connect(
            self._on_toggle_perpendicular_snap
        )
        menu.addAction(self._perpendicular_snap_action)

        # Toggle Tangent Snap (Package B — US-B6). Snaps to the tangent
        # point on a circle / arc from the active tool's anchor.
        self._tangent_snap_action = QAction(self.tr("Snap &Tangent"), self)
        self._tangent_snap_action.setCheckable(True)
        self._tangent_snap_action.setChecked(False)
        self._tangent_snap_action.setStatusTip(
            self.tr(
                "Toggle snap to the tangent point on a circle or arc from "
                "the last drawn point"
            )
        )
        self._tangent_snap_action.triggered.connect(self._on_toggle_tangent_snap)
        menu.addAction(self._tangent_snap_action)

        # Toggle Dynamic Input (Package A - US-A4)
        self._dynamic_input_action = QAction(self.tr("Enable Dynamic &Input"), self)
        self._dynamic_input_action.setCheckable(True)
        self._dynamic_input_action.setChecked(True)
        self._dynamic_input_action.setStatusTip(
            self.tr(
                "Toggle typed distance/angle input next to the cursor and in "
                "the status bar"
            )
        )
        self._dynamic_input_action.triggered.connect(self._on_toggle_dynamic_input)
        menu.addAction(self._dynamic_input_action)

        menu.addSeparator()

        # Toggle Shadows
        self._shadows_action = QAction(self.tr("Show &Shadows"), self)
        self._shadows_action.setCheckable(True)
        self._shadows_action.setChecked(True)  # Updated from settings in _setup_central_widget
        self._shadows_action.setStatusTip(self.tr("Toggle drop shadows on objects"))
        self._shadows_action.triggered.connect(self._on_toggle_shadows)
        menu.addAction(self._shadows_action)

        # Sun & shade simulation (US-E3) — deliberately named distinctly from
        # the cosmetic per-item drop shadows above; different machinery.
        self._sun_sim_action = QAction(self.tr("S&un && Shade Simulation"), self)
        self._sun_sim_action.setCheckable(True)
        self._sun_sim_action.setChecked(False)  # always starts off (runtime-only)
        self._sun_sim_action.setStatusTip(
            self.tr("Simulate solar shadows for a chosen date and time of day")
        )
        self._sun_sim_action.triggered.connect(self._on_toggle_sun_sim)
        menu.addAction(self._sun_sim_action)

        # 3D view (US-E6) — viewer window, engine per ADR-038 (PyQt6-3D).
        self._view3d_action = QAction(self.tr("&3D View…"), self)
        self._view3d_action.setStatusTip(
            self.tr("Open a 3D view of the plan with solar lighting")
        )
        self._view3d_action.triggered.connect(self._on_open_3d_view)
        menu.addAction(self._view3d_action)

        # Toggle Scale Bar
        self._scale_bar_action = QAction(self.tr("Show Scale &Bar"), self)
        self._scale_bar_action.setCheckable(True)
        self._scale_bar_action.setChecked(True)  # Updated from settings in _setup_central_widget
        self._scale_bar_action.setStatusTip(self.tr("Toggle the scale bar overlay on the canvas"))
        self._scale_bar_action.triggered.connect(self._on_toggle_scale_bar)
        menu.addAction(self._scale_bar_action)

        # Toggle Labels
        self._labels_action = QAction(self.tr("Show &Labels"), self)
        self._labels_action.setCheckable(True)
        self._labels_action.setChecked(True)  # Updated from settings in _setup_central_widget
        self._labels_action.setStatusTip(self.tr("Toggle object labels on the canvas"))
        self._labels_action.triggered.connect(self._on_toggle_labels)
        menu.addAction(self._labels_action)

        # Toggle Constraints
        self._constraints_action = QAction(self.tr("Show &Constraints"), self)
        self._constraints_action.setCheckable(True)
        self._constraints_action.setChecked(True)  # Updated from settings in _setup_central_widget
        self._constraints_action.setStatusTip(self.tr("Toggle constraint dimension lines on the canvas"))
        self._constraints_action.triggered.connect(self._on_toggle_constraints)
        menu.addAction(self._constraints_action)

        # Toggle Construction Geometry
        self._construction_action = QAction(self.tr("Show C&onstruction Geometry"), self)
        self._construction_action.setCheckable(True)
        self._construction_action.setChecked(True)
        self._construction_action.setStatusTip(self.tr("Toggle construction geometry visibility (excluded from exports)"))
        self._construction_action.triggered.connect(self._on_toggle_construction)
        menu.addAction(self._construction_action)

        # Toggle Guide Lines
        self._guides_action = QAction(self.tr("Show &Guide Lines"), self)
        self._guides_action.setShortcut(QKeySequence(";"))
        self._guides_action.setCheckable(True)
        self._guides_action.setChecked(True)
        self._guides_action.setStatusTip(self.tr("Toggle ruler and guide lines (drag from ruler to create)"))
        self._guides_action.triggered.connect(self._on_toggle_guides)
        menu.addAction(self._guides_action)

        # Toggle Companion Planting Warnings
        self._companion_warnings_action = QAction(self.tr("Show Companion &Warnings"), self)
        self._companion_warnings_action.setCheckable(True)
        self._companion_warnings_action.setChecked(True)
        self._companion_warnings_action.setStatusTip(
            self.tr("Highlight compatible and incompatible plants near the selected plant")
        )
        self._companion_warnings_action.triggered.connect(self._on_toggle_companion_warnings)
        menu.addAction(self._companion_warnings_action)

        # Toggle Spacing Circles (US-11.2)
        self._spacing_circles_action = QAction(self.tr("Show S&pacing Circles"), self)
        self._spacing_circles_action.setCheckable(True)
        self._spacing_circles_action.setChecked(True)
        self._spacing_circles_action.setStatusTip(
            self.tr("Show recommended spacing zones around plants")
        )
        self._spacing_circles_action.triggered.connect(self._on_toggle_spacing_circles)
        menu.addAction(self._spacing_circles_action)

        # Toggle Soil Health Overlay (US-12.10b)
        self._soil_overlay_action = QAction(self.tr("Soil &Health Overlay"), self)
        self._soil_overlay_action.setShortcut(QKeySequence("Ctrl+Shift+H"))
        self._soil_overlay_action.setCheckable(True)
        self._soil_overlay_action.setChecked(False)
        self._soil_overlay_action.setStatusTip(
            self.tr("Tint beds by soil-health rating (excluded from exports)")
        )
        self._soil_overlay_action.triggered.connect(self._on_toggle_soil_overlay)
        menu.addAction(self._soil_overlay_action)

        # Toggle Minimap (US-11.7)
        self._minimap_action = QAction(self.tr("Show &Minimap"), self)
        self._minimap_action.setCheckable(True)
        self._minimap_action.setChecked(True)
        self._minimap_action.setStatusTip(
            self.tr("Show a minimap overview for quick navigation")
        )
        self._minimap_action.triggered.connect(self._on_toggle_minimap)
        menu.addAction(self._minimap_action)

        # Toggle previous-season compare overlay (US-10.7)
        self._compare_overlay_action = QAction(self.tr("Show &Previous Season Overlay"), self)
        self._compare_overlay_action.setCheckable(True)
        self._compare_overlay_action.setChecked(False)
        self._compare_overlay_action.setEnabled(False)  # Enabled when overlay data is loaded
        self._compare_overlay_action.setStatusTip(
            self.tr("Overlay ghosted plant positions from the previous season")
        )
        self._compare_overlay_action.triggered.connect(self._on_toggle_compare_overlay)
        menu.addAction(self._compare_overlay_action)

        menu.addSeparator()

        # Fullscreen Preview
        self._preview_action = QAction(self.tr("&Fullscreen Preview"), self)
        self._preview_action.setShortcut(QKeySequence("F11"))
        self._preview_action.setCheckable(True)
        self._preview_action.setChecked(False)
        self._preview_action.setStatusTip(self.tr("Toggle fullscreen preview mode (hides all UI)"))
        self._preview_action.triggered.connect(self._on_toggle_preview_mode)
        menu.addAction(self._preview_action)

        menu.addSeparator()

        # Theme submenu
        theme_menu = menu.addMenu(self.tr("&Theme"))

        # Light theme
        self._light_theme_action = QAction(self.tr("&Light"), self)
        self._light_theme_action.setCheckable(True)
        self._light_theme_action.setStatusTip(self.tr("Use light color scheme"))
        self._light_theme_action.triggered.connect(lambda: self._on_theme_changed(ThemeMode.LIGHT))
        theme_menu.addAction(self._light_theme_action)

        # Dark theme
        self._dark_theme_action = QAction(self.tr("&Dark"), self)
        self._dark_theme_action.setCheckable(True)
        self._dark_theme_action.setStatusTip(self.tr("Use dark color scheme"))
        self._dark_theme_action.triggered.connect(lambda: self._on_theme_changed(ThemeMode.DARK))
        theme_menu.addAction(self._dark_theme_action)

        # System theme
        self._system_theme_action = QAction(self.tr("&System"), self)
        self._system_theme_action.setCheckable(True)
        self._system_theme_action.setStatusTip(self.tr("Follow system color scheme preference"))
        self._system_theme_action.triggered.connect(lambda: self._on_theme_changed(ThemeMode.SYSTEM))
        theme_menu.addAction(self._system_theme_action)

        # Initialize menu state from settings
        QTimer.singleShot(0, self._update_theme_menu_state)

        # Language submenu
        language_menu = menu.addMenu(self.tr("&Language"))
        self._language_actions: dict[str, QAction] = {}

        from open_garden_planner.core.i18n import SUPPORTED_LANGUAGES

        for lang_code, native_name in SUPPORTED_LANGUAGES.items():
            action = QAction(native_name, self)
            action.setCheckable(True)
            action.triggered.connect(
                lambda _checked, lc=lang_code: self._on_language_changed(lc)
            )
            language_menu.addAction(action)
            self._language_actions[lang_code] = action

        # Initialize language menu state from settings
        QTimer.singleShot(0, self._update_language_menu_state)

    def _setup_plants_menu(self, menu: QMenu) -> None:
        """Set up the Plants menu actions."""
        # Search Plant Database
        search_action = QAction(self.tr("&Search Plant Database"), self)
        search_action.setShortcut(QKeySequence("Ctrl+K"))
        search_action.setStatusTip(self.tr("Search for plant species in online databases"))
        search_action.triggered.connect(self._on_search_plant_database)
        menu.addAction(search_action)

        menu.addSeparator()

        # Manage Custom Plants
        manage_custom_action = QAction(self.tr("&Manage Custom Plants..."), self)
        manage_custom_action.setStatusTip(self.tr("View, edit, and delete your custom plant species"))
        manage_custom_action.triggered.connect(self._on_manage_custom_plants)
        menu.addAction(manage_custom_action)

        menu.addSeparator()

        # Check Companion Planting
        check_companion_action = QAction(self.tr("Check &Companion Planting..."), self)
        check_companion_action.setStatusTip(self.tr("Analyse the whole plan for companion planting compatibility"))
        check_companion_action.triggered.connect(self._on_check_companion_planting)
        menu.addAction(check_companion_action)

    def _setup_garden_menu(self, menu: QMenu) -> None:
        """Set up the Garden menu actions (US-12.10a — soil)."""
        # Set default soil test (project-wide fallback when a bed has no own test)
        default_soil_action = QAction(self.tr("&Set default soil test…"), self)
        default_soil_action.setStatusTip(
            self.tr("Set a project-wide soil test used when individual beds have none")
        )
        default_soil_action.triggered.connect(self._on_set_default_soil_test)
        menu.addAction(default_soil_action)

        # Amendment plan (US-12.10c) — aggregated cross-bed shopping list.
        menu.addSeparator()
        amendment_plan_action = QAction(self.tr("&Amendment Plan…"), self)
        amendment_plan_action.setStatusTip(
            self.tr("View amendment recommendations for deficient beds")
        )
        amendment_plan_action.triggered.connect(self._on_amendment_plan)
        menu.addAction(amendment_plan_action)

        # Shopping list (US-12.6)
        shopping_list_action = QAction(self.tr("&Shopping List…"), self)
        shopping_list_action.setStatusTip(
            self.tr("Generate a shopping list of plants, seeds, and materials")
        )
        shopping_list_action.triggered.connect(self._on_shopping_list)
        menu.addAction(shopping_list_action)

    def _setup_help_menu(self, menu: QMenu) -> None:
        """Set up the Help menu actions."""
        # Keyboard Shortcuts
        shortcuts_action = QAction(self.tr("&Keyboard Shortcuts"), self)
        shortcuts_action.setShortcut(QKeySequence("F1"))
        shortcuts_action.setStatusTip(self.tr("Show keyboard shortcuts reference"))
        shortcuts_action.triggered.connect(self._on_keyboard_shortcuts)
        menu.addAction(shortcuts_action)

        # Connect AI Assistant (US-D1.6)
        connect_ai_action = QAction(self.tr("Connect AI Assistant…"), self)
        connect_ai_action.setStatusTip(
            self.tr("Register this plan's MCP server with your AI assistant")
        )
        connect_ai_action.triggered.connect(self._on_connect_ai_assistant)
        menu.addAction(connect_ai_action)

        menu.addSeparator()

        # About
        about_action = QAction(self.tr("&About Open Garden Planner"), self)
        about_action.setStatusTip(self.tr("About this application"))
        about_action.triggered.connect(self._on_about)
        menu.addAction(about_action)

        # About Qt
        about_qt_action = QAction(self.tr("About &Qt"), self)
        about_qt_action.triggered.connect(QApplication.aboutQt)
        menu.addAction(about_qt_action)


    def _setup_status_bar(self) -> None:
        """Set up the status bar with coordinate and zoom display."""
        from open_garden_planner.ui.widgets.coordinate_input_field import (
            CoordinateInputField,
        )

        status_bar = self.statusBar()

        # Coordinate label (left side, permanent)
        self.coord_label = QLabel(self.tr("X: 0.00 cm  Y: 0.00 cm"))
        self.coord_label.setMinimumWidth(200)
        status_bar.addPermanentWidget(self.coord_label)

        # Typed coordinate input (Package A US-A1/A2). Wired up after
        # _setup_central_widget runs (which creates canvas_view).
        self.coordinate_input_field: CoordinateInputField | None = None

        # Zoom label
        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(60)
        status_bar.addPermanentWidget(self.zoom_label)

        # Selection info label
        self.selection_label = QLabel(self.tr("No selection"))
        self.selection_label.setMinimumWidth(150)
        status_bar.addPermanentWidget(self.selection_label)

        # Tool label
        self.tool_label = QLabel(self.tr("Select"))
        self.tool_label.setMinimumWidth(80)
        status_bar.addPermanentWidget(self.tool_label)

        # Location label
        self.location_label = QLabel(self.tr("No location set"))
        self.location_label.setMinimumWidth(160)
        self.location_label.setToolTip(self.tr("Garden GPS location — use File > Set Garden Location to configure"))
        status_bar.addPermanentWidget(self.location_label)

        # Season label (US-10.7)
        self.season_label = QLabel(self.tr("Season: —"))
        self.season_label.setMinimumWidth(100)
        self.season_label.setToolTip(self.tr("Current season year — use File > Manage Seasons to configure"))
        status_bar.addPermanentWidget(self.season_label)

        # Sun & shade simulation hint (US-E3/E4) — night / no-location notes.
        # Lives here, NOT on the sun toolbar: a variable-width label in the
        # toolbar's flow reflowed Qt's overflow popup and bumped the Animate
        # button to another row when the night text toggled (2026-07 fix).
        self._sun_hint_label = QLabel("")
        self._sun_hint_label.setStyleSheet("color: #806a00; font-style: italic;")
        self._sun_hint_label.setVisible(False)
        status_bar.addPermanentWidget(self._sun_hint_label)

        # Show ready message
        status_bar.showMessage(self.tr("Ready"))

    def _setup_central_widget(self) -> None:
        """Set up the central widget area with canvas and sidebar panels."""
        from open_garden_planner.ui.widgets.coordinate_input_field import (
            CoordinateInputField,
        )

        # Create canvas scene and view
        self.canvas_scene = CanvasScene(width_cm=5000, height_cm=3000)
        self.canvas_view = CanvasView(self.canvas_scene)

        # Status-bar typed coordinate input (Package A US-A1/A2). Created
        # here so it can attach to the canvas_view's shared input buffer.
        self.coordinate_input_field = CoordinateInputField(
            self.canvas_view.coordinate_input_buffer, self
        )
        self.coordinate_input_field.commit_requested.connect(
            self.canvas_view.commit_typed_coordinate
        )
        # Insert between the coordinate label and the zoom label.
        status_bar = self.statusBar()
        status_bar.insertPermanentWidget(1, self.coordinate_input_field)

        # Three top toolbars on the same row, left → right:
        #   MainToolbar (core tools)
        #   ConstraintToolbar (CAD constraints)
        #   CategoryToolbar (object categories + global search)
        self.main_toolbar = MainToolbar(self)
        self.addToolBar(self.main_toolbar)

        self.constraint_toolbar = ConstraintToolbar(self)
        self.addToolBar(self.constraint_toolbar)

        self.category_toolbar = CategoryToolbar(self)
        self.addToolBar(self.category_toolbar)

        # ── Companion planting service (shared by sidebar panel and highlights) ─
        self._companion_service = CompanionPlantingService()
        self._companion_warnings_enabled = True
        self._companion_radius_cm = 200.0  # 2 m default

        # ── Soil service (US-12.10a/b/d) — long-lived, shared by overlay & dialog ──
        self._soil_service = SoilService(self._project_manager)
        self.canvas_view.set_soil_service(self._soil_service)

        # Soil overlay parameter toolbar (US-12.10b) — hidden until overlay on.
        self._setup_soil_overlay_toolbar()

        # ── Crop rotation service (US-10.6) ──────────────────────────────────
        from open_garden_planner.services.crop_rotation_service import CropRotationService

        self._crop_rotation_service = CropRotationService()

        # Create sidebar panels
        self._setup_sidebar()

        # Create splitter for canvas and sidebar
        self._main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._main_splitter.addWidget(self.canvas_view)
        self._main_splitter.addWidget(self.sidebar)
        self._main_splitter.setStretchFactor(0, 1)  # Canvas takes most space
        self._main_splitter.setStretchFactor(1, 0)  # Sidebar fixed width
        self._main_splitter.setHandleWidth(1)  # Minimal splitter handle
        # Set initial sizes: give sidebar 450px, canvas gets the rest
        self._main_splitter.setSizes([1000, 450])
        splitter = self._main_splitter

        # Connect canvas signals to status bar updates
        self.canvas_view.coordinates_changed.connect(self.update_coordinates)
        self.canvas_view.zoom_changed.connect(self.update_zoom)

        # Connect view menu actions to canvas
        self.grid_action.triggered.connect(self._on_toggle_grid)
        self.snap_action.triggered.connect(self._on_toggle_snap)

        # Connect toolbars to canvas view: core tools, constraints, and the
        # category dropdowns + global search live on three separate toolbars.
        self.main_toolbar.tool_selected.connect(self._on_tool_selected)
        self.constraint_toolbar.tool_selected.connect(self._on_tool_selected)
        self.category_toolbar.tool_selected.connect(self._on_tool_selected)
        self.category_toolbar.item_selected.connect(self._on_gallery_item_selected)
        self.canvas_view.tool_changed.connect(self.update_tool)
        self.canvas_view.tool_changed.connect(self._sync_toolbar_state)
        self.canvas_view.import_background_image_requested.connect(
            self._on_import_background_image
        )
        # US-12.10a: bed → "Add soil test…" routes through CanvasView
        self.canvas_view.soil_test_requested.connect(self._on_soil_test_requested)
        # US-12.10e: bed top-right reminder badge → open dialog for that bed
        self.canvas_view.soil_test_badge_clicked.connect(
            self._on_soil_test_badge_clicked
        )
        # US-12.7: bed/plant → "Log Pest/Disease…" routes through CanvasView
        self.canvas_view.pest_log_requested.connect(self._on_pest_log_requested)
        self._project_manager.pest_logs_changed.connect(
            self._on_pest_logs_changed
        )
        # US-C1: bed/plant → "Log Harvest…" routes through CanvasView
        self.canvas_view.harvest_log_requested.connect(self._on_harvest_log_requested)
        # US-12.8: bed → "Plan Succession…" routes through CanvasView
        self.canvas_view.succession_plan_requested.connect(
            self._on_succession_plan_requested
        )
        self._project_manager.succession_plans_changed.connect(
            self._on_succession_plans_changed
        )
        # US-12.9: Journal Pin tool + pin double-click / delete
        self.canvas_view.journal_note_requested.connect(
            self._on_journal_note_placement
        )
        self.canvas_view.journal_note_edit_requested.connect(
            self._on_journal_note_edit
        )
        self.canvas_view.journal_note_delete_requested.connect(
            self._on_journal_note_delete
        )
        self.canvas_view.journal_notes_batch_delete_requested.connect(
            self._on_journal_notes_batch_delete
        )
        self._project_manager.garden_journal_notes_changed.connect(
            self._on_garden_journal_notes_changed
        )

        # Connect scene selection changes to status bar and panels
        self.canvas_scene.selectionChanged.connect(self._on_selection_changed)
        self.canvas_scene.selectionChanged.connect(self._update_properties_panel)
        self.canvas_scene.selectionChanged.connect(self._update_plant_database_panel)
        self.canvas_scene.selectionChanged.connect(self._update_companion_panel)
        self.canvas_scene.selectionChanged.connect(self._update_crop_rotation_panel)

        # ── Companion planting highlights (US-10.2) ──────────────────────────
        # Debounce timer for drag updates (avoids re-querying on every pixel move)
        self._companion_update_timer = QTimer(self)
        self._companion_update_timer.setSingleShot(True)
        self._companion_update_timer.setInterval(60)
        self._companion_update_timer.timeout.connect(self._update_companion_highlights)
        self._companion_update_timer.timeout.connect(self._update_companion_panel)
        self.canvas_scene.selectionChanged.connect(self._update_companion_highlights)
        self.canvas_scene.changed.connect(self._on_scene_changed_for_companion)

        # ── Spacing circle overlap detection (US-11.2) ───────────────────────
        self._spacing_circles_enabled = True
        self._spacing_update_timer = QTimer(self)
        self._spacing_update_timer.setSingleShot(True)
        self._spacing_update_timer.setInterval(150)
        self._spacing_update_timer.timeout.connect(self._update_spacing_overlaps)
        self.canvas_scene.selectionChanged.connect(self._update_spacing_overlaps)
        self.canvas_scene.changed.connect(self._on_scene_changed_for_spacing)

        # ── Minimap overlay (US-11.7) ────────────────────────────────────────
        from open_garden_planner.ui.widgets.minimap_widget import MinimapWidget

        self._minimap = MinimapWidget(self.canvas_view, self.canvas_scene)

        # ── Sun & shade simulation (US-E3) ─────────────────────────────
        from open_garden_planner.ui.canvas.sun_shadow_controller import (
            SunShadowController,
        )
        from open_garden_planner.ui.widgets.sun_sim_toolbar import SunSimToolbar

        self._sun_controller = SunShadowController(
            self.canvas_scene, lambda: self._project_manager.location, self
        )
        self._sun_controller.state_changed.connect(self._on_sun_state_changed)
        self._sun_toolbar = SunSimToolbar(self)
        self.addToolBarBreak()
        self.addToolBar(self._sun_toolbar)
        self._sun_toolbar.setVisible(False)
        self._sun_toolbar.datetime_changed.connect(self._on_sun_sim_datetime)
        # QMainWindow's built-in toolbar context menu can show/hide the toolbar
        # behind our back — keep the menu action + controller in sync.
        self._sun_toolbar.visibilityChanged.connect(self._on_sun_toolbar_visibility)
        # The sim instant is deliberately NOT persisted: it defaults to the
        # current date/time on every app start (the toolbar seeds "now" in its
        # constructor), so a fresh simulation always reflects today.
        self._project_manager.location_changed.connect(
            self._on_location_changed_for_sun
        )

        # ── Hours-of-sun heatmap (US-E4) — recompute on demand only ────────
        from open_garden_planner.ui.canvas.sun_heatmap import SunHeatmapController

        self._sun_heatmap = SunHeatmapController(
            self.canvas_scene, lambda: self._project_manager.location, self
        )
        self._sun_heatmap.finished.connect(self._on_heatmap_finished)
        self._sun_toolbar.heatmap_requested.connect(self._on_heatmap_requested)
        self._sun_toolbar.heatmap_cleared.connect(self._sun_heatmap.clear)

        # ── 3D view (US-E6) — created lazily on first menu use ────────────
        self._view3d_window = None

        # ── Find & Replace panel (US-11.24) ──────────────────────────────────
        from open_garden_planner.ui.panels.find_replace_panel import FindReplacePanel

        self._find_panel = FindReplacePanel(self.canvas_view, parent=self)

        # Connect delete action to canvas
        self._delete_action.triggered.connect(self.canvas_view._delete_selected_items)

        # Connect undo/redo action enable state to command manager
        cmd_mgr = self.canvas_view.command_manager
        cmd_mgr.can_undo_changed.connect(self._undo_action.setEnabled)
        cmd_mgr.can_redo_changed.connect(self._redo_action.setEnabled)

        # Mark project dirty on any stack mutation — execute AND undo/redo.
        # command_executed only fires on execute, so wiring mark_dirty there left
        # undo/redo silently "clean" (issue #209). stack_changed covers all three.
        cmd_mgr.stack_changed.connect(self._project_manager.mark_dirty)

        # Refresh dependent panels after any stack mutation (add/remove/edit/
        # undo/redo). stack_changed fires exactly once per execute/register_applied
        # /undo/redo — unlike command_executed (which misses undo/redo) and the
        # can_undo/redo_changed booleans (which fire redundantly and exist only to
        # drive the toolbar Undo/Redo actions, wired at 1086-1087). A single
        # stack_changed wiring collapses the former three-signal fan-out to one
        # refresh per command and gives correct undo/redo coverage.
        cmd_mgr.stack_changed.connect(self.constraints_panel.refresh)

        # Sun shadow overlay: metadata-only edits (e.g. an object-height change)
        # repaint nothing, so scene.changed alone would miss them — stack_changed
        # closes that gap; the controller's snapshot key makes duplicates free.
        cmd_mgr.stack_changed.connect(self._sun_controller.schedule_recompute)

        # Properties panel: defer via QTimer.singleShot to avoid rebuilding mid
        # spin-box interaction. The panel itself only rebuilds when the selection
        # changes; an unchanged selection refreshes values in place (#206/#222).
        cmd_mgr.stack_changed.connect(
            lambda: QTimer.singleShot(0, self._update_properties_panel)
        )

        # Plant database panel: refresh on undo/redo too — e.g. undoing a species
        # assignment while the plant stays selected. Without this it was wired
        # only to selectionChanged/object_type_changed, so an undo/redo left the
        # species details stale until reselection. set_selected_items uses an
        # incremental toggle-visibility update, so this is cheap.
        cmd_mgr.stack_changed.connect(
            lambda: QTimer.singleShot(0, self._update_plant_database_panel)
        )

        # Companion + crop-rotation panels reflect command-mutated state (species,
        # reparent, nearby plants) — refresh on undo/redo too, not just on
        # selectionChanged (#225). Cheap list rebuilds, no editable fields.
        cmd_mgr.stack_changed.connect(self._update_companion_panel)
        cmd_mgr.stack_changed.connect(self._update_crop_rotation_panel)

        # ── Tab-based main window (US-8.7) ──────────────────────────────────────
        self._tab_widget = QTabWidget()
        self._tab_widget.setDocumentMode(True)

        # Tab 0: Garden Plan (existing canvas + sidebar)
        self._tab_widget.addTab(splitter, self.tr("Garden Plan"))

        # Tab 1: Planting Calendar (US-8.5)
        self.calendar_view = PlantingCalendarView(self.canvas_scene, self._project_manager)
        self.calendar_view.set_soil_service(self._soil_service)
        self._tab_widget.addTab(self.calendar_view, self.tr("Planting Calendar"))

        # Tab 2: Seed Inventory (US-9.4)
        self.seed_inventory_view = SeedInventoryView()
        self.seed_inventory_view.set_canvas_scene(self.canvas_scene)  # US-9.6: bidirectional links
        self._tab_widget.addTab(self.seed_inventory_view, self.tr("Seed Inventory"))

        # Tab: Tasks (US-C2, #188) — appended last (keeps existing tab indices,
        # the frost-badge setCurrentIndex(1), and Ctrl+1..4 valid).
        self.tasks_view = TasksView(
            self.canvas_scene, self._project_manager, cmd_mgr
        )
        self.tasks_view.set_soil_service(self._soil_service)
        self._tab_widget.addTab(self.tasks_view, self.tr("Tasks"))

        # Tab: Harvest (US-C1, #188) — appended last (keeps existing tab indices
        # and the frost-badge setCurrentIndex(1) valid).
        self.harvest_view = HarvestView(self.canvas_scene, self._project_manager)
        self._tab_widget.addTab(self.harvest_view, self.tr("Harvest"))

        # Keyboard shortcuts: Ctrl+1 / Ctrl+2 / Ctrl+3 to switch tabs.
        # (The "Layout / Paper Space" tab was dropped — `pdf_report_service`
        # already produces multi-page PDFs at chosen paper sizes, so a
        # second-space CAD-style print workflow added no value on top.)
        tab0_shortcut = QAction(self)
        tab0_shortcut.setShortcut(QKeySequence("Ctrl+1"))
        tab0_shortcut.triggered.connect(lambda: self._tab_widget.setCurrentIndex(0))
        self.addAction(tab0_shortcut)
        tab1_shortcut = QAction(self)
        tab1_shortcut.setShortcut(QKeySequence("Ctrl+2"))
        tab1_shortcut.triggered.connect(lambda: self._tab_widget.setCurrentIndex(1))
        self.addAction(tab1_shortcut)
        tab2_shortcut = QAction(self)
        tab2_shortcut.setShortcut(QKeySequence("Ctrl+3"))
        tab2_shortcut.triggered.connect(lambda: self._tab_widget.setCurrentIndex(2))
        self.addAction(tab2_shortcut)

        # Refresh calendar on tab switch and on canvas/location/status changes.
        # The calendar now uses a debounced schedule_refresh() that skips work
        # while its tab is hidden, so it can be wired to stack_changed (covers
        # undo/redo) without the heavyweight churn #210 flagged — fixes #225.
        self._tab_widget.currentChanged.connect(self._on_tab_changed)
        self._project_manager.location_changed.connect(
            lambda _: self.calendar_view.schedule_refresh()
        )
        self._project_manager.task_states_changed.connect(
            lambda _: self.calendar_view.schedule_refresh()
        )
        cmd_mgr.stack_changed.connect(lambda: self.calendar_view.schedule_refresh())

        # Highlight plant on canvas when user clicks a dashboard task (US-8.6)
        self.calendar_view.highlight_species.connect(self._on_highlight_species)

        # Frost alert badge in the tab-bar corner (US-12.2)
        self._frost_badge = QPushButton(self._tab_widget)
        self._frost_badge.setFlat(True)
        self._frost_badge.setFixedHeight(24)
        self._frost_badge.setToolTip(self.tr("Frost alert — click to view details in Planting Calendar"))
        self._frost_badge.clicked.connect(lambda: self._tab_widget.setCurrentIndex(1))
        self._frost_badge.hide()
        self._tab_widget.setCornerWidget(self._frost_badge, Qt.Corner.TopRightCorner)
        self.calendar_view.frost_alert_ready.connect(self._on_frost_alert_ready)

        # ── Tasks tab wiring (US-C2, #188) ───────────────────────────────────
        # Ctrl shortcut for the Tasks tab — resolve its index (don't hardcode).
        tasks_shortcut = QAction(self)
        tasks_shortcut.setShortcut(QKeySequence("Ctrl+5"))
        tasks_shortcut.triggered.connect(
            lambda: self._tab_widget.setCurrentIndex(
                self._tab_widget.indexOf(self.tasks_view)
            )
        )
        self.addAction(tasks_shortcut)
        # Reuse the calendar's single weather fetch for frost tasks.
        self.calendar_view.frost_alerts_ready.connect(self.tasks_view.set_frost_alerts)
        # Regenerate (debounced inside the view) on relevant project changes.
        self._project_manager.location_changed.connect(
            lambda _: self.tasks_view.schedule_refresh()
        )
        self._project_manager.task_states_changed.connect(
            lambda _: self.tasks_view.schedule_refresh()
        )
        self._project_manager.manual_tasks_changed.connect(
            lambda _: self.tasks_view.schedule_refresh()
        )
        self._project_manager.succession_plans_changed.connect(
            lambda _: self.tasks_view.schedule_refresh()
        )
        cmd_mgr.command_executed.connect(lambda _: self.tasks_view.schedule_refresh())
        # Task → canvas navigation.
        self.tasks_view.navigate_to_bed.connect(self._on_navigate_to_bed)
        self.tasks_view.navigate_to_species.connect(self._on_highlight_species)
        self.tasks_view.navigate_to_items.connect(self._on_navigate_to_items)

        # ── Harvest tab wiring (US-C1, #188) ─────────────────────────────────
        harvest_shortcut = QAction(self)
        harvest_shortcut.setShortcut(QKeySequence("Ctrl+6"))
        harvest_shortcut.triggered.connect(
            lambda: self._tab_widget.setCurrentIndex(
                self._tab_widget.indexOf(self.harvest_view)
            )
        )
        self.addAction(harvest_shortcut)
        # Regenerate (debounced inside the view) when harvest logs change or on
        # undo/redo (stack_changed); skipped while the tab is hidden.
        self._project_manager.harvest_logs_changed.connect(
            lambda _: self.harvest_view.schedule_refresh()
        )
        cmd_mgr.stack_changed.connect(lambda: self.harvest_view.schedule_refresh())
        self.harvest_view.navigate_to_species.connect(self._on_highlight_species)

        # Wrap tab widget + update/reminder bars in a container
        self._update_bar = UpdateBar(self)
        self._update_bar.skip_version_requested.connect(self._on_skip_version)
        # Overdue-task reminder bar (US-C2, #188) — persistent, dismissible.
        self._task_reminder_bar = TaskReminderBar(self)
        self._task_reminder_bar.show_tasks_requested.connect(
            lambda: self._tab_widget.setCurrentIndex(
                self._tab_widget.indexOf(self.tasks_view)
            )
        )
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        container_layout.addWidget(self._update_bar)
        container_layout.addWidget(self._task_reminder_bar)
        container_layout.addWidget(self._tab_widget)
        self.setCentralWidget(container)

        # Initial zoom display
        self.update_zoom(self.canvas_view.zoom_percent)

        # Initial tool display
        self.update_tool("Select")

        # Initial selection display
        self.update_selection(0, [])

        # Initialize shadow, scale bar, labels, constraints, and object snap state from settings
        QTimer.singleShot(0, self._init_shadows_from_settings)
        QTimer.singleShot(0, self._init_scale_bar_from_settings)
        QTimer.singleShot(0, self._init_labels_from_settings)
        QTimer.singleShot(0, self._init_constraints_from_settings)
        QTimer.singleShot(0, self._init_object_snap_from_settings)
        QTimer.singleShot(0, self._init_spacing_circles_from_settings)

    def _setup_sidebar(self) -> None:
        """Set up the right sidebar with collapsible panels."""
        # Create sidebar container
        self.sidebar = QWidget()
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(4)

        # Properties Panel (collapsible) - first in the sidebar since the
        # Object Gallery moved into the top toolbar (category dropdowns).
        self.properties_panel = PropertiesPanel(
            command_manager=self.canvas_view.command_manager
        )
        # Re-evaluate all three contextual panels when the selected item's type
        # changes (e.g. tree → house): each may need to show or hide. Companion is
        # included explicitly so its visibility does not rely on the incidental
        # stack_changed signal alone.
        self.properties_panel.object_type_changed.connect(self._update_plant_database_panel)
        self.properties_panel.object_type_changed.connect(self._update_companion_panel)
        self.properties_panel.object_type_changed.connect(self._update_crop_rotation_panel)
        props_panel = CollapsiblePanel(self.tr("Properties"), self.properties_panel, expanded=True)
        sidebar_layout.addWidget(props_panel)

        # 3. Layers Panel (collapsible)
        self.layers_panel = LayersPanel()
        self.layers_panel.set_layers(self.canvas_scene.layers)

        # Connect layers panel signals. All layer mutations are routed through
        # undoable commands created here; the panel itself never mutates layers.
        self.layers_panel.active_layer_changed.connect(self._on_active_layer_changed)
        self.layers_panel.layer_visibility_changed.connect(self._on_layer_visibility_change_requested)
        self.layers_panel.layer_lock_changed.connect(self._on_layer_lock_change_requested)
        # Live slider preview is non-undoable; the drag commits once on release.
        self.layers_panel.layer_opacity_changed.connect(self.canvas_scene.preview_layer_opacity)
        self.layers_panel.layer_opacity_committed.connect(self._on_layer_opacity_committed)
        self.layers_panel.layers_reordered.connect(self._on_layers_reordered)
        self.layers_panel.layer_renamed.connect(self._on_layer_renamed)
        self.layers_panel.layer_deleted.connect(self._on_layer_deleted)
        self.layers_panel.layer_add_requested.connect(self._on_layer_add_requested)

        # Connect scene layer changes to panel
        self.canvas_scene.layers_changed.connect(lambda: self.layers_panel.set_layers(self.canvas_scene.layers))
        self.canvas_scene.layer_auto_unhidden.connect(self._on_layer_auto_unhidden)
        # Keep the panel selection in sync when the active layer changes from
        # outside the panel (e.g. undo/redo of layer commands).
        self.canvas_scene.active_layer_changed.connect(self._on_scene_active_layer_changed)

        layers_panel = CollapsiblePanel(self.tr("Layers"), self.layers_panel, expanded=True)
        sidebar_layout.addWidget(layers_panel)

        # 4. Constraints Panel (collapsible) - manage distance constraints
        self.constraints_panel = ConstraintsPanel()
        self.constraints_panel.set_scene(self.canvas_scene)
        self.constraints_panel.constraint_selected.connect(
            self._on_constraint_selected
        )
        self.constraints_panel.constraint_edit_requested.connect(
            self._on_constraint_edit_requested
        )
        self.constraints_panel.constraint_delete_requested.connect(
            self._on_constraint_delete_requested
        )
        constraints_collapsible = CollapsiblePanel(
            self.tr("Constraints"), self.constraints_panel, expanded=False
        )
        # Delete-all button lives in the header, aligned with individual row × buttons
        from PyQt6.QtWidgets import QToolButton
        delete_all_btn = QToolButton()
        delete_all_btn.setText("\u00d7")
        delete_all_btn.setFixedSize(20, 20)
        delete_all_btn.setToolTip(self.tr("Delete all constraints"))
        delete_all_btn.setStyleSheet("QToolButton { color: #cc3333; font-weight: bold; }")
        delete_all_btn.clicked.connect(self.constraints_panel.delete_all)
        constraints_collapsible.add_header_widget(delete_all_btn)
        sidebar_layout.addWidget(constraints_collapsible)

        # 5. Plant Search Panel (collapsible) - for finding plants in the project
        self.plant_search_panel = PlantSearchPanel()
        self.plant_search_panel.set_canvas_scene(self.canvas_scene)

        # Debounce timer so the very chatty QGraphicsScene.changed signal does not
        # rebuild the whole list on every repaint (which tore down rows mid-click and
        # made selection flaky - issue #212).
        self._plant_search_refresh_timer = QTimer(self)
        self._plant_search_refresh_timer.setSingleShot(True)
        self._plant_search_refresh_timer.setInterval(150)
        self._plant_search_refresh_timer.timeout.connect(self._refresh_plant_search_panel)

        # Connect scene changes to (debounced) refresh of the plant list
        self.canvas_scene.changed.connect(self._on_scene_changed_for_plant_search)

        plant_search_collapsible = CollapsiblePanel(self.tr("Find Plants"), self.plant_search_panel, expanded=False)
        sidebar_layout.addWidget(plant_search_collapsible)

        # 6. Plant Details Panel (collapsible) - only shown when a plant is selected
        self.plant_database_panel = PlantDatabasePanel()
        self.plant_database_panel.search_button.clicked.connect(self._on_search_plant_database)
        self.plant_details_collapsible = CollapsiblePanel(self.tr("Plant Details"), self.plant_database_panel, expanded=True)
        sidebar_layout.addWidget(self.plant_details_collapsible)

        # 7. Companion Planting Panel (collapsible, US-10.3) — only shown for plant selection
        self.companion_panel = CompanionPanel(self._companion_service)
        self.companion_panel.set_canvas_scene(self.canvas_scene)
        self.companion_panel.set_radius_cm(self._companion_radius_cm)
        self.companion_panel.highlight_species_requested.connect(
            self._on_companion_highlight_species
        )
        self.companion_collapsible = CollapsiblePanel(
            self.tr("Companion Planting"), self.companion_panel, expanded=True
        )
        sidebar_layout.addWidget(self.companion_collapsible)

        # 8. Crop Rotation Panel (collapsible, US-10.6) — only shown for bed selection
        self.crop_rotation_panel = CropRotationPanel(self._crop_rotation_service)
        self.crop_rotation_panel.set_project_manager(self._project_manager)
        self.crop_rotation_collapsible = CollapsiblePanel(
            self.tr("Crop Rotation"), self.crop_rotation_panel, expanded=True
        )
        sidebar_layout.addWidget(self.crop_rotation_collapsible)

        # 9. Active Pest/Disease overview (US-12.7)
        self.pest_overview_panel = PestOverviewPanel()
        self.pest_overview_panel.item_activated.connect(
            self._on_pest_log_requested
        )
        self.pest_overview_collapsible = CollapsiblePanel(
            self.tr("Active Pest/Disease Issues"),
            self.pest_overview_panel,
            expanded=True,
        )
        sidebar_layout.addWidget(self.pest_overview_collapsible)

        # 10. Garden journal (US-12.9) — map-linked notes browser
        self.journal_panel = JournalPanel()
        self.journal_panel.note_activated.connect(self._on_journal_note_activated)
        self.journal_collapsible = CollapsiblePanel(
            self.tr("Garden Journal"),
            self.journal_panel,
            expanded=False,
        )
        sidebar_layout.addWidget(self.journal_collapsible)

        # 11. Smart Symbols library (US-C4) — parametric blocks
        self.smart_symbols_panel = SmartSymbolsPanel()
        self.smart_symbols_panel.symbol_selected.connect(self._on_smart_symbol_selected)
        self.smart_symbols_collapsible = CollapsiblePanel(
            self.tr("Smart Symbols"),
            self.smart_symbols_panel,
            expanded=False,
        )
        sidebar_layout.addWidget(self.smart_symbols_collapsible)

        # Route every panel through the SidebarController (US-226 accordion):
        # all bars start collapsed; hover peeks them open in place, a title click
        # toggles them open/closed. Panels keep a fixed canonical order (they are
        # never reparented) and grow to their content height when open, the
        # sidebar scrolling on overflow. add_panel call order defines the order —
        # selection-related panels sit directly under Properties, then plan
        # tools, then garden state. The controller owns all layout/state; no
        # per-panel expand persistence (always collapsed at startup). See
        # ADR-030 / arc42 §8.17.
        canonical_panels: list[tuple[str, CollapsiblePanel]] = [
            ("properties", props_panel),
            ("plant_details", self.plant_details_collapsible),
            ("companion", self.companion_collapsible),
            ("crop_rotation", self.crop_rotation_collapsible),
            ("layers", layers_panel),
            ("constraints", constraints_collapsible),
            ("pest_overview", self.pest_overview_collapsible),
            ("plant_search", plant_search_collapsible),
            ("journal", self.journal_collapsible),
            ("smart_symbols", self.smart_symbols_collapsible),
        ]
        # Detach each panel from the scratch build layout before handing it to the
        # controller (panels were addWidget'd above purely to set their parent).
        for _key, panel in canonical_panels:
            sidebar_layout.removeWidget(panel)

        self._sidebar_controller = SidebarController()
        for key, panel in canonical_panels:
            self._sidebar_controller.add_panel(key, panel)  # registers COLLAPSED
        # The selection-driven panels have nothing to show until a matching item
        # is selected — hide their bars entirely until then (restored pre-US-226
        # behaviour; the selection updaters re-show them on a relevant selection).
        for key in ("plant_details", "companion", "crop_rotation"):
            self._sidebar_controller.set_panel_visible(key, False)
        # US-C4: the Smart Symbols engine, persistence, and DXF export ship, but
        # the sidebar panel is deferred from the UI for now. It stays registered
        # (so order/wiring are untouched) but its bar is permanently hidden —
        # nothing re-shows it. Re-enable by deleting this one line.
        self._sidebar_controller.set_panel_visible("smart_symbols", False)

        sidebar_layout.addWidget(self._sidebar_controller)

    def _startup_sequence(self) -> None:
        """Handle startup sequence: recovery check, then welcome dialog."""
        # First check for recovery files
        recovery_handled = self._check_recovery_files()

        # Then show welcome dialog if enabled and no recovery was handled
        if not recovery_handled:
            self._show_welcome_dialog()
        # Deferred so it runs after the modal Welcome dialog is gone and the
        # event queue has drained — a bar shown behind a modal dialog is unseen.
        QTimer.singleShot(0, self._check_overdue_tasks)

    def _check_overdue_tasks(self) -> None:
        """Show (or hide) the overdue-MANUAL-task reminder bar (US-C2).

        Scoped to manual tasks deliberately: auto-generated tasks depend on the
        scene + an async weather fetch that aren't guaranteed ready this early.
        Uses a persistent, dismissible bar rather than a status-bar message —
        the latter is invisible behind the modal Welcome dialog and is easily
        clobbered by other status writes (see §11.4). Gated by a Preferences
        toggle (default ON). Idempotent: safe to call from multiple deferred
        startup/open paths.
        """
        from datetime import date  # noqa: PLC0415

        from open_garden_planner.app.settings import get_settings  # noqa: PLC0415

        if not get_settings().notify_overdue_tasks_on_startup:
            self._task_reminder_bar.hide()
            return
        today_iso = date.today().isoformat()
        states = self._project_manager.task_states
        overdue = 0
        for tid, raw in self._project_manager.manual_tasks.items():
            due = raw.get("date", "")
            if not due or due >= today_iso:
                continue
            st = states.get(tid, {})
            if st.get("status") in ("done", "dismissed"):
                continue
            snooze = st.get("snooze_until")
            if snooze and snooze >= today_iso:
                continue
            overdue += 1
        # show_reminder() hides the bar when the count is 0.
        self._task_reminder_bar.show_reminder(overdue)

    def _show_welcome_dialog(self) -> None:
        """Show the welcome dialog if enabled in settings."""
        from open_garden_planner.app.settings import get_settings
        from open_garden_planner.ui.dialogs import WelcomeDialog

        if not get_settings().show_welcome_on_startup:
            return

        dialog = WelcomeDialog(self)

        # Connect signals
        dialog.new_project_requested.connect(self._on_new_project)
        dialog.open_project_requested.connect(self._on_open_project)
        dialog.recent_project_selected.connect(self._open_project_file)

        dialog.exec()

    def _start_update_check(self) -> None:
        """Launch the background update checker thread (installed .exe only)."""
        import sys

        if not getattr(sys, "frozen", False):
            return  # Only check for updates when running from the installed .exe

        from open_garden_planner.services.update_checker import UpdateChecker

        self._update_checker = UpdateChecker(self)
        self._update_checker.update_available.connect(self._on_update_available)
        self._update_checker.start()

    def _on_update_available(self, tag_name: str, body: str, download_url: str, html_url: str) -> None:
        """Show the update bar if the user has not skipped this version."""
        from open_garden_planner.app.settings import get_settings

        if get_settings().skipped_version == tag_name:
            return
        self._update_bar.show_update(tag_name, body, download_url, html_url)

    def _on_skip_version(self, tag_name: str) -> None:
        """Persist the skipped version to settings."""
        from open_garden_planner.app.settings import get_settings

        get_settings().skipped_version = tag_name

    def _setup_autosave(self) -> None:
        """Set up the auto-save manager."""
        from open_garden_planner.services import AutoSaveManager

        self._autosave_manager = AutoSaveManager(self)
        self._autosave_manager.set_scene(self.canvas_scene)

        # Connect dirty state changes
        self._project_manager.dirty_changed.connect(self._autosave_manager.set_dirty)

        # Connect project path changes
        self._project_manager.project_changed.connect(self._on_project_changed_for_autosave)

        # Connect auto-save events for status bar feedback
        self._autosave_manager.autosave_performed.connect(self._on_autosave_performed)
        self._autosave_manager.autosave_failed.connect(self._on_autosave_failed)

        # Start auto-save
        self._autosave_manager.start()

    def _on_project_changed_for_autosave(self, path: str | None) -> None:
        """Handle project path change for auto-save manager.

        Args:
            path: New project file path or None
        """
        self._autosave_manager.set_project_path(Path(path) if path else None)

    def _on_autosave_performed(self, _path: str) -> None:
        """Handle successful auto-save.

        Args:
            _path: Path where auto-save was written (unused)
        """
        self.statusBar().showMessage(self.tr("Auto-saved"), 2000)

    def _on_autosave_failed(self, error: str) -> None:
        """Handle failed auto-save.

        Args:
            error: Error message
        """
        logger.error("Auto-save failed: %s", error)
        self.statusBar().showMessage(self.tr("Auto-save failed: {error}").format(error=error), 5000)

    def _check_recovery_files(self) -> bool:
        """Check for recovery files on startup and offer to restore.

        Returns:
            True if user chose to recover a file, False otherwise
        """
        from open_garden_planner.services import AutoSaveManager

        recovery_files = AutoSaveManager.find_recovery_files()
        if not recovery_files:
            return False

        recovered = False
        # Found recovery file(s) - ask user what to do
        for autosave_path, metadata in recovery_files:
            timestamp = metadata.get("timestamp", "unknown time")
            original_file = metadata.get("original_file")

            if original_file:
                message = self.tr(
                    "A recovery file was found from {timestamp}.\n\n"
                    "Original project: {original_file}\n\n"
                    "Would you like to recover this file?"
                ).format(timestamp=timestamp, original_file=original_file)
            else:
                message = self.tr(
                    "A recovery file for an unsaved project was found from {timestamp}.\n\n"
                    "Would you like to recover this file?"
                ).format(timestamp=timestamp)

            result = QMessageBox.question(
                self,
                self.tr("Recover Auto-Save"),
                message,
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Discard,
                QMessageBox.StandardButton.Yes,
            )

            if result == QMessageBox.StandardButton.Yes:
                # Load the recovery file
                self._load_recovery_file(autosave_path)
                recovered = True
            elif result == QMessageBox.StandardButton.Discard:
                # Delete the recovery file
                AutoSaveManager.delete_recovery_file(autosave_path)
            # If No, just leave it for next time

        return recovered

    def _load_recovery_file(self, recovery_path: Path) -> None:
        """Load a recovery file.

        Args:
            recovery_path: Path to the recovery file
        """
        try:
            self._project_manager.load(self.canvas_scene, recovery_path)
            self.canvas_view.command_manager.clear()
            self.canvas_view.fit_in_view()
            self.canvas_scene.update_dimension_lines()
            self.constraints_panel.refresh()

            # Mark as dirty since this is a recovery (not a normal saved project)
            self._project_manager.mark_dirty()

            # Reset the project path to None (since this is a recovery)
            self._project_manager._current_file = None
            self._project_manager.project_changed.emit(None)

            self.statusBar().showMessage(self.tr("Recovered from auto-save. Remember to save your work!"))
            QMessageBox.information(
                self,
                self.tr("Recovery Complete"),
                self.tr(
                    "Your work has been recovered from the auto-save file.\n\n"
                    "Please save your project to a permanent location."
                ),
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                self.tr("Recovery Failed"),
                self.tr("Failed to recover from auto-save:\n{error}").format(error=e),
            )

    def _update_properties_panel(self) -> None:
        """Update properties panel with current selection."""
        try:
            selected_items = self.canvas_scene.selectedItems()
            self.properties_panel.set_selected_items(selected_items)
        except RuntimeError:
            # Canvas scene has been deleted (happens during app shutdown)
            pass

    def _update_plant_database_panel(self) -> None:
        """Update plant database panel with current selection."""
        from open_garden_planner.core.object_types import ObjectType

        try:
            selected_items = self.canvas_scene.selectedItems()

            # Check if exactly one plant item is selected
            show_panel = False
            if len(selected_items) == 1:
                item = selected_items[0]
                if hasattr(item, "object_type") and item.object_type in (
                    ObjectType.TREE,
                    ObjectType.SHRUB,
                    ObjectType.PERENNIAL,
                ):
                    show_panel = True

            # Update content BEFORE auto-pinning so the open animation tweens to
            # the real content height (else it grows to the stale height, then
            # snaps when the clamp releases — US-226). The bar is hidden entirely
            # when no plant is selected (no empty placeholder bar).
            self.plant_database_panel.set_selected_items(selected_items)
            self._sidebar_controller.set_panel_visible("plant_details", show_panel)
            self._sidebar_controller.set_selection_pinned("plant_details", show_panel)
        except RuntimeError:
            # Scene has been deleted, ignore
            pass

    def _update_companion_panel(self) -> None:
        """Update the companion planting panel for the current plant selection (US-10.3)."""
        try:
            selected_items = self.canvas_scene.selectedItems()
            show_panel = False
            plant_item = None
            if len(selected_items) == 1 and self._is_canvas_plant(selected_items[0]):
                plant_item = selected_items[0]
                show_panel = bool(self._companion_species_name(plant_item))

            # Content before pin so the open animation tweens to the real height;
            # the bar is hidden when there is no companion data to show.
            self.companion_panel.update_for_plant(plant_item)
            self._sidebar_controller.set_panel_visible("companion", show_panel)
            self._sidebar_controller.set_selection_pinned("companion", show_panel)
        except RuntimeError:
            pass

    def _update_crop_rotation_panel(self) -> None:
        """Update the crop rotation panel for the current bed selection (US-10.6)."""
        try:
            selected_items = self.canvas_scene.selectedItems()
            show_panel = False
            bed_item = None
            area_id = None
            if len(selected_items) == 1:
                item = selected_items[0]
                if self._is_bed_item(item):
                    bed_item = item
                    area_id = str(item.item_id)
                    show_panel = True

            # Content before pin so the open animation tweens to the real height;
            # the bar is hidden when no bed is selected.
            self.crop_rotation_panel.update_for_bed(bed_item, area_id)
            self._sidebar_controller.set_panel_visible("crop_rotation", show_panel)
            self._sidebar_controller.set_selection_pinned("crop_rotation", show_panel)
        except RuntimeError:
            pass

    @staticmethod
    def _is_bed_item(item: object) -> bool:
        """Check if a canvas item is a bed/area suitable for crop rotation."""
        from open_garden_planner.core.object_types import ObjectType

        ot = getattr(item, "object_type", None)
        return ot in (
            ObjectType.GARDEN_BED,
            ObjectType.RAISED_BED,
            ObjectType.GREENHOUSE,
            ObjectType.COLD_FRAME,
        )

    def _on_companion_highlight_species(self, species: str) -> None:
        """Select canvas plants matching *species* when user clicks a companion entry.

        Selection is deferred via QTimer to avoid conflicts with the list widget's
        itemClicked processing (which triggers selectionChanged → panel clear mid-click).
        """
        def _do_select() -> None:
            self._tab_widget.setCurrentIndex(0)
            self.canvas_scene.clearSelection()
            matched: list = []
            for item in self.canvas_scene.items():
                if not self._is_canvas_plant(item):
                    continue
                item_species = self._companion_species_name(item)
                if item_species and self._companion_service.resolve_name(item_species) == self._companion_service.resolve_name(species):
                    item.setSelected(True)
                    matched.append(item)
            # Scroll canvas to the first matched item so the user can see it
            if matched:
                self.canvas_view.ensureVisible(matched[0])

        QTimer.singleShot(0, _do_select)

    # Slot methods for menu actions

    def _on_new_project(self) -> None:
        """Handle New Project action."""
        if not self._confirm_discard_changes():
            return

        from open_garden_planner.ui.dialogs import NewProjectDialog

        dialog = NewProjectDialog(self)
        # Pre-fill with current canvas dimensions
        dialog.set_dimensions_cm(
            self.canvas_scene.width_cm,
            self.canvas_scene.height_cm
        )

        if dialog.exec():
            # User clicked OK - create new project with specified dimensions
            width_cm = dialog.width_cm
            height_cm = dialog.height_cm

            # Reset constraints and dimension lines BEFORE scene.clear() to
            # avoid RuntimeError from accessing deleted C++ graphics objects
            self.canvas_scene.reset_constraints()

            # Clear existing objects from scene
            self.canvas_scene.clear()

            # Resize the canvas
            self.canvas_scene.resize_canvas(width_cm, height_cm)

            # Reset layers to default
            from open_garden_planner.models.layer import create_default_layers
            self.canvas_scene.set_layers(create_default_layers())
            self.layers_panel.set_layers(self.canvas_scene.layers)

            # Fit the new canvas in view
            self.canvas_view.fit_in_view()

            # Clear undo history and reset project state
            self.canvas_view.command_manager.clear()
            self.constraints_panel.refresh()
            self._project_manager.new_project()

            # Apply optional garden year chosen in dialog
            if dialog.garden_year is not None:
                self._project_manager.set_season(dialog.garden_year)

            # Clear any existing auto-save
            self._autosave_manager.clear_autosave()
            self._autosave_manager.set_project_path(None)

            # Reset compare overlay (US-10.7)
            self.canvas_scene.clear_compare_overlay()
            self._compare_overlay_action.setEnabled(False)
            self._compare_overlay_action.setChecked(False)

            # A fresh project has no overdue tasks — clear any stale reminder.
            self._task_reminder_bar.hide()

            # Update status bar
            width_m = width_cm / 100.0
            height_m = height_cm / 100.0
            status_bar = self.statusBar()
            if status_bar:
                status_bar.showMessage(
                    self.tr("New project created: {width}m x {height}m").format(
                        width=f"{width_m:.1f}", height=f"{height_m:.1f}"
                    )
                )

    def _on_canvas_size(self) -> None:
        """Handle Canvas Size action — resize the current canvas."""
        from open_garden_planner.ui.dialogs import NewProjectDialog

        dialog = NewProjectDialog(self)
        dialog.setWindowTitle(self.tr("Canvas Size"))
        dialog.set_dimensions_cm(
            self.canvas_scene.width_cm,
            self.canvas_scene.height_cm,
        )

        if dialog.exec():
            width_cm = dialog.width_cm
            height_cm = dialog.height_cm
            self.canvas_scene.resize_canvas(width_cm, height_cm)
            self.canvas_view.fit_in_view()

            width_m = width_cm / 100.0
            height_m = height_cm / 100.0
            status_bar = self.statusBar()
            if status_bar:
                status_bar.showMessage(
                    self.tr("Canvas resized to {width}m x {height}m").format(
                        width=f"{width_m:.1f}", height=f"{height_m:.1f}"
                    )
                )

    def _default_dialog_dir(self) -> Path:
        """Resolve the directory file dialogs should open in (issue #199).

        Delegates to the shared chokepoint, anchoring on the currently open
        project's folder when there is one. Never resolves to the install
        directory, where user files get wiped on upgrade.
        """
        return default_dialog_dir(self._project_manager.current_file)

    def _default_save_path(self, filename: str) -> str:
        """Build a full default path (dir + filename) for a save dialog."""
        return default_save_path(filename, self._project_manager.current_file)

    def _on_open_project(self) -> None:
        """Handle Open Project action."""
        if not self._confirm_discard_changes():
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Open Project"),
            str(self._default_dialog_dir()),
            self.tr("Open Garden Planner (*.ogp);;All Files (*)"),
        )
        if file_path:
            self._open_project_file(file_path)

    def _open_project_file(self, file_path: str) -> None:
        """Open a project file.

        Args:
            file_path: Path to the project file to open
        """
        try:
            # Clear any existing auto-save before loading new project
            self._autosave_manager.clear_autosave()

            self._project_manager.load(self.canvas_scene, Path(file_path))
            self.canvas_view.command_manager.clear()
            self.canvas_view.fit_in_view()
            self.layers_panel.set_layers(self.canvas_scene.layers)
            self.canvas_scene.update_dimension_lines()
            self.constraints_panel.refresh()
            self.statusBar().showMessage(self.tr("Opened: {path}").format(path=file_path))
            # Load compare overlay if previous seasons are linked (US-10.7)
            self._load_compare_overlay_from_previous_season()
            self.tasks_view.refresh()
            # Deferred: when opened from the modal Welcome dialog, a bar shown
            # now would sit behind it. singleShot(0) runs after it closes.
            QTimer.singleShot(0, self._check_overdue_tasks)
        except Exception as e:
            QMessageBox.critical(self, self.tr("Error"), self.tr("Failed to open file:\n{error}").format(error=e))

    def _populate_recent_menu(self) -> None:
        """Populate the Open Recent submenu with recent files."""
        from open_garden_planner.app.settings import get_settings

        self._recent_menu.clear()

        recent_files = get_settings().recent_files
        if not recent_files:
            no_recent = QAction(self.tr("No recent projects"), self)
            no_recent.setEnabled(False)
            self._recent_menu.addAction(no_recent)
            return

        for file_path in recent_files:
            path = Path(file_path)
            if path.exists():
                action = QAction(path.stem, self)
                action.setToolTip(str(path))
                action.setData(str(path))
                action.triggered.connect(
                    lambda _checked, fp=str(path): self._on_open_recent_file(fp)
                )
                self._recent_menu.addAction(action)
            else:
                # Show missing files with indicator (grayed out)
                action = QAction(self.tr("{name} (not found)").format(name=path.stem), self)
                action.setToolTip(self.tr("File not found: {path}").format(path=path))
                action.setEnabled(False)
                self._recent_menu.addAction(action)

        self._recent_menu.addSeparator()

        # Clear recent files action
        clear_action = QAction(self.tr("Clear Recent Projects"), self)
        clear_action.triggered.connect(self._on_clear_recent_files)
        self._recent_menu.addAction(clear_action)

    def _on_open_recent_file(self, file_path: str) -> None:
        """Handle opening a recent file.

        Args:
            file_path: Path to the file to open
        """
        if not self._confirm_discard_changes():
            return
        self._open_project_file(file_path)

    def _on_clear_recent_files(self) -> None:
        """Handle clearing recent files list."""
        from open_garden_planner.app.settings import get_settings

        get_settings().clear_recent_files()
        self.statusBar().showMessage(self.tr("Recent projects list cleared"), 2000)

    def _on_save(self) -> None:
        """Handle Save action."""
        if self._project_manager.current_file:
            self._save_to_file(self._project_manager.current_file)
        else:
            self._on_save_as()

    def _on_save_as(self) -> None:
        """Handle Save As action."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Save Project As"),
            self._default_save_path(self._project_manager.project_name + ".ogp"),
            self.tr("Open Garden Planner (*.ogp);;All Files (*)"),
        )
        if file_path:
            self._save_to_file(Path(file_path))

    def _save_to_file(self, file_path: Path) -> None:
        """Save the project to a specific file."""
        try:
            # Prune orphan shopping-list price entries before writing (issue #178)
            from open_garden_planner.services.shopping_list_service import (
                ShoppingListService,  # noqa: PLC0415
            )
            ShoppingListService(
                scene=self.canvas_scene,
                soil_service=self._soil_service,
                project_manager=self._project_manager,
            ).prune_stale_prices()
            self._project_manager.save(self.canvas_scene, file_path)
            # Clear the auto-save file since we've saved manually
            self._autosave_manager.clear_autosave()
            self.statusBar().showMessage(self.tr("Saved: {path}").format(path=file_path))
        except Exception as e:
            QMessageBox.critical(self, self.tr("Error"), self.tr("Failed to save file:\n{error}").format(error=e))

    def _on_export_png(self) -> None:
        """Handle Export as PNG action."""
        from open_garden_planner.ui.dialogs.export_dialog import ExportPngDialog

        # Show export dialog
        dialog = ExportPngDialog(
            self.canvas_scene.width_cm,
            self.canvas_scene.height_cm,
            self,
        )

        if dialog.exec() != ExportPngDialog.DialogCode.Accepted:
            return

        # Get file path
        default_name = self._default_save_path(self._project_manager.project_name + ".png")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Export as PNG"),
            default_name,
            self.tr("PNG Image (*.png);;All Files (*)"),
        )

        if not file_path:
            return

        # Ensure .png extension
        file_path = Path(file_path)
        if file_path.suffix.lower() != ".png":
            file_path = file_path.with_suffix(".png")

        try:
            ExportService.export_to_png(
                self.canvas_scene,
                file_path,
                dpi=dialog.selected_dpi,
                output_width_cm=dialog.selected_output_width_cm,
            )
            self.statusBar().showMessage(self.tr("Exported: {path}").format(path=file_path))
        except Exception as e:
            QMessageBox.critical(self, self.tr("Export Error"), self.tr("Failed to export PNG:\n{error}").format(error=e))

    def _on_export_svg(self) -> None:
        """Handle Export as SVG action."""
        # Get file path
        default_name = self._default_save_path(self._project_manager.project_name + ".svg")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Export as SVG"),
            default_name,
            self.tr("SVG Vector (*.svg);;All Files (*)"),
        )

        if not file_path:
            return

        # Ensure .svg extension
        file_path = Path(file_path)
        if file_path.suffix.lower() != ".svg":
            file_path = file_path.with_suffix(".svg")

        try:
            ExportService.export_to_svg(
                self.canvas_scene,
                file_path,
                output_width_cm=ExportService.PAPER_A4_LANDSCAPE_WIDTH_CM,
                title=self._project_manager.project_name,
                description="Created with Open Garden Planner",
            )
            self.statusBar().showMessage(self.tr("Exported: {path}").format(path=file_path))
        except Exception as e:
            QMessageBox.critical(self, self.tr("Export Error"), self.tr("Failed to export SVG:\n{error}").format(error=e))

    def _on_export_plant_csv(self) -> None:
        """Handle Export Plant List as CSV action."""
        # Get file path
        default_name = self._default_save_path(self._project_manager.project_name + "_plants.csv")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Export Plant List as CSV"),
            default_name,
            self.tr("CSV Spreadsheet (*.csv);;All Files (*)"),
        )

        if not file_path:
            return

        # Ensure .csv extension
        file_path = Path(file_path)
        if file_path.suffix.lower() != ".csv":
            file_path = file_path.with_suffix(".csv")

        try:
            count = ExportService.export_plant_list_to_csv(
                self.canvas_scene,
                file_path,
                include_species_data=True,
            )
            if count == 0:
                QMessageBox.information(
                    self,
                    self.tr("No Plants Found"),
                    self.tr("No plants found in the project. The CSV file will be empty."),
                )
            self.statusBar().showMessage(
                self.tr("Exported {count} plant(s) to: {path}").format(count=count, path=file_path)
            )
        except Exception as e:
            QMessageBox.critical(
                self, self.tr("Export Error"), self.tr("Failed to export plant list:\n{error}").format(error=e)
            )

    def _on_print(self) -> None:
        """Handle Print action - show options dialog then print preview."""
        from open_garden_planner.ui.dialogs import GardenPrintManager, PrintOptionsDialog

        # Show options dialog
        options = PrintOptionsDialog(
            self.canvas_scene.width_cm,
            self.canvas_scene.height_cm,
            grid_visible=self.canvas_view.grid_visible,
            labels_visible=self.canvas_scene.labels_enabled,
            parent=self,
        )

        if options.exec() != PrintOptionsDialog.DialogCode.Accepted:
            return

        # Create print manager and configure
        print_mgr = GardenPrintManager(
            self.canvas_scene,
            project_name=self._project_manager.project_name,
        )
        print_mgr.configure(
            scale_denominator=options.scale_denominator,
            include_grid=options.include_grid,
            include_labels=options.include_labels,
            include_legend=options.include_legend,
        )

        # Show print preview (which allows printing)
        print_mgr.print_preview(parent=self)

    def _on_import_dxf(self) -> None:
        """Handle Import DXF action."""
        from open_garden_planner.core.commands import CreateItemsCommand
        from open_garden_planner.services.dxf_service import DxfImportService
        from open_garden_planner.ui.dialogs.dxf_import_dialog import DxfImportDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Import DXF"),
            str(self._default_dialog_dir()),
            self.tr("DXF Files (*.dxf);;All Files (*)"),
        )
        if not file_path:
            return

        dialog = DxfImportDialog(file_path, parent=self)
        if dialog.exec() != DxfImportDialog.DialogCode.Accepted:
            return

        try:
            result = DxfImportService.import_file(
                self.canvas_scene,
                file_path,
                scale_factor=dialog.scale_factor,
                selected_layers=dialog.selected_layers,
            )
        except Exception as e:
            QMessageBox.critical(
                self, self.tr("Import Error"), self.tr("Failed to import DXF:\n{error}").format(error=e)
            )
            return

        if not result.items:
            QMessageBox.information(
                self,
                self.tr("Nothing Imported"),
                self.tr("No supported entities found in the selected layers."),
            )
            return

        cmd = CreateItemsCommand(self.canvas_scene, result.items, "DXF import")
        self.canvas_view.command_manager.execute(cmd)

        msg = self.tr("Imported {n} item(s) from DXF.").format(n=len(result.items))
        if result.skipped_count:
            types = ", ".join(result.skipped_types)
            msg += " " + self.tr("Skipped {k} unsupported entity/entities ({types}).").format(
                k=result.skipped_count, types=types
            )
        self.statusBar().showMessage(msg)

    def _on_export_dxf(self) -> None:
        """Handle Export as DXF action."""
        from open_garden_planner.services.dxf_service import DxfExportService

        default_name = self._default_save_path(self._project_manager.project_name + ".dxf")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Export as DXF"),
            default_name,
            self.tr("DXF Files (*.dxf);;All Files (*)"),
        )
        if not file_path:
            return

        file_path_obj = Path(file_path)
        if file_path_obj.suffix.lower() != ".dxf":
            file_path_obj = file_path_obj.with_suffix(".dxf")

        try:
            DxfExportService.export(self.canvas_scene, file_path_obj)
            self.statusBar().showMessage(self.tr("Exported: {path}").format(path=file_path_obj))
        except Exception as e:
            QMessageBox.critical(
                self, self.tr("Export Error"), self.tr("Failed to export DXF:\n{error}").format(error=e)
            )

    def _on_export_pdf_report(self) -> None:
        """Handle Export PDF Report action."""
        from PyQt6.QtWidgets import QProgressDialog

        from open_garden_planner.services.pdf_report_service import (
            PdfReportOptions,
            PdfReportService,
        )
        from open_garden_planner.ui.dialogs.pdf_report_dialog import PdfReportDialog

        dialog = PdfReportDialog(
            project_name=self._project_manager.project_name,
            parent=self,
        )
        if dialog.exec() != PdfReportDialog.DialogCode.Accepted:
            return

        default_name = self._default_save_path(self._project_manager.project_name + ".pdf")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Export PDF Report"),
            default_name,
            self.tr("PDF Files (*.pdf);;All Files (*)"),
        )
        if not file_path:
            return

        file_path_obj = Path(file_path)
        if file_path_obj.suffix.lower() != ".pdf":
            file_path_obj = file_path_obj.with_suffix(".pdf")

        opts = PdfReportOptions(
            paper_size=dialog.paper_size,
            orientation=dialog.orientation,
            include_cover=dialog.include_cover,
            include_overview=dialog.include_overview,
            include_bed_details=dialog.include_bed_details,
            include_plant_list=dialog.include_plant_list,
            include_garden_notes=dialog.include_garden_notes,
            garden_journal_notes=(
                self._project_manager.garden_journal_notes
                if dialog.include_garden_notes
                else None
            ),
            include_harvest_summary=dialog.include_harvest_summary,
            harvest_logs=(
                self._project_manager.harvest_logs
                if dialog.include_harvest_summary
                else None
            ),
            include_legend=dialog.include_legend,
            project_name=dialog.project_name,
            author=dialog.author,
        )

        progress = QProgressDialog(
            self.tr("Generating PDF…"), self.tr("Cancel"), 0, 100, self
        )
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(500)

        def on_progress(current: int, total: int) -> None:
            if total > 0:
                progress.setValue(int(current / total * 100))

        try:
            PdfReportService.generate(self.canvas_scene, opts, file_path_obj, on_progress)
            progress.setValue(100)
            self.statusBar().showMessage(self.tr("Exported: {path}").format(path=file_path_obj))
        except Exception as e:
            progress.cancel()
            QMessageBox.critical(
                self,
                self.tr("Export Error"),
                self.tr("Failed to export PDF report:\n{error}").format(error=e),
            )

    def _confirm_discard_changes(self) -> bool:
        """Ask user to save if there are unsaved changes.

        Returns:
            True if it's OK to proceed (saved or discarded), False to cancel.
        """
        if not self._project_manager.is_dirty:
            return True

        result = QMessageBox.question(
            self,
            self.tr("Unsaved Changes"),
            self.tr("Do you want to save changes before proceeding?"),
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )

        if result == QMessageBox.StandardButton.Save:
            self._on_save()
            return not self._project_manager.is_dirty  # True if save succeeded
        return result == QMessageBox.StandardButton.Discard

    def _update_window_title(self, _: object = None) -> None:
        """Update the window title with project name and dirty indicator."""
        name = self._project_manager.project_name
        dirty = "*" if self._project_manager.is_dirty else ""
        self.setWindowTitle(f"{name}{dirty} - Open Garden Planner")

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close - prompt to save if dirty."""
        if self._confirm_discard_changes():
            # Stop the Agent API server first, while the scene/bridge still exist.
            self._stop_agent_api()
            # Join a running heatmap worker — a QThread destroyed while
            # running aborts the process (the #230 class).
            self._sun_heatmap.shutdown()
            # Persist window/splitter/panel state before tearing down.
            self._save_ui_state()
            # Stop auto-save timer
            self._autosave_manager.stop()
            # Clear auto-save file (user chose to save or discard)
            self._autosave_manager.clear_autosave()
            event.accept()
        else:
            event.ignore()

    def _restore_ui_state(self) -> None:
        """Restore persisted window geometry and the main splitter sizes.

        Sets ``self._geometry_restored`` so the caller can decide whether to
        fall back to ``showMaximized()`` on a fresh install. Per-panel state is
        deliberately NOT restored — the sidebar accordion always starts fully
        collapsed every session (US-226, ADR-030).
        """
        self._geometry_restored = self._ui_state.restore_geometry(self)
        self._ui_state.restore_splitter("main", self._main_splitter)
        # QMainWindow.restoreState may re-show the sun-sim toolbar from a past
        # session; the simulation itself always starts OFF (runtime-only), so
        # keep menu action, toolbar and overlay in sync by forcing it hidden.
        self._sun_toolbar.setVisible(False)

    def _save_ui_state(self) -> None:
        """Persist current window geometry and the main splitter sizes.

        Pin/peek state is intentionally not persisted (US-226, ADR-030).
        """
        self._ui_state.save_geometry(self)
        self._ui_state.save_splitter("main", self._main_splitter)

    def _on_undo(self) -> None:
        """Handle Undo action."""
        cmd_mgr = self.canvas_view.command_manager
        if cmd_mgr.can_undo:
            desc = cmd_mgr.undo_description
            cmd_mgr.undo()
            self.statusBar().showMessage(self.tr("Undo: {desc}").format(desc=desc))
        else:
            self.statusBar().showMessage(self.tr("Nothing to undo"))

    def _on_redo(self) -> None:
        """Handle Redo action."""
        cmd_mgr = self.canvas_view.command_manager
        if cmd_mgr.can_redo:
            desc = cmd_mgr.redo_description
            cmd_mgr.redo()
            self.statusBar().showMessage(self.tr("Redo: {desc}").format(desc=desc))
        else:
            self.statusBar().showMessage(self.tr("Nothing to redo"))

    def _on_copy(self) -> None:
        """Handle Copy action."""
        self.canvas_view.copy_selected()

    def _on_cut(self) -> None:
        """Handle Cut action."""
        self.canvas_view.cut_selected()

    def _on_paste(self) -> None:
        """Handle Paste action."""
        self.canvas_view.paste()

    def _on_duplicate(self) -> None:
        """Handle Duplicate action."""
        self.canvas_view.duplicate_selected()

    def _on_select_all(self) -> None:
        """Handle Select All action."""
        try:
            for item in self.canvas_scene.items():
                # Only select items that are selectable (not background, grid, etc.)
                if item.flags() & item.GraphicsItemFlag.ItemIsSelectable:
                    item.setSelected(True)
            count = len(self.canvas_scene.selectedItems())
            self.statusBar().showMessage(self.tr("Selected {count} object(s)").format(count=count))
        except RuntimeError:
            pass

    def _update_autosave_menu_state(self) -> None:
        """Update auto-save menu state from settings."""
        from open_garden_planner.app.settings import get_settings

        settings = get_settings()

        # Update enabled checkbox
        self._autosave_action.setChecked(settings.autosave_enabled)

        # Update interval radio buttons
        current_interval = settings.autosave_interval_minutes
        for action in self._autosave_interval_actions:
            action.setChecked(action.data() == current_interval)

    def _on_toggle_autosave(self, enabled: bool) -> None:
        """Handle toggle auto-save action.

        Args:
            enabled: Whether auto-save should be enabled
        """
        from open_garden_planner.app.settings import get_settings

        settings = get_settings()
        settings.autosave_enabled = enabled

        if enabled:
            self._autosave_manager.start()
            self.statusBar().showMessage(self.tr("Auto-save enabled"), 2000)
        else:
            self._autosave_manager.stop()
            self.statusBar().showMessage(self.tr("Auto-save disabled"), 2000)

    def _on_set_autosave_interval(self, minutes: int) -> None:
        """Handle setting auto-save interval.

        Args:
            minutes: Interval in minutes
        """
        from open_garden_planner.app.settings import get_settings

        settings = get_settings()
        settings.autosave_interval_minutes = minutes

        # Update menu checkmarks
        for action in self._autosave_interval_actions:
            action.setChecked(action.data() == minutes)

        # Restart timer with new interval
        self._autosave_manager.restart()

        self.statusBar().showMessage(
            self.tr("Auto-save interval set to {n} minute(s)").format(n=minutes),
            2000,
        )

    def _init_shadows_from_settings(self) -> None:
        """Initialize shadow state from persisted settings."""
        from open_garden_planner.app.settings import get_settings

        enabled = get_settings().show_shadows
        self._shadows_action.setChecked(enabled)
        self.canvas_scene.set_shadows_enabled(enabled)

    def _on_toggle_shadows(self, checked: bool) -> None:
        """Handle toggle shadows action."""
        from open_garden_planner.app.settings import get_settings

        self.canvas_scene.set_shadows_enabled(checked)
        get_settings().show_shadows = checked

    def _on_toggle_sun_sim(self, checked: bool) -> None:
        """Toggle the sun & shade simulation overlay + its time toolbar (US-E3)."""
        self._sun_toolbar.setVisible(checked)
        if checked:
            self._sun_controller.set_sim_datetime(
                self._sun_toolbar.current_datetime_local()
            )
            self._sun_controller.set_enabled(True)
        else:
            self._sun_toolbar.stop_animation()
            self._sun_controller.set_enabled(False)
            self._sun_heatmap.clear()
            self._sun_toolbar.set_heatmap_active(False)

    def _on_sun_sim_datetime(self, dt) -> None:
        """A new sim instant from the toolbar — recompute the overlay."""
        self._sun_controller.set_sim_datetime(dt)
        # A daily heatmap goes stale when the DATE changes; a time-of-day
        # change leaves it valid (it aggregates the whole day).
        if (
            self._sun_heatmap.heatmap_visible()
            and self._sun_heatmap.computed_day != dt.date()
        ):
            self._sun_heatmap.clear()
            self._sun_toolbar.set_heatmap_active(False)
        if self._view3d_window is not None:
            self._apply_sun_to_3d()  # 3D light follows the sim time (US-E6)

    def _on_heatmap_requested(self) -> None:
        """Heatmap button checked — compute the shown date's hours of sun."""
        day = self._sun_toolbar.current_datetime_local().date()
        if self._sun_heatmap.run_for_day(day):
            self._sun_toolbar.set_heatmap_busy(True)
            return
        # Refused: already running, or no garden location.
        self._sun_toolbar.set_heatmap_active(False)
        if not self._sun_heatmap.is_running:
            self._set_sun_hint(
                self.tr("Set garden location first: File → Set Garden Location…")
            )

    def _on_heatmap_finished(self, success: bool) -> None:
        """Worker done — clear busy state, sync the button."""
        self._sun_toolbar.set_heatmap_busy(False)
        self._sun_toolbar.set_heatmap_active(
            success and self._sun_heatmap.heatmap_visible()
        )

    def _on_sun_toolbar_visibility(self, visible: bool) -> None:
        """Sync menu action + controller when the toolbar is shown/hidden via
        QMainWindow's built-in toolbar context menu (bypassing our action)."""
        if visible == self._sun_controller.enabled:
            return
        self._sun_sim_action.setChecked(visible)
        if visible:
            self._sun_controller.set_sim_datetime(
                self._sun_toolbar.current_datetime_local()
            )
            self._sun_controller.set_enabled(True)
        else:
            self._sun_toolbar.stop_animation()
            self._sun_controller.set_enabled(False)
            self._sun_heatmap.clear()
            self._sun_toolbar.set_heatmap_active(False)

    def _on_sun_state_changed(self, state: str) -> None:
        """Surface the simulation's empty states as a toolbar hint."""
        from open_garden_planner.ui.canvas.sun_shadow_controller import (
            STATE_NIGHT,
            STATE_NO_LOCATION,
        )

        if state == STATE_NO_LOCATION:
            self._set_sun_hint(
                self.tr("Set garden location first: File → Set Garden Location…")
            )
        elif state == STATE_NIGHT:
            self._set_sun_hint(
                self.tr("Night — the sun is below the horizon")
            )
        else:
            self._set_sun_hint("")

    def _set_sun_hint(self, text: str) -> None:
        """Show/clear the sun-sim hint on the STATUS BAR (empty text hides it).

        Deliberately not a sun-toolbar widget: a variable-width label in the
        toolbar's flow reflowed Qt's overflow popup and bumped the Animate
        button to another row when the night text toggled on/off (2026-07).
        """
        self._sun_hint_label.setText(text)
        self._sun_hint_label.setVisible(bool(text))

    def _on_location_changed_for_sun(self, _location: object) -> None:
        """Location edits re-solve the sun position immediately (no debounce)."""
        self._sun_controller.recompute_now()
        if self._view3d_window is not None:
            self._apply_sun_to_3d()

    # ── 3D view (US-E6) ──────────────────────────────────────────

    def _on_open_3d_view(self) -> None:
        """Open (or raise) the 3D viewer; snapshot the plan on open.

        Lazy import — the view3d package (and with it PyQt6.Qt3D*) loads
        only when the user actually asks for 3D (ADR-038 boundary).
        """
        if self._view3d_window is None:
            from open_garden_planner.ui.view3d.view3d_window import View3DWindow

            window = View3DWindow(None)  # top-level sibling window
            window.refresh_requested.connect(self._refresh_3d_view)
            self._view3d_window = window
        self._refresh_3d_view()
        self._apply_sun_to_3d()
        self._view3d_window.show()
        self._view3d_window.raise_()
        self._view3d_window.activateWindow()

    def _refresh_3d_view(self) -> None:
        if self._view3d_window is None:
            return
        from open_garden_planner.ui.view3d.snapshot import collect_scene3d_records

        # US-E8: the 3D view shares the sim growth timeline.
        records = collect_scene3d_records(
            self.canvas_scene,
            at_date=self._sun_controller.sim_datetime_utc.date(),
        )
        self._view3d_window.rebuild(
            records, self.canvas_scene.width_cm, self.canvas_scene.height_cm
        )

    def _apply_sun_to_3d(self) -> None:
        """Drive the 3D light from the sim instant + project location.

        Without a location there is no solar position — a pleasant fixed
        default (elev 50°, az 180° ≈ southern midday sun) keeps the view
        usable; documented in FR-SUN-06."""
        if self._view3d_window is None:
            return
        from open_garden_planner.core.solar import solar_position

        location = self._project_manager.location
        latitude = location.get("latitude") if isinstance(location, dict) else None
        longitude = location.get("longitude") if isinstance(location, dict) else None
        if latitude is None or longitude is None:
            self._view3d_window.set_sun(50.0, 180.0)
            return
        position = solar_position(
            latitude, longitude, self._sun_controller.sim_datetime_utc
        )
        self._view3d_window.set_sun(
            position.elevation_deg, position.azimuth_deg
        )

    # NOTE: the 3D window is created ONCE per session and merely hides on
    # close (QMainWindow default) — destroying a live Qt3DWindow mid-session
    # (deleteLater on close) races the RHI render thread and segfaults
    # (#230-class, reproduced by the E2E workflow test). Reopening reuses
    # the window and re-snapshots the plan.

    def _init_scale_bar_from_settings(self) -> None:
        """Initialize scale bar state from persisted settings."""
        from open_garden_planner.app.settings import get_settings

        enabled = get_settings().show_scale_bar
        self._scale_bar_action.setChecked(enabled)
        self.canvas_view.set_scale_bar_visible(enabled)

    def _on_toggle_scale_bar(self, checked: bool) -> None:
        """Handle toggle scale bar action."""
        from open_garden_planner.app.settings import get_settings

        self.canvas_view.set_scale_bar_visible(checked)
        get_settings().show_scale_bar = checked

    def _init_labels_from_settings(self) -> None:
        """Initialize labels state from persisted settings."""
        from open_garden_planner.app.settings import get_settings

        enabled = get_settings().show_labels
        self._labels_action.setChecked(enabled)
        self.canvas_scene.set_labels_visible(enabled)

    def _on_toggle_labels(self, checked: bool) -> None:
        """Handle toggle labels action."""
        from open_garden_planner.app.settings import get_settings

        self.canvas_scene.set_labels_visible(checked)
        get_settings().show_labels = checked

    def _init_constraints_from_settings(self) -> None:
        """Initialize constraints visibility from persisted settings."""
        from open_garden_planner.app.settings import get_settings

        enabled = get_settings().show_constraints
        self._constraints_action.setChecked(enabled)
        self.canvas_view.set_constraints_visible(enabled)

    def _on_toggle_constraints(self, checked: bool) -> None:
        """Handle toggle constraints action."""
        from open_garden_planner.app.settings import get_settings

        self.canvas_view.set_constraints_visible(checked)
        get_settings().show_constraints = checked

    def _on_toggle_construction(self, checked: bool) -> None:
        """Handle toggle construction geometry visibility action."""
        self.canvas_scene.set_construction_visible(checked)

    def _on_toggle_guides(self, checked: bool) -> None:
        """Handle toggle guide lines and rulers visibility action."""
        self.canvas_view.set_guides_visible(checked)

    def _on_toggle_companion_warnings(self, checked: bool) -> None:
        """Handle toggle companion planting warnings."""
        self._companion_warnings_enabled = checked
        if not checked:
            self._clear_companion_highlights()
        else:
            self._update_companion_highlights()

    def _init_spacing_circles_from_settings(self) -> None:
        """Initialize spacing circles state from persisted settings."""
        from open_garden_planner.app.settings import get_settings

        enabled = get_settings().show_spacing_circles
        self._spacing_circles_action.setChecked(enabled)
        self.canvas_scene.set_spacing_circles_visible(enabled)
        self._spacing_circles_enabled = enabled
        if enabled:
            self._update_spacing_overlaps()

    def _on_toggle_spacing_circles(self, checked: bool) -> None:
        """Handle toggle spacing circles action."""
        from open_garden_planner.app.settings import get_settings

        self._spacing_circles_enabled = checked
        self.canvas_scene.set_spacing_circles_visible(checked)
        get_settings().show_spacing_circles = checked
        if checked:
            self._update_spacing_overlaps()
        else:
            self._clear_spacing_overlaps()

    def _on_toggle_minimap(self, checked: bool) -> None:
        """Handle toggle minimap action."""
        self._minimap.set_visible(checked)

    def _setup_soil_overlay_toolbar(self) -> None:
        """Build the parameter-picker toolbar for the soil overlay (US-12.10b).

        The toolbar is visible only while the overlay is active so it doesn't
        clutter the UI for users who don't track soil tests.
        """
        self.soil_overlay_toolbar = QToolBar(self.tr("Soil Overlay"), self)
        self.soil_overlay_toolbar.setObjectName("soil_overlay_toolbar")
        self.soil_overlay_toolbar.setMovable(False)
        self.soil_overlay_toolbar.addWidget(QLabel(self.tr("Soil parameter:") + " "))
        self._soil_param_combo = QComboBox(self.soil_overlay_toolbar)
        # (display label, parameter key) — labels translated via self.tr.
        for key, label in (
            (PARAM_OVERALL, self.tr("Overall")),
            (PARAM_PH, self.tr("pH")),
            (PARAM_N, self.tr("Nitrogen (N)")),
            (PARAM_P, self.tr("Phosphorus (P)")),
            (PARAM_K, self.tr("Potassium (K)")),
        ):
            self._soil_param_combo.addItem(label, key)
        self._soil_param_combo.currentIndexChanged.connect(
            self._on_soil_overlay_param_changed
        )
        self.soil_overlay_toolbar.addWidget(self._soil_param_combo)
        self.addToolBar(self.soil_overlay_toolbar)
        self.soil_overlay_toolbar.setVisible(False)

    def _on_toggle_soil_overlay(self, checked: bool) -> None:
        """Show/hide the soil-health overlay and its parameter toolbar."""
        self.canvas_view.set_soil_overlay_visible(checked)
        self.soil_overlay_toolbar.setVisible(checked)

    def _on_soil_overlay_param_changed(self, index: int) -> None:
        """Forward combo changes to the canvas view."""
        key = self._soil_param_combo.itemData(index)
        if isinstance(key, str) and key in ALL_PARAMS:
            self.canvas_view.set_soil_overlay_param(key)

    def _on_toggle_find_replace(self) -> None:
        """Toggle Find & Replace panel visibility."""
        self._find_panel.refresh_combos()
        self._find_panel.setVisible(not self._find_panel.isVisible())
        if self._find_panel.isVisible():
            self._find_panel.activateWindow()
            self._find_panel.raise_()

    def _on_scene_changed_for_companion(self) -> None:
        """Debounce companion highlight refresh when scene items move."""
        # Guarded: the scene can emit `changed` during teardown after the timer's
        # C++ object is gone — an unguarded slot RuntimeError aborts the interpreter
        # (matches _on_scene_changed_for_plant_search).
        with contextlib.suppress(RuntimeError):
            self._companion_update_timer.start()

    @staticmethod
    def _companion_species_name(item: object) -> str:
        """Return the best available species name for companion lookup.

        Plants placed via gallery set ``item.plant_species`` (the SVG key).
        Plants assigned via plant-search store full data in
        ``item.metadata["plant_species"]`` as a dict with ``common_name`` /
        ``scientific_name``.  We try the metadata dict first (more precise),
        then fall back to the SVG key.
        """
        meta = getattr(item, 'metadata', {}) or {}
        species_data = meta.get("plant_species") if isinstance(meta, dict) else None
        if isinstance(species_data, dict):
            name = species_data.get("common_name") or species_data.get("scientific_name") or ""
            if name:
                return name
        return getattr(item, 'plant_species', '') or ''

    @staticmethod
    def _is_canvas_plant(item: object) -> bool:
        """Return True if *item* is a plant-type canvas item."""
        return (
            hasattr(item, 'plant_species')
            and is_plant_type(getattr(item, 'object_type', None))
        )

    def _clear_companion_highlights(self) -> None:
        """Remove all companion highlight rings and warning badges from canvas items."""
        for item in self.canvas_scene.items():
            if hasattr(item, 'set_companion_highlight'):
                item.set_companion_highlight(None)
            if hasattr(item, 'set_antagonist_warning'):
                item.set_antagonist_warning(False)

    def _update_companion_highlights(self) -> None:
        """Refresh companion planting highlight rings and permanent warning badges."""
        import math

        try:
            scene_items = self.canvas_scene.items()
        except RuntimeError:
            return  # Scene already deleted during shutdown

        # Clear existing highlights and warnings
        for item in scene_items:
            if hasattr(item, 'set_companion_highlight'):
                item.set_companion_highlight(None)
            if hasattr(item, 'set_antagonist_warning'):
                item.set_antagonist_warning(False)

        if not self._companion_warnings_enabled:
            return

        all_plants = [
            it for it in self.canvas_scene.items()
            if self._is_canvas_plant(it) and self._companion_species_name(it)
        ]

        # 1. Selection-based coloured rings (beneficial / antagonistic)
        selected_plants = [it for it in self.canvas_scene.selectedItems() if it in all_plants]
        for selected_plant in selected_plants:
            sel_center = selected_plant.mapToScene(selected_plant.rect().center())  # type: ignore[attr-defined]
            sel_species = self._companion_species_name(selected_plant)

            for other in all_plants:
                if other is selected_plant:
                    continue
                other_center = other.mapToScene(other.rect().center())  # type: ignore[attr-defined]
                dist = math.hypot(
                    sel_center.x() - other_center.x(),
                    sel_center.y() - other_center.y(),
                )
                if dist > self._companion_radius_cm:
                    continue

                other_species = self._companion_species_name(other)
                rel = self._companion_service.get_relationship(sel_species, other_species)
                if rel is None:
                    continue

                # Antagonistic takes priority over beneficial when multiple plants selected
                current = getattr(other, '_companion_highlight', None)
                if rel.type == ANTAGONISTIC:
                    other.set_companion_highlight(ANTAGONISTIC)  # type: ignore[attr-defined]
                elif rel.type == BENEFICIAL and current != ANTAGONISTIC:
                    other.set_companion_highlight(BENEFICIAL)  # type: ignore[attr-defined]

        # 2. Permanent warning badge: show on any plant that has an antagonist nearby
        for plant_a in all_plants:
            center_a = plant_a.mapToScene(plant_a.rect().center())  # type: ignore[attr-defined]
            species_a = self._companion_species_name(plant_a)
            for plant_b in all_plants:
                if plant_b is plant_a:
                    continue
                center_b = plant_b.mapToScene(plant_b.rect().center())  # type: ignore[attr-defined]
                dist = math.hypot(center_a.x() - center_b.x(), center_a.y() - center_b.y())
                if dist > self._companion_radius_cm:
                    continue
                rel = self._companion_service.get_relationship(
                    species_a, self._companion_species_name(plant_b)
                )
                if rel is not None and rel.type == ANTAGONISTIC:
                    plant_a.set_antagonist_warning(True)  # type: ignore[attr-defined]
                    break  # one antagonist is enough

    # -- Spacing circle overlap detection (US-11.2) --

    def _on_scene_changed_for_spacing(self) -> None:
        """Debounce spacing overlap refresh when scene items move."""
        with contextlib.suppress(RuntimeError):
            self._spacing_update_timer.start()

    def _clear_spacing_overlaps(self) -> None:
        """Clear all spacing overlap indicators."""
        try:
            items = self.canvas_scene.items()
        except RuntimeError:
            return
        for item in items:
            if hasattr(item, 'set_spacing_overlap'):
                item.set_spacing_overlap(None)

    def _update_spacing_overlaps(self) -> None:
        """Refresh spacing overlap status for all plants.

        Groups plants by parent bed for efficient pairwise checks.
        """
        import math

        # Container capacity is independent of the spacing-circle toggle, so it
        # runs first — on the same triggers (timer, selection, create/move).
        self._update_container_capacity()

        if not self._spacing_circles_enabled:
            return

        try:
            scene_items = self.canvas_scene.items()
        except RuntimeError:
            return

        all_plants = [
            it for it in scene_items
            if self._is_canvas_plant(it)
        ]

        # Clear existing overlap status
        for plant in all_plants:
            plant.set_spacing_overlap(None)  # type: ignore[attr-defined]

        # Group plants by parent bed
        bed_groups: dict[str, list] = {}
        orphans: list = []
        for plant in all_plants:
            bed_id = getattr(plant, '_parent_bed_id', None)
            if bed_id is not None:
                key = str(bed_id)
                bed_groups.setdefault(key, []).append(plant)
            else:
                orphans.append(plant)

        # Index every item by id once so each group can resolve its parent
        # without an O(n) scan (US-C3b: trellis groups need a 1-D distance).
        by_id: dict[str, object] = {}
        for it in scene_items:
            iid = getattr(it, "item_id", None)
            if iid is not None:
                by_id[str(iid)] = it

        # Check overlaps within each group. A TRELLIS parent uses a 1-D distance
        # measured along its long axis (climbers are spaced along the bar; their
        # perpendicular/canvas-Y offset is placement noise — US-C3b).
        from open_garden_planner.core.object_types import ObjectType

        for key, group in bed_groups.items():
            parent = by_id.get(key)
            if parent is not None and getattr(parent, "object_type", None) is ObjectType.TRELLIS:
                distance = self._trellis_axis_distance_fn(parent)
            else:
                distance = math.hypot
            self._check_spacing_group(group, distance)
        if orphans:
            self._check_spacing_group(orphans, math.hypot)

    def _trellis_axis_distance_fn(self, trellis: object):
        """Return a 1-D distance callable projecting onto the trellis long axis.

        Climbers on a trellis are spaced along its long (rotation-aware) edge;
        the perpendicular component of the separation is discarded. Returns a
        ``(dx, dy) -> float`` callable measuring ``|separation · axis_unit|`` in
        scene space. Falls back to ``math.hypot`` for a degenerate (zero-size)
        rectangle.
        """
        import math

        from PyQt6.QtCore import QPointF

        # TRELLIS is rectangle-only for app-authored files, but a hand-edited or
        # future-imported .ogp could tag a non-rect shape — degrade to 2-D rather
        # than crash the whole spacing refresh.
        if not hasattr(trellis, "rect"):
            return math.hypot
        rect = trellis.rect()  # type: ignore[attr-defined]
        if rect.width() >= rect.height():
            p0 = QPointF(rect.left(), rect.center().y())
            p1 = QPointF(rect.right(), rect.center().y())
        else:
            p0 = QPointF(rect.center().x(), rect.top())
            p1 = QPointF(rect.center().x(), rect.bottom())
        s0 = trellis.mapToScene(p0)  # type: ignore[attr-defined]
        s1 = trellis.mapToScene(p1)  # type: ignore[attr-defined]
        vx, vy = s1.x() - s0.x(), s1.y() - s0.y()
        mag = math.hypot(vx, vy)
        if mag == 0:
            return math.hypot
        ux, uy = vx / mag, vy / mag
        return lambda dx, dy: abs(dx * ux + dy * uy)

    def _check_spacing_group(self, plants: list, distance: object) -> None:
        """Check spacing overlaps within a group of sibling plants.

        Only plants with real spacing data (from database or user override)
        participate in overlap detection. Plants without data are skipped.

        ``distance`` is a ``(dx, dy) -> float`` callable: ``math.hypot`` for the
        normal 2-D case, or a 1-D along-axis projection for a trellis group
        (US-C3b). Both have the same signature, so the loop below is identical.
        """
        # Filter to plants that have spacing data
        with_data = [
            p for p in plants
            if p.effective_spacing_radius() is not None  # type: ignore[attr-defined]
        ]
        if len(with_data) < 2:
            # Single plant with data gets "ideal"
            for p in with_data:
                p.set_spacing_overlap("ideal")  # type: ignore[attr-defined]
            return

        overlap_set: set[int] = set()

        for i, plant_a in enumerate(with_data):
            center_a = plant_a.mapToScene(plant_a.rect().center())  # type: ignore[attr-defined]
            radius_a = plant_a.effective_spacing_radius()  # type: ignore[attr-defined]

            for plant_b in with_data[i + 1:]:
                center_b = plant_b.mapToScene(plant_b.rect().center())  # type: ignore[attr-defined]
                radius_b = plant_b.effective_spacing_radius()  # type: ignore[attr-defined]

                dist = distance(  # type: ignore[operator]
                    center_a.x() - center_b.x(),
                    center_a.y() - center_b.y(),
                )

                if dist < radius_a + radius_b:
                    overlap_set.add(id(plant_a))
                    overlap_set.add(id(plant_b))

        for plant in with_data:
            if id(plant) in overlap_set:
                plant.set_spacing_overlap("overlap")  # type: ignore[attr-defined]
            else:
                plant.set_spacing_overlap("ideal")  # type: ignore[attr-defined]

    def _update_container_capacity(self) -> None:
        """Flag containers whose plants overflow their footprint (US-C3).

        Sums each container's child plant footprints (true drawn area, not the
        spacing circle) and compares to the container footprint via
        ``container_model.is_capacity_exceeded``; sets the per-item badge state.
        """
        from open_garden_planner.core import container_model as cm
        from open_garden_planner.core.object_types import is_container_type
        from open_garden_planner.ui.canvas.items.garden_item import GardenItemMixin

        try:
            scene_items = list(self.canvas_scene.items())
        except RuntimeError:
            return

        by_id: dict[str, object] = {}
        for it in scene_items:
            iid = getattr(it, "item_id", None)
            if iid is not None:
                by_id[str(iid)] = it

        for item in scene_items:
            if not isinstance(item, GardenItemMixin):
                continue
            if not is_container_type(getattr(item, "object_type", None)):
                continue
            footprint = item._compute_area_cm2() or 0.0
            child_areas: list[float] = []
            for child_id in item.child_item_ids:
                child = by_id.get(str(child_id))
                if child is None:
                    continue
                area = child._compute_area_cm2() if hasattr(child, "_compute_area_cm2") else None
                if area:
                    child_areas.append(float(area))
            item.set_capacity_overrun(cm.is_capacity_exceeded(footprint, child_areas))

    # -- Constraints panel handlers --

    def _on_constraint_selected(self, constraint_id: object) -> None:
        """Handle constraint selected in constraints panel.

        Selects both objects involved in the constraint on the canvas.

        Args:
            constraint_id: UUID of the selected constraint
        """
        from uuid import UUID

        from open_garden_planner.ui.canvas.items.garden_item import GardenItemMixin

        cid = constraint_id if isinstance(constraint_id, UUID) else UUID(str(constraint_id))
        graph = self.canvas_scene.constraint_graph
        constraint = graph.constraints.get(cid)
        if constraint is None:
            return

        # Clear current selection and select both constrained objects
        self.canvas_scene.clearSelection()
        target_ids = {constraint.anchor_a.item_id, constraint.anchor_b.item_id}
        for item in self.canvas_scene.items():
            if isinstance(item, GardenItemMixin) and item.item_id in target_ids:
                item.setSelected(True)

    def _on_constraint_edit_requested(self, constraint_id: object) -> None:
        """Handle constraint double-click for distance editing.

        Args:
            constraint_id: UUID of the constraint to edit
        """
        from uuid import UUID

        cid = constraint_id if isinstance(constraint_id, UUID) else UUID(str(constraint_id))
        self.canvas_view._edit_constraint_distance(cid)
        self.constraints_panel.refresh()

    def _on_constraint_delete_requested(self, constraint_id: object) -> None:
        """Handle constraint delete from constraints panel.

        Args:
            constraint_id: UUID of the constraint to delete
        """
        from uuid import UUID

        from open_garden_planner.core.commands import RemoveConstraintCommand

        cid = constraint_id if isinstance(constraint_id, UUID) else UUID(str(constraint_id))
        graph = self.canvas_scene.constraint_graph
        constraint = graph.constraints.get(cid)
        if constraint is None:
            return

        cmd = RemoveConstraintCommand(graph, constraint)
        self.canvas_view.command_manager.execute(cmd)
        self.canvas_scene.update_dimension_lines()

    def _init_object_snap_from_settings(self) -> None:
        """Initialize object snap state from persisted settings."""
        from open_garden_planner.app.settings import get_settings

        settings = get_settings()
        enabled = settings.object_snap_enabled
        self._object_snap_action.setChecked(enabled)
        self.canvas_view.set_object_snap_enabled(enabled)

        mid = settings.midpoint_snap_enabled
        self._midpoint_snap_action.setChecked(mid)
        self.canvas_view.set_midpoint_snap_enabled(mid)

        inter = settings.intersection_snap_enabled
        self._intersection_snap_action.setChecked(inter)
        self.canvas_view.set_intersection_snap_enabled(inter)

        near = settings.nearest_snap_enabled
        self._nearest_snap_action.setChecked(near)
        self.canvas_view.set_nearest_snap_enabled(near)

        perp = settings.perpendicular_snap_enabled
        self._perpendicular_snap_action.setChecked(perp)
        self.canvas_view.set_perpendicular_snap_enabled(perp)

        tan = settings.tangent_snap_enabled
        self._tangent_snap_action.setChecked(tan)
        self.canvas_view.set_tangent_snap_enabled(tan)

        dyn = settings.dynamic_input_enabled
        self._dynamic_input_action.setChecked(dyn)
        self.canvas_view.set_dynamic_input_enabled(dyn)

    def _on_toggle_preview_mode(self, checked: bool) -> None:
        """Handle toggle preview mode action."""
        if checked:
            self._enter_preview_mode()
        else:
            self._exit_preview_mode()

    def _enter_preview_mode(self) -> None:
        """Enter fullscreen preview mode, hiding all UI chrome."""
        if self._preview_mode:
            return

        # Save current state so we can restore it
        self._pre_preview_state = {
            "grid_visible": self.canvas_view.grid_visible,
            "scale_bar_visible": self.canvas_view.scale_bar_visible,
            "labels_visible": self.canvas_scene.labels_enabled,
            "constraints_visible": self.canvas_scene.constraints_visible,
            "was_maximized": self.isMaximized(),
        }

        self._preview_mode = True

        # Deselect all objects (hides selection handles and annotations)
        self.canvas_scene.clearSelection()

        # Switch to select tool to cancel any in-progress drawing
        self.canvas_view.set_active_tool(ToolType.SELECT)

        # Hide UI chrome
        self.menuBar().hide()
        self.statusBar().hide()
        self.main_toolbar.hide()
        self.sidebar.hide()
        self._pre_preview_state["soil_overlay_toolbar_visible"] = (
            self.soil_overlay_toolbar.isVisible()
        )
        self.soil_overlay_toolbar.hide()

        # Hide canvas overlays
        self.canvas_view.set_grid_visible(False)
        self.canvas_view.set_scale_bar_visible(False)
        self.canvas_scene.set_labels_visible(False)
        self.canvas_view.set_constraints_visible(False)

        # Go fullscreen
        self.showFullScreen()

        # Fit the canvas nicely after entering fullscreen
        QTimer.singleShot(50, self.canvas_view.fit_in_view)

    def _exit_preview_mode(self) -> None:
        """Exit fullscreen preview mode, restoring all UI chrome."""
        if not self._preview_mode:
            return

        self._preview_mode = False
        self._preview_action.setChecked(False)

        # Restore UI chrome
        self.menuBar().show()
        self.statusBar().show()
        self.main_toolbar.show()
        self.sidebar.show()
        if (self._pre_preview_state or {}).get("soil_overlay_toolbar_visible"):
            self.soil_overlay_toolbar.show()

        # Restore canvas overlays from saved state
        state = self._pre_preview_state or {}
        self.canvas_view.set_grid_visible(state.get("grid_visible", False))
        self.grid_action.setChecked(state.get("grid_visible", False))
        self.canvas_view.set_scale_bar_visible(state.get("scale_bar_visible", True))
        self._scale_bar_action.setChecked(state.get("scale_bar_visible", True))
        self.canvas_scene.set_labels_visible(state.get("labels_visible", True))
        self._labels_action.setChecked(state.get("labels_visible", True))
        self.canvas_view.set_constraints_visible(state.get("constraints_visible", True))
        self._constraints_action.setChecked(state.get("constraints_visible", True))

        # Restore window state
        if state.get("was_maximized", True):
            self.showMaximized()
        else:
            self.showNormal()

        self._pre_preview_state = None

    def keyPressEvent(self, event) -> None:
        """Handle key press events for preview mode toggle."""
        if event.key() == Qt.Key.Key_F11:
            if self._preview_mode:
                self._exit_preview_mode()
            else:
                self._enter_preview_mode()
            event.accept()
            return
        if self._preview_mode and event.key() == Qt.Key.Key_Escape:
            self._exit_preview_mode()
            event.accept()
            return
        super().keyPressEvent(event)

    def _on_toggle_grid(self, checked: bool) -> None:
        """Handle toggle grid action."""
        self.canvas_view.set_grid_visible(checked)

    def _on_toggle_snap(self, checked: bool) -> None:
        """Handle toggle snap action."""
        self.canvas_view.set_snap_enabled(checked)

    def _on_toggle_object_snap(self, checked: bool) -> None:
        """Handle toggle object snap action."""
        from open_garden_planner.app.settings import get_settings

        self.canvas_view.set_object_snap_enabled(checked)
        get_settings().object_snap_enabled = checked

    def _on_toggle_midpoint_snap(self, checked: bool) -> None:
        """Handle toggle midpoint snap action (Package A US-A3)."""
        from open_garden_planner.app.settings import get_settings

        self.canvas_view.set_midpoint_snap_enabled(checked)
        get_settings().midpoint_snap_enabled = checked

    def _on_toggle_intersection_snap(self, checked: bool) -> None:
        """Handle toggle intersection snap action (Package A US-A3)."""
        from open_garden_planner.app.settings import get_settings

        self.canvas_view.set_intersection_snap_enabled(checked)
        get_settings().intersection_snap_enabled = checked

    def _on_toggle_nearest_snap(self, checked: bool) -> None:
        """Handle toggle nearest-point fallback snap (Package B US-B4)."""
        from open_garden_planner.app.settings import get_settings

        self.canvas_view.set_nearest_snap_enabled(checked)
        get_settings().nearest_snap_enabled = checked

    def _on_toggle_perpendicular_snap(self, checked: bool) -> None:
        """Handle toggle perpendicular snap (Package B US-B5)."""
        from open_garden_planner.app.settings import get_settings

        self.canvas_view.set_perpendicular_snap_enabled(checked)
        get_settings().perpendicular_snap_enabled = checked

    def _on_toggle_tangent_snap(self, checked: bool) -> None:
        """Handle toggle tangent snap (Package B US-B6)."""
        from open_garden_planner.app.settings import get_settings

        self.canvas_view.set_tangent_snap_enabled(checked)
        get_settings().tangent_snap_enabled = checked

    def _on_toggle_dynamic_input(self, checked: bool) -> None:
        """Handle toggle dynamic input action (Package A US-A4)."""
        from open_garden_planner.app.settings import get_settings

        self.canvas_view.set_dynamic_input_enabled(checked)
        get_settings().dynamic_input_enabled = checked

    def _on_align_left(self) -> None:
        """Align selected objects to the left edge."""
        from open_garden_planner.core.alignment import AlignMode
        self.canvas_view.align_selected(AlignMode.LEFT)

    def _on_align_right(self) -> None:
        """Align selected objects to the right edge."""
        from open_garden_planner.core.alignment import AlignMode
        self.canvas_view.align_selected(AlignMode.RIGHT)

    def _on_align_top(self) -> None:
        """Align selected objects to the top edge."""
        from open_garden_planner.core.alignment import AlignMode
        self.canvas_view.align_selected(AlignMode.TOP)

    def _on_align_bottom(self) -> None:
        """Align selected objects to the bottom edge."""
        from open_garden_planner.core.alignment import AlignMode
        self.canvas_view.align_selected(AlignMode.BOTTOM)

    def _on_align_center_h(self) -> None:
        """Align selected objects to horizontal center."""
        from open_garden_planner.core.alignment import AlignMode
        self.canvas_view.align_selected(AlignMode.CENTER_H)

    def _on_align_center_v(self) -> None:
        """Align selected objects to vertical center."""
        from open_garden_planner.core.alignment import AlignMode
        self.canvas_view.align_selected(AlignMode.CENTER_V)

    def _on_distribute_horizontal(self) -> None:
        """Distribute selected objects with equal horizontal spacing."""
        from open_garden_planner.core.alignment import DistributeMode
        self.canvas_view.distribute_selected(DistributeMode.HORIZONTAL)

    def _on_distribute_vertical(self) -> None:
        """Distribute selected objects with equal vertical spacing."""
        from open_garden_planner.core.alignment import DistributeMode
        self.canvas_view.distribute_selected(DistributeMode.VERTICAL)

    def _on_zoom_in(self) -> None:
        """Handle zoom in action."""
        self.canvas_view.zoom_in()

    def _on_zoom_out(self) -> None:
        """Handle zoom out action."""
        self.canvas_view.zoom_out()

    def _on_fit_to_window(self) -> None:
        """Handle fit to window action."""
        self.canvas_view.fit_in_view()

    def _update_theme_menu_state(self) -> None:
        """Update theme menu state from settings."""
        from open_garden_planner.app.settings import get_settings

        settings = get_settings()
        current_theme = settings.theme_mode

        # Update checkboxes
        self._light_theme_action.setChecked(current_theme == ThemeMode.LIGHT)
        self._dark_theme_action.setChecked(current_theme == ThemeMode.DARK)
        self._system_theme_action.setChecked(current_theme == ThemeMode.SYSTEM)

    def _on_theme_changed(self, mode: ThemeMode) -> None:
        """Handle theme change action.

        Args:
            mode: New theme mode to apply
        """
        from open_garden_planner.app.settings import get_settings

        settings = get_settings()
        settings.theme_mode = mode

        # Update menu checkmarks
        self._light_theme_action.setChecked(mode == ThemeMode.LIGHT)
        self._dark_theme_action.setChecked(mode == ThemeMode.DARK)
        self._system_theme_action.setChecked(mode == ThemeMode.SYSTEM)

        # Apply theme to application
        apply_theme(QApplication.instance(), mode)

        # Show feedback
        theme_name = mode.value.capitalize()
        self.statusBar().showMessage(self.tr("Theme changed to {theme}").format(theme=theme_name), 2000)

    def _update_language_menu_state(self) -> None:
        """Update language menu checkmarks from settings."""
        from open_garden_planner.app.settings import get_settings

        current_lang = get_settings().language
        for lang_code, action in self._language_actions.items():
            action.setChecked(lang_code == current_lang)

    def _on_language_changed(self, lang_code: str) -> None:
        """Handle language change action.

        Args:
            lang_code: New language code (e.g. 'en', 'de')
        """
        from open_garden_planner.app.settings import get_settings

        settings = get_settings()

        # No change needed
        if settings.language == lang_code:
            return

        settings.language = lang_code

        # Update menu checkmarks
        for lc, action in self._language_actions.items():
            action.setChecked(lc == lang_code)

        # Show restart-required message
        from open_garden_planner.core.i18n import SUPPORTED_LANGUAGES

        lang_name = SUPPORTED_LANGUAGES.get(lang_code, lang_code)
        QMessageBox.information(
            self,
            self.tr("Language Changed"),
            self.tr(
                "Language has been set to {language}.\n\n"
                "Please restart the application for the change to take effect."
            ).format(language=lang_name),
        )

    def _on_tool_selected(self, tool_type: ToolType) -> None:
        """Handle tool selection from toolbar.

        Args:
            tool_type: The selected tool type
        """
        self.canvas_view.set_active_tool(tool_type)

    def _on_gallery_item_selected(self, item: object) -> None:
        """Handle gallery item selection - update toolbar and pass plant info.

        Args:
            item: The GalleryItem that was selected
        """
        if hasattr(item, "tool_type"):
            self.main_toolbar.set_active_tool(item.tool_type)

        # Pass plant category/species to the active circle tool
        from open_garden_planner.core.tools.circle_tool import CircleTool

        active_tool = self.canvas_view.active_tool
        if isinstance(active_tool, CircleTool):
            category = getattr(item, "plant_category", None)
            species = getattr(item, "species", "")
            active_tool.set_plant_info(category=category, species=species)

    def _sync_toolbar_state(self, tool_name: str) -> None:
        """Sync toolbar button states when the active tool changes.

        Args:
            tool_name: Display name of the current tool
        """
        main_tool_map = {
            "Select": ToolType.SELECT,
            "Measure": ToolType.MEASURE,
            "Text": ToolType.TEXT,
            "Callout": ToolType.CALLOUT,
            "Journal Pin": ToolType.JOURNAL_PIN,
        }
        constraint_tool_map = {
            "Distance Constraint": ToolType.CONSTRAINT,
            "Horizontal Constraint": ToolType.CONSTRAINT_HORIZONTAL,
            "Vertical Constraint": ToolType.CONSTRAINT_VERTICAL,
        }
        if tool_type := main_tool_map.get(tool_name):
            self.main_toolbar.set_active_tool(tool_type)
            self.constraint_toolbar.set_active_tool(tool_type)  # uncheck all constraint btns
        elif tool_type := constraint_tool_map.get(tool_name):
            self.constraint_toolbar.set_active_tool(tool_type)

    def _on_active_layer_changed(self, layer_id) -> None:
        """Handle active layer change from layers panel.

        Args:
            layer_id: UUID of the newly active layer
        """
        try:
            layer = self.canvas_scene.get_layer_by_id(layer_id)
            if layer:
                self.canvas_scene.set_active_layer(layer)
        except RuntimeError:
            # Scene has been deleted, ignore
            pass

    def _on_layer_add_requested(self, name: str) -> None:
        """Create a new layer at the top of the order (undoable).

        Args:
            name: Unique name computed by the layers panel
        """
        from open_garden_planner.core.commands import AddLayerCommand  # noqa: PLC0415
        from open_garden_planner.models.layer import Layer  # noqa: PLC0415

        try:
            layer = Layer(name=name)
            self.canvas_view.command_manager.execute(
                AddLayerCommand(self.canvas_scene, layer)
            )
        except RuntimeError:
            # Scene has been deleted, ignore
            pass

    def _on_layers_reordered(self, new_order) -> None:
        """Handle layer reordering from layers panel (undoable).

        Args:
            new_order: New list of layers in order
        """
        from open_garden_planner.core.commands import ReorderLayersCommand  # noqa: PLC0415

        try:
            if [lyr.id for lyr in new_order] == [
                lyr.id for lyr in self.canvas_scene.layers
            ]:
                return  # No-op drag — don't push an empty undo step
            self.canvas_view.command_manager.execute(
                ReorderLayersCommand(self.canvas_scene, new_order)
            )
        except RuntimeError:
            # Scene has been deleted, ignore
            pass

    def _on_layer_renamed(self, layer_id, new_name: str) -> None:
        """Handle layer rename from layers panel (undoable).

        Args:
            layer_id: UUID of the layer to rename
            new_name: Requested new name
        """
        from open_garden_planner.core.commands import RenameLayerCommand  # noqa: PLC0415

        try:
            layer = self.canvas_scene.get_layer_by_id(layer_id)
            if layer is None or layer.name == new_name:
                return
            self.canvas_view.command_manager.execute(
                RenameLayerCommand(self.canvas_scene, layer, new_name)
            )
        except RuntimeError:
            # Scene has been deleted, ignore
            pass

    def _on_layer_deleted(self, layer_id) -> None:
        """Handle layer deletion from layers panel (undoable).

        Args:
            layer_id: UUID of the layer to delete
        """
        from open_garden_planner.core.commands import DeleteLayerCommand  # noqa: PLC0415

        try:
            if len(self.canvas_scene.layers) <= 1:
                return  # Must keep at least one layer
            if self.canvas_scene.get_layer_by_id(layer_id) is None:
                return
            self.canvas_view.command_manager.execute(
                DeleteLayerCommand(self.canvas_scene, layer_id)
            )
        except RuntimeError:
            # Scene has been deleted, ignore
            pass

    def _on_layer_visibility_change_requested(self, layer_id, visible: bool) -> None:
        """Toggle a layer's visibility (undoable).

        Args:
            layer_id: UUID of the layer
            visible: New visibility state
        """
        from open_garden_planner.core.commands import SetLayerPropertyCommand  # noqa: PLC0415

        try:
            layer = self.canvas_scene.get_layer_by_id(layer_id)
            if layer is None or layer.visible == visible:
                return
            self.canvas_view.command_manager.execute(
                SetLayerPropertyCommand(
                    self.canvas_scene, layer, "visible", layer.visible, visible
                )
            )
        except RuntimeError:
            # Scene has been deleted, ignore
            pass

    def _on_layer_lock_change_requested(self, layer_id, locked: bool) -> None:
        """Toggle a layer's lock state (undoable).

        Args:
            layer_id: UUID of the layer
            locked: New lock state
        """
        from open_garden_planner.core.commands import SetLayerPropertyCommand  # noqa: PLC0415

        try:
            layer = self.canvas_scene.get_layer_by_id(layer_id)
            if layer is None or layer.locked == locked:
                return
            self.canvas_view.command_manager.execute(
                SetLayerPropertyCommand(
                    self.canvas_scene, layer, "locked", layer.locked, locked
                )
            )
        except RuntimeError:
            # Scene has been deleted, ignore
            pass

    def _on_layer_opacity_committed(self, layer_id, old: float, new: float) -> None:
        """Commit an opacity change as one undoable step.

        Args:
            layer_id: UUID of the layer
            old: Opacity before the change (snapshotted at drag start)
            new: Final opacity
        """
        from open_garden_planner.core.commands import SetLayerPropertyCommand  # noqa: PLC0415

        try:
            layer = self.canvas_scene.get_layer_by_id(layer_id)
            if layer is None or abs(old - new) < 1e-9:
                return
            self.canvas_view.command_manager.execute(
                SetLayerPropertyCommand(self.canvas_scene, layer, "opacity", old, new)
            )
        except RuntimeError:
            # Scene has been deleted, ignore
            pass

    def _on_scene_active_layer_changed(self, layer) -> None:
        """Sync the layers panel selection with the scene's active layer.

        Args:
            layer: The newly active Layer (or None)
        """
        try:
            if layer is not None:
                self.layers_panel.select_layer(layer.id)
        except RuntimeError:
            # Panel has been deleted, ignore
            pass

    def _on_layer_auto_unhidden(self, layer_id) -> None:
        """Update the layers panel when the scene auto-unhides a hidden layer."""
        self.layers_panel.refresh_layer_visibility(layer_id, True)
        self._project_manager.mark_dirty()

    def _on_scene_changed_for_plant_search(self) -> None:
        """Coalesce bursts of scene changes into a single debounced refresh."""
        with contextlib.suppress(RuntimeError):
            self._plant_search_refresh_timer.start()

    def _refresh_plant_search_panel(self) -> None:
        """Refresh the plant search panel (debounce timer slot)."""
        with contextlib.suppress(RuntimeError):
            self.plant_search_panel.refresh_plant_list()

    def _on_selection_changed(self) -> None:
        """Handle selection changes in the canvas scene."""
        # A genuine selection change clears per-panel dismissals so a newly
        # selected item re-opens its contextual panels even if the user had
        # closed them for the previous selection (US-226). This runs before the
        # _update_*_panel slots (connected after this one) call set_selection_pinned.
        self._sidebar_controller.reset_selection_dismissals()
        # Guard against accessing deleted scene (can happen during shutdown or dialog execution)
        try:
            selected_items = self.canvas_scene.selectedItems()
            count = len(selected_items)
            self.update_selection(count, selected_items)
        except RuntimeError:
            # Scene has been deleted, ignore
            pass

    def _on_manage_custom_plants(self) -> None:
        """Handle Manage Custom Plants action."""
        from open_garden_planner.ui.dialogs import CustomPlantsDialog

        dialog = CustomPlantsDialog(self)
        dialog.exec()

    def _on_check_companion_planting(self) -> None:
        """Run whole-plan companion planting analysis and show report."""
        from open_garden_planner.ui.dialogs.companion_check_dialog import (
            CompanionCheckDialog,
            analyse_plan,
        )

        lang = self._current_lang()
        beneficial, antagonistic = analyse_plan(
            scene=self.canvas_scene,
            service=self._companion_service,
            radius_cm=self._companion_radius_cm,
            species_name_fn=self._companion_species_name,
            is_plant_fn=self._is_canvas_plant,
            lang=lang,
        )

        dialog = CompanionCheckDialog(
            beneficial=beneficial,
            antagonistic=antagonistic,
            service=self._companion_service,
            scene=self.canvas_scene,
            lang=lang,
            parent=self,
        )
        dialog.exec()

    @staticmethod
    def _current_lang() -> str:
        """Return the current app language code."""
        try:
            from open_garden_planner.app.settings import get_settings
            return get_settings().language
        except Exception:
            return "en"

    def _on_preferences(self) -> None:
        """Handle Preferences action; apply Agent API changes live."""
        from open_garden_planner.app.settings import get_settings
        from open_garden_planner.ui.dialogs import PreferencesDialog

        settings = get_settings()

        def _agent_api_state() -> tuple[bool, int, bool, str]:
            # Include writes-enabled + token so toggling AI editing or
            # regenerating the token also restarts the server (re-registering the
            # write tools / applying the new token).
            return (
                settings.agent_api_enabled,
                settings.agent_api_port,
                settings.agent_api_writes_enabled,
                settings.agent_api_token if settings.agent_api_writes_enabled else "",
            )

        before = _agent_api_state()
        dialog = PreferencesDialog(self)
        if dialog.exec():
            after = _agent_api_state()
            if before != after:
                # Restart so a toggle, port, writes or token change takes effect.
                self._stop_agent_api()
                if after[0]:
                    self._start_agent_api()

    def _on_search_plant_database(self) -> None:
        """Handle Search Plant Database action."""
        import os

        from open_garden_planner.app.settings import get_settings
        from open_garden_planner.services import PlantAPIManager
        from open_garden_planner.ui.dialogs import PlantSearchDialog, PreferencesDialog

        # Read API credentials from QSettings, with env var fallback
        settings = get_settings()
        trefle_token = settings.trefle_api_token or os.environ.get("TREFLE_API_TOKEN", "")
        perenual_key = settings.perenual_api_key or os.environ.get("PERENUAL_API_KEY", "")
        permapeople_id = settings.permapeople_key_id or os.environ.get("PERMAPEOPLE_KEY_ID", "")
        permapeople_secret = settings.permapeople_key_secret or os.environ.get("PERMAPEOPLE_KEY_SECRET", "")

        # If no credentials configured anywhere, open Preferences dialog
        if not any([trefle_token, perenual_key, permapeople_id and permapeople_secret]):
            dialog = PreferencesDialog(self)
            if dialog.exec():
                # Re-read settings after user saved
                trefle_token = settings.trefle_api_token
                perenual_key = settings.perenual_api_key
                permapeople_id = settings.permapeople_key_id
                permapeople_secret = settings.permapeople_key_secret
                # If still no credentials, abort
                if not any([trefle_token, perenual_key, permapeople_id and permapeople_secret]):
                    return
            else:
                return

        api_manager = PlantAPIManager(
            trefle_api_token=settings.trefle_api_token or None,
            perenual_api_key=settings.perenual_api_key or None,
            permapeople_key_id=settings.permapeople_key_id or None,
            permapeople_key_secret=settings.permapeople_key_secret or None,
        )

        dialog = PlantSearchDialog(api_manager, self)
        if dialog.exec():
            # User selected a plant species
            plant_data = dialog.selected_plant
            if plant_data:
                # Check if there's a selected plant item to update
                selected_items = self.canvas_scene.selectedItems()
                from open_garden_planner.core.object_types import ObjectType

                # Find a plant item in selection
                plant_item = None
                for item in selected_items:
                    if hasattr(item, 'object_type') and item.object_type in (
                        ObjectType.TREE,
                        ObjectType.SHRUB,
                        ObjectType.PERENNIAL,
                    ):
                        plant_item = item
                        break

                if plant_item:
                    # Update existing plant with species data (merge local calendar
                    # DB). Routed through the shared assignment helper so the spacing
                    # circle refreshes, a manual override is reconciled, and the
                    # change is a single undoable step (issue #213).
                    from open_garden_planner.services.bundled_species_db import (
                        merge_calendar_data,  # noqa: PLC0415
                    )
                    from open_garden_planner.ui.plant_species_assignment import (
                        apply_species_to_item,  # noqa: PLC0415
                        confirm_apply_database_values,  # noqa: PLC0415
                    )
                    apply_species_to_item(
                        plant_item,
                        merge_calendar_data(plant_data.to_dict()),
                        confirm=lambda: confirm_apply_database_values(self),
                    )

                    # Update the panel display
                    self._update_plant_database_panel()

                    self.statusBar().showMessage(
                        self.tr("Updated plant with species: {name}").format(
                            name=plant_data.common_name
                        ),
                        3000,
                    )
                else:
                    # No plant selected - show message
                    self.statusBar().showMessage(
                        self.tr("Select a plant object (tree, shrub, or perennial) to assign species data"),
                        5000,
                    )

    def _on_keyboard_shortcuts(self) -> None:
        """Handle Keyboard Shortcuts action."""
        from open_garden_planner.ui.dialogs import ShortcutsDialog

        dialog = ShortcutsDialog(self)
        dialog.exec()

    def agent_api_running_url(self) -> str | None:
        """The Agent API's connect URL if the server is actually running, else
        None — the one place both the Help menu and Preferences dialog (D1.6)
        ask "is there a live server to register?" so neither can reconstruct
        a URL from settings/widget state and hand a dead endpoint to an AI
        client's config.
        """
        if self._agent_server is not None and self._agent_server.is_running:
            return self._agent_server.url
        return None

    def agent_api_write_token(self) -> str | None:
        """The bearer token to hand a client, or None if writes aren't live.

        Returns the token the *running server* was started with — never the raw
        settings value — so the Connect dialog can only ever hand out a token the
        live server will actually accept. Regenerating the token in Preferences
        without saving persists a new settings value but doesn't restart the
        server; deriving from the server (like ``agent_api_running_url``) avoids
        registering a client with a token the server would reject.
        """
        server = self._agent_server
        if server is None or not server.is_running:
            return None
        return server.write_token

    def _on_connect_ai_assistant(self) -> None:
        """Handle Connect AI Assistant action (US-D1.6)."""
        from open_garden_planner.ui.dialogs import ConnectAiAssistantDialog

        dialog = ConnectAiAssistantDialog(
            self.agent_api_running_url(), self, token=self.agent_api_write_token()
        )
        dialog.exec()

    def _on_about(self) -> None:
        """Handle About action."""
        from pathlib import Path

        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QPixmap
        from PyQt6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout

        # Create custom about dialog to show logo
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("About Open Garden Planner"))
        dialog.setFixedSize(450, 280)

        layout = QHBoxLayout(dialog)

        # Logo on the left
        icon_path = Path(__file__).parent.parent / "resources" / "icons" / "OGP_logo.png"
        if icon_path.exists():
            logo_label = QLabel()
            pixmap = QPixmap(str(icon_path))
            scaled_pixmap = pixmap.scaled(
                128, 128, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            logo_label.setPixmap(scaled_pixmap)
            logo_label.setAlignment(Qt.AlignmentFlag.AlignTop)
            layout.addWidget(logo_label)

        # Text on the right
        text_layout = QVBoxLayout()
        text_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title_label = QLabel("<h2>Open Garden Planner</h2>")
        text_layout.addWidget(title_label)

        from open_garden_planner.services.update_checker import get_current_version

        version_label = QLabel(self.tr("<p>Version {v}</p>").format(v=get_current_version()))
        text_layout.addWidget(version_label)

        description_label = QLabel(
            self.tr("<p>Precision garden planning for passionate gardeners.</p>"
            "<p>Free and open source under GPLv3.</p>")
        )
        description_label.setWordWrap(True)
        text_layout.addWidget(description_label)

        link_label = QLabel(
            "<p><a href='https://github.com/cofade/open-garden-planner'>"
            "github.com/cofade/open-garden-planner</a></p>"
        )
        link_label.setOpenExternalLinks(True)
        text_layout.addWidget(link_label)

        text_layout.addStretch()
        layout.addLayout(text_layout)

        dialog.exec()

    # Public methods for updating status bar

    def update_coordinates(self, x: float, y: float) -> None:
        """Update the coordinate display in the status bar.

        Args:
            x: X coordinate in centimeters
            y: Y coordinate in centimeters
        """
        self.coord_label.setText(self.tr("X: {x} cm  Y: {y} cm").format(x=f"{x:.2f}", y=f"{y:.2f}"))

    def update_zoom(self, zoom_percent: float) -> None:
        """Update the zoom display in the status bar.

        Args:
            zoom_percent: Zoom level as percentage (100 = 100%)
        """
        self.zoom_label.setText(f"{zoom_percent:.0f}%")

    def update_selection(self, count: int, selected_items: list | None = None) -> None:
        """Update the selection info in the status bar.

        Args:
            count: Number of selected objects
            selected_items: List of selected QGraphicsItems (optional)
        """
        if count == 0:
            self.selection_label.setText(self.tr("No selection"))
        elif count == 1:
            # For single selection, show area and perimeter if available
            if selected_items:
                item = selected_items[0]
                measurements = calculate_area_and_perimeter(item)
                if measurements:
                    area, perimeter = measurements
                    area_str = format_area(area)
                    length_str = format_length(perimeter)
                    self.selection_label.setText(
                        self.tr("1 object | Area: {area} | Perimeter: {perimeter}").format(
                            area=area_str, perimeter=length_str
                        )
                    )
                else:
                    self.selection_label.setText(self.tr("1 object selected"))
            else:
                self.selection_label.setText(self.tr("1 object selected"))
        else:
            # For multiple selection, show total area and perimeter
            if selected_items:
                total_area = 0.0
                total_perimeter = 0.0
                measurable_count = 0

                for item in selected_items:
                    measurements = calculate_area_and_perimeter(item)
                    if measurements:
                        area, perimeter = measurements
                        total_area += area
                        total_perimeter += perimeter
                        measurable_count += 1

                if measurable_count > 0:
                    area_str = format_area(total_area)
                    length_str = format_length(total_perimeter)
                    self.selection_label.setText(
                        self.tr(
                            "{count} objects | Total Area: {area} | Total Perimeter: {perimeter}"
                        ).format(count=count, area=area_str, perimeter=length_str)
                    )
                else:
                    self.selection_label.setText(self.tr("{count} objects selected").format(count=count))
            else:
                self.selection_label.setText(self.tr("{count} objects selected").format(count=count))

    def update_tool(self, tool_name: str) -> None:
        """Update the current tool display in the status bar.

        Args:
            tool_name: Name of the active tool
        """
        self.tool_label.setText(tool_name)

    def _on_import_background_image(self) -> None:
        """Handle Import Background Image action."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Import Background Image"),
            str(self._default_dialog_dir()),
            self.tr("Images (*.png *.jpg *.jpeg *.tiff *.bmp);;All Files (*)"),
        )
        if file_path:
            try:
                from open_garden_planner.ui.canvas.items import BackgroundImageItem

                image_item = BackgroundImageItem(file_path)
                self.canvas_scene.addItem(image_item)

                # Center the image on the canvas
                canvas_center = self.canvas_scene.canvas_rect.center()
                image_rect = image_item.boundingRect()
                image_item.setPos(
                    canvas_center.x() - image_rect.width() / 2,
                    canvas_center.y() - image_rect.height() / 2,
                )

                self._project_manager.mark_dirty()
                self.statusBar().showMessage(self.tr("Imported: {path}").format(path=file_path))
            except Exception as e:
                QMessageBox.critical(self, self.tr("Error"), self.tr("Failed to import image:\n{error}").format(error=e))

    def _on_load_satellite_background(self) -> None:
        """Open the embedded Google Maps picker and import the chosen area."""
        import io  # noqa: PLC0415
        from datetime import UTC, datetime  # noqa: PLC0415

        from open_garden_planner.ui.canvas.items import BackgroundImageItem  # noqa: PLC0415
        from open_garden_planner.ui.dialogs.map_picker_dialog import (  # noqa: PLC0415
            MapPickerDialog,
        )

        if not MapPickerDialog.is_available():
            QMessageBox.warning(
                self,
                self.tr("API key missing"),
                self.tr(
                    "Set OGP_GOOGLE_MAPS_KEY in your .env file to enable "
                    "satellite background loading."
                ),
            )
            return

        dialog = MapPickerDialog(self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        result = dialog.fetch_result
        if result is None:
            return

        # PIL image → PNG bytes.
        buf = io.BytesIO()
        result.image.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        # Replace any existing background image (a project has at most one
        # logical 'satellite layer'; stacking would only confuse the user).
        scene = self.canvas_scene
        for item in list(scene.items()):
            if isinstance(item, BackgroundImageItem):
                scene.removeItem(item)

        image_item = BackgroundImageItem.from_fetch_result(
            image_path=f"google_satellite_z{result.zoom}.png",
            png_bytes=png_bytes,
            meters_per_pixel=result.meters_per_pixel,
            bbox_nw=(result.bbox.nw_lat, result.bbox.nw_lng),
            bbox_se=(result.bbox.se_lat, result.bbox.se_lng),
            zoom=result.zoom,
            fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        scene.addItem(image_item)

        # Resize the canvas to match the selected area so the satellite image
        # IS the canvas. Image scene-size in cm = image_local_size_px / scale_factor
        # (px/cm). Using the item's own dimensions keeps us in sync with the
        # cropped image, no matter what the service returned.
        image_rect = image_item.boundingRect()
        canvas_w_cm = image_rect.width() / image_item.scale_factor
        canvas_h_cm = image_rect.height() / image_item.scale_factor
        scene.resize_canvas(canvas_w_cm, canvas_h_cm)

        # Centre on the new canvas. ``boundingRect()`` is in local (pre-scale)
        # coords; because ``transformOriginPoint`` is at the local centre, the
        # scene centre after ``setPos(pos)`` is ``pos + (w/2, h/2)`` regardless
        # of the scale factor — so we must NOT multiply by ``scale`` here.
        canvas_center = scene.canvas_rect.center()
        image_item.setPos(
            canvas_center.x() - image_rect.width() / 2,
            canvas_center.y() - image_rect.height() / 2,
        )

        # Zoom the view to the new canvas so the user sees the whole import.
        self.canvas_view.fit_in_view()

        self._project_manager.mark_dirty()
        self.statusBar().showMessage(
            self.tr(
                "Loaded satellite background ({cols}x{rows} tiles, zoom {zoom}) — "
                "canvas resized to {w_m:.0f}m x {h_m:.0f}m"
            ).format(
                cols=result.tile_grid[0],
                rows=result.tile_grid[1],
                zoom=result.zoom,
                w_m=canvas_w_cm / 100,
                h_m=canvas_h_cm / 100,
            )
        )

    def _on_set_location(self) -> None:
        """Handle Set Garden Location action."""
        from PyQt6.QtWidgets import QDialog  # noqa: PLC0415

        from open_garden_planner.ui.dialogs.location_dialog import LocationDialog  # noqa: PLC0415

        dialog = LocationDialog(self, location=self._project_manager.location)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._project_manager.set_location(dialog.location_data)
            self.statusBar().showMessage(self.tr("Garden location updated"), 3000)

    def _on_soil_test_requested(self, target_id: str, display_name: str) -> None:
        """Open SoilTestDialog for a bed (US-12.10a)."""
        self._open_soil_test_dialog(target_id, display_name)

    def _on_set_default_soil_test(self) -> None:
        """Open SoilTestDialog for the project-wide default (US-12.10a)."""
        self._open_soil_test_dialog("global", "")

    def _on_soil_test_badge_clicked(self, bed_id: str) -> None:
        """Open SoilTestDialog when the seasonal reminder badge is clicked (US-12.10e)."""
        self._open_soil_test_dialog(bed_id, self._lookup_bed_display_name(bed_id))

    def _lookup_bed_display_name(self, bed_id: str) -> str:
        """Return the bed's name for the dialog title, or empty string if not found."""
        from open_garden_planner.core.object_types import is_bed_type  # noqa: PLC0415

        scene = (
            getattr(self.canvas_view, "_canvas_scene", None) or self.canvas_view.scene()
        )
        if scene is None:
            return ""
        for item in scene.items():
            if not is_bed_type(getattr(item, "object_type", None)):
                continue
            if str(getattr(item, "item_id", "")) != bed_id:
                continue
            return getattr(item, "name", "") or ""
        return ""

    def _open_soil_test_dialog(self, target_id: str, display_name: str) -> None:
        """Open the soil test dialog and execute AddSoilTestCommand on accept."""
        from PyQt6.QtWidgets import QDialog  # noqa: PLC0415

        from open_garden_planner.core import AddSoilTestCommand  # noqa: PLC0415
        from open_garden_planner.ui.dialogs import SoilTestDialog  # noqa: PLC0415

        history = self._soil_service.get_history(target_id)
        existing = history.latest
        bed_area_m2 = (
            self._lookup_bed_area_m2(target_id) if target_id != "global" else 0.0
        )
        # F6: when this dialog is for a bed (not the global target), pass the
        # global-default history so the History tab can merge those rows in
        # chronologically with a "(default)" badge.
        default_history = (
            None
            if target_id == "global"
            else self._soil_service.get_history("global")
        )

        dialog = SoilTestDialog(
            parent=self,
            target_id=target_id,
            target_name=display_name,
            existing_latest=existing,
            existing_history=history,
            existing_default_history=default_history,
            bed_area_m2=bed_area_m2,
            project_manager=self._project_manager,
            command_manager=self.canvas_view.command_manager,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        record = dialog.result_record()
        latest_after = self._soil_service.get_history(target_id).latest
        if _should_skip_add_after_dialog(record, existing, latest_after):
            self.statusBar().showMessage(self.tr("No changes"), 3000)
            return
        cmd = AddSoilTestCommand(self._project_manager, target_id, record)
        self.canvas_view.command_manager.execute(cmd)
        self.statusBar().showMessage(self.tr("Soil test recorded"), 3000)
        # Refresh the soil overlay if it's currently visible.
        if self.canvas_view.soil_overlay_visible:
            self.canvas_view.viewport().update()
        # Recompute mismatch borders and dashboard cards (US-12.10d).
        self.canvas_view.refresh_soil_mismatches()
        # Recompute seasonal reminder badges (US-12.10e).
        self.canvas_view.refresh_soil_badges()
        self.calendar_view.refresh()

    def _on_pest_log_requested(self, target_id: str, display_name: str) -> None:
        """Open PestLogDialog for a bed/plant (US-12.7)."""
        self._open_pest_log_dialog(target_id, display_name)

    def _on_pest_logs_changed(self, _pest_logs: object) -> None:
        """Refresh the overview panel whenever pest logs change."""
        self._refresh_pest_overview()

    def _open_pest_log_dialog(self, target_id: str, display_name: str) -> None:
        """Open the pest/disease dialog and execute AddPestLogCommand on accept."""
        from PyQt6.QtWidgets import QDialog  # noqa: PLC0415

        from open_garden_planner.core import AddPestLogCommand  # noqa: PLC0415
        from open_garden_planner.ui.dialogs import PestLogDialog  # noqa: PLC0415

        if not display_name:
            display_name = self._lookup_bed_display_name(target_id) or self._lookup_item_name(target_id)
        history = self._project_manager.get_pest_log_history(target_id)
        dialog = PestLogDialog(
            parent=self,
            target_id=target_id,
            target_name=display_name,
            existing_history=history,
            project_manager=self._project_manager,
            command_manager=self.canvas_view.command_manager,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        if not dialog.has_new_entry:
            # User managed history (edit/delete) without adding a new entry.
            self._refresh_pest_overview()
            return

        record = dialog.result_record()
        cmd = AddPestLogCommand(self._project_manager, target_id, record)
        self.canvas_view.command_manager.execute(cmd)
        self.statusBar().showMessage(self.tr("Pest/disease log recorded"), 3000)
        self._refresh_pest_overview()

    # ── Harvest log (US-C1) ───────────────────────────────────────────────────

    def _on_harvest_log_requested(self, target_id: str, display_name: str) -> None:
        """Open HarvestLogDialog for a bed/plant (US-C1)."""
        self._open_harvest_dialog(target_id, display_name)

    def _harvest_species_for_target(
        self, target_id: str, display_name: str
    ) -> tuple[str, str]:
        """Return ``(species_key, species_name)`` cached on a harvest history.

        Reads the target item's ``plant_species`` metadata; falls back to the
        display name, then to the item's localized object-type name (e.g. "Bed")
        so an unnamed bed/plant never caches an empty name (which would surface
        as the internal ``target:<uuid>`` key on the dashboard).
        """
        from open_garden_planner.core.object_types import (  # noqa: PLC0415
            get_translated_display_name,
        )
        from open_garden_planner.models.plant_data import (  # noqa: PLC0415
            species_key as _species_key,
        )

        scene = (
            getattr(self.canvas_view, "_canvas_scene", None) or self.canvas_view.scene()
        )
        species: dict = {}
        type_fallback = ""
        if scene is not None:
            for item in scene.items():
                if str(getattr(item, "item_id", "")) == target_id:
                    meta = getattr(item, "metadata", {}) or {}
                    species = meta.get("plant_species", {}) or {}
                    obj_type = getattr(item, "object_type", None)
                    if obj_type is not None:
                        try:
                            type_fallback = get_translated_display_name(obj_type)
                        except Exception:
                            type_fallback = ""
                    break
        key = _species_key(species) if species else ""
        name = (
            species.get("common_name")
            or species.get("scientific_name")
            or display_name
            or type_fallback
        )
        return key, name

    def _open_harvest_dialog(self, target_id: str, display_name: str) -> None:
        """Open the harvest dialog and execute AddHarvestRecordCommand on accept."""
        from PyQt6.QtWidgets import QDialog  # noqa: PLC0415

        from open_garden_planner.core import AddHarvestRecordCommand  # noqa: PLC0415
        from open_garden_planner.ui.dialogs import HarvestLogDialog  # noqa: PLC0415

        if not display_name:
            display_name = (
                self._lookup_bed_display_name(target_id)
                or self._lookup_item_name(target_id)
            )
        history = self._project_manager.get_harvest_history(target_id)
        dialog = HarvestLogDialog(
            parent=self,
            target_id=target_id,
            target_name=display_name,
            existing_history=history,
            project_manager=self._project_manager,
            command_manager=self.canvas_view.command_manager,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        if not dialog.has_new_entry:
            # User managed history (edit/delete) without adding a new entry.
            return

        species_key, species_name = self._harvest_species_for_target(
            target_id, display_name
        )
        record = dialog.result_record()
        cmd = AddHarvestRecordCommand(
            self._project_manager,
            target_id,
            record,
            species_key=species_key,
            species_name=species_name,
        )
        self.canvas_view.command_manager.execute(cmd)
        self.statusBar().showMessage(self.tr("Harvest recorded"), 3000)

    def _on_succession_plan_requested(self, bed_id: str, display_name: str) -> None:
        """Open SuccessionPlanDialog for a bed (US-12.8)."""
        self._open_succession_plan_dialog(bed_id, display_name)

    def _on_succession_plans_changed(self, _plans: object) -> None:
        """Refresh bed succession indicators whenever plans change (US-12.8)."""
        self._refresh_succession_indicators()

    def _open_succession_plan_dialog(self, bed_id: str, display_name: str) -> None:
        """Open the succession plan dialog and execute SetSuccessionPlanCommand on accept."""
        from PyQt6.QtWidgets import QDialog  # noqa: PLC0415

        from open_garden_planner.core.commands import SetSuccessionPlanCommand  # noqa: PLC0415
        from open_garden_planner.models.succession import SuccessionPlan  # noqa: PLC0415
        from open_garden_planner.ui.dialogs.succession_plan_dialog import (  # noqa: PLC0415
            SuccessionPlanDialog,
        )

        if not display_name:
            display_name = self._lookup_item_name(bed_id)

        existing_raw = self._project_manager.succession_plans.get(bed_id)
        existing_plan = SuccessionPlan.from_dict(existing_raw) if existing_raw else None

        dialog = SuccessionPlanDialog(
            parent=self,
            bed_id=bed_id,
            bed_name=display_name,
            existing_plan=existing_plan,
            frost_dates=self._project_manager.location,
            project_manager=self._project_manager,
            command_manager=self.canvas_view.command_manager,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        plan = dialog.result_plan()
        cmd = SetSuccessionPlanCommand(self._project_manager, bed_id, plan)
        self.canvas_view.command_manager.execute(cmd)
        self._refresh_succession_indicators()
        self.statusBar().showMessage(self.tr("Succession plan saved"), 3000)

    def _refresh_succession_indicators(self) -> None:
        """Update the succession badge on every bed-capable canvas item (US-12.8).

        Builds an ordered ``[(common_name, is_current), ...]`` list for each
        bed and hands it to the mixin's ``set_succession_indicator``. Past
        entries are skipped; the current entry (if any) is marked with
        ``is_current=True`` so the badge can highlight it. Works for any
        bed shape (Rectangle/Polygon/Ellipse/Circle) since the badge is a
        graphics-item child managed in ``GardenItemMixin``.
        """
        import datetime  # noqa: PLC0415

        from open_garden_planner.core.object_types import is_bed_type  # noqa: PLC0415
        from open_garden_planner.models.succession import SuccessionPlan  # noqa: PLC0415
        from open_garden_planner.ui.canvas.items.garden_item import (  # noqa: PLC0415
            GardenItemMixin,
        )

        today = datetime.date.today()
        plans = self._project_manager.succession_plans
        scene = getattr(self.canvas_view, "_canvas_scene", None) or self.canvas_view.scene()
        if scene is None:
            return

        bed_map = {
            str(item.item_id): item
            for item in scene.items()
            if isinstance(item, GardenItemMixin) and is_bed_type(item.object_type)
        }

        for item in bed_map.values():
            item.set_succession_indicator(None)

        for bed_id, plan_dict in plans.items():
            item = bed_map.get(bed_id)
            if item is None:
                continue
            plan = SuccessionPlan.from_dict(plan_dict)
            current = plan.current_entry(today)
            lines: list[tuple[str, bool]] = []
            for entry in plan.entries_sorted():
                if not entry.end_date:
                    continue
                try:
                    end = datetime.date.fromisoformat(entry.end_date)
                except ValueError:
                    continue
                if end < today:
                    continue  # skip past entries
                lines.append((entry.common_name, entry is current))
            item.set_succession_indicator(lines or None)

    def _lookup_item_name(self, target_id: str) -> str:
        """Return the display name for any scene item (bed or plant) by id, else ''."""
        scene = (
            getattr(self.canvas_view, "_canvas_scene", None) or self.canvas_view.scene()
        )
        if scene is None:
            return ""
        for item in scene.items():
            if str(getattr(item, "item_id", "")) == target_id:
                return getattr(item, "name", "") or ""
        return ""

    # ── Garden journal (US-12.9) ──────────────────────────────────────────

    def _on_journal_note_placement(self, scene_x: float, scene_y: float) -> None:
        """Open dialog for a new pin placed at ``(scene_x, scene_y)``."""
        from PyQt6.QtWidgets import QDialog  # noqa: PLC0415

        from open_garden_planner.core import AddJournalNoteCommand  # noqa: PLC0415
        from open_garden_planner.models.journal_note import JournalNote  # noqa: PLC0415
        from open_garden_planner.ui.canvas.items.journal_pin_item import (  # noqa: PLC0415
            JournalPinItem,
        )
        from open_garden_planner.ui.dialogs.journal_note_dialog import (  # noqa: PLC0415
            JournalNoteDialog,
        )

        note = JournalNote(scene_x=scene_x, scene_y=scene_y)
        dialog = JournalNoteDialog(
            parent=self,
            note=note,
            project_manager=self._project_manager,
            edit_mode=False,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = dialog.result_note()
        scene = (
            getattr(self.canvas_view, "_canvas_scene", None)
            or self.canvas_view.scene()
        )
        if scene is None:
            return
        layer_id = (
            scene.active_layer.id
            if hasattr(scene, "active_layer") and scene.active_layer
            else None
        )
        pin = JournalPinItem(
            x=result.scene_x,
            y=result.scene_y,
            note_id=result.id,
            layer_id=layer_id,
        )
        cmd = AddJournalNoteCommand(self._project_manager, scene, pin, result)
        self.canvas_view.command_manager.execute(cmd)
        self.statusBar().showMessage(self.tr("Journal note added"), 3000)

    def _on_journal_note_edit(self, note_id: str) -> None:
        """Open the dialog to edit an existing journal note."""
        from PyQt6.QtWidgets import QDialog  # noqa: PLC0415

        from open_garden_planner.core import EditJournalNoteCommand  # noqa: PLC0415
        from open_garden_planner.ui.dialogs.journal_note_dialog import (  # noqa: PLC0415
            JournalNoteDialog,
        )

        note = self._project_manager.get_journal_note(note_id)
        if note is None:
            return
        dialog = JournalNoteDialog(
            parent=self,
            note=note,
            project_manager=self._project_manager,
            edit_mode=True,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        updated = dialog.result_note()
        cmd = EditJournalNoteCommand(self._project_manager, updated)
        self.canvas_view.command_manager.execute(cmd)

    def _on_journal_note_delete(self, note_id: str) -> None:
        """Confirm + remove the pin and its note."""
        from PyQt6.QtWidgets import QMessageBox  # noqa: PLC0415

        from open_garden_planner.core import DeleteJournalNoteCommand  # noqa: PLC0415
        from open_garden_planner.ui.canvas.items.journal_pin_item import (  # noqa: PLC0415
            JournalPinItem,
        )

        reply = QMessageBox.question(
            self,
            self.tr("Delete journal note"),
            self.tr("Delete this journal note?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        scene = (
            getattr(self.canvas_view, "_canvas_scene", None)
            or self.canvas_view.scene()
        )
        if scene is None:
            return
        for item in scene.items():
            if isinstance(item, JournalPinItem) and item.note_id == note_id:
                cmd = DeleteJournalNoteCommand(self._project_manager, scene, item)
                self.canvas_view.command_manager.execute(cmd)
                return

    def _on_journal_notes_batch_delete(self, note_ids: list[str]) -> None:
        """Keyboard-Delete batch: drop pins + notes for every id, no per-pin prompt.

        Matches the Delete-key UX for regular items (no confirmation; undo is
        available). The right-click "Delete" path stays single-pin + confirmed.
        """
        from open_garden_planner.core import DeleteJournalNoteCommand  # noqa: PLC0415
        from open_garden_planner.ui.canvas.items.journal_pin_item import (  # noqa: PLC0415
            JournalPinItem,
        )

        scene = (
            getattr(self.canvas_view, "_canvas_scene", None)
            or self.canvas_view.scene()
        )
        if scene is None:
            return
        pins_by_id: dict[str, JournalPinItem] = {
            item.note_id: item
            for item in scene.items()
            if isinstance(item, JournalPinItem)
        }
        for note_id in note_ids:
            pin = pins_by_id.get(note_id)
            if pin is None:
                continue
            self.canvas_view.command_manager.execute(
                DeleteJournalNoteCommand(self._project_manager, scene, pin)
            )

    def _on_journal_note_activated(self, note_id: str) -> None:
        """Sidebar double-click → centre viewport on pin + open editor."""
        self.canvas_view.focus_on_journal_pin(note_id)
        self._on_journal_note_edit(note_id)

    def _on_smart_symbol_selected(self, symbol_id: str) -> None:
        """Drop a parametric smart symbol at the viewport centre (US-C4)."""
        from open_garden_planner.core.commands import CreateItemCommand
        from open_garden_planner.services.smart_symbol_library import (
            get_smart_symbol_library,
        )
        from open_garden_planner.ui.canvas.items.smart_symbol_item import SmartSymbolItem

        definition = get_smart_symbol_library().get(symbol_id)
        if definition is None:
            return
        scene = (
            getattr(self.canvas_view, "_canvas_scene", None)
            or self.canvas_view.scene()
        )
        if scene is None:
            return
        layer_id = (
            scene.active_layer.id
            if getattr(scene, "active_layer", None)
            else None
        )
        # No canvas name → no floating label child to entangle with the
        # regenerated geometry; the panel header shows the symbol's name.
        symbol = SmartSymbolItem(
            symbol_id=symbol_id,
            symbol_version=definition.version,
            params=definition.param_defaults(),
            layer_id=layer_id,
        )
        center = self.canvas_view.mapToScene(
            self.canvas_view.viewport().rect().center()
        )
        symbol.setPos(center)
        symbol.regenerate_geometry()
        self.canvas_view.command_manager.execute(CreateItemCommand(scene, symbol))
        scene.clearSelection()
        symbol.setSelected(True)

    def _on_garden_journal_notes_changed(self, notes: object) -> None:
        """Refresh the sidebar panel when notes change (added / edited / removed)."""
        panel = getattr(self, "journal_panel", None)
        if panel is None or not isinstance(notes, dict):
            return
        panel.refresh(notes)

    def _refresh_pest_overview(self) -> None:
        """Rebuild the Active Pest/Disease Issues panel (US-12.7)."""
        panel = getattr(self, "pest_overview_panel", None)
        if panel is None:
            return
        items_by_id: dict[str, str] = {}
        scene = (
            getattr(self.canvas_view, "_canvas_scene", None)
            or self.canvas_view.scene()
        )
        if scene is not None:
            for item in scene.items():
                iid = getattr(item, "item_id", None)
                if iid is None:
                    continue
                name = getattr(item, "name", "") or ""
                if name:
                    items_by_id[str(iid)] = name
        panel.refresh(self._project_manager.pest_logs, items_by_id)

    def _lookup_bed_area_m2(self, target_id: str) -> float:
        """Return the area of the bed identified by ``target_id`` in m².

        Returns 0.0 when the bed is not found, when its shape isn't supported by
        ``calculate_area_and_perimeter`` (e.g. EllipseItem — pre-existing gap),
        or when the canvas scene isn't available.
        """
        from open_garden_planner.core.measurements import (  # noqa: PLC0415
            calculate_area_and_perimeter,
        )
        from open_garden_planner.core.object_types import is_bed_type  # noqa: PLC0415

        scene = getattr(self.canvas_view, "_canvas_scene", None) or self.canvas_view.scene()
        if scene is None:
            return 0.0
        for item in scene.items():
            if not is_bed_type(getattr(item, "object_type", None)):
                continue
            if str(getattr(item, "item_id", "")) != target_id:
                continue
            result = calculate_area_and_perimeter(item)
            if result is None:
                return 0.0
            area_cm2, _ = result
            return area_cm2 / 10_000.0
        return 0.0

    def _on_amendment_plan(self) -> None:
        """Open the cross-bed Amendment Plan dialog (US-12.10c)."""
        from open_garden_planner.ui.dialogs import AmendmentPlanDialog  # noqa: PLC0415

        scene = (
            getattr(self.canvas_view, "_canvas_scene", None)
            or self.canvas_view.scene()
        )
        dialog = AmendmentPlanDialog(
            parent=self,
            canvas_scene=scene,
            soil_service=self._soil_service,
            on_add_to_shopping_list=self._on_shopping_list,
            project_manager=self._project_manager,
        )
        dialog.exec()

    def _on_shopping_list(self) -> None:
        """Open the Shopping List dialog (US-12.6)."""
        from open_garden_planner.services.shopping_list_service import (  # noqa: PLC0415
            ShoppingListService,
        )
        from open_garden_planner.ui.dialogs import ShoppingListDialog  # noqa: PLC0415

        scene = (
            getattr(self.canvas_view, "_canvas_scene", None)
            or self.canvas_view.scene()
        )
        service = ShoppingListService(
            scene=scene,
            soil_service=self._soil_service,
            project_manager=self._project_manager,
        )
        dialog = ShoppingListDialog(service=service, parent=self)
        dialog.exec()

    def _on_location_changed(self, location: object) -> None:
        """Update the location label in the status bar."""
        if location is None:
            self.location_label.setText(self.tr("No location set"))
            self.location_label.setToolTip(
                self.tr("Garden GPS location — use File > Set Garden Location to configure")
            )
        else:
            loc = location  # type: ignore[assignment]
            lat = loc.get("latitude", 0.0)
            lon = loc.get("longitude", 0.0)
            lat_str = f"{abs(lat):.4f}°{'N' if lat >= 0 else 'S'}"
            lon_str = f"{abs(lon):.4f}°{'E' if lon >= 0 else 'W'}"
            self.location_label.setText(f"{lat_str}, {lon_str}")
            frost = loc.get("frost_dates", {}) or {}
            zone = frost.get("hardiness_zone", "")
            tip = self.tr("Latitude: {lat}, Longitude: {lon}").format(lat=lat, lon=lon)
            if zone:
                tip += f"\n{self.tr('Zone')}: {zone}"
            spring = frost.get("last_spring_frost", "")
            fall = frost.get("first_fall_frost", "")
            if spring:
                tip += f"\n{self.tr('Last spring frost')}: {spring}"
            if fall:
                tip += f"\n{self.tr('First fall frost')}: {fall}"
            self.location_label.setToolTip(tip)

    def _on_crop_rotation_changed(self, rotation_data: object) -> None:
        """Update the crop rotation service when project data changes (US-10.6)."""
        from open_garden_planner.models.crop_rotation import CropRotationHistory

        if rotation_data and isinstance(rotation_data, dict):
            self._crop_rotation_service.history = CropRotationHistory.from_dict(
                rotation_data
            )
        else:
            self._crop_rotation_service.history = CropRotationHistory()
        self._update_bed_rotation_indicators()

    def _on_season_changed(self, year: object) -> None:
        """Update the season label in the status bar (US-10.7)."""
        if year is None:
            self.season_label.setText(self.tr("Season: —"))
            self.season_label.setToolTip(
                self.tr("Current season year — use File > Manage Seasons to configure")
            )
        else:
            self.season_label.setText(self.tr("Season: {year}").format(year=year))
            self.season_label.setToolTip(
                self.tr("Season {year} — use File > Manage Seasons to manage seasons").format(year=year)
            )

    def _on_manage_seasons(self) -> None:
        """Open the Season Manager dialog (US-10.7)."""
        from open_garden_planner.ui.dialogs.season_manager_dialog import SeasonManagerDialog

        dialog = SeasonManagerDialog(self._project_manager, self)
        if dialog.exec() != SeasonManagerDialog.DialogCode.Accepted:
            return

        action = dialog.action
        if action == "open":
            path = dialog.open_season_path
            if path:
                if not self._confirm_discard_changes():
                    return
                self._open_project_file(str(path))

        elif action == "create":
            path = dialog.new_season_path
            year = dialog.new_season_year
            keep_plants = dialog.new_season_keep_plants
            if path is None or year is None:
                return
            try:
                self._project_manager.create_new_season(
                    self.canvas_scene, year, path, keep_plants
                )
            except Exception as e:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(
                    self,
                    self.tr("Error"),
                    self.tr("Failed to create season file:\n{error}").format(error=e),
                )
                return

            # Ask user whether to open the new season now
            from PyQt6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self,
                self.tr("New Season Created"),
                self.tr(
                    "Season {year} has been created.\n\nOpen the new season now?"
                ).format(year=year),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                if not self._confirm_discard_changes():
                    return
                self._open_project_file(str(path))

    def _on_toggle_compare_overlay(self, checked: bool) -> None:
        """Show or hide the previous-season compare overlay (US-10.7)."""
        self.canvas_scene.set_compare_overlay_visible(checked)

    def _load_compare_overlay_from_previous_season(self) -> None:
        """Load the most recent linked season as a compare overlay (US-10.7).

        Called after a project is loaded if linked_seasons is non-empty.
        """
        linked = self._project_manager.linked_seasons
        if not linked:
            self._compare_overlay_action.setEnabled(False)
            self.canvas_scene.clear_compare_overlay()
            return

        current_file = self._project_manager.current_file
        # Use the most recent previous season (highest year that exists)
        current_year = self._project_manager.season_year or 0
        candidates = [s for s in linked if s.get("year", 0) < current_year]
        if not candidates:
            candidates = linked  # Fall back to any linked season

        target = max(candidates, key=lambda s: s.get("year", 0))
        file_str = target.get("file", "")
        if current_file and file_str and not Path(file_str).is_absolute():
            resolved = current_file.parent / file_str
        else:
            resolved = Path(file_str) if file_str else None

        if resolved is None or not resolved.exists():
            self._compare_overlay_action.setEnabled(False)
            self.canvas_scene.clear_compare_overlay()
            return

        try:
            objects = self._project_manager.load_season_objects(resolved)
            self.canvas_scene.set_compare_overlay(objects)
            self._compare_overlay_action.setEnabled(True)
            self._compare_overlay_action.setToolTip(
                self.tr("Overlay {year} season plants (ghosted)").format(
                    year=target.get("year", "?")
                )
            )
        except Exception:
            self._compare_overlay_action.setEnabled(False)

    def _update_bed_rotation_indicators(self) -> None:
        """Update visual rotation status indicators on all bed items (US-10.6)."""
        from open_garden_planner.services.crop_rotation_service import RotationStatus

        try:
            for item in self.canvas_scene.items():
                if self._is_bed_item(item):
                    area_id = str(item.item_id)
                    rec = self._crop_rotation_service.get_recommendation(area_id)
                    status_str = rec.status.value if rec.status != RotationStatus.UNKNOWN else None
                    item.set_rotation_status(status_str)
        except RuntimeError:
            pass

    def _on_tab_changed(self, index: int) -> None:
        """Refresh tab views when they become active."""
        if index == 1:
            self.calendar_view.refresh()
        elif index == 2:
            self.seed_inventory_view.refresh()
        elif index == self._tab_widget.indexOf(self.tasks_view):
            self.tasks_view.refresh()
        elif index == self._tab_widget.indexOf(self.harvest_view):
            self.harvest_view.refresh()

    def _on_frost_alert_ready(self, count: int, max_severity: str) -> None:
        """Update the frost alert corner badge."""
        if count == 0:
            self._frost_badge.hide()
            return
        icon = "❄" if max_severity == "red" else "⚠"
        bg = "#dc3545" if max_severity == "red" else "#fd7e14"
        label = self.tr("frost alert") if count == 1 else self.tr("frost alerts")
        self._frost_badge.setText(f"  {icon} {count} {label}  ")
        self._frost_badge.setStyleSheet(
            f"QPushButton {{ background: {bg}; color: white; font-weight: bold;"
            "  border-radius: 4px; padding: 2px 6px; }}"
            f"QPushButton:hover {{ border: 1px solid white; }}"
        )
        self._frost_badge.show()

    def _on_highlight_species(self, species_key: str) -> None:
        """Switch to Garden Plan tab and select all items matching species_key."""
        if species_key.startswith("frost_items:"):
            ids = set(species_key[len("frost_items:"):].split(","))
            self._tab_widget.setCurrentIndex(0)
            def _do_select(ids: set = ids) -> None:
                self.canvas_scene.clearSelection()
                first = None
                for item in self.canvas_scene.items():
                    if hasattr(item, "item_id") and str(item.item_id) in ids:
                        item.setSelected(True)
                        if first is None:
                            first = item
                if first is not None:
                    self.canvas_view.centerOn(first)
            QTimer.singleShot(0, _do_select)
            return

        # Harvest dashboard rows for an unkeyed target (a bed, or a species-less
        # plant) carry a ``target:<uuid>`` key — select that one item by id.
        if species_key.startswith("target:"):
            self._select_items_by_id({species_key[len("target:"):]})
            return

        from open_garden_planner.models.plant_data import species_key as _species_key

        self._tab_widget.setCurrentIndex(0)
        self.canvas_scene.clearSelection()
        # The signal carries a canonical species_key (ADR-016: source_id →
        # scientific → common, lowercased) — emitted identically by the planting
        # calendar, Tasks tab and Harvest tab. Match on the same canonical key on
        # both sides; comparing against the raw-cased display name never matched.
        first = None
        for item in self.canvas_scene.items():
            if not hasattr(item, "metadata") or not item.metadata:
                continue
            ps_dict = item.metadata.get("plant_species")
            if not ps_dict:
                continue
            try:
                if _species_key(ps_dict) == species_key:
                    item.setSelected(True)
                    if first is None:
                        first = item
            except Exception:
                continue
        if first is not None:
            self.canvas_view.centerOn(first)

    def _select_items_by_id(self, ids: set[str]) -> None:
        """Switch to Garden Plan and select/center the items with these UUIDs."""
        self._tab_widget.setCurrentIndex(0)

        def _do_select() -> None:
            self.canvas_scene.clearSelection()
            first = None
            for item in self.canvas_scene.items():
                if hasattr(item, "item_id") and str(item.item_id) in ids:
                    item.setSelected(True)
                    if first is None:
                        first = item
            if first is not None:
                self.canvas_view.centerOn(first)

        QTimer.singleShot(0, _do_select)

    def _on_navigate_to_bed(self, bed_id: str) -> None:
        """Navigate to a single bed from a task (US-C2)."""
        self._select_items_by_id({bed_id})

    def _on_navigate_to_items(self, ids: object) -> None:
        """Navigate to a set of items from a task (US-C2, e.g. frost-affected)."""
        self._select_items_by_id({str(i) for i in (ids or [])})
