"""Integration gate (§8.10) for the Package-3c iconography migration (#310).

`tests/integration/test_icon_system.py` covers the main window (menus, View
submenus, status bar, tabs, theme refresh). This file covers the panel- and
widget-level sites that used to render emoji / unicode pseudo-icons or a
private `QSvgRenderer` path, proving each now shows a PROVIDER icon (a real
pixmap, no glyph text) and — where the widget opts in — re-tints on a theme
switch through `refresh_theme_icons`.
"""

# ruff: noqa: ARG001, ARG002

import uuid

import pytest
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QApplication

from open_garden_planner.models.layer import Layer
from open_garden_planner.ui.panels.constraints_panel import _TYPE_ICONS as _CONSTRAINT_TYPE_ICONS
from open_garden_planner.ui.panels.constraints_panel import ConstraintListItem
from open_garden_planner.ui.panels.layers_panel import LayerListItem
from open_garden_planner.ui.panels.plant_search_panel import PlantSearchPanel
from open_garden_planner.ui.theme import ThemeMode, apply_theme
from open_garden_planner.ui.widgets.collapsible_panel import CollapsiblePanel
from open_garden_planner.ui.widgets.sun_sim_toolbar import SunSimToolbar


def _img(pixmap: QPixmap) -> QImage:
    return pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)


# Code-point ranges that count as pseudo-icons (one definition, used both by
# the widget-level checks and by the static source guard below): arrows,
# mathematical operators, misc technical, geometric shapes, misc symbols,
# dingbats, supplemental arrows/symbols, emoji pictographs.
PSEUDO_ICON_RANGES = [
    (0x2190, 0x21FF),  # arrows (→ ↔ ↕ ↳ ↺ …)
    (0x2200, 0x22FF),  # mathematical operators (∠ ∥ ⊾ ≡ …)
    (0x2300, 0x23FF),  # misc technical (⌒ …)
    (0x25A0, 0x25FF),  # geometric shapes (● ▶ ▼ ▾ ◯ …)
    (0x2600, 0x26FF),  # misc symbols (☀ ⛅ ★ ⚠ ❄ …)
    (0x2700, 0x27BF),  # dingbats (✓ ✗ …)
    (0x27C0, 0x2BFF),  # supplemental arrows / math / symbols (⟷ ⦿ …)
    (0x1F300, 0x1FAFF),  # emoji pictographs (🌳 🌿 🌸 🌱 📷 🔄 🔒 🌫 …)
]


def _is_pseudo_icon_char(ch: str) -> bool:
    o = ord(ch)
    return any(lo <= o <= hi for lo, hi in PSEUDO_ICON_RANGES)


def _has_glyph(text: str) -> bool:
    """True if a widget label/text carries a pseudo-icon character."""
    return any(_is_pseudo_icon_char(ch) for ch in text)


class TestLayersPanelProviderIcons:
    def test_eye_and_lock_are_provider_icons_and_retint(self, qtbot) -> None:
        item = LayerListItem(Layer(name="Test"))
        qtbot.addWidget(item)
        assert not item.visibility_btn.icon().isNull()
        assert not item.lock_btn.icon().isNull()
        app = QApplication.instance()
        apply_theme(app, ThemeMode.LIGHT)
        try:
            light = _img(item.visibility_btn.icon().pixmap(QSize(20, 20)))
            apply_theme(app, ThemeMode.DARK)  # propagates refresh_theme_icons to the item
            dark = _img(item.visibility_btn.icon().pixmap(QSize(20, 20)))
            assert light != dark, "layer eye icon did not re-tint on theme switch"
        finally:
            apply_theme(app, ThemeMode.LIGHT)

    def test_state_changes_swap_icons(self, qtbot) -> None:
        """The buttons only emit; the panel pushes the new state back through
        `update_layer` (pre-existing flow) — that path must swap eye/eye_off
        and lock/lock_open."""
        layer = Layer(name="Test", visible=True, locked=False)
        item = LayerListItem(layer)
        qtbot.addWidget(item)
        open_eye = _img(item.visibility_btn.icon().pixmap(QSize(20, 20)))
        open_lock = _img(item.lock_btn.icon().pixmap(QSize(20, 20)))
        item.update_layer(Layer(name="Test", visible=False, locked=True, id=layer.id))
        assert _img(item.visibility_btn.icon().pixmap(QSize(20, 20))) != open_eye
        assert _img(item.lock_btn.icon().pixmap(QSize(20, 20))) != open_lock


