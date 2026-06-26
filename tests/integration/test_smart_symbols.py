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
        pos_before = (sym.pos().x(), sym.pos().y())

        win.properties_panel.set_command_manager(win.canvas_view.command_manager)
        win.properties_panel.set_selected_items([sym])
        win.properties_panel._on_symbol_param_changed(sym, "rows", 7)
        assert _geometry_children(sym) == 7
        assert (sym.pos().x(), sym.pos().y()) == pos_before  # position preserved

        win.canvas_view.command_manager.undo()
        assert _geometry_children(sym) == 4
        win.canvas_view.command_manager.redo()
        assert _geometry_children(sym) == 7

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
    def manager(self, qtbot) -> ProjectManager:  # noqa: ARG002
        return ProjectManager()

    def test_round_trips_as_parametric(self, manager, qtbot) -> None:  # noqa: ARG002
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        sym = SmartSymbolItem("raised_bed_rows", 1, {"rows": 5})
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

    def test_missing_definition_uses_cached_geometry(self, manager, qtbot) -> None:  # noqa: ARG002
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        sym = SmartSymbolItem("raised_bed_rows", 1, {"rows": 4})
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

    def test_version_mismatch_uses_cached_geometry(self, manager, qtbot) -> None:  # noqa: ARG002
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


class TestDxfExport:
    def test_emits_block_insert_not_flat(self, qtbot) -> None:  # noqa: ARG002
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        sym = SmartSymbolItem("raised_bed_rows", 1, {"rows": 4})
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
