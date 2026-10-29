"""AgentHost: one responsibility extracted from GardenPlannerApp."""
from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any, Literal, NoReturn, cast
from uuid import UUID

from PyQt6.QtCore import QCoreApplication

from open_garden_planner.core.plant_renderer import is_plant_type
from open_garden_planner.services.soil_service import (
    SoilService,
)

if TYPE_CHECKING:
    import datetime


if TYPE_CHECKING:
    from open_garden_planner.app.application import GardenPlannerApp
    from open_garden_planner.core.commands import Command

logger = logging.getLogger(__name__)


def _entry_species_names(entry: dict[str, Any]) -> list[str]:
    """Every name an entry can be resolved by, machine key FIRST.

    ``species_key`` is the machine contract and ``common_name`` is display text
    (that is how the curated schema documents them, and what
    ``set_succession_plan`` validates). An earlier version preferred
    ``common_name``; since the validator never checks it, an agent could store
    ``{species_key: "solanum lycopersicum", common_name: "Cabbage"}`` and the
    rotation filter would then exclude the WRONG family - Brassicaceae instead
    of Solanaceae. Key first, display name only as the fallback for a
    free-text slot.
    """
    names: list[str] = []
    for field in ("species_key", "common_name", "scientific_name"):
        value = str(entry.get(field, "") or "").strip()
        if value and value not in names:
            names.append(value)
    return names


