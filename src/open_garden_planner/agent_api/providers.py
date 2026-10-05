"""Provider bundle injected into the Agent API server (Qt-free).

The server thread must never touch Qt directly. Instead the GUI passes a bundle
of callables that each already hop to the Qt main thread (via
:class:`~open_garden_planner.agent_api.bridge.MainThreadBridge`) and return plain
data. Bundling them keeps :func:`~open_garden_planner.agent_api.server.build_server`
stable as the surface grows: US-D1.2 needs ``snapshot`` + ``diagnostics``; US-D1.3
adds ``render``; US-D1.4 adds ``save_plan``/``export_pdf``/``export_dxf``/
``export_csv``; D2 adds the command-backed write ops and global ``undo``/``redo``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol


class CreateObjectProvider(Protocol):
    """The `create_object` provider's call signature, named parameters included.

    A plain ``Callable[[str, float, float, float | None, ...], ...]`` would type
    six of the eight arguments identically (`float | None` / `str | None`), so a
    width/height or name/species transposition anywhere along the chain would be
    type-identical and silently build the wrong object. Spelling it as a
    Protocol makes the parameter NAMES part of the contract, which is what lets
    `server.py` call it by keyword and have that mean something.
    """

    def __call__(
        self,
        object_type: str,
        x: float | None,
        y: float | None,
        width: float | None,
        height: float | None,
        radius: float | None,
        name: str | None,
        species: str | None,
        points: list[list[float]] | None,
        text: str | None,
        box_dx: float | None,
        box_dy: float | None,
    ) -> dict[str, Any]: ...


class ResizeObjectProvider(Protocol):
    """The `resize_object` provider's call signature, named parameters included.

    Same reasoning as :class:`CreateObjectProvider`: ``width``/``height``/
    ``radius`` are all ``float | None``, so a transposition would be
    type-identical and silently resize the wrong axis. Spelling it as a Protocol
    makes the parameter NAMES part of the contract, and ``server.py`` calls it
    by keyword.
    """

    def __call__(
        self,
        item_id: str,
        width: float | None,
        height: float | None,
        radius: float | None,
    ) -> dict[str, Any]: ...


class SetLayerPropertyProvider(Protocol):
    """The `set_layer_property` provider's call signature, named parameters included.

    Same reasoning as :class:`CreateObjectProvider`: ``visible``/``locked`` are
    both ``bool | None``, so a transposition would be type-identical and
    silently toggle the wrong property (and toggling ``locked`` is refused by
    policy — a transposed argument must not sneak past that refusal).
    ``server.py`` calls it by keyword.
    """

    def __call__(
        self,
        layer_id: str,
        visible: bool | None,
        opacity: float | None,
        locked: bool | None,
    ) -> dict[str, Any]: ...


class SetSuccessionPlanProvider(Protocol):
    """The `set_succession_plan` provider's call signature, named parameters.

    Same reasoning as :class:`CreateObjectProvider`: the ``year: int | None`` /
    ``bed_id: str`` / ``entries: list | None`` trio would be type-identical under
    a transposition, which would silently write a plan to the wrong bed or year.
    Spelling it as a Protocol keeps the parameter NAMES part of the contract,
    exactly as for :class:`CreateObjectProvider`.
    """

    def __call__(
        self,
        bed_id: str,
        entries: list[dict[str, Any]] | None,
        year: int | None,
    ) -> dict[str, Any]: ...


class SetSoilTestProvider(Protocol):
    """The `record_soil_test` provider's call signature, named parameters included.

    Same reasoning as :class:`CreateObjectProvider`, and sharper here: the six
    `*_level` parameters are ALL `int | None` over six DIFFERENT ranges, so a
    transposition would be type-identical and would write a nitrogen reading
    into the potassium slot of a soil record. Spelling it as a Protocol keeps
    the parameter NAMES part of the contract, and `server.py` calls it by
    keyword.
    """

    def __call__(
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
    ) -> dict[str, Any]: ...


class ManualTaskProvider(Protocol):
    """The `add_manual_task` provider's call signature, named parameters included.

    `title` and `date` are both plain strings and `notes` is an optional string,
    so a positional transposition is type-identical and would file a task under
    its own title. `server.py` calls it by keyword.
    """

    def __call__(
        self,
        title: str,
        date: str | None,
        notes: str | None,
        bed_id: str | None,
        task_id: str | None,
    ) -> dict[str, Any]: ...


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
        new_plan: **Write (issue #365).** Discards the open document and starts
            a fresh empty plan. Takes optional canvas width/height in cm and a
            ``force`` flag standing in for the GUI's unsaved-changes prompt;
            refuses on a dirty plan without it. Returns a plain dict. NOT an
            undo step — a new document resets the undo stack.
        open_plan: **Write (issue #365).** Loads an existing ``.ogp`` file,
            replacing the open document, under the same ``force`` guard. Returns
            a plain dict. NOT an undo step.
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
        create_object: **Write (D2.1/D2.5).** Creates one object from the
            supported shape families. Takes the centre/dimension parameters for
            circles, rectangles and ellipses, ``points`` for polygons and
            polylines (or a rectangular footprint for polygons), and ``text``
            plus a leader target for callouts. Runs ONE undoable command on the
            main thread (a HOUSE and its linked roof ridge are one composite
            command) and returns a plain ``WriteResult``-shaped dict. Raises
            on an unsupported/excluded type or invalid geometry
            (``agent_api.creates.build_create_dict``).
        get_geometry: **Read (D2.6).** Returns curated live geometry for one
            object in scene-centimetre Y-up coordinates, including vertex/curve
            data and every constraint referencing it. Read-only; it never
            mutates or dirties the plan.
        move_object: **Write (D2).** Moves one object by a relative offset
            (dx, dy in scene cm; +x east, +y north — the canvas is Y-up, so a
            negative dy moves south). Takes ``(item_id, dx, dy)``; runs one
            undoable move command on the main thread and returns a plain
            ``WriteResult``-shaped dict. Raises if the id is unknown.
        set_object_position: **Write (D2.6).** Sets one object's absolute scene
            centre. Uses the same move orchestration as ``move_object`` and
            inherits its child propagation and reparenting semantics.
        delete_object: **Write (D2).** Deletes one object by id. Takes
            ``(item_id,)``; runs one undoable ``DeleteItemsCommand`` on the main
            thread and returns a plain ``WriteResult``-shaped dict. Raises if the
            id is unknown.
        resize_object: **Write (D2.2).** Resizes one object to absolute target
            dimensions in cm, preserving its scene CENTRE. Takes
            ``(item_id, width, height, radius)`` — the pair that fits the
            object's shape; runs one undoable ``ResizeItemCommand`` through the
            canonical ``ui.canvas.geometry_apply`` path and returns a plain
            ``WriteResult``-shaped dict.
        rotate_object: **Write (D2.2).** Rotates one object. Takes
            ``(item_id, angle, relative)`` in degrees, positive =
            counter-clockwise; runs one undoable ``RotateItemCommand`` and
            returns a plain ``WriteResult``-shaped dict.
        set_vertex: **Write (D2.6).** Moves one polygon/polyline vertex to an
            absolute scene-frame point; exactly one undoable command.
        add_vertex: **Write (D2.6).** Inserts one polygon/polyline vertex at a
            list index; exactly one undoable command.
        delete_vertex: **Write (D2.6).** Removes one polygon/polyline vertex
            while preserving the shape's minimum vertex count.
        set_species: **Write (D2.3).** Assigns (or clears) an existing plant's
            species. Takes ``(item_id, species, apply_database_size)``; runs one
            undoable ``ApplySpeciesCommand`` and returns a plain
            ``WriteResult``-shaped dict.
        set_parent_bed: **Write (D2.3).** Links a plant to a bed, or detaches it
            when ``bed_id`` is ``None`` — a link change only, the plant does not
            move. Takes ``(item_id, bed_id)``; runs one undoable
            ``SetParentBedCommand`` and returns a plain ``WriteResult``-shaped
            dict.
        arrange_object: **Write (#338).** Reorders one object within its own
            layer — bring to front, bring forward, send backward, or send to
            back. Takes ``(item_id, action)`` where ``action`` is one of
            ``"bring_to_front"``/``"bring_forward"``/``"send_backward"``/
            ``"send_to_back"``; runs the one arrange command through the
            shared ``ui.canvas.arrange.build_arrange_command`` seam and
            returns a plain ``WriteResult``-shaped dict (its ``stack_index``
            reports the resulting position). Raises when there is nothing to
            change (already at the front/back, or no overlapping object to
            step past) — mirroring ``set_parent_bed``'s no-op precedent.
        set_object_layer: **Write (D2.4).** Moves one object to another layer.
            Takes ``(item_id, layer_id)``; runs one undoable
            ``MoveToLayerCommand`` and returns a plain ``WriteResult``-shaped
            dict.
        create_layer: **Write (D2.4).** Creates a layer at the top of the
            stack and activates it. Takes ``(name,)``; runs one undoable
            ``AddLayerCommand``.
        rename_layer: **Write (D2.4).** Takes ``(layer_id, name)``; runs one
            undoable ``RenameLayerCommand``.
        delete_layer: **Write (D2.4).** Takes ``(layer_id,)``; runs one
            undoable ``DeleteLayerCommand`` — the layer's objects survive on a
            replacement layer inside the same single undo step.
        set_active_layer: **Write (D2.4).** Takes ``(layer_id,)``; switches the
            session's active layer (``CanvasScene.set_active_layer``). NOT an
            undo step: the active layer is session state, never persisted and
            never dirtying the document — same as the layers panel's own
            row-click activation.
        set_layer_property: **Write (D2.4).** Takes ``(layer_id, visible,
            opacity, locked)``; runs one undoable ``SetLayerPropertyCommand``
            per call, so exactly one property may change per call. ``locked``
            is refused by policy in both directions (ADR-036 D2.4 addendum).
        undo: **Write (MCP history).** Reverses exactly one command on the
            global, GUI-shared LIFO history stack. Refuses an empty stack.
        redo: **Write (MCP history).** Reapplies exactly one command on the
            global, GUI-shared LIFO history stack. Refuses an empty stack.
        get_history: **Read (US-D2.7).** Returns the current undo/redo stack
            state — depths and next undo/redo texts — without mutating the
            stack. Read-only; no token required.
        suggest_companions: **Read (US-D3.1).** Returns ranked companion
            suggestions for a species. Takes (species_key,
            exclude_antagonists_of). Read-only. Each `name` is a display
            string in the current UI language; `species_key` is the stable key.
        find_compatible_sets: **Read (US-D3.1).** Finds mutually compatible
            sets of plants among candidates. Takes (candidates, size,
            must_include). Read-only.
        find_sets_for_bed: **Read (US-D3.1).** Ranks compatible sets by how
            many of a bed's current plants each one satisfies, and reports the
            bed plants that fit no set. Takes (bed_plants, size). Read-only.
        check_placement: **Read (US-D3.1).** Checks whether a species is
            well-placed in a bed. Takes (species_key, bed_id, bed_plants).
            Read-only.
        get_succession_plan: **Read (US-D3.2).** Returns a bed's succession
            plan for a year, curated, with the season segments, the current and
            next slot against an injected reference date, and an explicit
            ``coverage`` marker when the plan has no frost dates. Takes
            (bed_id, year, today). Read-only.
        find_succession_gaps: **Read (US-D3.2).** Returns the growing-season
            date ranges a bed's plan leaves uncovered, each with its season
            label. Takes (bed_id, year, today). Read-only.
        suggest_succession: **Read (US-D3.2).** Ranks candidate crops for one
            succession gap, excluding crop-rotation conflicts and antagonists.
            Takes (bed_id, gap_start, gap_end, candidates). Read-only.
        set_succession_plan: **Write (US-D3.2).** Replaces a bed's succession
            plan, or deletes it when ``entries`` is empty/None. Takes
            ``(bed_id, entries, year)``; runs exactly one undoable
            ``SetSuccessionPlanCommand`` on the main thread — the FIRST agent
            write into ``ProjectData`` rather than the scene graph — and returns
            a plain ``WriteResult``-shaped dict. Raises on an unknown bed, a
            non-soil-container target, overlapping ranges or malformed dates,
            leaving both the plan state and the undo stack untouched.
        get_tasks: **Read (US-D3.3).** Curated task calendar for a date window,
            with the render-time urgency and the shared task status folded in.
            Takes keyword filters; read-only.
        get_task_calendar: **Read (US-D3.3).** Month-bucketed counts by source
            and urgency for one year. Takes ``(year, today)``; read-only.
        add_manual_task: **Write (US-D3.3).** Files one user-authored task.
            Takes ``(title, date, notes, bed_id, task_id)`` — ``task_id`` is
            supplied only by an edit. Runs exactly one undoable
            ``AddManualTaskCommand`` and returns a ``ManualTaskResult``.
        edit_manual_task: **Write (US-D3.3).** Same signature as
            ``add_manual_task``; runs one ``EditManualTaskCommand``. Refuses a
            GENERATED task by name — generated tasks are derived state.
        delete_manual_task: **Write (US-D3.3).** Takes ``(task_id,)``; runs one
            ``DeleteManualTaskCommand``. Refuses a generated task by name.
        get_soil_status: **Read (US-D3.4).** One bed's EFFECTIVE soil record —
            its own latest, else the plan-wide default's latest — plus which of
            the two answered, the per-nutrient health ratings and the overdue
            check. Takes ``(bed_id, today)``; read-only.
        recommend_amendments: **Read (US-D3.4).** ``calculate_amendments``
            output, curated, with stable amendment ids beside display names.
            Takes ``(bed_id, today)``; read-only.
        get_soil_mismatches: **Read (US-D3.4).** Plants that disagree with
            their bed's soil, as stable reason codes beside display text. Takes
            ``(bed_id, today)``; ``bed_id=None`` checks every soil bed.
        record_soil_test: **Write (US-D3.4).** Records a soil test on the
            Rapitest KIT scale. Runs exactly one undoable
            ``AddSoilTestCommand`` — the second agent write into ``ProjectData``
            — and returns a ``WriteResult``. Raises before building the record
            on any out-of-range reading, leaving ``soil_tests`` and the undo
            stack untouched. Lab ppm values are refused by design.
    """

    snapshot: Callable[[], dict[str, Any]]
    diagnostics: Callable[[], list[dict[str, Any]]]
    get_history: Callable[[], dict[str, Any]]
    suggest_companions: Callable[..., list[dict[str, Any]]]
    find_compatible_sets: Callable[..., list[dict[str, Any]]]
    find_sets_for_bed: Callable[..., dict[str, Any]]
    check_placement: Callable[..., dict[str, Any]]
    get_succession_plan: Callable[..., dict[str, Any]]
    find_succession_gaps: Callable[..., dict[str, Any]]
    suggest_succession: Callable[..., list[dict[str, Any]]]
    set_succession_plan: SetSuccessionPlanProvider
    get_tasks: Callable[..., dict[str, Any]]
    get_task_calendar: Callable[..., dict[str, Any]]
    add_manual_task: ManualTaskProvider
    edit_manual_task: ManualTaskProvider
    delete_manual_task: Callable[[str], dict[str, Any]]
    get_soil_status: Callable[..., dict[str, Any]]
    recommend_amendments: Callable[..., dict[str, Any]]
    get_soil_mismatches: Callable[..., dict[str, Any]]
    record_soil_test: SetSoilTestProvider
    render: Callable[
        [tuple[float, float, float, float] | None, list[str] | None, int],
        dict[str, Any],
    ]
    save_plan: Callable[[str | None], dict[str, Any]]
    new_plan: Callable[[float | None, float | None, bool], dict[str, Any]]
    open_plan: Callable[[str, bool], dict[str, Any]]
    export_pdf: Callable[
        [str | None, Literal["A4", "A3", "Letter", "Legal"], Literal["landscape", "portrait"]],
        dict[str, Any],
    ]
    export_dxf: Callable[[str | None], dict[str, Any]]
    export_csv: Callable[[Literal["shopping_list", "harvest"], str | None], dict[str, Any]]
    create_object: CreateObjectProvider
    get_geometry: Callable[[str], dict[str, Any]]
    move_object: Callable[[str, float, float], dict[str, Any]]
    set_object_position: Callable[[str, float, float], dict[str, Any]]
    delete_object: Callable[[str], dict[str, Any]]
    resize_object: ResizeObjectProvider
    rotate_object: Callable[[str, float, bool], dict[str, Any]]
    set_vertex: Callable[[str, int, float, float], dict[str, Any]]
    add_vertex: Callable[[str, int, float, float], dict[str, Any]]
    delete_vertex: Callable[[str, int], dict[str, Any]]
    set_species: Callable[[str, str | None, bool], dict[str, Any]]
    set_parent_bed: Callable[[str, str | None], dict[str, Any]]
    arrange_object: Callable[[str, str], dict[str, Any]]
    set_object_layer: Callable[[str, str], dict[str, Any]]
    create_layer: Callable[[str], dict[str, Any]]
    rename_layer: Callable[[str, str], dict[str, Any]]
    delete_layer: Callable[[str], dict[str, Any]]
    set_active_layer: Callable[[str], dict[str, Any]]
    set_layer_property: SetLayerPropertyProvider
    undo: Callable[[], dict[str, Any]]
    redo: Callable[[], dict[str, Any]]
