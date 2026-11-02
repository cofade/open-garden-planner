"""Integration tests for smart symbols (US-C4)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import ezdxf
import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from open_garden_planner.core.project import ProjectManager
from open_garden_planner.services.dxf_service import DxfExportService
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.smart_symbol_item import SmartSymbolItem


def _make_app(qtbot, monkeypatch):
    from open_garden_planner.app.application import GardenPlannerApp

    monkeypatch.setattr(
        QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Discard
    )
    monkeypatch.setattr(QApplication, "focusWidget", lambda: None)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    return win


def _geometry_children(symbol: SmartSymbolItem) -> int:
    return len(symbol.childItems())


class TestPlacementAndEditing:
    def test_panel_lists_bundled_symbols(self, qtbot, monkeypatch) -> None:
        win = _make_app(qtbot, monkeypatch)
        assert win.smart_symbols_panel._list.count() >= 5

    def test_insert_creates_parametric_item(self, qtbot, monkeypatch) -> None:
        win = _make_app(qtbot, monkeypatch)
        win._on_smart_symbol_selected("raised_bed_rows")
        syms = [it for it in win.canvas_scene.items() if isinstance(it, SmartSymbolItem)]
        assert len(syms) == 1
        assert _geometry_children(syms[0]) == 4  # 1 rect + 3 rows

    def test_param_edit_regenerates_undoably(self, qtbot, monkeypatch) -> None:
        win = _make_app(qtbot, monkeypatch)
        win._on_smart_symbol_selected("raised_bed_rows")
        sym = next(it for it in win.canvas_scene.items() if isinstance(it, SmartSymbolItem))
        sym.setPos(200.0, 150.0)
        pos_before = (sym.pos().x(), sym.pos().y())

        win.properties_panel.set_command_manager(win.canvas_view.command_manager)
        win.properties_panel.set_selected_items([sym])
        win.properties_panel._on_symbol_param_changed(sym, "rows", 7)
        assert _geometry_children(sym) == 7
        assert (sym.pos().x(), sym.pos().y()) == pos_before  # position preserved
        assert all(c.scenePos().x() >= 200.0 for c in sym.childItems())  # children do not jump to (0, 0)
        assert all(c.scenePos().y() >= 150.0 for c in sym.childItems())

        win.canvas_view.command_manager.undo()
        assert _geometry_children(sym) == 4
        assert (sym.pos().x(), sym.pos().y()) == pos_before
        assert all(c.scenePos().x() >= 200.0 for c in sym.childItems())
        win.canvas_view.command_manager.redo()
        assert _geometry_children(sym) == 7
        assert (sym.pos().x(), sym.pos().y()) == pos_before
        assert all(c.scenePos().x() >= 200.0 for c in sym.childItems())

    def test_repeated_edits_do_not_leak_items(self, qtbot, monkeypatch) -> None:
        win = _make_app(qtbot, monkeypatch)
        win._on_smart_symbol_selected("raised_bed_rows")
        sym = next(it for it in win.canvas_scene.items() if isinstance(it, SmartSymbolItem))
        for rows in (5, 8, 3, 6):
            sym.params["rows"] = rows
            sym.regenerate_geometry()
            assert _geometry_children(sym) == rows  # exactly N, no orphans

    def test_divide_by_zero_param_edit_survives(self, qtbot, monkeypatch) -> None:
        """A user symbol that divides by an editable param must not crash the GUI
        when the param reaches zero — it keeps the last good geometry."""
        from open_garden_planner.models.smart_symbol import SmartSymbolDefinition
        from open_garden_planner.services.smart_symbol_library import (
            get_smart_symbol_library,
        )

        win = _make_app(qtbot, monkeypatch)
        definition = SmartSymbolDefinition.from_dict(
            {"id": "dz", "version": 1, "name": "DZ", "name_de": "DZ", "category": "c",
             "parameters": [{"name": "n", "type": "number", "label": "N", "default": 2,
                             "min": 0, "max": 10}],
             "elements": [{"kind": "line", "x1": 0, "y1": 0, "x2": "10 / n", "y2": 0}]}
        )
        lib = get_smart_symbol_library()
        lib._ensure_loaded()
        lib._symbols["dz"] = definition

        win._on_smart_symbol_selected("dz")
        sym = next(it for it in win.canvas_scene.items() if isinstance(it, SmartSymbolItem))
        assert _geometry_children(sym) == 1
        win.properties_panel.set_command_manager(win.canvas_view.command_manager)
        win.properties_panel.set_selected_items([sym])
        # n → 0 triggers a divide-by-zero inside regenerate; must not raise.
        win.properties_panel._on_symbol_param_changed(sym, "n", 0)
        assert _geometry_children(sym) == 1  # last good geometry kept

    def test_ungroup_action_suppressed(self, qtbot, monkeypatch) -> None:
        win = _make_app(qtbot, monkeypatch)
        win._on_smart_symbol_selected("raised_bed_rows")
        sym = next(it for it in win.canvas_scene.items() if isinstance(it, SmartSymbolItem))
        # SmartSymbolItem overrides contextMenuEvent and must not wire the
        # destructive ungroup action (which GroupItem does via ungroup_item).
        from open_garden_planner.ui.canvas.items.group_item import GroupItem

        assert type(sym).contextMenuEvent is not GroupItem.contextMenuEvent
        import inspect
        src = inspect.getsource(type(sym).contextMenuEvent)
        assert "ungroup_item" not in src


class TestSerialization:
    @pytest.fixture
    def manager(self, qtbot) -> ProjectManager:
        return ProjectManager()

    def test_round_trips_as_parametric(self, manager, qtbot) -> None:
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        sym = SmartSymbolItem("raised_bed_rows", 2, {"rows": 5})
        scene.addItem(sym)
        sym.regenerate_geometry()
        sym.setPos(120, 80)

        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "s.ogp"
            manager.save(scene, fp)
            scene.clear()
            manager.load(scene, fp)
        loaded = [it for it in scene.items() if isinstance(it, SmartSymbolItem)]
        assert len(loaded) == 1
        assert loaded[0].params["rows"] == 5
        assert _geometry_children(loaded[0]) == 5
        assert (loaded[0].pos().x(), loaded[0].pos().y()) == (120, 80)

    def test_missing_definition_uses_cached_geometry(self, manager, qtbot) -> None:
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        sym = SmartSymbolItem("raised_bed_rows", 2, {"rows": 4})
        scene.addItem(sym)
        sym.regenerate_geometry()

        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "s.ogp"
            manager.save(scene, fp)
            # Simulate an unknown symbol: rename id in the saved JSON.
            text = fp.read_text(encoding="utf-8").replace(
                '"raised_bed_rows"', '"vanished_symbol"'
            )
            fp.write_text(text, encoding="utf-8")
            scene.clear()
            manager.load(scene, fp)  # must not raise
        loaded = [it for it in scene.items() if isinstance(it, SmartSymbolItem)]
        assert len(loaded) == 1
        # Definition is gone → the cached serialized children are rebuilt.
        assert _geometry_children(loaded[0]) == 4

    def test_version_mismatch_uses_cached_geometry(self, manager, qtbot) -> None:
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        sym = SmartSymbolItem("raised_bed_rows", 99, {"rows": 4})  # future version
        scene.addItem(sym)
        sym.regenerate_geometry()  # no live def at v99 → empty unless cached
        # Seed cached specs from the real definition so there is geometry to keep.
        from open_garden_planner.services.smart_symbol_library import (
            get_smart_symbol_library,
        )
        real = get_smart_symbol_library().get("raised_bed_rows")
        sym.set_cached_specs(real.generate({"rows": 4}))
        sym.regenerate_geometry()
        assert _geometry_children(sym) == 4

        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "s.ogp"
            manager.save(scene, fp)
            scene.clear()
            manager.load(scene, fp)
        loaded = [it for it in scene.items() if isinstance(it, SmartSymbolItem)]
        assert len(loaded) == 1 and _geometry_children(loaded[0]) == 4
        # Subsequent regenerate_geometry on a loaded version-mismatched symbol must
        # preserve its deserialized children rather than clearing them (#599).
        loaded[0].regenerate_geometry()
        assert _geometry_children(loaded[0]) == 4


class TestDxfExport:
    def test_emits_block_insert_not_flat(self, qtbot) -> None:
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        sym = SmartSymbolItem("raised_bed_rows", 2, {"rows": 4})
        scene.addItem(sym)
        sym.regenerate_geometry()
        sym.setPos(100, 50)

        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "s.dxf"
            DxfExportService.export(scene, fp)
            doc = ezdxf.readfile(str(fp))
            msp = doc.modelspace()
            inserts = [e for e in msp if e.dxftype() == "INSERT"]
            flat = [e for e in msp if e.dxftype() in ("LWPOLYLINE", "CIRCLE")]
            assert len(inserts) == 1
            assert len(flat) == 0  # children live in the block, not modelspace
            block = doc.blocks.get(inserts[0].dxf.name)
            assert len(list(block)) == 4
            assert inserts[0].dxf.insert.x == 100.0
            assert inserts[0].dxf.insert.y == 50.0


class TestTypedMembersAnd3DSnapshot:
    """Issue #599: typed smart-symbol members, 3D records, guides, and bed links."""

    def test_bundled_symbols_create_typed_children_and_3d_records(self, qtbot) -> None:
        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.core.scene3d import PARAM_PATH_STYLE
        from open_garden_planner.services.smart_symbol_library import (
            get_smart_symbol_library,
        )
        from open_garden_planner.ui.canvas.sun_shadow_controller import (
            collect_identified_casters,
        )
        from open_garden_planner.ui.view3d.snapshot import snapshot_records

        lib = get_smart_symbol_library()
        scene = CanvasScene(width_cm=5000, height_cm=3000)

        expected_primary = {
            "raised_bed_rows": ObjectType.RAISED_BED,
            "compost_bay_3": ObjectType.COMPOST_BIN,
            "greenhouse_gabled": ObjectType.GREENHOUSE,
            "fence_panel": ObjectType.FENCE,
            "pergola": ObjectType.PERGOLA,
        }
        for idx, (sym_id, primary_type) in enumerate(expected_primary.items()):
            defn = lib.get(sym_id)
            assert defn is not None and defn.version == 2
            sym = SmartSymbolItem(sym_id, defn.version, defn.param_defaults())
            scene.addItem(sym)
            sym.regenerate_geometry()
            sym.setPos(idx * 400.0, 100.0)
            child_types = [getattr(c, "object_type", None) for c in sym.childItems()]
            assert primary_type in child_types

        records = list(snapshot_records(scene).values())
        kinds = [r.kind for r in records]
        assert "RAISED_BED" in kinds
        assert "COMPOST_BIN" in kinds
        assert "GREENHOUSE" in kinds
        assert "PERGOLA" in kinds
        assert "FENCE" in kinds

        # Plain-panel dividers from raised_bed_rows (3) + compost_bay_3 (2) = 5 PLAIN fences,
        # plus 1 standard FENCE from fence_panel (6 total FENCE records; guides excluded).
        fence_records = [r for r in records if r.kind == "FENCE"]
        plain_records = [
            r for r in fence_records if r.params.get(PARAM_PATH_STYLE) == "PLAIN"
        ]
        assert len(plain_records) == 5
        assert len(fence_records) == 6
        assert sorted(round(r.height_cm) for r in plain_records) == [40, 40, 40, 100, 100]

        # Guides are also excluded from 2D shadow casters while typed members are included.
        casters = collect_identified_casters(scene)
        caster_ids = {c.item_id for c in casters}
        for item in scene.items():
            if isinstance(item, SmartSymbolItem):
                for child in item.childItems():
                    cid = str(getattr(child, "item_id", ""))
                    if getattr(child, "metadata", {}).get("smart_symbol_guide"):
                        assert cid not in caster_ids
                    else:
                        assert cid in caster_ids

    def test_raised_bed_rows_plant_parenting_regen_and_undo(
        self, qtbot, monkeypatch
    ) -> None:
        from open_garden_planner.core.commands import CreateItemCommand
        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.ui.canvas.items.circle_item import CircleItem

        win = _make_app(qtbot, monkeypatch)
        win.properties_panel.set_command_manager(win.canvas_view.command_manager)

        win._on_smart_symbol_selected("raised_bed_rows")
        sym = next(
            it for it in win.canvas_scene.items() if isinstance(it, SmartSymbolItem)
        )
        bed_child = next(
            c
            for c in sym.childItems()
            if getattr(c, "object_type", None) == ObjectType.RAISED_BED
        )
        bed_uuid_initial = bed_child.item_id
        bed_scene_center = bed_child.mapToScene(bed_child.boundingRect().center())

        # Place a plant inside the smart symbol's RAISED_BED child (on the same layer).
        plant = CircleItem(
            bed_scene_center.x(),
            bed_scene_center.y(),
            15.0,
            object_type=ObjectType.PERENNIAL,
            name="Tomato",
            layer_id=sym.layer_id,
        )
        win.canvas_view.command_manager.execute(
            CreateItemCommand(win.canvas_scene, plant, "plant")
        )
        assert plant.parent_bed_id == bed_uuid_initial
        assert plant.item_id in bed_child.child_item_ids
        assert plant.zValue() > sym.zValue()

        # Regenerating rows preserves deterministic bed child UUID and plant link.
        win.properties_panel.set_selected_items([sym])
        win.properties_panel._on_symbol_param_changed(sym, "rows", 6)
        new_bed_child = next(
            c
            for c in sym.childItems()
            if getattr(c, "object_type", None) == ObjectType.RAISED_BED
        )
        assert new_bed_child.item_id == bed_uuid_initial
        assert plant.parent_bed_id == bed_uuid_initial
        assert plant.item_id in new_bed_child.child_item_ids

        # Shrinking W so the plant falls outside unlinks the plant in the SAME undo step,
        # and undoing restores both W and the plant's parent_bed_id link.
        win.properties_panel._on_symbol_param_changed(sym, "W", 20.0)
        assert plant.parent_bed_id is None
        win.canvas_view.command_manager.undo()
        assert sym.params["W"] == 100
        assert plant.parent_bed_id == bed_uuid_initial

        # Transform-only movement carries the linked plant in one undoable command.
        from PyQt6.QtCore import QEvent, Qt
        from PyQt6.QtGui import QKeyEvent

        from open_garden_planner.ui.view3d.snapshot import snapshot_records

        win.canvas_scene.clearSelection()
        sym.setSelected(True)
        sym_pos_before = sym.pos()
        plant_pos_before = plant.pos()
        key_ev = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier
        )
        win.canvas_view._move_selected_items(key_ev)
        sym_delta = sym.pos() - sym_pos_before
        plant_delta = plant.pos() - plant_pos_before
        assert sym_delta.x() > 0.0
        assert abs(plant_delta.x() - sym_delta.x()) < 1e-6
        assert abs(plant_delta.y() - sym_delta.y()) < 1e-6
        assert plant.parent_bed_id == bed_uuid_initial

        # Two non-axis-aligned rotations (25 deg and 65 deg) preserve typed 3D records.
        for angle in (25.0, 65.0):
            sym.setRotation(angle)
            snap_recs = snapshot_records(win.canvas_scene)
            bed_rec = snap_recs[str(bed_uuid_initial)]
            assert bed_rec.kind == "RAISED_BED"
            assert abs((bed_rec.transform.rotation_deg - angle + 180.0) % 360.0 - 180.0) < 1e-3
        sym.setRotation(0.0)

        # Save and reopen preserves deterministic child UUIDs and plant->bed link.
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "bed_rows.ogp"
            ProjectManager().save(win.canvas_scene, fp)
            scene2 = CanvasScene(width_cm=5000, height_cm=3000)
            ProjectManager().load(scene2, fp)
            loaded_sym = next(
                it for it in scene2.items() if isinstance(it, SmartSymbolItem)
            )
            loaded_bed = next(
                c
                for c in loaded_sym.childItems()
                if getattr(c, "object_type", None) == ObjectType.RAISED_BED
            )
            loaded_plant = next(
                it
                for it in scene2.items()
                if isinstance(it, CircleItem) and it.name == "Tomato"
            )
            assert loaded_bed.item_id == bed_uuid_initial
            assert loaded_plant.parent_bed_id == bed_uuid_initial
            assert loaded_plant.item_id in loaded_bed.child_item_ids

    def test_invalid_param_edit_and_version_mismatch_read_only_in_panel(
        self, qtbot, monkeypatch
    ) -> None:
        from PyQt6.QtWidgets import QAbstractSpinBox, QLabel

        from open_garden_planner.models.smart_symbol import SmartSymbolDefinition
        from open_garden_planner.services.smart_symbol_library import (
            get_smart_symbol_library,
        )

        win = _make_app(qtbot, monkeypatch)
        win.properties_panel.set_command_manager(win.canvas_view.command_manager)

        definition = SmartSymbolDefinition.from_dict(
            {
                "id": "dz_panel",
                "version": 2,
                "name": "DZ Panel",
                "name_de": "DZ Panel",
                "category": "c",
                "parameters": [
                    {
                        "name": "n",
                        "type": "number",
                        "label": "N",
                        "default": 2,
                        "min": 0,
                        "max": 10,
                    }
                ],
                "elements": [
                    {"kind": "line", "x1": 0, "y1": 0, "x2": "10 / n", "y2": 0}
                ],
            }
        )
        lib = get_smart_symbol_library()
        lib._ensure_loaded()
        lib._symbols["dz_panel"] = definition

        win._on_smart_symbol_selected("dz_panel")
        sym = next(
            it
            for it in win.canvas_scene.items()
            if isinstance(it, SmartSymbolItem) and it.symbol_id == "dz_panel"
        )
        orig_children = list(sym.childItems())
        orig_undo_depth = len(win.canvas_view.command_manager._undo_stack)
        win.properties_panel.set_selected_items([sym])

        # Invalid parameter edit (n=0 -> ZeroDivisionError) is refused before command execution:
        # params, child object identities, and undo stack stay untouched.
        win.properties_panel._on_symbol_param_changed(sym, "n", 0)
        assert sym.params["n"] == 2
        assert list(sym.childItems()) == orig_children
        assert len(win.canvas_view.command_manager._undo_stack) == orig_undo_depth

        # Version mismatch shows read-only caution and disables parameter widgets.
        sym.symbol_version = 1
        win.properties_panel._current_identity = None
        win.properties_panel.set_selected_items([sym])
        labels = [
            w.text()
            for w in win.properties_panel.findChildren(QLabel)
            if "read-only" in w.text()
        ]
        assert len(labels) == 1
        spins = win.properties_panel.findChildren(QAbstractSpinBox)
        assert spins and all(not s.isEnabled() for s in spins)