def _lookup_entry_species(entry: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve a succession entry to a bundled species record, or None."""
    from open_garden_planner.services.bundled_species_db import lookup_species

    for name in _entry_species_names(entry):
        found = lookup_species(name)
        if found is not None:
            return found
    return None


def _read_crop_rotation_record(raw: object) -> Any:
    """Deserialize one `crop_rotation` row, or return None if it is unusable.

    A ``.ogp`` is untrusted input (architecture invariant 14), so the catch is
    deliberately broad rather than an enumerated list of exception families: a
    previous version listed four types and still let a row through, because
    `PlantingRecord.from_dict` only does `data["year"]` and never type-checks it.
    A STRING or None year then survives deserialization and raises `TypeError`
    later, inside `get_records_for_area`'s sort - i.e. outside the loop that
    was supposed to protect it, and inside a Qt signal handler whose own guard
    catches only `RuntimeError`. That is an uncaught exception in the event
    loop, the `qFatal()`/abort shape #366 recorded.

    So the row is validated, not just parsed: `year` must really be an int.
    """
    from open_garden_planner.models.crop_rotation import PlantingRecord

    try:
        record = PlantingRecord.from_dict(raw)  # type: ignore[arg-type]
        if not isinstance(record.year, int) or isinstance(record.year, bool):
            raise ValueError(f"year is not an int: {record.year!r}")
        return record
    except Exception:
        logger.warning(
            "Skipping an unreadable crop-rotation record; crop rotation "
            "indicators and the family cooldown stay incomplete until it is fixed"
        )
        return None


def _parse_agent_date(
    value: str | None,
    fallback: datetime.date,
    field: str,
) -> datetime.date:
    """Parse an agent-supplied ISO date, falling back when omitted.

    Agent read tools that answer "what is current" accept an injected date so
    the answer is reproducible and testable — a suite that pins "today"
    silently rots the day after it is written, and an agent that cannot name the
    date it reasoned about cannot explain its own answer. Omitting the field
    still means "today"; supplying a malformed one is refused rather than
    quietly ignored, because a wrong reference date produces a confidently wrong
    current_entry.
    """
    import datetime

    if value is None or value == "":
        return fallback
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError:
        raise ValueError(
            f"{field}={value!r} is not an ISO date. Use YYYY-MM-DD."
        ) from None


class AgentHost:
    """Uses the original host for state, translation context and command ownership."""

    def __init__(self, host: GardenPlannerApp) -> None:
        self._host = host

    def _agent_snapshot(self) -> dict[str, Any]:
        """Read a snapshot of the live plan ON the Qt main thread (for the server)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._project_manager.snapshot_dict(host.canvas_scene)
        )


    def _agent_diagnostics(self) -> list[dict[str, Any]]:
        """Harvest the plan's current warnings ON the Qt main thread (for the server)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._project_manager.diagnostics_snapshot(host.canvas_scene)
        )


    def _agent_render(
        self,
        region: tuple[float, float, float, float] | None,
        layers: list[str] | None,
        image_width_px: int,
    ) -> dict[str, Any]:
        """Render a PNG of the live plan ON the Qt main thread (for the server)."""
        host = self._host
        from open_garden_planner.agent_api.render import render_canvas_image

        return host._sun_export_gate.run_worker(host._agent_bridge,
            lambda: render_canvas_image(host.canvas_scene, region, layers, image_width_px)
        )


    def _agent_save_plan(self, file_path: str | None) -> dict[str, Any]:
        """Save the live plan to disk ON the Qt main thread (for the server)."""
        host = self._host
        from open_garden_planner.agent_api.exports import save_plan_file

        return host._agent_bridge.run_on_main(
            lambda: save_plan_file(
                host.canvas_scene, host._project_manager, host._soil_service, file_path
            )
        )


    def _agent_new_plan(
        self,
        width_cm: float | None,
        height_cm: float | None,
        force: bool,
    ) -> dict[str, Any]:
        """Start a fresh, empty plan ON the Qt main thread (issue #365).

        The unsaved-changes guard lives HERE rather than in the Qt-free
        validation module, because only the main thread can read the live
        ``is_dirty`` flag — and because the GUI's own equivalent is
        ``_confirm_discard_changes``, which is likewise a main-thread
        interaction. An agent cannot raise a modal prompt, so the choice is
        binary: refuse, or proceed when the caller passes ``force=True``.
        """
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_new_plan(width_cm, height_cm, force)
        )


    def _do_agent_new_plan(
        self,
        width_cm: float | None = None,
        height_cm: float | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Main-thread body of ``new_plan``.

        Reuses ``_new_project_document`` — the same method File > New runs
        after its dialog, so there is exactly one new-document path.
        """
        host = self._host
        from open_garden_planner.agent_api.exports import validate_new_plan

        host._flush_pending_panel_edits()
        if host._project_manager.is_dirty and not force:
            raise ValueError(
                "The open plan has unsaved changes. Re-run with force=true to "
                "discard them and start a new plan, or save it first with "
                "save_plan. (The GUI asks the user at this point; an agent "
                "cannot, so it must be told.)"
            )

        # Read BEFORE the mutation: after _new_project_document the plan is
        # clean by construction, so reading it afterwards would always report
        # False and the agent would never learn that it just discarded work.
        was_dirty = bool(host._project_manager.is_dirty)

        plan_width, plan_height = validate_new_plan(
            width_cm, height_cm, host.canvas_scene.width_cm, host.canvas_scene.height_cm
        )
        host._new_project_document(width_cm=plan_width, height_cm=plan_height)
        return {
            "file_path": None,
            "width_cm": plan_width,
            "height_cm": plan_height,
            "was_dirty": was_dirty,
        }


    def _agent_open_plan(self, file_path: str, force: bool) -> dict[str, Any]:
        """Load a ``.ogp`` file ON the Qt main thread (issue #365).

        Reuses ``_open_project_file`` — the same method File > Open and the
        Recent-files menu run — so the agent and the GUI load a plan through
        one path rather than two that can drift.
        """
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_open_plan(file_path, force)
        )


    def _do_agent_open_plan(self, file_path: str, force: bool = False) -> dict[str, Any]:
        """Main-thread body of ``open_plan``.

        Path handling deliberately mirrors ``save_plan`` and NOT a sandbox:
        this server is loopback-only (ADR-033), so a local MCP client already
        has the same filesystem access as the OS user account. Inventing a
        stricter rule here than the export tools enforce would be a policy the
        rest of the surface does not hold. What IS enforced is the part that
        prevents a silent surprise: the file must exist, and the extension
        must be ``.ogp``.
        """
        host = self._host
        from open_garden_planner.agent_api.exports import validate_open_plan

        host._flush_pending_panel_edits()
        if host._project_manager.is_dirty and not force:
            raise ValueError(
                "The open plan has unsaved changes. Re-run with force=true to "
                "discard them and open another plan, or save it first with "
                "save_plan. (The GUI asks the user at this point; an agent "
                "cannot, so it must be told.)"
            )

        resolved = validate_open_plan(file_path)
        # Read before the load, which resets the flag.
        was_dirty = bool(host._project_manager.is_dirty)
        # _load_project_file RAISES on a parse failure, which is what an agent
        # needs. The GUI's _open_project_file is the same call wrapped in a
        # modal QMessageBox, which an agent must never raise on its behalf.
        host._load_project_file(str(resolved))
        return {
            "file_path": str(resolved),
            "width_cm": host.canvas_scene.width_cm,
            "height_cm": host.canvas_scene.height_cm,
            # A load resets the dirty flag, so read it BEFORE, for the same
            # reason new_plan does.
            "was_dirty": was_dirty,
        }


    def _agent_export_pdf(
        self,
        file_path: str | None,
        paper_size: Literal["A4", "A3", "Letter", "Legal"],
        orientation: Literal["landscape", "portrait"],
    ) -> dict[str, Any]:
        """Export the PDF report ON the Qt main thread (for the server)."""
        host = self._host
        from open_garden_planner.agent_api.exports import export_pdf_file

        return host._sun_export_gate.run_worker(host._agent_bridge,
            lambda: export_pdf_file(
                host.canvas_scene, host._project_manager, file_path, paper_size, orientation
            )
        )


    def _agent_export_dxf(self, file_path: str | None) -> dict[str, Any]:
        """Export a DXF drawing ON the Qt main thread (for the server)."""
        host = self._host
        from open_garden_planner.agent_api.exports import export_dxf_file

        return host._agent_bridge.run_on_main(
            lambda: export_dxf_file(host.canvas_scene, host._project_manager, file_path)
        )


    def _agent_export_csv(
        self, kind: Literal["shopping_list", "harvest"], file_path: str | None
    ) -> dict[str, Any]:
        """Export a shopping-list/harvest CSV ON the Qt main thread (for the server)."""
        host = self._host
        from open_garden_planner.agent_api.exports import export_csv_file

        return host._agent_bridge.run_on_main(
            lambda: export_csv_file(
                host.canvas_scene, host._project_manager, host._soil_service, kind, file_path
            )
        )


    def _agent_create_object(
        self,
        object_type: str,
        x: float | None,
        y: float | None,
        width: float | None,
        height: float | None,
        radius: float | None,
        name: str | None,
        species: str | None,
        points: list[list[float]] | None = None,
        text: str | None = None,
        box_dx: float | None = None,
        box_dy: float | None = None,
    ) -> dict[str, Any]:
        """Create one object ON the Qt main thread (for the server)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_create_object(
                object_type,
                x,
                y,
                width,
                height,
                radius,
                name,
                species,
                points,
                text,
                box_dx,
                box_dy,
            )
        )


    def _do_agent_create_object(
        self,
        object_type: str,
        x: float | None,
        y: float | None,
        width: float | None,
        height: float | None,
        radius: float | None,
        name: str | None,
        species: str | None,
        points: list[list[float]] | None = None,
        text: str | None = None,
        box_dx: float | None = None,
        box_dy: float | None = None,
    ) -> dict[str, Any]:
        """Create one supported object — one undoable step (US-D2.1/D2.5).

        Mirrors the GUI's own creation orchestration, not merely
        ``CreateItemCommand``. The gallery-drop path in ``CanvasView`` does five
        things in order, and skipping any of them ships a subtly broken object:
        build the item, apply the species, auto-populate its species metadata
        from the bundled DB (so the plant-detail panel and US-12.10d
        soil-mismatch warnings light up without a manual "Suchen"), stamp
        the active plan date as planting date (US-E8/F4 — OUTSIDE the species guard,
        so a placeholder that gains a species later is not left permanently
        undated, which would break the growth model), and assign the active
        layer.

        The item itself is built by ``_deserialize_item_core`` — the file
        loader's own factory — so an agent-created object is constructed by
        exactly the code path a loaded one is.

        Bed membership needs no work here: ``CreateItemCommand.execute`` already
        calls ``_auto_parent_plant``, which links a plant to the smallest bed
        containing it (and ``undo`` calls ``_detach_from_parent``). So the link
        is established *inside* the single create step — unlike ``move_object``,
        which must reconcile explicitly because ``MoveItemsCommand`` has no such
        hook. This is therefore ALWAYS exactly one undo step. The resulting
        parent, if any, is reported back as ``new_parent_bed_id``.

        Refuses (raises) rather than guessing: an unsupported type, a dimension
        that doesn't fit the type's shape, a non-finite or non-positive extent
        (all in the Qt-free ``creates`` module), or a locked active layer — the
        GUI can't draw onto a locked layer either.
        """
        host = self._host

        from open_garden_planner.agent_api import creates
        from open_garden_planner.core.commands import CreateItemCommand, CreateItemsCommand
        from open_garden_planner.core.growth_model import stamp_default_planting_date

        if species and not creates.is_plant_type_name(object_type):
            # The only silent-ignore an otherwise loud tool would have had.
            raise ValueError(
                f"{object_type} is not a plant, so it cannot take a species "
                f"({species!r}). Drop the 'species' argument, or create a "
                "TREE/SHRUB/PERENNIAL instead."
            )

        canvas_rect = host.canvas_scene.canvas_rect
        spec = creates.build_create_dict(
            object_type=object_type,
            x=x,
            y=y,
            canvas_width_cm=canvas_rect.width(),
            canvas_height_cm=canvas_rect.height(),
            width=width,
            height=height,
            radius=radius,
            name=name,
            points=points,
            text=text,
            box_dx=box_dx,
            box_dy=box_dy,
        )

        active_layer = host._agent_creation_target_layer()
        if active_layer is not None:
            spec["layer_id"] = str(active_layer.id)

        item = host._project_manager._deserialize_item_core(spec)
        if item is None:
            raise ValueError(f"Could not build a {object_type} from those parameters.")

        if creates.is_plant_type_name(object_type):
            if species:
                from open_garden_planner.services.bundled_species_db import (
                    populate_item_species_metadata,
                )

                cast(Any, item).plant_species = species
                populate_item_species_metadata(item, species)
            # US-E8: every new plant is dated, species or not (see docstring).
            stamp_default_planting_date(cast(Any, item).metadata, host._sim_clock.plan_date)

        linked_items: list[Any] = []
        if object_type == "HOUSE":
            from open_garden_planner.core.roof_ridge import compute_roof_ridge_endpoints

            p1, p2 = compute_roof_ridge_endpoints(cast(Any, item).polygon(), item.pos())
            # Keep the derived sibling on the loader path too.  The house and
            # ridge are both created from the same serialized shape vocabulary
            # that ProjectManager.load() consumes; CreateItemsCommand still
            # makes their visible appearance one atomic undo step.
            ridge_spec = {
                "type": "polyline",
                "object_type": "ROOF_RIDGE",
                "points": [
                    {"x": p1.x(), "y": p1.y()},
                    {"x": p2.x(), "y": p2.y()},
                ],
                "layer_id": str(getattr(item, "layer_id", None))
                if getattr(item, "layer_id", None) is not None
                else None,
            }
            if ridge_spec["layer_id"] is None:
                ridge_spec.pop("layer_id")
            ridge = host._project_manager._deserialize_item_core(ridge_spec)
            if ridge is None:
                raise ValueError("Could not build the HOUSE roof ridge.")
            cast(Any, ridge).set_metadata("owner_polygon_id", str(cast(Any, item).item_id))
            cast(Any, item).set_metadata("ridge_item_id", str(cast(Any, ridge).item_id))
            linked_items.append(ridge)

        items = [item, *linked_items]
        # Clamp the whole creation group onto the canvas (issue #380). The GUI
        # clamps every object it draws; before this an agent could create one
        # entirely off-plan and it became invisible and unselectable. `creates`
        # stays Qt-free — the clamp is applied here, where the live bounding
        # rects are available, and uses the same shared math the GUI drag path
        # does (core/canvas_bounds).
        host._clamp_agent_items_to_canvas(items)

        if linked_items:
            create_cmd: Command = CreateItemsCommand(host.canvas_scene, items, "objects")
        else:
            create_cmd = CreateItemCommand(host.canvas_scene, item)
        host.canvas_view.command_manager.execute(create_cmd)

        # Read back whatever _auto_parent_plant established inside the command.
        # (See _agent_creation_target_layer for what creation validates; the
        # shape/size/position half lives in the Qt-free agent_api.creates.)
        parent_bed_id = getattr(item, "parent_bed_id", None)

        cx, cy = host._agent_item_center(item)
        return {
            "item_id": str(cast(Any, item).item_id),
            "action": "create",
            "undo_description": create_cmd.description,
            "x": cx,
            "y": cy,
            # False by definition for create: the link (if any) happened inside
            # the one create step, not as a separate second one.
            "bed_membership_changed": False,
            "new_parent_bed_id": str(parent_bed_id) if parent_bed_id else None,
            "linked_items_created": len(linked_items),
        }


    def _agent_creation_target_layer(self) -> Any:
        """The layer a new agent-created object must land on, or raise.

        The creation-side counterpart of ``_resolve_agent_item``'s checks: a
        write tool that *resolves* an existing item inherits that chokepoint,
        but a tool that creates one has nothing to resolve, so the scene-level
        guard lives here — as a seam, so the next creation-shaped tool
        (`create_shape`, `duplicate_object`, …) inherits it instead of
        copy-pasting the check.

        Returns ``None`` when the scene has no active layer at all, matching the
        GUI drop path (which also leaves ``layer_id`` unset in that case).

        The shape/size/position half of creation's validation is the Qt-free
        ``agent_api.creates`` module — keep the two in step.
        """
        host = self._host
        active_layer = host.canvas_scene.active_layer
        if active_layer is None:
            return None
        if active_layer.locked:
            # The GUI enforces layer-lock by clearing the item interaction
            # flags, so nothing can be drawn onto a locked layer there either.
            raise ValueError(
                f"The active layer {active_layer.name!r} is locked; unlock it "
                "with set_layer_property(layer_id, locked=False) (or make "
                "another layer active) before creating objects."
            )
        return active_layer


    def _agent_get_geometry(self, item_id: str) -> dict[str, Any]:
        """Read one object's live low-level geometry ON the Qt main thread."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_get_geometry(item_id)
        )


    def _do_agent_get_geometry(self, item_id: str) -> dict[str, Any]:
        """Main-thread body of the unauthenticated ``get_geometry`` read."""
        host = self._host
        from open_garden_planner.ui.canvas.geometry_inspect import describe_geometry

        item = host._resolve_agent_read_item(item_id)
        host._agent_require_unique_items([item], action="get_geometry")
        center = host._agent_item_center(item)
        constraints = host._agent_item_constraints(item)
        return describe_geometry(
            item,
            center=center,
            constraints=constraints,
        )


    def _agent_move_object(self, item_id: str, dx: float, dy: float) -> dict[str, Any]:
        """Move one object by (dx, dy) scene cm ON the Qt main thread (for the server)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_move_object(item_id, dx, dy)
        )


    def _do_agent_move_object(
        self, item_id: str, dx: float, dy: float
    ) -> dict[str, Any]:
        """Main-thread body of ``move_object`` (US-D2.0)."""
        host = self._host
        from PyQt6.QtCore import QPointF

        item = host._resolve_agent_item(item_id)
        return host._agent_apply_object_move(
            item,
            item_id,
            QPointF(float(dx), float(dy)),
            action="move",
        )


    def _agent_set_object_position(
        self, item_id: str, x: float, y: float
    ) -> dict[str, Any]:
        """Set one object's centre ON the Qt main thread (for the server)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_set_object_position(item_id, x, y)
        )


    def _do_agent_set_object_position(
        self, item_id: str, x: float, y: float
    ) -> dict[str, Any]:
        """Main-thread body of ``set_object_position`` (US-D2.6)."""
        host = self._host
        import math

        from PyQt6.QtCore import QPointF

        from open_garden_planner.agent_api import edits
        from open_garden_planner.ui.canvas.geometry_apply import (
            GEOMETRY_ROUNDTRIP_EPS_CM,
        )

        canvas = host.canvas_scene.canvas_rect
        target_x, target_y = edits.validate_scene_point(
            x,
            y,
            canvas_width_cm=canvas.width(),
            canvas_height_cm=canvas.height(),
        )
        item = host._resolve_agent_item(item_id)
        host._agent_require_unique_items([item], action="set_object_position")
        current_x, current_y = host._agent_item_center(item)
        delta = QPointF(target_x - current_x, target_y - current_y)
        item_deltas = host._agent_move_item_deltas(item, delta)
        host._agent_preflight_object_move(item_deltas, item_id, "set_object_position")
        if math.hypot(target_x - current_x, target_y - current_y) <= (
            GEOMETRY_ROUNDTRIP_EPS_CM
        ):
            raise ValueError(
                f"{item_id} is already centred at ({current_x:g}, {current_y:g}); "
                "nothing to change."
            )
        return host._agent_apply_object_move(
            item,
            item_id,
            delta,
            action="set_position",
            item_deltas=item_deltas,
        )


    def _clamp_agent_items_to_canvas(self, items: list[Any]) -> None:
        """Shift a group of newly created items so it lies inside the canvas.

        The agent counterpart of ``CanvasView._clamp_items_to_canvas`` (issue
        #380), using the same shared math so the two cannot drift. Background
        images are exempt, matching the GUI. A no-op when everything is already
        inside.
        """
        host = self._host
        from open_garden_planner.core.canvas_bounds import clamp_shift_within_canvas
        from open_garden_planner.ui.canvas.items import BackgroundImageItem

        clampable = [i for i in items if not isinstance(i, BackgroundImageItem)]
        if not clampable:
            return
        canvas = host.canvas_scene.canvas_rect
        rects = [
            (
                bounded.sceneBoundingRect().left(),
                bounded.sceneBoundingRect().top(),
                bounded.sceneBoundingRect().right(),
                bounded.sceneBoundingRect().bottom(),
            )
            for bounded in clampable
        ]
        dx, dy = clamp_shift_within_canvas(rects, canvas.width(), canvas.height())
        if dx != 0 or dy != 0:
            for bounded in clampable:
                bounded.moveBy(dx, dy)


    def _agent_preflight_object_move(
        self,
        item_deltas: list[tuple[Any, Any]],
        item_id: str,
        tool_name: str,
    ) -> None:
        """Refuse the complete move graph before any command can be executed."""
        host = self._host
        for constrained_item, _ in item_deltas:
            constrained_id = getattr(constrained_item, "item_id", None)
            subject_id = str(constrained_id) if constrained_id is not None else item_id
            host._agent_require_unconstrained(
                constrained_item,
                subject_id,
                tool_name,
            )


    def _agent_apply_object_move(
        self,
        item: Any,
        item_id: str,
        delta: Any,
        *,
        action: str,
        item_deltas: list[tuple[Any, Any]] | None = None,
    ) -> dict[str, Any]:
        """Apply the complete GUI move orchestration for one resolved item.

        ``move_object`` and ``set_object_position`` differ only in how they
        derive ``delta``. Both therefore share child propagation, constraint
        preflight, command selection, and bed-membership reconciliation. A plant
        crossing a bed boundary inherits ``move_object``'s documented second
        undo step; every other move is one step.
        """
        host = self._host
        from open_garden_planner.core.commands import AlignItemsCommand, MoveItemsCommand

        if item_deltas is None:
            item_deltas = host._agent_move_item_deltas(item, delta)
            constraint_tool_name = (
                "set_object_position" if action == "set_position" else "move_object"
            )
            host._agent_preflight_object_move(
                item_deltas, item_id, constraint_tool_name
            )

        # Clamp the move so the whole group stays on the canvas (issue #380) —
        # the GUI clamps drags and nudges; the agent path did not, so it could
        # push an object entirely off-plan in one call. Shared math with the GUI
        # (core/canvas_bounds). Background images are exempt, as in the GUI.
        from PyQt6.QtCore import QPointF as _QPointF

        from open_garden_planner.core.canvas_bounds import clamp_delta_within_canvas
        from open_garden_planner.ui.canvas.items import BackgroundImageItem

        canvas = host.canvas_scene.canvas_rect
        clampable_rects = [
            (
                moved_item.sceneBoundingRect().left(),
                moved_item.sceneBoundingRect().top(),
                moved_item.sceneBoundingRect().right(),
                moved_item.sceneBoundingRect().bottom(),
            )
            for moved_item, _ in item_deltas
            if not isinstance(moved_item, BackgroundImageItem)
        ]
        clamped_dx, clamped_dy = clamp_delta_within_canvas(
            clampable_rects,
            delta.x(),
            delta.y(),
            canvas.width(),
            canvas.height(),
        )
        # A NON-ZERO requested move that the clamp erases entirely is a no-op, not
        # a move. Without this it still executed a MoveItemsCommand that changed
        # nothing but pushed a dead undo step — a Ctrl+Z that visibly does nothing
        # (issue #380 review). Refuse instead, matching the existing unclamped
        # no-op guard in _do_agent_set_object_position, so the stack stays
        # untouched.
        #
        # A requested delta that is ALREADY zero is deliberately left alone: it is
        # a legal call that re-reads and returns the current centre (an existing
        # test relies on `move_object(0, 0)` reporting the read-layer centre for a
        # badge-bearing plant). Only a request the clamp *canceled* is refused.
        from open_garden_planner.ui.canvas.geometry_apply import (
            GEOMETRY_ROUNDTRIP_EPS_CM,
        )

        requested_was_nonzero = (
            abs(delta.x()) > GEOMETRY_ROUNDTRIP_EPS_CM
            or abs(delta.y()) > GEOMETRY_ROUNDTRIP_EPS_CM
        )
        clamp_erased_the_move = (
            abs(clamped_dx) <= GEOMETRY_ROUNDTRIP_EPS_CM
            and abs(clamped_dy) <= GEOMETRY_ROUNDTRIP_EPS_CM
        )
        if requested_was_nonzero and clamp_erased_the_move:
            raise ValueError(
                f"{item_id} (with anything it carries) is already at the canvas "
                "edge; the requested move was clamped to no displacement. "
                "Nothing to change."
            )
        if clamped_dx != delta.x() or clamped_dy != delta.y():
            item_deltas = [
                (moved_item, _QPointF(clamped_dx, clamped_dy))
                for moved_item, _ in item_deltas
            ]
            delta = _QPointF(clamped_dx, clamped_dy)

        if len(item_deltas) == 1:
            move_cmd: Command = MoveItemsCommand([item], delta)
        else:
            from PyQt6.QtCore import QCoreApplication

            move_cmd = AlignItemsCommand(
                item_deltas, QCoreApplication.translate("Commands", "Move item")
            )
        host.canvas_view.command_manager.execute(move_cmd)

        reparented, new_parent_bed_id = host._agent_reconcile_bed_membership(item)
        cx, cy = host._agent_item_center(item)
        return {
            "item_id": item_id,
            "action": action,
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
        host = self._host
        from open_garden_planner.core.object_types import is_plant_parent_type
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        item_deltas: list[tuple[Any, Any]] = [(item, delta)]
        if isinstance(item, GardenItemMixin) and is_plant_parent_type(item.object_type):
            for child_id in item.child_item_ids:
                child = host.canvas_scene.find_item_by_id(child_id)
                if child is not None:
                    item_deltas.append((child, delta))
        return item_deltas


    def _agent_reconcile_bed_membership(self, item: Any) -> tuple[bool, str | None]:
        """After moving a plant, re-evaluate its bed membership — the
        release-time equivalent of ``CanvasView._update_plant_bed_relationships``.
        Returns ``(changed, new_parent_bed_id)``; a non-plant item or an
        unchanged membership returns ``(False, None)``."""
        host = self._host
        from open_garden_planner.core.commands import SetParentBedCommand
        from open_garden_planner.ui.canvas.footprints import bed_membership_point
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        if not isinstance(item, GardenItemMixin) or not is_plant_type(item.object_type):
            return False, None

        plant_center = bed_membership_point(item)
        current_parent_id = item.parent_bed_id
        new_bed = host.canvas_scene.find_smallest_bed_containing(plant_center)
        new_parent_id = (
            new_bed.item_id
            if new_bed is not None and isinstance(new_bed, GardenItemMixin)
            else None
        )
        if new_parent_id == current_parent_id:
            return False, None

        cmd = SetParentBedCommand(
            host.canvas_scene, cast(Any, item), current_parent_id, new_parent_id
        )
        host.canvas_view.command_manager.execute(cmd)
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
        host = self._host
        from open_garden_planner.agent_api import queries

        data = host._project_manager._serialize_item(item)
        if data is not None:
            return queries.object_center(data)
        c = item.sceneBoundingRect().center()
        return c.x(), c.y()


    def _agent_delete_object(self, item_id: str) -> dict[str, Any]:
        """Delete one object ON the Qt main thread (for the server)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_delete_object(item_id)
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
        host = self._host
        from open_garden_planner.core.commands import DeleteItemsCommand, RemoveConstraintCommand

        item = host._resolve_agent_item(item_id)
        linked_ridge = host._agent_linked_roof_ridge(item)
        targets = [item, *linked_ridge]
        host._agent_require_unique_items(targets)
        target_ids = {
            host._agent_item_uuid(candidate) for candidate in targets
        }

        constraints = host._agent_item_constraints(item)
        for constraint in constraints:
            host.canvas_view.command_manager.execute(
                RemoveConstraintCommand(host.canvas_scene.constraint_graph, constraint)
            )

        cmd = DeleteItemsCommand(host.canvas_scene, targets)
        host.canvas_view.command_manager.execute(cmd)
        # The response is a completion receipt, not merely a command queued on
        # the main thread.  Check every serialized UUID, not just the Python
        # wrappers we passed to DeleteItemsCommand: a cross-class duplicate
        # could otherwise survive and make a successful reply a lie.
        remaining = [
            candidate
            for candidate in host._agent_document_items()
            if host._agent_item_uuid(candidate) in target_ids
        ]
        if remaining:
            raise RuntimeError(
                "delete_object left a live document object with a target UUID; "
                "the operation was not reported as successful."
            )
        return {
            "item_id": item_id,
            "action": "delete",
            "undo_description": cmd.description,
            "linked_items_deleted": len(linked_ridge),
            "constraints_removed": len(constraints),
        }


    def _agent_undo(self) -> dict[str, Any]:
        """Undo one command on the GUI's global history stack."""
        host = self._host
        return host._agent_bridge.run_on_main(host._do_agent_undo)


    def _do_agent_undo(self) -> dict[str, Any]:
        """Main-thread body of the authenticated MCP ``undo`` tool."""
        host = self._host
        manager = host.canvas_view.command_manager
        if not manager.can_undo:
            raise ValueError("Nothing to undo.")
        description = manager.undo_description or "Unknown command"
        manager.undo()
        return {
            "action": "undo",
            "command_description": description,
            "can_undo": manager.can_undo,
            "can_redo": manager.can_redo,
        }


    def _agent_redo(self) -> dict[str, Any]:
        """Redo one command on the GUI's global history stack."""
        host = self._host
        return host._agent_bridge.run_on_main(host._do_agent_redo)


    def _do_agent_redo(self) -> dict[str, Any]:
        """Main-thread body of the authenticated MCP ``redo`` tool."""
        host = self._host
        manager = host.canvas_view.command_manager
        if not manager.can_redo:
            raise ValueError("Nothing to redo.")
        description = manager.redo_description or "Unknown command"
        manager.redo()
        return {
            "action": "redo",
            "command_description": description,
            "can_undo": manager.can_undo,
            "can_redo": manager.can_redo,
        }


    def _agent_get_history(self) -> dict[str, Any]:
        """Read the undo/redo stack state (US-D2.7, read-only)."""
        host = self._host
        from open_garden_planner.agent_api.history import history_from_command_manager

        return host._agent_bridge.run_on_main(
            lambda: history_from_command_manager(
                host.canvas_view.command_manager
            ).model_dump()
        )


    def _agent_suggest_companions(
        self,
        species_key: str,
        exclude_antagonists_of: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Suggest companion plants for a species (US-D3.1, read-only)."""
        host = self._host
        from open_garden_planner.agent_api.domain import suggest_companions_for_agent
        from open_garden_planner.app.settings import active_language

        def _run() -> list[dict[str, Any]]:
            # Resolve the language on the main thread, beside the other
            # settings reads the agent bodies perform.
            language = active_language()
            return [
                s.model_dump()
                for s in suggest_companions_for_agent(
                    host._companion_service,
                    species_key,
                    exclude_antagonists_of=exclude_antagonists_of,
                    language=language,
                )
            ]

        return host._agent_bridge.run_on_main(_run)


    def _agent_find_compatible_sets(
        self,
        candidates: list[str],
        size: int = 3,
        must_include: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Find mutually compatible sets of plants (US-D3.1, read-only)."""
        host = self._host
        from open_garden_planner.agent_api.domain import find_compatible_sets_for_agent

        return host._agent_bridge.run_on_main(
            lambda: [
                s.model_dump()
                for s in find_compatible_sets_for_agent(
                    host._companion_service,
                    candidates,
                    size=size,
                    must_include=must_include,
                )
            ]
        )


    def _agent_find_sets_for_bed(
        self,
        bed_plants: list[str],
        size: int = 3,
    ) -> dict[str, Any]:
        """Rank compatible sets by bed coverage (US-D3.1, read-only)."""
        host = self._host
        from open_garden_planner.services.companion_sets import find_sets_for_bed

        return host._agent_bridge.run_on_main(
            lambda: find_sets_for_bed(host._companion_service, bed_plants, size=size)
        )


    def _agent_check_placement(
        self,
        species_key: str,
        bed_id: str,
        bed_plants: list[str] | None = None,
    ) -> dict[str, Any]:
        """Check whether a species is well-placed in a bed (US-D3.1, read-only)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_check_placement(species_key, bed_id, bed_plants)
        )


    def _do_agent_check_placement(
        self,
        species_key: str,
        bed_id: str,
        bed_plants: list[str] | None = None,
    ) -> dict[str, Any]:
        """Main-thread body of the read-only MCP ``check_placement`` tool.

        Resolves the bed's own plants when the caller did not supply them, so
        an unknown ``bed_id`` is reported as such instead of looking like an
        empty bed (P1-5).

        Bed membership in this codebase is the ``parent_bed_id`` PROPERTY on
        ``GardenItem`` — NOT Qt item parenting. ``bed.childItems()`` returns
        ``[]`` for every real bed (``setParentItem`` is used only for label
        items), so the first version of this silently reported every bed as
        empty and answered ``overall="neutral"`` for a bed whose real answer
        was ``"critical"`` — a fabricated clean result, the exact failure class
        this tool exists to avoid. Membership is read the way
        ``queries.plants_in_bed`` does, and ``bed_exists`` is resolved
        UNCONDITIONALLY so supplying ``bed_plants`` cannot bypass the
        existence check.
        """
        host = self._host
        from open_garden_planner.agent_api.domain import check_placement_for_agent
        from open_garden_planner.core.object_types import is_plant_parent_type

        bed_exists: bool | None = None
        try:
            target_id = UUID(bed_id)
        except (ValueError, TypeError, AttributeError):
            target_id = None

        resolved = bed_plants
        if target_id is not None:
            bed = host.canvas_scene.find_item_by_id(target_id)
            # Existence is NOT enough: a plant's own id, or a shape's, also
            # resolves. Reporting "neutral" for a non-bed says "I inspected
            # this bed's plants and none relate" about an object that is not a
            # bed — the same fabrication ADR-045's honesty invariant forbids,
            # and the published contract says an id that names no bed is
            # `unknown_bed`. `is_plant_parent_type` is the codebase's own
            # predicate for "can hold plants" and covers every bed type plus
            # TRELLIS.
            if bed is None or not is_plant_parent_type(
                getattr(bed, "object_type", None)
            ):
                bed_exists = False
            else:
                bed_exists = True
                if resolved is None:
                    resolved = host._agent_bed_species_keys(target_id)
        else:
            bed_exists = False

        if resolved is None and bed_exists is not False:
            # Bed exists but we could not enumerate it — say so rather than
            # implying the bed is empty.
            bed_exists = None

        return check_placement_for_agent(
            host._companion_service,
            species_key,
            bed_id,
            bed_plants=resolved,
            bed_exists=bed_exists,
        ).model_dump()


    def _agent_bed_species_keys(self, bed_id: UUID) -> list[str] | None:
        """Species keys of the plants linked to ``bed_id``.

        Reads the ``parent_bed_id`` PROPERTY, which is how this codebase
        records bed membership (``queries.plants_in_bed`` does the same, and
        ``canvas_scene``/``commands`` maintain it). Returns ``None`` only if
        the scene cannot be walked at all, so the caller can tell "the bed is
        empty" apart from "I could not look".
        """
        host = self._host
        try:
            items = list(host.canvas_scene.items())
        except Exception:
            return None

        out: list[str] = []
        for item in items:
            if not host.canvas_scene.is_present(item):
                continue
            if getattr(item, "parent_bed_id", None) != bed_id:
                continue
            # Delegate to the SHARED resolver rather than re-implementing the
            # precedence. This was attribute-first while
            # `_companion_species_name` and `queries._species_name` are
            # metadata-first, so on a plant where both are set and DISAGREE
            # (a gallery drop sets both; a later species-search assignment
            # overwrites only the metadata) the agent resolved the stale
            # attribute and found zero relationships while the panel found real
            # ones. One resolver, one answer (the same divergence class ADR-045's
            # addendum is about).
            name = host._companion_species_name(item)
            if name:
                out.append(str(name).lower())
        return out


    def _agent_resolve_soil_bed(self, bed_id: str) -> Any:
        """Resolve ``bed_id`` to a soil-capable canvas item, or raise.

        Succession planning attaches to a BED, so this uses ``is_bed_type``
        (soil-capable: GARDEN_BED, RAISED_BED, CONTAINER, CONTAINER_ROUND,
        WALL_PLANTER) rather than the looser ``is_plant_parent_type`` that
        ``check_placement`` uses. A TRELLIS is a plant parent but holds no soil,
        so a succession plan on one is refused rather than silently accepted —
        the difference is deliberate and commented so it is not "corrected" later.
        """
        host = self._host
        from open_garden_planner.core.object_types import is_bed_type

        try:
            target = UUID(bed_id)
        except (ValueError, TypeError, AttributeError):
            raise ValueError(
                f"{bed_id!r} is not a valid bed id. Use the stable UUID from "
                "list_objects or get_object."
            ) from None

        item = host.canvas_scene.find_item_by_id(target)
        if item is None:
            raise ValueError(
                f"No object with id {bed_id!r} exists in this plan. Read "
                "list_objects for the beds it contains."
            )
        if not is_bed_type(getattr(item, "object_type", None)):
            raise ValueError(
                f"{bed_id!r} is a "
                f"{getattr(item, 'object_type', None)} — succession planning "
                "needs a soil-capable bed (GARDEN_BED, RAISED_BED, CONTAINER, "
                "CONTAINER_ROUND or WALL_PLANTER)."
            )
        return item


    def _agent_succession_plan_raw(self, bed_id: str) -> dict[str, Any] | None:
        """The bed's raw succession plan dict, or None when it has no plan."""
        host = self._host
        return host._project_manager.succession_plans.get(bed_id)


    def _agent_get_succession_plan(
        self,
        bed_id: str,
        year: int | None = None,
        today: str | None = None,
    ) -> dict[str, Any]:
        """Read a bed's succession plan (US-D3.2, read-only)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_get_succession_plan(bed_id, year, today)
        )


    def _do_agent_get_succession_plan(
        self,
        bed_id: str,
        year: int | None,
        today: str | None,
    ) -> dict[str, Any]:
        """Main-thread body of the read-only ``get_succession_plan`` tool."""
        host = self._host
        import datetime

        from open_garden_planner.agent_api.domain import get_succession_plan_for_agent

        host._agent_resolve_soil_bed(bed_id)
        reference = _parse_agent_date(today, datetime.date.today(), "today")
        view = get_succession_plan_for_agent(
            host._agent_succession_plan_raw(bed_id),
            bed_id,
            year=year,
            today=reference,
            location=host._project_manager.location,
        )
        return view.model_dump()


    def _agent_find_succession_gaps(
        self,
        bed_id: str,
        year: int | None = None,
        today: str | None = None,
    ) -> list[dict[str, Any]]:
        """Report a bed's uncovered growing-season ranges (US-D3.2, read-only)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_find_succession_gaps(bed_id, year, today)
        )


    def _do_agent_find_succession_gaps(
        self,
        bed_id: str,
        year: int | None,
        today: str | None,
    ) -> list[dict[str, Any]]:
        """Main-thread body of the read-only ``find_succession_gaps`` tool."""
        host = self._host
        import datetime

        from open_garden_planner.agent_api.domain import find_succession_gaps_for_agent

        host._agent_resolve_soil_bed(bed_id)
        reference = _parse_agent_date(today, datetime.date.today(), "today")
        return [
            gap.model_dump()
            for gap in find_succession_gaps_for_agent(
                host._agent_succession_plan_raw(bed_id),
                year=year,
                today=reference,
                location=host._project_manager.location,
            )
        ]


    def _agent_suggest_succession(
        self,
        bed_id: str,
        gap_start: str,
        gap_end: str,
        candidates: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Rank crops for a succession gap (US-D3.2, read-only)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_suggest_succession(
                bed_id, gap_start, gap_end, candidates
            )
        )


    def _do_agent_suggest_succession(
        self,
        bed_id: str,
        gap_start: str,
        gap_end: str,
        candidates: list[str] | None,
    ) -> list[dict[str, Any]]:
        """Main-thread body of the read-only ``suggest_succession`` tool."""
        host = self._host
        from open_garden_planner.agent_api.domain import suggest_succession_for_agent

        host._agent_resolve_soil_bed(bed_id)
        plan_raw = host._agent_succession_plan_raw(bed_id)
        records = host._agent_species_records(candidates)
        within = host._agent_plan_families_before(plan_raw, gap_start)
        avoid = host._agent_rotation_avoid_families(bed_id)
        neighbours = host._agent_concurrent_species_keys(plan_raw, gap_start, gap_end)

        return [
            s.model_dump()
            for s in suggest_succession_for_agent(
                candidates=records,
                gap_start=gap_start,
                gap_end=gap_end,
                avoid_families=avoid,
                within_plan_families=within,
                neighbour_keys=neighbours,
                service=host._companion_service,
            )
        ]


    def _agent_species_records(self, candidates: list[str] | None) -> list[dict[str, Any]]:
        """Resolve species names/keys to bundled species records.

        An unresolvable name yields NO record rather than a blank placeholder, so
        it cannot be suggested as a crop with no family and no maturity.
        """

        names = candidates or []
        from open_garden_planner.services.bundled_species_db import lookup_species

        records: list[dict[str, Any]] = []
        for name in names:
            found = lookup_species(str(name))
            if found is not None:
                records.append(dict(found))
        return records


    def _agent_plan_families_before(self, plan_raw: dict[str, Any] | None, gap_start: str) -> list[str]:
        """Botanical families the bed already plans BEFORE a gap starts.

        Succession is several crops in ONE season, which is why
        ``CropRotationService.check_plant_placement`` cannot answer this: it
        compares a candidate only against ``records[0]``, the single most recent
        planting record, and therefore cannot see "tomato after the garlic entry
        three slots ago". Succession entries also never enter the rotation
        history (only the Crop Rotation panel writes those). So the within-plan
        rule is computed here, from the plan itself, and the cross-YEAR rule is
        still delegated to the service by ``_agent_rotation_avoid_families``.
        """
        from open_garden_planner.agent_api.domain import parse_iso_date

        if not plan_raw:
            return []
        start = parse_iso_date(gap_start)
        families: list[str] = []
        for entry in plan_raw.get("entries", []):
            entry_start = parse_iso_date(str(entry.get("start_date", "")))
            if start is None or entry_start is None or entry_start >= start:
                continue
            found = _lookup_entry_species(entry)
            if found is not None and found.get("family"):
                families.append(str(found["family"]))
        return families


    def _agent_rotation_avoid_families(self, bed_id: str) -> list[str]:
        """Cross-year family cooldown from the existing rotation service.

        Reuses ``CropRotationService.get_recommendation`` verbatim — the 3-year
        same-family rule is its job and is already Qt-free. With no recorded
        history it reports UNKNOWN and no families to avoid, which correctly
        constrains nothing.
        """
        host = self._host
        from open_garden_planner.models.crop_rotation import CropRotationHistory, PlantingRecord
        from open_garden_planner.services.crop_rotation_service import CropRotationService

        # One malformed record must not silently disable the cooldown for
        # EVERY bed, which a comprehension plus a broad catch did: a record
        # missing `year` raised and returned [] for the whole garden.
        records: list[PlantingRecord] = [
            rec
            for rec in (
                _read_crop_rotation_record(raw)
                for raw in host._project_manager.crop_rotation.get("records", [])
            )
            if rec is not None
        ]
        service = CropRotationService(CropRotationHistory(records=records))
        return list(service.get_recommendation(bed_id).avoid_families)


    def _agent_concurrent_species_keys(
        self, plan_raw: dict[str, Any] | None, gap_start: str, gap_end: str
    ) -> list[str]:
        """Species planted in the plan OVERLAPPING a gap — the antagonism peers."""
        from open_garden_planner.agent_api.domain import parse_iso_date

        if not plan_raw:
            return []
        start = parse_iso_date(gap_start)
        end = parse_iso_date(gap_end)
        if start is None or end is None:
            return []
        keys: list[str] = []
        for entry in plan_raw.get("entries", []):
            entry_start = parse_iso_date(str(entry.get("start_date", "")))
            entry_end = parse_iso_date(str(entry.get("end_date", "")))
            if entry_start is None or entry_end is None:
                continue
            if entry_start <= end and entry_end >= start:
                keys.extend(_entry_species_names(entry))
        return keys


    def _agent_set_succession_plan(
        self,
        bed_id: str,
        entries: list[dict[str, Any]] | None,
        year: int | None = None,
    ) -> dict[str, Any]:
        """Write a bed's succession plan (US-D3.2, token-gated write)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_set_succession_plan(bed_id, entries, year)
        )


    def _do_agent_set_succession_plan(
        self,
        bed_id: str,
        entries: list[dict[str, Any]] | None,
        year: int | None,
    ) -> dict[str, Any]:
        """Main-thread body of the token-gated ``set_succession_plan`` tool.

        Validation happens BEFORE the command is built, so a refused call never
        touches ``ProjectManager.succession_plans`` and never pushes onto the
        undo stack — the refusal path is asserted, not assumed.

        Mirrors ``_open_succession_plan_dialog``'s orchestration exactly: one
        ``SetSuccessionPlanCommand`` executed through the shared CommandManager.
        The canvas succession badge is refreshed by the already-wired
        ``succession_plans_changed`` signal chain, not by a duplicated call here.
        """
        host = self._host
        import datetime

        from open_garden_planner.agent_api.domain import (
            SuccessionPlanError,
            build_succession_plan_for_agent,
        )
        from open_garden_planner.agent_api.schema import WriteResult
        from open_garden_planner.core.commands import SetSuccessionPlanCommand

        host._agent_resolve_soil_bed(bed_id)

        resolved_year = year or datetime.date.today().year
        if resolved_year < 1900 or resolved_year > 2200:
            raise ValueError(
                f"year {resolved_year} is out of range; pass a four-digit year."
            )

        known = host._agent_known_species_keys()
        if not known:
            logger.warning(
                "Species roster unavailable; succession writes will accept any "
                "species_key, so the rotation and companion checks cannot run "
                "on them."
            )

        try:
            plan = build_succession_plan_for_agent(
                entries,
                bed_id,
                resolved_year,
                known_species_keys=known or None,
            )
        except SuccessionPlanError as exc:
            raise ValueError(str(exc)) from exc

        cmd = SetSuccessionPlanCommand(host._project_manager, bed_id, plan)
        host.canvas_view.command_manager.execute(cmd)
        return WriteResult(
            action="set_succession_plan",
            undo_description=(
                "Delete succession plan"
                if plan is None
                else f"Set succession plan ({len(plan.entries)} entries)"
            ),
        ).model_dump()


    def _agent_set_frost_alerts(self, alerts: list[Any]) -> None:
        """Keep an application-owned copy of the frost alerts (US-D3.3)."""
        host = self._host
        host._agent_frost_alerts = list(alerts or [])


    def _agent_build_task_state(
        self, today: datetime.date, *, year: int | None = None,
        actionable_only: bool = True,
    ) -> Any:
        """Build the shared ``PlanState`` with an injected reference date.

        One snapshot per tool call, exactly as the Tasks tab builds it, so an
        agent and the user's own task list can never describe different tasks
        from different inputs. ``today`` is threaded through
        ``build_plan_state`` rather than read here, which is what makes the
        whole answer reproducible.
        """
        host = self._host
        from open_garden_planner.services.task_generator import build_plan_state

        return build_plan_state(
            host.canvas_scene,
            host._project_manager,
            getattr(host, "_agent_frost_alerts", None) or None,
            host._soil_service,
            today=today,
            year=year,
            actionable_only=actionable_only,
            include_propagation=True,
        )


    def _agent_reference_date(self, today: str | None) -> datetime.date:
        """Parse the tool's injected reference date, defaulting to the wall clock."""
        import datetime

        return _parse_agent_date(today, datetime.date.today(), "today")


    def _agent_get_tasks(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
        source: str | None = None,
        bed_id: str | None = None,
        species_key: str | None = None,
        include_dismissed: bool = False,
        today: str | None = None,
    ) -> dict[str, Any]:
        """Read the task calendar (US-D3.3, read-only)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_get_tasks(
                from_date, to_date, source, bed_id, species_key, include_dismissed, today
            )
        )


    def _do_agent_get_tasks(
        self,
        from_date: str | None,
        to_date: str | None,
        source: str | None,
        bed_id: str | None,
        species_key: str | None,
        include_dismissed: bool,
        today: str | None,
    ) -> dict[str, Any]:
        """Main-thread body of the read-only ``get_tasks`` tool."""
        host = self._host
        import datetime

        from open_garden_planner.agent_api.domain import (
            TASK_SOURCES,
            get_tasks_for_agent,
        )
        from open_garden_planner.services.task_generator import generate_for_date_window

        if source is not None and source not in TASK_SOURCES:
            raise ValueError(
                f"source={source!r} is not a task source. Use one of: "
                f"{', '.join(TASK_SOURCES)}."
            )
        if bed_id is not None:
            host._agent_resolve_soil_bed(bed_id)

        reference = host._agent_reference_date(today)
        start = (
            _parse_agent_date(from_date, reference - datetime.timedelta(days=30), "from_date")
            if from_date
            else None
        )
        end = (
            _parse_agent_date(to_date, reference + datetime.timedelta(days=30), "to_date")
            if to_date
            else None
        )

        state = host._agent_build_task_state(
            reference, actionable_only=from_date is None and to_date is None,
        )
        view = get_tasks_for_agent(
            generate_for_date_window(
                state,
                start or reference - datetime.timedelta(days=30),
                end or reference + datetime.timedelta(days=30),
            ),
            today=reference,
            task_states=host._project_manager.task_states,
            from_date=start,
            to_date=end,
            source=source,
            bed_id=bed_id,
            species_key=species_key,
            include_dismissed=include_dismissed,
            has_frost_dates=state.last_frost is not None,
        )
        return view.model_dump()


    def _agent_get_task_calendar(
        self,
        year: int | None = None,
        today: str | None = None,
    ) -> dict[str, Any]:
        """Read the month-bucketed task overview (US-D3.3, read-only)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_get_task_calendar(year, today)
        )


    def _do_agent_get_task_calendar(
        self,
        year: int | None,
        today: str | None,
    ) -> dict[str, Any]:
        """Main-thread body of the read-only ``get_task_calendar`` tool."""
        host = self._host
        import datetime

        from open_garden_planner.agent_api.domain import get_task_calendar_for_agent
        from open_garden_planner.services.task_generator import generate_for_date_window

        reference = host._agent_reference_date(today)
        if year is not None and (year < 1900 or year > 2200):
            raise ValueError(f"year {year} is out of range; pass a four-digit year.")
        state = host._agent_build_task_state(reference, year=year, actionable_only=False)
        view = get_task_calendar_for_agent(
            generate_for_date_window(
                state, datetime.date(state.year, 1, 1), datetime.date(state.year, 12, 31),
            ),
            today=reference,
            year=year,
            task_states=host._project_manager.task_states,
            has_frost_dates=state.last_frost is not None,
        )
        return view.model_dump()


    def _agent_add_manual_task(
        self,
        title: str,
        date: str | None = None,
        notes: str | None = None,
        bed_id: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """File or edit one manual task (US-D3.3, token-gated write)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_manual_task(
                title, date, notes, bed_id, task_id, adding=task_id is None
            )
        )


    def _agent_edit_manual_task(
        self,
        title: str,
        date: str | None = None,
        notes: str | None = None,
        bed_id: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Edit one manual task (US-D3.3, token-gated write).

        Shares one body with ``add_manual_task``: the only difference is which
        command runs, and a separate body would be a second validation path.
        """
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_manual_task(
                title, date, notes, bed_id, task_id, adding=False
            )
        )


    def _do_agent_manual_task(
        self,
        title: str,
        date: str | None,
        notes: str | None,
        bed_id: str | None,
        task_id: str | None,
        *,
        adding: bool,
    ) -> dict[str, Any]:
        """Main-thread body of ``add_manual_task`` / ``edit_manual_task``.

        Validation happens BEFORE the command is built, so a refused call never
        touches ``ProjectManager.manual_tasks`` and never pushes onto the undo
        stack. One command either way, so one call is exactly one undo step.
        """
        host = self._host
        import datetime

        from open_garden_planner.agent_api.schema import ManualTaskResult
        from open_garden_planner.core.commands import (
            AddManualTaskCommand,
            EditManualTaskCommand,
        )
        from open_garden_planner.models.task import ManualTask

        clean_title = (title or "").strip()
        if not clean_title:
            raise ValueError("title is required and must not be empty.")

        resolved_date = ""
        if date:
            resolved_date = _parse_agent_date(
                date, datetime.date.today(), "date"
            ).isoformat()

        if bed_id is not None:
            host._agent_resolve_soil_bed(bed_id)

        if not adding:
            if not task_id:
                raise ValueError("task_id is required to edit a task.")
            if task_id not in host._project_manager.manual_tasks:
                host._agent_refuse_generated_task(task_id)

        task = ManualTask(
            date=resolved_date,
            title=clean_title,
            notes=notes or "",
            bed_id=bed_id,
        )
        if task_id:
            task.id = task_id

        cmd = (
            AddManualTaskCommand(host._project_manager, task)
            if adding
            else EditManualTaskCommand(host._project_manager, task)
        )
        host.canvas_view.command_manager.execute(cmd)
        host.tasks_view.schedule_refresh()
        return ManualTaskResult(
            task_id=task.id,
            title=task.title,
            date=task.date,
        ).model_dump()


    def _agent_refuse_generated_task(self, task_id: str) -> NoReturn:
        """Refuse a non-manual task id, naming why (US-D3.3).

        Raised when an id is not in ``manual_tasks``. The id is then either a
        generated task — which is derived state, rebuilt from the plan on every
        call, so editing or deleting it would be silently undone by the next
        read — or simply unknown. Both are refusals, and the message says which
        is which rather than pretending to know.
        """
        from open_garden_planner.agent_api.domain import TASK_SOURCES

        raise ValueError(
            f"No manual task has id {task_id!r}. Generated tasks "
            f"({', '.join(s for s in TASK_SOURCES if s != 'manual')}) are "
            "derived from the plan and are rebuilt on every read, so they cannot "
            "be edited or deleted — editing one would be undone by the next "
            "call. Use add_manual_task for new work, and dismiss or complete "
            "this task in the Tasks tab."
        )


    def _agent_delete_manual_task(self, task_id: str) -> dict[str, Any]:
        """Delete one manual task (US-D3.3, token-gated write)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_delete_manual_task(task_id)
        )


    def _do_agent_delete_manual_task(self, task_id: str) -> dict[str, Any]:
        """Main-thread body of the token-gated ``delete_manual_task`` tool."""
        host = self._host
        from open_garden_planner.agent_api.schema import ManualTaskResult
        from open_garden_planner.core.commands import DeleteManualTaskCommand

        # `manual_tasks` stores ManualTask.to_dict() values, not objects.
        existing = host._project_manager.manual_tasks.get(task_id)
        if existing is None:
            host._agent_refuse_generated_task(task_id)

        host.canvas_view.command_manager.execute(
            DeleteManualTaskCommand(host._project_manager, task_id)
        )
        host.tasks_view.schedule_refresh()
        return ManualTaskResult(
            task_id=task_id,
            title=cast(Any, existing).get("title", ""),
            date=cast(Any, existing).get("date", ""),
            deleted=True,
        ).model_dump()


    @staticmethod
    def _agent_global_target_id() -> str:
        """The plan-wide soil-test target id (the GUI's 'global' default)."""
        from open_garden_planner.services.soil_service import GLOBAL_TARGET_ID

        return GLOBAL_TARGET_ID


    def _agent_soil_target(self, bed_id: str | None) -> tuple[str, str, bool]:
        """Resolve ``bed_id`` to a soil-test target id, its label, and a flag.

        Returns ``(target_id, display_name, is_global)``. ``bed_id=None`` means
        the plan-wide default, the same target the GUI's context menu offers.
        Anything else must be a soil-capable bed: a TRELLIS is a plant parent
        but holds no soil, so it is refused here for soil reads exactly as it is
        for a succession plan.
        """
        host = self._host
        from open_garden_planner.services.soil_service import GLOBAL_TARGET_ID

        if bed_id is None:
            return GLOBAL_TARGET_ID, QCoreApplication.translate("GardenPlannerApp", "Plan-wide default"), True
        item = host._agent_resolve_soil_bed(bed_id)
        name = getattr(item, "name", "") or str(bed_id)
        return bed_id, name, False


    def _agent_get_soil_status(
        self,
        bed_id: str | None = None,
        today: str | None = None,
    ) -> dict[str, Any]:
        """Read one bed's effective soil record (US-D3.4, read-only).

        ``bed_id=None`` covers every soil-capable bed, each labelled with its own
        ``record_source``, so a bed answered by the plan default is never
        mistaken for a bed that was tested.
        """
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_get_soil_status(bed_id, today)
        )


    def _do_agent_get_soil_status(
        self,
        bed_id: str | None,
        today: str | None,
    ) -> dict[str, Any]:
        """Main-thread body of the read-only ``get_soil_status`` tool."""
        host = self._host
        from open_garden_planner.agent_api.domain import _soil_status_from

        reference = host._agent_reference_date(today)
        if bed_id is not None:
            targets = [host._agent_soil_target(bed_id)]
        else:
            targets = [
                host._agent_soil_target(item_id)
                for item_id in host._agent_soil_bed_ids()
            ]

        payload: dict[str, Any] = {"beds": []}
        for target_id, name, _is_global in targets:
            record, source, history = host._agent_effective_soil(target_id)
            view = _soil_status_from(
                bed_id=target_id,
                bed_name=name,
                record=record,
                record_source=source,
                history=history,
                today=reference,
                health_level=SoilService.health_level,
                is_test_overdue=SoilService.is_test_overdue,
            )
            payload["beds"].append(view.model_dump())
        return payload


    def _agent_effective_soil(self, target_id: str) -> tuple[Any, str, Any]:
        """The service's effective record, provenance and matching history."""
        host = self._host
        return host._soil_service.get_effective_record_with_source(target_id)


    def _agent_soil_bed_ids(self) -> list[str]:
        """Every soil-capable bed id in the plan, sorted."""
        host = self._host
        from open_garden_planner.core.object_types import is_bed_type

        ids = [
            str(cast(Any, item).item_id)
            for item in host.canvas_scene.items()
            if is_bed_type(getattr(item, "object_type", None))
        ]
        return sorted(ids)


    def _agent_recommend_amendments(
        self,
        bed_id: str,
        today: str | None = None,
    ) -> dict[str, Any]:
        """Read amendment recommendations for one bed (US-D3.4, read-only)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_recommend_amendments(bed_id, today)
        )


    def _do_agent_recommend_amendments(
        self,
        bed_id: str,
        today: str | None,
    ) -> dict[str, Any]:
        """Main-thread body of the read-only ``recommend_amendments`` tool."""
        host = self._host
        from open_garden_planner.agent_api.domain import (
            recommend_amendments_for_agent,
        )
        from open_garden_planner.app.settings import active_language

        reference = host._agent_reference_date(today)
        target_id, _name, _is_global = host._agent_soil_target(bed_id)
        record, _source, _history = host._agent_effective_soil(target_id)
        recs = SoilService.calculate_amendments(
            record,
            bed_area_m2=(
                host._lookup_bed_area_m2(target_id)
                if target_id != host._agent_global_target_id()
                else 0.0
            ),
        )
        view = recommend_amendments_for_agent(
            bed_id=target_id,
            record=record,
            today=reference,
            recommendations=recs,
            language=active_language(),
        )
        return view.model_dump()


    def _agent_get_soil_mismatches(
        self,
        bed_id: str | None = None,
        today: str | None = None,
    ) -> dict[str, Any]:
        """Read plant/soil disagreements (US-D3.4, read-only)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_get_soil_mismatches(bed_id, today)
        )


    def _do_agent_get_soil_mismatches(
        self,
        bed_id: str | None,
        today: str | None,
    ) -> dict[str, Any]:
        """Main-thread body of the read-only ``get_soil_mismatches`` tool.

        Builds the per-bed species lists the same way the canvas overlay does
        (``child.metadata['plant_species']`` -> ``PlantSpeciesData.from_dict``),
        so the agent's disagreements and the user's red/amber borders come from
        one set of records rather than two lookups that can drift.
        """
        host = self._host
        from open_garden_planner.agent_api.domain import (
            get_soil_mismatches_for_agent,
        )
        from open_garden_planner.models.plant_data import PlantSpeciesData

        reference = host._agent_reference_date(today)
        wanted: set[str] | None = None
        if bed_id is not None:
            wanted = {host._agent_soil_target(bed_id)[0]}
        else:
            wanted = set(host._agent_soil_bed_ids())

        all_items = list(host.canvas_scene.items())
        by_bed: dict[str, Any] = {}
        for item in all_items:
            target_id = str(getattr(item, "item_id", ""))
            if target_id not in wanted:
                continue
            record, _source, _history = host._agent_effective_soil(target_id)
            if record is None:
                by_bed[target_id] = get_soil_mismatches_for_agent(
                    bed_id=target_id,
                    today=reference,
                    details=[],
                    coverage="no_soil_test",
                ).model_dump()
                continue
            child_ids = {str(c) for c in getattr(item, "_child_item_ids", []) or []}
            specs: list[Any] = []
            for child in all_items:
                if str(getattr(child, "item_id", "")) not in child_ids:
                    continue
                ps_dict = (getattr(child, "metadata", None) or {}).get("plant_species")
                if isinstance(ps_dict, dict) and ps_dict:
                    with contextlib.suppress(Exception):
                        specs.append(PlantSpeciesData.from_dict(ps_dict))
            by_bed[target_id] = get_soil_mismatches_for_agent(
                bed_id=target_id,
                today=reference,
                details=SoilService.get_mismatch_details(record, specs),
            ).model_dump()

        tested = sum(b["coverage"] == "ok" for b in by_bed.values())
        coverage = (
            "no_beds" if not by_bed else
            "no_soil_test" if not tested else
            "ok" if tested == len(by_bed) else "partial_soil_tests"
        )
        return {
            "coverage": coverage,
            "today": reference.isoformat(),
            "beds": dict(sorted(by_bed.items())),
        }


    def _agent_record_soil_test(
        self,
        bed_id: str | None = None,
        ph: float | None = None,
        n_level: int | None = None,
        p_level: int | None = None,
        k_level: int | None = None,
        ca_level: int | None = None,
        mg_level: int | None = None,
        s_level: int | None = None,
        soil_texture: str | None = None,
        test_date: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Record a soil test on the Rapitest kit scale (US-D3.4, token-gated write)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_record_soil_test(
                bed_id, ph, n_level, p_level, k_level, ca_level, mg_level,
                s_level, soil_texture, test_date, notes,
            )
        )


    def _do_agent_record_soil_test(
        self,
        bed_id: str | None,
        ph: float | None,
        n_level: int | None,
        p_level: int | None,
        k_level: int | None,
        ca_level: int | None,
        mg_level: int | None,
        s_level: int | None,
        soil_texture: str | None,
        test_date: str | None,
        notes: str | None,
    ) -> dict[str, Any]:
        """Main-thread body of the token-gated ``record_soil_test`` tool.

        Validation runs BEFORE the command is built, so a refused call leaves
        ``ProjectManager.soil_tests`` and the undo stack untouched — asserted in
        the tests, not assumed.

        Mirrors the GUI's soil-test orchestration: one ``AddSoilTestCommand``
        through the shared CommandManager, then the same three refreshes the
        dialog path performs, so the canvas mismatch borders, the seasonal
        badges and the dashboard all agree with the new reading.
        """
        host = self._host
        import datetime

        from open_garden_planner.agent_api.domain import (
            SoilTestError,
            build_soil_record_for_agent,
        )
        from open_garden_planner.agent_api.schema import WriteResult
        from open_garden_planner.core.commands import AddSoilTestCommand

        target_id, _name, _is_global = host._agent_soil_target(bed_id)
        try:
            record = build_soil_record_for_agent(
                ph=ph,
                n_level=n_level,
                p_level=p_level,
                k_level=k_level,
                ca_level=ca_level,
                mg_level=mg_level,
                s_level=s_level,
                soil_texture=soil_texture,
                test_date=test_date,
                notes=notes,
                today=datetime.date.today(),
            )
        except SoilTestError as exc:
            raise ValueError(str(exc)) from exc

        host.canvas_view.command_manager.execute(
            AddSoilTestCommand(host._project_manager, target_id, record)
        )
        host.canvas_view.refresh_soil_mismatches()
        host.canvas_view.refresh_soil_badges()
        host.calendar_view.refresh()
        host.tasks_view.schedule_refresh()
        return WriteResult(
            action="record_soil_test",
            undo_description=QCoreApplication.translate("GardenPlannerApp", "Remove soil test"),
        ).model_dump()


    def _agent_get_plant_lists(self) -> list[dict[str, Any]]:
        """Get plant lists and favorites catalog ON the Qt main thread (US-G4)."""
        host = self._host
        return host._agent_bridge.run_on_main(host._do_agent_get_plant_lists)


    def _do_agent_get_plant_lists(self) -> list[dict[str, Any]]:
        from open_garden_planner.models.plant_lists import get_plant_list_store

        store = get_plant_list_store()
        result: list[dict[str, Any]] = []
        for pl in store.all_lists():
            result.append(
                {
                    "id": pl.id,
                    "name": pl.name,
                    "description": pl.description,
                    "entries": [
                        {
                            "id": entry.id,
                            "species_key": entry.species_key,
                            "common_name": entry.species.common_name
                            if entry.species
                            else "",
                            "scientific_name": entry.species.scientific_name
                            if entry.species
                            else "",
                            "note": entry.note,
                            "added_at": entry.added_at,
                        }
                        for entry in pl.entries
                    ],
                }
            )
        return result


    def _agent_known_species_keys(self) -> set[str]:
        """Every canonical species key this plan accepts: bundled DB + placed plants.

        The write validator needs KEYS, so this derives them directly with the
        canonical ``species_key()`` (ADR-016) instead of collecting names and
        re-resolving them.

        That distinction is the whole point for placed plants. A Permapeople or
        custom species has a ``source_id`` that is its canonical key, and its
        name resolves to NOTHING in the bundled DB - so an earlier version that
        pushed placed-plant names back through ``lookup_species`` got None for
        every one of them. The roster then missed them and ``set_succession_plan``
        refused a species the app had just shown the agent, while the sibling
        tool ``set_species`` accepted it. Three agents disagreeing about the same
        plant is worse than any one of them being wrong.
        """
        host = self._host
        from open_garden_planner.models.plant_data import species_key
        from open_garden_planner.services.bundled_species_db import get_species_db

        keys: set[str] = set()

        def _add(record: object) -> None:
            if not isinstance(record, dict):
                return
            key = species_key(record)
            if key and key != "_unknown":
                keys.add(key)

        try:
            for record in get_species_db().values():
                _add(record)
        except Exception:
            # that fails a write; without the bundled roster the species check is
            # skipped rather than turned into a blanket refusal. The placed-plant
            # pass below still runs.
            logger.warning("Could not enumerate bundled species for validation")

        try:
            for item in host.canvas_scene.items():
                meta = getattr(item, "metadata", None)
                species = (meta or {}).get("plant_species")
                _add(species)
        except Exception:
            logger.warning("Could not enumerate placed plants for validation")

        return keys


    def _agent_linked_roof_ridge(self, item: Any) -> list[Any]:
        """A HOUSE's linked ``ROOF_RIDGE`` item, if any — mirroring
        ``CanvasView._delete_selected_items``'s ``ridge_item_id`` expansion so
        deleting a house doesn't orphan its ridge polyline."""
        host = self._host
        from uuid import UUID

        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        if not isinstance(item, GardenItemMixin) or item.object_type != ObjectType.HOUSE:
            return []
        ridge_id_str = item.metadata.get("ridge_item_id")
        if not ridge_id_str:
            return []
        try:
            ridge = host.canvas_scene.find_item_by_id(UUID(ridge_id_str))
        except ValueError:
            return []
        return [ridge] if ridge is not None else []


    def _agent_require_unconstrained(
        self,
        item: Any,
        item_id: str,
        tool_name: str,
    ) -> None:
        """Refuse a geometry edit on a constrained object — the final D2.6 rule.

        ``CanvasView`` runs a live, iterative solver that may move several
        connected items. US-D2.6 deliberately does not expose that multi-item
        mutation to one-shot agent calls: silently skipping it would violate the
        user's design intent. The agent can call ``get_geometry`` to see the
        exact constraints, then ask the user to remove or edit them in the app.

        This one helper is the perimeter for every geometry-changing tool:
        move/set-position, resize/rotate, species assignment when it resizes,
        and vertex writes.
        """
        host = self._host
        constraints = sorted(
            host._agent_item_constraints(item),
            key=lambda constraint: (
                constraint.constraint_type.name,
                str(constraint.constraint_id),
            ),
        )
        if not constraints:
            return
        first = constraints[0]
        extra = f" (+{len(constraints) - 1} more)" if len(constraints) > 1 else ""
        subject = str(item_id)
        raise ValueError(
            f"{subject} participates in geometric constraint "
            f"{first.constraint_type.name}/{first.constraint_id}{extra}; "
            f"{tool_name} does not support constrained objects. Call get_geometry "
            "to inspect the constraints, then remove them or edit the object in "
            "the app."
        )


    def _agent_resize_object(
        self,
        item_id: str,
        width: float | None,
        height: float | None,
        radius: float | None,
    ) -> dict[str, Any]:
        """Resize one object ON the Qt main thread (for the server)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_resize_object(item_id, width, height, radius)
        )


    def _do_agent_resize_object(
        self,
        item_id: str,
        width: float | None,
        height: float | None,
        radius: float | None,
    ) -> dict[str, Any]:
        """Main-thread body of ``resize_object`` — one undoable step (US-D2.2).

        Goes through ``ui.canvas.geometry_apply``, the canonical apply path the
        properties panel's numeric-entry branches and each item's drag-release
        handler now share. That extraction is the load-bearing half of this
        story: before it, every caller carried its own ``apply_func`` closure
        and the copies had already drifted (the panel's never re-pinned
        ``transformOriginPoint``, so a rotated item jumped — see section 11.4).
        A third copy for the agent would have been a third chance to drift.

        Anchor policy: **the object's scene centre is preserved**, for every
        type. ``create_object`` and every read tool speak in centres, so it is
        the only rule an agent can reason about without knowing an item's
        internal anchor — and it is achieved by passing ``keep_center=True`` to
        the shared builder, not by a second code path.

        Refuses (raises) rather than guessing: a vertex-backed object
        (polygon/polyline — US-D2.6's vertex tools own those), a dimension that
        doesn't fit the shape, a missing dimension, a non-finite/non-positive
        or implausible extent, and — like every D2 geometry tool — a
        constrained object. ``_resolve_agent_item`` supplies the shared
        group-member / journal-pin / locked-layer refusals.
        """
        host = self._host
        from open_garden_planner.agent_api import edits
        from open_garden_planner.core.commands import ResizeItemCommand
        from open_garden_planner.ui.canvas.geometry_apply import (
            apply_rect_like_geometry,
            build_circle_resize,
            build_rect_resize,
            is_resizable_rect_like,
            is_round_like,
        )

        item = host._resolve_agent_item(item_id)
        type_name = host._agent_object_type_name(item)
        host._agent_require_unconstrained(item, item_id, "resize_object")

        if not is_resizable_rect_like(item):
            # A polygon/polyline has a different geometry model; a text label or
            # group has no width/height box at all. Name the applicable path
            # without implying a tool exists for every non-rect-backed item.
            raise ValueError(
                f"{item_id} is a {type_name}, which has no width/height box, so "
                "resize_object cannot resize it. Polygons and polylines are "
                "vertex-backed — use get_geometry and set_vertex; a group is "
                "resized by addressing its members individually."
            )

        # Same predicate the builders use internally — see is_round_like.
        is_round = is_round_like(item)
        current_rect = item.rect()
        canvas_rect = host.canvas_scene.canvas_rect
        new_width, new_height = edits.validate_resize_request(
            object_type=type_name,
            is_round=is_round,
            current_width=current_rect.width(),
            current_height=current_rect.height(),
            canvas_width_cm=canvas_rect.width(),
            canvas_height_cm=canvas_rect.height(),
            width=width,
            height=height,
            radius=radius,
        )

        if is_round:
            old_geometry, new_geometry = build_circle_resize(
                item, new_width, keep_center=True
            )
        else:
            old_geometry, new_geometry = build_rect_resize(
                item, new_width, new_height, keep_center=True
            )

        cmd = ResizeItemCommand(
            item, old_geometry, new_geometry, apply_rect_like_geometry
        )
        host.canvas_view.command_manager.execute(cmd)

        cx, cy = host._agent_item_center(item)
        return {
            "item_id": item_id,
            "action": "resize",
            "undo_description": cmd.description,
            "x": cx,
            "y": cy,
            "width": None if is_round else new_width,
            "height": None if is_round else new_height,
            "radius": (new_width / 2.0) if is_round else None,
        }


    def _agent_rotate_object(
        self, item_id: str, angle: float, relative: bool
    ) -> dict[str, Any]:
        """Rotate one object ON the Qt main thread (for the server)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_rotate_object(item_id, angle, relative)
        )


    def _do_agent_rotate_object(
        self, item_id: str, angle: float, relative: bool
    ) -> dict[str, Any]:
        """Main-thread body of ``rotate_object`` — one undoable step (US-D2.2).

        Uses ``geometry_apply.apply_rotation``, which is exactly what every
        per-item drag-release closure already did: call the item's own
        ``_apply_rotation``. That matters for ``PolygonItem``, which overrides
        it to keep an attached roof ridge on the boundary — reimplementing the
        rotation here would have silently dropped that.

        **Sign convention, measured rather than assumed** (issue #267 is the
        cautionary tale — a plausible-sounding docstring that sent agents the
        wrong way): a positive angle rotates the object COUNTER-CLOCKWISE. An
        object whose long axis points east points north after ``+90``.
        ``tests/unit/test_agent_api_edits.py`` pins this against a real item's
        corner positions, so the test fails if the convention ever inverts.

        Refuses a non-finite or implausibly large angle, and — like every D2
        geometry tool — a constrained object.
        """
        host = self._host
        from open_garden_planner.agent_api import edits
        from open_garden_planner.core.commands import RotateItemCommand
        from open_garden_planner.ui.canvas.geometry_apply import apply_rotation

        item = host._resolve_agent_item(item_id)
        host._agent_require_unconstrained(item, item_id, "rotate_object")

        current_angle = float(getattr(item, "rotation_angle", 0.0))
        if not hasattr(item, "_apply_rotation"):
            raise ValueError(
                f"{item_id} is a "
                f"{self._agent_object_type_name(item)}, which cannot be "
                "rotated."
            )
        new_angle = edits.validate_rotation(
            angle, relative=relative, current_angle=current_angle
        )

        cmd = RotateItemCommand(item, current_angle, new_angle, apply_rotation)
        host.canvas_view.command_manager.execute(cmd)

        cx, cy = host._agent_item_center(item)
        return {
            "item_id": item_id,
            "action": "rotate",
            "undo_description": cmd.description,
            "x": cx,
            "y": cy,
            "rotation_deg": new_angle,
        }


    def _agent_resolve_vertex_item(self, item_id: str, tool_name: str) -> Any:
        """Resolve a writable vertex-backed item and clear the D2 geometry gate."""
        host = self._host
        from open_garden_planner.ui.canvas.geometry_apply import is_vertex_editable

        item = host._resolve_agent_item(item_id)
        host._agent_require_unique_items([item], action=tool_name)
        host._agent_require_unconstrained(item, item_id, tool_name)
        if not is_vertex_editable(item):
            raise ValueError(
                f"{item_id} is a {self._agent_object_type_name(item)}, which is not "
                "a vertex-backed shape. set_vertex/add_vertex/delete_vertex only "
                "edit polygon and polyline items; use resize_object for "
                "rect-backed shapes."
            )
        return item


    def _agent_validate_vertex_point(
        self, x: float, y: float
    ) -> tuple[float, float]:
        host = self._host
        from open_garden_planner.agent_api import edits

        canvas = host.canvas_scene.canvas_rect
        return edits.validate_scene_point(
            x,
            y,
            canvas_width_cm=canvas.width(),
            canvas_height_cm=canvas.height(),
        )


    def _agent_set_vertex(
        self, item_id: str, index: int, x: float, y: float
    ) -> dict[str, Any]:
        """Move one polygon/polyline vertex ON the Qt main thread."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_set_vertex(item_id, index, x, y)
        )


    def _do_agent_set_vertex(
        self, item_id: str, index: int, x: float, y: float
    ) -> dict[str, Any]:
        host = self._host
        from PyQt6.QtCore import QPointF

        from open_garden_planner.agent_api import edits
        from open_garden_planner.ui.canvas.geometry_apply import (
            build_move_vertex_command,
            local_vertex_for_scene,
        )

        item = host._agent_resolve_vertex_item(item_id, "set_vertex")
        count = int(item._get_vertex_count())
        edits.validate_vertex_index(index, vertex_count=count, operation="set")
        target_x, target_y = host._agent_validate_vertex_point(x, y)
        old_local = QPointF(item._get_vertex_position(index))
        new_local = local_vertex_for_scene(item, index, target_x, target_y)
        if new_local == old_local:
            raise ValueError(
                f"vertex {index} of {item_id} is already at "
                f"({target_x:g}, {target_y:g}); nothing to change."
            )
        command = build_move_vertex_command(item, index, old_local, new_local)
        host.canvas_view.command_manager.execute(command)
        actual = item.mapToScene(item._get_vertex_position(index))
        return host._agent_vertex_result(
            item,
            item_id,
            action="set_vertex",
            command=command,
            index=index,
            actual=actual,
        )


    def _agent_add_vertex(
        self, item_id: str, index: int, x: float, y: float
    ) -> dict[str, Any]:
        """Insert one polygon/polyline vertex ON the Qt main thread."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_add_vertex(item_id, index, x, y)
        )


    def _do_agent_add_vertex(
        self, item_id: str, index: int, x: float, y: float
    ) -> dict[str, Any]:
        host = self._host
        from PyQt6.QtCore import QPointF

        from open_garden_planner.agent_api import edits
        from open_garden_planner.ui.canvas.geometry_apply import (
            build_add_vertex_command,
        )

        item = host._agent_resolve_vertex_item(item_id, "add_vertex")
        count = int(item._get_vertex_count())
        edits.validate_vertex_index(index, vertex_count=count, operation="add")
        target_x, target_y = host._agent_validate_vertex_point(x, y)
        local = item.mapFromScene(QPointF(target_x, target_y))
        command = build_add_vertex_command(item, index, local)
        host.canvas_view.command_manager.execute(command)
        actual = item.mapToScene(item._get_vertex_position(index))
        return host._agent_vertex_result(
            item,
            item_id,
            action="add_vertex",
            command=command,
            index=index,
            actual=actual,
        )


    def _agent_delete_vertex(self, item_id: str, index: int) -> dict[str, Any]:
        """Delete one polygon/polyline vertex ON the Qt main thread."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_delete_vertex(item_id, index)
        )


    def _do_agent_delete_vertex(self, item_id: str, index: int) -> dict[str, Any]:
        host = self._host
        from open_garden_planner.agent_api import edits
        from open_garden_planner.ui.canvas.geometry_apply import (
            build_delete_vertex_command,
        )

        item = host._agent_resolve_vertex_item(item_id, "delete_vertex")
        count = int(item._get_vertex_count())
        edits.validate_vertex_index(
            index,
            vertex_count=count,
            operation="delete",
            minimum_count=int(item._get_minimum_vertex_count()),
        )
        deleted = item.mapToScene(item._get_vertex_position(index))
        command = build_delete_vertex_command(item, index)
        host.canvas_view.command_manager.execute(command)
        return host._agent_vertex_result(
            item,
            item_id,
            action="delete_vertex",
            command=command,
            index=index,
            actual=deleted,
        )


    def _agent_vertex_result(
        self,
        item: Any,
        item_id: str,
        *,
        action: str,
        command: Any,
        index: int,
        actual: Any,
    ) -> dict[str, Any]:
        host = self._host
        cx, cy = host._agent_item_center(item)
        return {
            "item_id": item_id,
            "action": action,
            "undo_description": command.description,
            "x": cx,
            "y": cy,
            "vertex_index": index,
            "vertex_x_cm": float(actual.x()),
            "vertex_y_cm": float(actual.y()),
            "vertex_count": int(item._get_vertex_count()),
        }


    def _agent_set_species(
        self, item_id: str, species: str | None, apply_database_size: bool
    ) -> dict[str, Any]:
        """Assign a plant's species ON the Qt main thread (for the server)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_set_species(item_id, species, apply_database_size)
        )


    def _do_agent_set_species(
        self, item_id: str, species: str | None, apply_database_size: bool
    ) -> dict[str, Any]:
        """Main-thread body of ``set_species`` — one undoable step (US-D2.3).

        Delegates to ``ui.plant_species_assignment.apply_species_to_item``, the
        helper issue #213 already extracted so the plant-database panel and the
        Plants-menu species search behave identically. The agent is simply a
        third caller of it — building an ``ApplySpeciesCommand`` here would
        have been a fourth definition of "assign a species".

        That helper resizes the drawn footprint so its diameter equals the
        species' ``max_spread_cm``, silently, unless a manual
        ``spacing_radius_cm`` override disagrees — in which case the GUI shows
        a two-button dialog. ``apply_database_size`` is the agent's answer to
        that dialog: ``True`` applies the database values (clearing the
        override), ``False`` keeps the user's custom ones. **It is not a
        general "don't resize" switch** — without a conflicting override the
        footprint always adopts the database size, exactly as it does in the
        app.

        Deliberate asymmetry with ``create_object`` (recorded in ADR-036's
        D2.3 addendum): creation sizes a new plant from the gallery defaults,
        because ``radius`` is an explicit creation parameter and having a
        species silently overrule it would make the two arguments fight. An
        agent that wants a database-sized new plant calls ``create_object``
        and then ``set_species`` — two documented steps, not a gap.

        Clearing (``species=None``) goes through the same command with
        ``new_species=None`` and leaves the footprint alone: there is no
        database size to adopt, and shrinking a plant the user drew because
        its label was removed would be surprising.
        """
        host = self._host
        from open_garden_planner.core.commands import ApplySpeciesCommand
        from open_garden_planner.services.bundled_species_db import (
            lookup_species,
            merge_calendar_data,
        )
        from open_garden_planner.ui.plant_species_assignment import apply_species_to_item

        item = host._agent_resolve_plant(item_id, "set_species")
        # Assigning a species RESIZES the footprint (to max_spread_cm), so this
        # is a geometry mutation and must clear the same gate resize_object
        # does. Without this an agent refused by resize_object could get the
        # resize through set_species instead — the perimeter with a door in it
        # that the US-D2.2 senior review found.
        if species is not None:
            host._agent_require_unconstrained(item, item_id, "set_species")

        current = item.metadata.get("plant_species")
        if species is None:
            old_species = current
            if not isinstance(old_species, dict):
                raise ValueError(
                    f"{item_id} has no species to clear; nothing to change."
                )
            cmd = ApplySpeciesCommand(
                item,
                old_species,  # a dict — the guard above raised otherwise
                None,
                getattr(item, "spacing_radius_cm", None),
                getattr(item, "spacing_radius_cm", None),
                None,
                None,
                old_species_name=getattr(item, "plant_species", "") or "",  # the name it had
                new_species_name="",                     # ... and the name it has now
            )
            host.canvas_view.command_manager.execute(cmd)
            host._agent_refresh_soil_mismatches()
            resulting_key = None
            undo_description = cmd.description
        else:
            record = lookup_species(species)
            if record is None:
                raise ValueError(
                    f"No species named {species!r} in the bundled database. "
                    "Read the garden://species resource for the full list "
                    "(scientific names, common names and aliases all match)."
                )
            species_dict = merge_calendar_data(dict(record))
            # Re-assigning the species a plant already has is a no-op that would
            # still push an undo step — the same lie set_parent_bed refuses.
            # Compared on the canonical key, so "Tomato" and its scientific name
            # are recognised as the same request.
            resolved = species_dict.get("scientific_name")
            if (
                isinstance(current, dict)
                and resolved
                and current.get("scientific_name") == resolved
            ):
                raise ValueError(
                    f"{item_id} already has species {resolved!r}; nothing to "
                    "change."
                )
            apply_species_to_item(
                item, species_dict, confirm=lambda: apply_database_size
            )
            resulting_key = species_dict.get("scientific_name") or species
            # The command's label is a constant; name it directly rather than
            # reading the undo stack's top (apply_species_to_item applies
            # without pushing when there is no command manager, and the stack
            # top would then be an unrelated command the agent would be told
            # Ctrl+Z reverses) or constructing a throwaway command to ask it.
            # INVARIANT: this string must equal ApplySpeciesCommand.description;
            # it is the same label the real command would have produced.
            undo_description = QCoreApplication.translate(
                "Commands", "Apply species data"
            )

        cx, cy = host._agent_item_center(item)
        return {
            "item_id": item_id,
            "action": "set_species",
            "undo_description": undo_description,
            "x": cx,
            "y": cy,
            "species_key": resulting_key,
        }


    def _agent_set_parent_bed(self, item_id: str, bed_id: str | None) -> dict[str, Any]:
        """Link/unlink a plant to a bed ON the Qt main thread (for the server)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_set_parent_bed(item_id, bed_id)
        )


    def _do_agent_set_parent_bed(
        self, item_id: str, bed_id: str | None
    ) -> dict[str, Any]:
        """Main-thread body of ``set_parent_bed`` — one undoable step (US-D2.3).

        A **link change only** — the plant does not move. ``move_object`` is
        the implicit path (crossing a boundary reparents); this is the explicit
        one, and it is the only way to reach a state the GUI can reach but no
        agent could: a plant already sitting inside a bed that was drawn around
        it, and therefore never linked.

        **It deliberately does not require the plant to be geometrically inside
        the bed.** The app's own properties-panel Link action does not either,
        and refusing would make the tool useless for exactly the case it exists
        for. ``link_is_geometric`` in the result says whether the link and the
        geometry agree, so an agent can notice and tell the user.

        ``SetParentBedCommand`` handles the rest of the contract itself: it
        removes the child id from the old bed, adds it to the new one, raises
        the plant above its parent, snapshots ``zValue`` so undo restores the
        user's original elevation rather than a recomputed one, and calls
        ``trigger_soil_mismatch_refresh`` because parent-link mutations do not
        fire ``QGraphicsScene.changed`` (#173).
        """
        host = self._host

        from open_garden_planner.agent_api import edits
        from open_garden_planner.core.commands import SetParentBedCommand
        from open_garden_planner.ui.canvas.footprints import centre_is_inside

        plant = host._agent_resolve_plant(item_id, "set_parent_bed")
        old_parent_id = plant.parent_bed_id

        new_parent_id: UUID | None = None
        link_is_geometric: bool | None = None
        if bed_id is not None:
            bed = host._resolve_agent_item(bed_id)
            edits.require_plant_parent_type(
                host._agent_object_type_name(bed), bed_id
            )
            new_parent_id = bed.item_id
            # Containment uses the same construct CanvasView's own reparent test
            # does (boundingRect centre), so the agent's link and the GUI's
            # auto-link agree on the boundary case. Note this is deliberately
            # NOT _agent_item_center's rect-based centre: that one exists so a
            # reported x/y matches the read tools, whereas this one exists to
            # match the GUI's containment decision. The two differ by the
            # antagonist badge's asymmetric overflow (~0.07 * radius).
            #
            # Whether the sun study and the 3D scene LIFT the plant onto the
            # bed's soil (L1.6, footprints.item_base_cm) is the same predicate
            # asked with the plant's stable geometric centre — where a solid
            # stands must not follow a badge. So within that overflow of a
            # bed's edge a link reported as not geometric here can still be
            # lifted there, and the other way round.
            link_is_geometric = centre_is_inside(plant, bed)

        if new_parent_id == old_parent_id:
            where = "already unlinked" if bed_id is None else f"already linked to {bed_id}"
            raise ValueError(f"{item_id} is {where}; nothing to change.")

        cmd = SetParentBedCommand(
            host.canvas_scene, plant, old_parent_id, new_parent_id
        )
        host.canvas_view.command_manager.execute(cmd)

        cx, cy = host._agent_item_center(plant)
        return {
            "item_id": item_id,
            "action": "set_parent_bed",
            "undo_description": cmd.description,
            "x": cx,
            "y": cy,
            "bed_membership_changed": True,
            "new_parent_bed_id": str(new_parent_id) if new_parent_id else None,
            "link_is_geometric": link_is_geometric,
        }


    def _agent_arrange_object(self, item_id: str, action: str) -> dict[str, Any]:
        """Arrange one object within its layer ON the Qt main thread (for the server)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_arrange_object(item_id, action)
        )


    def _do_agent_arrange_object(self, item_id: str, action: str) -> dict[str, Any]:
        """Main-thread body of ``arrange_object`` — one undoable step (#338).

        Routes through ``ui.canvas.arrange.build_arrange_command`` — the ONE
        apply seam every arrange surface shares (Edit menu, context menu,
        Properties panel buttons, and this tool). That seam already carries a
        bed's contained plants along as one block and clamps a plant so it can
        never sit below its own bed; duplicating that logic here instead of
        calling the seam would be exactly the kind of second implementation
        the seam exists to prevent (see ``ui/canvas/arrange.py``'s docstring).

        ``_resolve_agent_item`` supplies the shared group-member / journal-pin
        / locked-layer refusals. On top of those, this refuses (raises)
        whenever the arrange gesture would be a no-op: already at the
        front/back of the layer, or no overlapping object to step past for
        bring_forward/send_backward — mirroring the ``set_parent_bed``
        no-op precedent rather than silently reporting success for nothing.
        """
        host = self._host
        from open_garden_planner.core.stacking import ArrangeMode, ArrangeOutcome
        from open_garden_planner.ui.canvas.arrange import build_arrange_command

        try:
            mode = ArrangeMode(action)
        except ValueError as exc:
            allowed = ", ".join(m.value for m in ArrangeMode)
            raise ValueError(
                f"{action!r} is not a valid arrange action; must be one of "
                f"{allowed}."
            ) from exc

        item = host._resolve_agent_item(item_id)

        cmd, outcome = build_arrange_command(host.canvas_scene, [item], mode)
        if cmd is None:
            messages = {
                ArrangeOutcome.ALREADY_AT_FRONT: (
                    f"{item_id} is already at the front of its layer; "
                    "nothing to change."
                ),
                ArrangeOutcome.ALREADY_AT_BACK: (
                    f"{item_id} is already at the back of its layer; "
                    "nothing to change."
                ),
                ArrangeOutcome.NO_OVERLAP_ABOVE: (
                    f"{item_id} has no overlapping object in front of it in "
                    "its layer; nothing to change."
                ),
                ArrangeOutcome.NO_OVERLAP_BELOW: (
                    f"{item_id} has no overlapping object behind it in its "
                    "layer; nothing to change."
                ),
                ArrangeOutcome.NOTHING_SELECTED: (
                    f"{item_id} is not on an arrangeable layer; nothing to "
                    "change."
                ),
            }
            raise ValueError(messages[outcome])

        host.canvas_view.command_manager.execute(cmd)

        cx, cy = host._agent_item_center(item)
        # Reuse the EXACT same derivation the read tools (get_object/
        # list_objects) use for ObjectRef.stack_index, instead of a second,
        # independent one over the live scene -- the two could otherwise
        # silently drift apart (issue #338 review round 2, P1-3). See
        # agent_api.queries.get_object / _stack_indices.
        from open_garden_planner.agent_api import queries

        snapshot = host._project_manager.snapshot_dict(host.canvas_scene)
        detail = queries.get_object(snapshot, item_id)
        stack_index = cast(Any, detail).stack_index if detail is not None else None
        return {
            "item_id": item_id,
            "action": "arrange",
            "undo_description": cmd.description,
            "x": cx,
            "y": cy,
            "stack_index": stack_index,
        }


    def _agent_resolve_layer(self, layer_id: str) -> Any:
        """Look up a scene layer by UUID string for a write tool, or raise.

        The layer-side counterpart of ``_resolve_agent_item`` — one chokepoint
        so every layer tool refuses a bad/unknown id with the same wording and
        cannot drift on whether it checks at all.
        """
        host = self._host
        from uuid import UUID

        try:
            uuid = UUID(layer_id)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Not a valid layer id: {layer_id!r}") from exc
        layer = host.canvas_scene.get_layer_by_id(uuid)
        if layer is None:
            raise ValueError(
                f"No layer with id {layer_id}. Use list_layers to see the "
                "plan's layer ids."
            )
        return layer


    def _agent_set_object_layer(self, item_id: str, layer_id: str) -> dict[str, Any]:
        """Move one object to another layer ON the Qt main thread (for the server)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_set_object_layer(item_id, layer_id)
        )


    def _do_agent_set_object_layer(self, item_id: str, layer_id: str) -> dict[str, Any]:
        """Main-thread body of ``set_object_layer`` — one ``MoveToLayerCommand``.

        Mirrors the GUI's single-selection "Move to Layer" exactly: only the
        addressed object changes layer — a bed's contained plants keep their
        own layer, just as they would when the user moves the bed alone (the
        GUI's layer move works off ``selectedItems()``; plants are not
        auto-selected with their bed). ``MoveToLayerCommand`` snapshots the
        item's original ``layer_id`` AND ``stack_order``, so undo restores the
        object to its exact previous layer position (issue #338 semantics).

        Refuses, via the shared chokepoints: a group member, a journal pin, or
        an item on a locked layer (``_resolve_agent_item``); an unknown layer,
        a LOCKED target layer (the creation-side lock policy — the GUI clears
        interaction flags on locked layers, so nothing can be placed there),
        or a no-op move onto the layer the object already occupies
        (``set_parent_bed``'s loud-no-op precedent — a pushed no-op command
        would pollute the undo stack with a step that changes nothing).
        """
        host = self._host
        from open_garden_planner.core.commands import MoveToLayerCommand

        item = host._resolve_agent_item(item_id)
        layer = host._agent_resolve_layer(layer_id)
        if layer.locked:
            raise ValueError(
                f"The target layer {layer.name!r} is locked; objects cannot be "
                "moved onto a locked layer. Unlock it first with "
                "set_layer_property(layer_id, locked=False)."
            )
        if getattr(item, "layer_id", None) == layer.id:
            raise ValueError(
                f"{item_id} is already on layer {layer.name!r}; nothing to do."
            )
        cmd = MoveToLayerCommand([item], layer.id, host.canvas_scene, layer.name)
        host.canvas_view.command_manager.execute(cmd)
        cx, cy = host._agent_item_center(item)
        return {
            "item_id": item_id,
            "action": "set_object_layer",
            "undo_description": cmd.description,
            "x": cx,
            "y": cy,
            "layer_id": str(layer.id),
        }


    def _agent_create_layer(self, name: str) -> dict[str, Any]:
        """Create a layer ON the Qt main thread (for the server)."""
        host = self._host
        return host._agent_bridge.run_on_main(lambda: host._do_agent_create_layer(name))


    def _do_agent_create_layer(self, name: str) -> dict[str, Any]:
        """Main-thread body of ``create_layer`` — one ``AddLayerCommand``.

        Same command the Layers panel's add button runs: the new layer is
        inserted at the TOP of the stack and becomes the ACTIVE layer, so a
        subsequent ``create_object`` lands on it — asserted end to end in the
        integration tests, since that interaction is the point of the tool.
        """
        host = self._host
        from open_garden_planner.core.commands import AddLayerCommand
        from open_garden_planner.models.layer import Layer

        clean = host._agent_require_layer_name(name)
        layer = Layer(name=clean)
        cmd = AddLayerCommand(host.canvas_scene, layer)
        host.canvas_view.command_manager.execute(cmd)
        return {
            "item_id": None,
            "action": "create_layer",
            "undo_description": cmd.description,
            "layer_id": str(layer.id),
        }


    def _agent_rename_layer(self, layer_id: str, name: str) -> dict[str, Any]:
        """Rename a layer ON the Qt main thread (for the server)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_rename_layer(layer_id, name)
        )


    def _do_agent_rename_layer(self, layer_id: str, name: str) -> dict[str, Any]:
        """Main-thread body of ``rename_layer`` — one ``RenameLayerCommand``.

        Works on a locked layer too: the lock protects the layer's OBJECTS
        from editing, not the layer's own name — the Layers panel renames a
        locked layer exactly the same way.
        """
        host = self._host
        from open_garden_planner.core.commands import RenameLayerCommand

        layer = host._agent_resolve_layer(layer_id)
        clean = host._agent_require_layer_name(name)
        if layer.name == clean:
            raise ValueError(
                f"Layer {layer.name!r} already has that name; nothing to do."
            )
        cmd = RenameLayerCommand(host.canvas_scene, layer, clean)
        host.canvas_view.command_manager.execute(cmd)
        return {
            "item_id": None,
            "action": "rename_layer",
            "undo_description": cmd.description,
            "layer_id": str(layer.id),
        }


    def _agent_delete_layer(self, layer_id: str) -> dict[str, Any]:
        """Delete a layer ON the Qt main thread (for the server)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_delete_layer(layer_id)
        )


    def _do_agent_delete_layer(self, layer_id: str) -> dict[str, Any]:
        """Main-thread body of ``delete_layer`` — one ``DeleteLayerCommand``.

        Deleting a layer NEVER deletes its objects: ``DeleteLayerCommand``'s
        existing policy (which this tool follows exactly, rather than inventing
        a second one) moves them to a sibling replacement layer, and the whole
        thing — layer removal plus every object reassignment — is ONE undo
        step. ``objects_moved`` reports how many were reassigned.

        Refuses a locked layer (ADR-036 D2.4: the lock is the user's "agent,
        keep out" signal; deleting the layer out from under that protection
        would defeat it — an agent-side hardening the ADR records) and refuses
        to delete the plan's only layer (the command itself requires a
        replacement to exist).
        """
        host = self._host
        from open_garden_planner.core.commands import DeleteLayerCommand

        layer = host._agent_resolve_layer(layer_id)
        if layer.locked:
            raise ValueError(
                f"The layer {layer.name!r} is locked, so it cannot be deleted. "
                "Unlock it first with set_layer_property(layer_id, "
                "locked=False) and then delete it."
            )
        if len(host.canvas_scene.layers) <= 1:
            raise ValueError(
                f"Cannot delete {layer.name!r}: it is the plan's only layer. "
                "A plan always keeps at least one layer."
            )
        objects_moved = sum(
            1
            for item in host.canvas_scene.items()
            if getattr(item, "layer_id", None) == layer.id
        )
        cmd = DeleteLayerCommand(host.canvas_scene, layer.id)
        host.canvas_view.command_manager.execute(cmd)
        return {
            "item_id": None,
            "action": "delete_layer",
            "undo_description": cmd.description,
            "layer_id": str(layer.id),
            "objects_moved": objects_moved,
        }


    def _agent_set_active_layer(self, layer_id: str) -> dict[str, Any]:
        """Switch the active layer ON the Qt main thread (for the server)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_set_active_layer(layer_id)
        )


    def _do_agent_set_active_layer(self, layer_id: str) -> dict[str, Any]:
        """Main-thread body of ``set_active_layer``.

        Deliberately NOT a command: the active layer is session state — it is
        never persisted to ``.ogp`` and never marks the document dirty, and
        the GUI switches it the same way (the Layers panel's row click calls
        ``CanvasScene.set_active_layer`` directly, application.py's
        ``_on_active_layer_changed``). Wrapping it in a command would push an
        undo step that changes no document state. The result says so plainly
        instead of pretending there is something to Ctrl+Z.

        Works on a locked layer: activating changes where NEW objects would
        land, and creating onto a locked layer is refused separately
        (``_agent_creation_target_layer``) — the lock stays load-bearing.
        """
        host = self._host
        layer = host._agent_resolve_layer(layer_id)
        active = host.canvas_scene.active_layer
        if active is not None and active.id == layer.id:
            raise ValueError(
                f"Layer {layer.name!r} is already the active layer; nothing "
                "to do."
            )
        host.canvas_scene.set_active_layer(layer)
        return {
            "item_id": None,
            "action": "set_active_layer",
            # Not a command description: there is no undo step for session
            # state. Agent-facing text is an English API contract (no tr()).
            "undo_description": (
                f"Set active layer '{layer.name}' (session state — not an "
                "undo step; the active layer is not part of the document)"
            ),
            "layer_id": str(layer.id),
        }


    def _agent_set_layer_property(
        self,
        layer_id: str,
        visible: bool | None,
        opacity: float | None,
        locked: bool | None,
    ) -> dict[str, Any]:
        """Set a layer property ON the Qt main thread (for the server)."""
        host = self._host
        return host._agent_bridge.run_on_main(
            lambda: host._do_agent_set_layer_property(
                layer_id=layer_id, visible=visible, opacity=opacity, locked=locked
            )
        )


    def _do_agent_set_layer_property(
        self,
        layer_id: str,
        visible: bool | None = None,
        opacity: float | None = None,
        locked: bool | None = None,
    ) -> dict[str, Any]:
        """Main-thread body of ``set_layer_property`` — one command, one property.

        ``locked`` IS changeable in both directions (issue #365, a deliberate
        policy reversal of ADR-036's D2.4 addendum): the project owner decided
        agents may lock and unlock layers. It goes through the SAME
        ``SetLayerPropertyCommand`` the Layers panel's lock toggle runs, so it
        is one undo step like every other property and there is no second
        write path.

        What did NOT change: a locked layer's OBJECTS are still protected. The
        item-level guard in ``_resolve_agent_item`` tests the layer's *current*
        lock state, so an agent that wants to edit a locked layer unlocks it
        first and edits second — two calls, two undo steps, both visible to the
        user. The other locked-layer refusals (create onto a locked layer,
        deleting a locked layer) stay absolute for the same reason.

        Exactly one of ``visible``/``opacity``/``locked`` may be given per call:
        each maps to one ``SetLayerPropertyCommand``, and one agent call is one
        undo step (invariants #4/#13) — two properties would be two steps, so
        the tool refuses rather than silently over-stepping.

        Changing visibility/opacity of a LOCKED layer is allowed: the lock
        protects the layer's objects from editing, not the layer's own display
        properties — same as the Layers panel, which keeps both controls live
        on a locked layer.
        """
        host = self._host
        from open_garden_planner.core.commands import SetLayerPropertyCommand

        given = [
            name
            for name, value in (
                ("visible", visible),
                ("opacity", opacity),
                ("locked", locked),
            )
            if value is not None
        ]
        if not given:
            raise ValueError(
                "Pass 'visible' (bool), 'opacity' (0.0-1.0) and/or 'locked' "
                "(bool) — there is nothing to change otherwise."
            )
        if len(given) > 1:
            raise ValueError(
                f"Pass exactly ONE of 'visible'/'opacity'/'locked' per call: "
                f"each property change is one undo step, and one call is one "
                f"undo step. Got {', '.join(given)} — make separate calls."
            )
        layer = host._agent_resolve_layer(layer_id)
        if visible is not None:
            new_visible = bool(visible)
            if layer.visible == new_visible:
                raise ValueError(
                    f"Layer {layer.name!r} is already "
                    f"{'visible' if new_visible else 'hidden'}; nothing to do."
                )
            cmd = SetLayerPropertyCommand(
                host.canvas_scene, layer, "visible", layer.visible, new_visible
            )
        elif locked is not None:
            new_locked = bool(locked)
            if layer.locked == new_locked:
                raise ValueError(
                    f"Layer {layer.name!r} is already "
                    f"{'locked' if new_locked else 'unlocked'}; nothing to do."
                )
            cmd = SetLayerPropertyCommand(
                host.canvas_scene, layer, "locked", layer.locked, new_locked
            )
        else:
            import math

            new_opacity = float(opacity)  # type: ignore[arg-type]
            if not math.isfinite(new_opacity) or not (0.0 <= new_opacity <= 1.0):
                raise ValueError(
                    f"opacity must be a number between 0.0 and 1.0, got "
                    f"{opacity!r}"
                )
            if abs(layer.opacity - new_opacity) < 1e-9:
                raise ValueError(
                    f"Layer {layer.name!r} already has opacity "
                    f"{new_opacity:g}; nothing to do."
                )
            cmd = SetLayerPropertyCommand(
                host.canvas_scene, layer, "opacity", layer.opacity, new_opacity
            )
        host.canvas_view.command_manager.execute(cmd)
        return {
            "item_id": None,
            "action": "set_layer_property",
            "undo_description": cmd.description,
            "layer_id": str(layer.id),
        }


    @staticmethod
    def _agent_require_layer_name(name: str) -> str:
        """Validate a layer name for create/rename: non-empty after stripping.

        Duplicate names are NOT refused — the GUI's own rename path accepts
        them (``_on_layer_renamed``), and ids are the canonical address; this
        must not invent a stricter policy than the surface it mirrors.
        """
        clean = name.strip() if isinstance(name, str) else ""
        if not clean:
            raise ValueError("A layer name must contain at least one character.")
        return clean


    def _agent_resolve_plant(self, item_id: str, tool_name: str) -> Any:
        """``_resolve_agent_item`` plus "and it must be a plant".

        Shared by ``set_species`` and ``set_parent_bed``: both are meaningless
        on a bed or a shed, and the D2.1 precedent is to say so by name rather
        than no-op.
        """
        host = self._host
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        item = host._resolve_agent_item(item_id)
        if not isinstance(item, GardenItemMixin) or not is_plant_type(
            item.object_type
        ):
            raise ValueError(
                f"{item_id} is a {self._agent_object_type_name(item)}, not a "
                f"plant, so {tool_name} does not apply to it. Plants are "
                "TREE, SHRUB and PERENNIAL objects."
            )
        return item


    def _agent_object_type_name(self, item: Any) -> str:
        """``item``'s ``ObjectType`` name, or a readable stand-in."""
        object_type = getattr(item, "object_type", None)
        name = getattr(object_type, "name", None)
        return str(name) if name else type(item).__name__


    def _agent_refresh_soil_mismatches(self) -> None:
        """Recompute soil-mismatch borders after a species change.

        ``apply_species_to_item`` does this itself; the clear-species branch
        builds its command directly and so must do it explicitly, or the
        FR-SOIL warning border outlives the species that caused it.
        """
        host = self._host
        for view in host.canvas_scene.views():
            refresh = getattr(view, "refresh_soil_mismatches", None)
            if callable(refresh):
                refresh()


    def _resolve_agent_read_item(self, item_id: str) -> Any:
        """Resolve a top-level live item for a read that needs Qt geometry.

        Read visibility intentionally differs from write protection: a locked
        layer or journal pin remains inspectable. Group members are still not
        independently addressable because the curated read tools expose only
        the group's top-level id.
        """
        host = self._host
        from uuid import UUID

        from open_garden_planner.ui.canvas.items.group_item import GroupItem

        try:
            uuid = UUID(item_id)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Not a valid object id: {item_id!r}") from exc
        item = host.canvas_scene.find_item_by_id(uuid)
        if item is None:
            raise ValueError(f"No object with id {item_id}")
        if isinstance(item.parentItem(), GroupItem):
            raise ValueError(
                f"{item_id} is a member of a group; address the group itself "
                "rather than an individual member."
            )
        return item


    def _resolve_agent_item(self, item_id: str) -> Any:
        """Look up a scene item by UUID string for a write tool, or raise.

        Raising here surfaces to the agent as a failed tool call (the bridge
        propagates the exception across the main-thread hop).
        """
        host = self._host
        from uuid import UUID

        from open_garden_planner.ui.canvas.items.group_item import GroupItem
        from open_garden_planner.ui.canvas.items.journal_pin_item import JournalPinItem

        try:
            uuid = UUID(item_id)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Not a valid object id: {item_id!r}") from exc
        item = host.canvas_scene.find_item_by_id(uuid)
        if item is None:
            raise ValueError(f"No object with id {item_id}")
        if isinstance(item.parentItem(), GroupItem):
            # A group member isn't a top-level object (list_objects/get_object
            # skip it; only a raw snapshot exposes its id nested in the group).
            # The GUI never lets you select a lone member — you move/delete the
            # whole group — and moveBy on a QGraphicsItemGroup child would
            # displace it *within* the group. Address the group by its own id.
            raise ValueError(
                f"{item_id} is a member of a group; address the group itself "
                "(its own id) rather than an individual member."
            )
        if isinstance(item, JournalPinItem):
            # Journal pins have their own ProjectData-linked delete path
            # (DeleteJournalNoteCommand prunes the note dict; a plain
            # DeleteItemsCommand would remove the pin but silently orphan the
            # note record). Not supported by move_object/delete_object yet.
            raise ValueError(
                f"{item_id} is a journal pin, not a garden object — the write "
                "tools don't support journal pins yet."
            )
        if host._agent_item_is_locked(item):
            # The GUI enforces layer-lock by clearing ItemIsSelectable/
            # ItemIsMovable, so a locked-layer item can't be dragged, arrow-
            # moved, or deleted at all (every GUI edit works off selectedItems()).
            # The agent resolves by UUID, bypassing selection — so honour the
            # lock explicitly here, the one chokepoint every write tool shares.
            raise ValueError(
                f"{item_id} is on a locked layer. Unlock it with "
                "set_layer_property(layer_id, locked=False) and then retry — "
                "each is one undo step."
            )
        return item


    def _agent_item_is_locked(self, item: Any) -> bool:
        """Whether ``item`` sits on a locked layer (which the GUI makes
        entirely non-interactive)."""
        host = self._host
        layer_id = getattr(item, "layer_id", None)
        if layer_id is None:
            return False
        layer = host.canvas_scene.get_layer_by_id(layer_id)
        return bool(layer is not None and layer.locked)


    def _agent_item_constraints(self, item: Any) -> list[Any]:
        """Every constraint (distance/fixed/tangent/…) referencing ``item``."""
        host = self._host
        return host.canvas_scene.constraint_graph.get_item_constraints(item.item_id)


    def _agent_document_items(self) -> list[Any]:
        """Return every live serialized document item with a UUID.

        This deliberately uses the same predicate as project loading instead
        of a second ``GardenItemMixin``-only census: Arc/Bezier and other
        serialized classes can collide with a UUID too, and a delete receipt
        must not ignore them.
        """
        host = self._host
        return [
            item
            for item in host.canvas_scene.items()
            if host._project_manager._is_project_document_item(item)
            and host._agent_item_uuid(item) is not None
        ]


    @staticmethod
    def _agent_item_uuid(item: Any) -> Any:
        """Return a document item's UUID, or ``None`` for non-addressables."""
        value = getattr(item, "item_id", None)
        return value if isinstance(value, UUID) else None


    def _agent_require_unique_items(
        self, items: list[Any], *, action: str = "delete_object"
    ) -> None:
        """Refuse an operation if any target UUID occurs more than once live."""
        host = self._host
        from collections import Counter

        target_ids = {host._agent_item_uuid(item) for item in items}
        if None in target_ids:
            raise ValueError(f"{action} requires every target to have a UUID.")

        counts: Counter[Any] = Counter()
        for candidate in host._agent_document_items():
            candidate_id = host._agent_item_uuid(candidate)
            if candidate_id in target_ids:
                counts[candidate_id] += 1

        duplicates = [
            f"{candidate_id} ({count} live objects)"
            for candidate_id, count in sorted(counts.items(), key=lambda pair: str(pair[0]))
            if count > 1
        ]
        if duplicates:
            raise ValueError(
                f"Cannot {action} because the document contains duplicate live "
                f"UUIDs: {', '.join(duplicates)}. Resolve the duplicate records "
                f"before continuing; {action} will not choose one arbitrarily."
            )


    def _maybe_start_agent_api(self) -> None:
        """Start the Agent API server iff it is enabled in settings."""
        host = self._host
        from open_garden_planner.app.settings import get_settings

        if get_settings().agent_api_enabled:
            host._start_agent_api()


    def _start_agent_api(self) -> None:
        """Start the embedded MCP server, surfacing failures in the status bar."""
        host = self._host
        from open_garden_planner.agent_api import (
            AgentApiServer,
            PortInUseError,
        )
        from open_garden_planner.app.settings import get_settings

        if host._agent_server is not None and host._agent_server.is_running:
            return
        settings = get_settings()
        port = settings.agent_api_port
        providers = host._build_agent_providers()
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
            host._agent_server = None
            cast(Any, host.statusBar()).showMessage(
                QCoreApplication.translate("GardenPlannerApp", "Agent API: port {port} is already in use").format(port=port),
                8000,
            )
            return
        except Exception:
            host._agent_server = None
            logger.exception("Agent API failed to start")
            cast(Any, host.statusBar()).showMessage(
                QCoreApplication.translate("GardenPlannerApp", "Agent API failed to start (see log)"), 8000
            )
            return
        host._agent_server = server
        cast(Any, host.statusBar()).showMessage(
            QCoreApplication.translate("GardenPlannerApp", "Agent API running at {url}").format(url=server.url), 5000
        )


    def _build_agent_providers(self) -> Any:
        """Build the one production provider graph used by the embedded MCP server.

        Keeping construction separate from server lifecycle gives integration
        tests a way to drive the exact application wiring over MCP without
        duplicating the write orchestration in a test-only provider bundle.
        """
        host = self._host
        from open_garden_planner.agent_api import AgentProviders

        return AgentProviders(
            snapshot=host._agent_snapshot,
            diagnostics=host._agent_diagnostics,
            render=host._agent_render,
            save_plan=host._agent_save_plan,
            new_plan=host._agent_new_plan,
            open_plan=host._agent_open_plan,
            export_pdf=host._agent_export_pdf,
            export_dxf=host._agent_export_dxf,
            export_csv=host._agent_export_csv,
            create_object=host._agent_create_object,
            get_geometry=host._agent_get_geometry,
            move_object=host._agent_move_object,
            set_object_position=host._agent_set_object_position,
            delete_object=host._agent_delete_object,
            resize_object=host._agent_resize_object,
            rotate_object=host._agent_rotate_object,
            set_vertex=host._agent_set_vertex,
            add_vertex=host._agent_add_vertex,
            delete_vertex=host._agent_delete_vertex,
            set_species=host._agent_set_species,
            set_parent_bed=host._agent_set_parent_bed,
            arrange_object=host._agent_arrange_object,
            set_object_layer=host._agent_set_object_layer,
            create_layer=host._agent_create_layer,
            rename_layer=host._agent_rename_layer,
            delete_layer=host._agent_delete_layer,
            set_active_layer=host._agent_set_active_layer,
            set_layer_property=host._agent_set_layer_property,
            undo=host._agent_undo,
            redo=host._agent_redo,
            get_history=host._agent_get_history,
            suggest_companions=host._agent_suggest_companions,
            find_compatible_sets=host._agent_find_compatible_sets,
            find_sets_for_bed=host._agent_find_sets_for_bed,
            check_placement=host._agent_check_placement,
            get_succession_plan=host._agent_get_succession_plan,
            find_succession_gaps=host._agent_find_succession_gaps,
            suggest_succession=host._agent_suggest_succession,
            set_succession_plan=host._agent_set_succession_plan,
            get_tasks=host._agent_get_tasks,
            get_task_calendar=host._agent_get_task_calendar,
            add_manual_task=host._agent_add_manual_task,
            edit_manual_task=host._agent_edit_manual_task,
            delete_manual_task=host._agent_delete_manual_task,
            get_soil_status=host._agent_get_soil_status,
            recommend_amendments=host._agent_recommend_amendments,
            get_soil_mismatches=host._agent_get_soil_mismatches,
            record_soil_test=host._agent_record_soil_test,
            get_plant_lists=host._agent_get_plant_lists,
        )


    def _stop_agent_api(self) -> None:
        """Stop the embedded MCP server if it is running."""
        host = self._host
        if host._agent_server is not None:
            # Abort any in-flight main-thread hops first so the server thread's
            # tool handler returns at once — otherwise stop()'s join could wait
            # on a queued call the (now tearing-down) main thread won't service.
            host._agent_bridge.abort_pending()
            host._agent_server.stop()
            host._agent_server = None