class TestPanelsAndWidgets:
    def test_plant_search_type_filters_carry_icons_not_emoji(self, qtbot) -> None:
        panel = PlantSearchPanel()
        qtbot.addWidget(panel)
        for checkbox in (panel.tree_checkbox, panel.shrub_checkbox, panel.perennial_checkbox):
            assert not checkbox.icon().isNull()
            assert not _has_glyph(checkbox.text()), checkbox.text()

    def test_plant_list_item_type_icon_retints(self, qtbot) -> None:
        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.ui.panels.plant_search_panel import PlantListItem

        item = PlantListItem(uuid.uuid4(), "Apple", "Malus domestica", ObjectType.TREE)
        qtbot.addWidget(item)
        app = QApplication.instance()
        apply_theme(app, ThemeMode.LIGHT)
        try:
            light = _img(item._type_label.pixmap())
            apply_theme(app, ThemeMode.DARK)
            assert _img(item._type_label.pixmap()) != light
        finally:
            apply_theme(app, ThemeMode.LIGHT)

    def test_journal_and_companion_row_icons_retint(self, qtbot) -> None:
        """Rows are `QListWidgetItem`s: the panels re-set their icons through
        `refresh_theme_icons` (flag stored in a data role)."""
        from PyQt6.QtWidgets import QListWidgetItem

        from open_garden_planner.ui.panels.companion_panel import _NEARBY_ROLE, CompanionPanel
        from open_garden_planner.ui.panels.journal_panel import _HAS_PHOTO_ROLE, JournalPanel

        journal = JournalPanel()
        qtbot.addWidget(journal)
        row = QListWidgetItem("2026-08-18 — note")
        row.setData(_HAS_PHOTO_ROLE, True)
        journal._list.addItem(row)
        from open_garden_planner.services.companion_planting_service import CompanionPlantingService

        companion = CompanionPanel(CompanionPlantingService())
        qtbot.addWidget(companion)
        entry = QListWidgetItem("basil")
        entry.setData(_NEARBY_ROLE, True)
        companion._good_list.addItem(entry)
        app = QApplication.instance()
        apply_theme(app, ThemeMode.LIGHT)
        try:
            journal.refresh_theme_icons()
            companion.refresh_theme_icons()
            j_light = _img(row.icon().pixmap(QSize(16, 16)))
            c_light = _img(entry.icon().pixmap(QSize(16, 16)))
            legend_light = _img(companion._legend_icon.pixmap())
            apply_theme(app, ThemeMode.DARK)
            assert _img(row.icon().pixmap(QSize(16, 16))) != j_light, "journal camera icon did not re-tint"
            assert _img(entry.icon().pixmap(QSize(16, 16))) != c_light, "companion star did not re-tint"
            assert _img(companion._legend_icon.pixmap()) != legend_light
        finally:
            apply_theme(app, ThemeMode.LIGHT)

    def test_succession_notes_are_list_rows_with_icons(self, qtbot, monkeypatch) -> None:
        from open_garden_planner.ui.dialogs.succession_plan_dialog import (
            _NOTE_KIND_ROLE,
            SuccessionPlanDialog,
        )

        dlg = SuccessionPlanDialog(bed_name="Bed A")
        qtbot.addWidget(dlg)
        monkeypatch.setattr(
            dlg, "_compute_companion_notes",
            lambda: [("good", "A → B: fine"), ("warn", "A overlaps B: antagonist"), ("neutral", "A → C: n/a")],
        )
        dlg._refresh_companion_notes()
        rows = [dlg._companion_list.item(i) for i in range(dlg._companion_list.count())]
        assert [r.data(_NOTE_KIND_ROLE) for r in rows] == ["good", "warn", "neutral"]
        assert not rows[0].icon().isNull() and not rows[1].icon().isNull() and rows[2].icon().isNull()
        # no ✓ / ⚠ / · prefix in the text (the → between names is prose)
        assert all(not _has_glyph(r.text()[:2]) for r in rows)

    @pytest.mark.parametrize("type_name", sorted(_CONSTRAINT_TYPE_ICONS))
    def test_constraint_row_shows_type_icon_and_no_glyph_prefix(self, qtbot, type_name: str) -> None:
        """Every constraint type: exactly ONE status dot + ONE type icon (a
        duplicated block once shipped three type icons per row — review
        2026-08-18), no pseudo-icon glyph anywhere in the row's text or
        tooltip, and the delete button is an icon, not a "×"."""
        row = ConstraintListItem(uuid.uuid4(), "Bed A", "Bed B", 120.0, True, type_name)
        qtbot.addWidget(row)
        from PyQt6.QtWidgets import QLabel, QToolButton

        labels = row.findChildren(QLabel)
        pixmap_labels = [lbl for lbl in labels if lbl.pixmap() is not None and not lbl.pixmap().isNull()]
        assert len(pixmap_labels) == 2, f"status dot + type icon expected, got {len(pixmap_labels)}"
        texts = [lbl.text() for lbl in labels if lbl.text()] + [lbl.toolTip() for lbl in labels if lbl.toolTip()]
        assert texts and not any(_has_glyph(t) for t in texts), texts
        delete_btn = row.findChild(QToolButton)
        assert delete_btn is not None and not delete_btn.icon().isNull() and delete_btn.text() == ""

    def test_constraint_row_retints_on_theme_switch(self, qtbot) -> None:
        row = ConstraintListItem(uuid.uuid4(), "Bed A", "Bed B", 120.0, True, "FIXED")
        qtbot.addWidget(row)
        app = QApplication.instance()
        apply_theme(app, ThemeMode.LIGHT)
        try:
            light = _img(row._type_label.pixmap())
            apply_theme(app, ThemeMode.DARK)
            assert _img(row._type_label.pixmap()) != light, "constraint type icon did not re-tint"
        finally:
            apply_theme(app, ThemeMode.LIGHT)

    def test_collapsible_panel_chevron_is_a_pixmap(self, qtbot) -> None:
        panel = CollapsiblePanel("Title", expanded=True)
        qtbot.addWidget(panel)
        assert panel._indicator.pixmap() is not None and not panel._indicator.pixmap().isNull()
        assert panel._indicator.text() == ""
        expanded_img = _img(panel._indicator.pixmap())
        panel.set_expanded(False, emit=False)
        assert _img(panel._indicator.pixmap()) != expanded_img
        panel.set_info_tooltip("hint")
        assert panel._info_label.pixmap() is not None and not panel._info_label.pixmap().isNull()

    def test_view3d_toolbar_actions_carry_icons(self, qtbot) -> None:
        pytest.importorskip("PyQt6.Qt3DCore")
        from open_garden_planner.ui.view3d.view3d_window import View3DWindow

        try:
            win = View3DWindow()
        except Exception:  # noqa: BLE001 — no GL / no Qt3D on this machine
            pytest.skip("Qt3D window not constructible here")
        qtbot.addWidget(win)
        assert not win._refresh_action.icon().isNull()
        assert not win._walk_action.icon().isNull()

    def test_sun_sim_toolbar_buttons_carry_icons(self, qtbot) -> None:
        bar = SunSimToolbar()
        qtbot.addWidget(bar)
        assert not bar._animate_button.icon().isNull()
        assert not bar._heatmap_button.icon().isNull()
        assert bar._time_icon.pixmap() is not None and not bar._time_icon.pixmap().isNull()
        play = _img(bar._animate_button.icon().pixmap(QSize(20, 20)))
        bar._animate_button.setChecked(True)  # play → pause
        assert _img(bar._animate_button.icon().pixmap(QSize(20, 20))) != play
        bar._animate_button.setChecked(False)