def test_a_light_member_of_a_rotated_symbol_lights_and_survives_save(qtbot, monkeypatch) -> None:
    """L5's two lights joined #686's typed-member table on the merge: a STRING_LIGHTS and a
    GARDEN_LIGHT member of a rotated symbol instantiate as their own type, become 3D
    records that light (``lamp_sources``), and survive save and load (senior review of
    L5, round 5 — only the table's equality was pinned)."""
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.core.scene3d.lights import lamp_sources
    from open_garden_planner.models.smart_symbol import SmartSymbolDefinition
    from open_garden_planner.services.smart_symbol_library import get_smart_symbol_library
    from open_garden_planner.ui.view3d.snapshot import snapshot_records

    definition = SmartSymbolDefinition.from_dict({
        "id": "lit_pergola", "version": 1, "name": "Lit", "name_de": "Lit", "category": "c",
        "parameters": [],
        "elements": [
            {"kind": "rect", "x": 0, "y": 0, "w": 400, "h": 300, "object_type": "PERGOLA"},
            {"kind": "rect", "x": 0, "y": 135, "w": 400, "h": 30, "object_type": "STRING_LIGHTS",
             "member_key": "string"},
            {"kind": "circle", "cx": 450, "cy": 150, "r": 20, "object_type": "GARDEN_LIGHT",
             "member_key": "lamp"},
        ],
    })
    library = get_smart_symbol_library()
    library._ensure_loaded()
    monkeypatch.setitem(library._symbols, "lit_pergola", definition)

    def lights(scene: CanvasScene) -> list[tuple[str, int]]:
        return sorted((source.kind, len(source.bulb_points))
                      for source in lamp_sources(snapshot_records(scene).values()))

    scene = CanvasScene(width_cm=5000, height_cm=3000)
    symbol = SmartSymbolItem("lit_pergola", 1, {})
    scene.addItem(symbol)
    symbol.regenerate_geometry()
    symbol.setPos(1000, 1000)
    symbol.setRotation(30)
    kinds = {getattr(child, "object_type", None) for child in symbol.childItems()}
    assert {ObjectType.STRING_LIGHTS, ObjectType.GARDEN_LIGHT} <= kinds
    before = lights(scene)
    assert [kind for kind, _bulbs in before] == ["GARDEN_LIGHT", "STRING_LIGHTS"]
    assert all(bulbs >= 1 for _kind, bulbs in before)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "lit.ogp"
        ProjectManager().save(scene, path)
        scene.clear()
        ProjectManager().load(scene, path)
    assert lights(scene) == before, "the same lights after save and load"