class TestNoEmojiInChromeSources:
    """Static guard over the migrated modules: no pseudo-icon character
    (PSEUDO_ICON_RANGES — arrows, math operators, technical, geometric,
    misc symbols, dingbats, supplemental symbols, pictographs) may appear in
    CODE outside the documented prose exceptions below. Comments are ignored;
    the exceptions are the textual arrows inside sentences that §8.21.5 keeps
    ("File → Set Garden Location", "A → B: reason", "5.8 → 6.5")."""

    # (module, substring) pairs that are prose, not chrome — each one is a
    # deliberate §8.21.5 exception, listed so the guard stays honest
    PROSE_EXCEPTIONS = {
        ("app/application.py", "File → Set Garden Location"),
        ("ui/dialogs/succession_plan_dialog.py", "{a.common_name} → {b.common_name}"),
    }
    MODULES = [
        "app/application.py",
        "ui/panels/layers_panel.py",
        "ui/panels/plant_search_panel.py",
        "ui/panels/companion_panel.py",
        "ui/panels/journal_panel.py",
        "ui/panels/constraints_panel.py",
        "ui/views/planting_calendar_view.py",
        "ui/views/tasks_view.py",
        "ui/views/seed_inventory_view.py",
        "ui/dialogs/seed_inventory_dialog.py",
        "ui/dialogs/season_manager_dialog.py",
        "ui/widgets/collapsible_panel.py",
        "ui/widgets/weather_widget.py",
        "services/weather_service.py",
        "ui/theme.py",
        "ui/dialogs/succession_plan_dialog.py",
        "ui/dialogs/shortcuts_dialog.py",
        "ui/view3d/view3d_window.py",
        "ui/widgets/sun_sim_toolbar.py",
    ]

    @staticmethod
    def _string_literals(source_path):
        """(lineno, text) of every string literal that is NOT a docstring —
        chrome text lives in literals; docstrings/comments are prose."""
        import ast
        import io
        import tokenize

        text = source_path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        doc_lines: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                body = getattr(node, "body", [])
                if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant)                         and isinstance(body[0].value.value, str):
                    doc_lines.update(range(body[0].lineno, body[0].end_lineno + 1))
        out = []
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.STRING and tok.start[0] not in doc_lines:
                out.append((tok.start[0], tok.string))
        return out

    @pytest.mark.parametrize("module", MODULES)
    def test_no_banned_glyph_in_code(self, module: str) -> None:
        from pathlib import Path

        src = Path(__file__).parents[2] / "src" / "open_garden_planner" / module
        exceptions = [frag for mod, frag in self.PROSE_EXCEPTIONS if mod == module]
        offenders = []
        for lineno, literal in self._string_literals(src):
            if any(frag in literal for frag in exceptions):
                continue
            if any(_is_pseudo_icon_char(ch) for ch in literal):
                offenders.append((lineno, literal[:80]))
        assert offenders == [], offenders

    def test_prose_exceptions_still_exist(self) -> None:
        """An exception whose text vanished would silently widen the guard."""
        from pathlib import Path

        for mod, frag in self.PROSE_EXCEPTIONS:
            src = Path(__file__).parents[2] / "src" / "open_garden_planner" / mod
            assert frag in src.read_text(encoding="utf-8"), (mod, frag)
