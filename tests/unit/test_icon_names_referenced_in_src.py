"""Code → file icon-name gate (Package 3c, #310, ADR-039 / ADR-042).

Before #310 `properties_panel.py` had requested ``lawn.svg`` — a file that
did not exist — since Phase 5, and the provider silently returned ``None``:
no test could see the drift because nothing cross-checked the names the CODE
requests against the files the SET ships. This gate closes that hole in both
directions that matter:

- every string literal passed to a provider entry point anywhere under
  ``src/`` (`get_icon("…")`, `get_pixmap("…")`, the app's `_set_action_icon`,
  `_make_icon_label`, `_set_tab_icon` helpers, the panels'
  `_themed_icon` / `_set_checkbox_icon`) names an existing icon;
- every icon name in the code-side lookup TABLES (plant-search type map,
  constraints-panel type map, seed-viability map, weather WMO map,
  properties-panel object-type map) exists.

The regex deliberately catches literals only — a name computed at runtime
still goes through the provider's own ``None`` fallback, which
`test_icon_system.py::test_unknown_icon_name_falls_back_to_text` pins.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from open_garden_planner.ui.icons import available_icons

_SRC = Path(__file__).parents[2] / "src" / "open_garden_planner"

# entry points whose FIRST or SECOND string argument is an icon name, plus the
# `.get(key, "fallback")` literals of icon lookup tables
_CALL_RE = re.compile(
    r"""(?:get_icon|get_pixmap|_themed_icon|_make_icon_label)\(\s*["']([a-z0-9_]+)["']"""
    r"""|(?:_set_action_icon|_set_tab_icon|_set_checkbox_icon)\([^,\n]+,\s*["']([a-z0-9_]+)["']"""
    r"""|_ICONS\.get\([^,\n]+,\s*["']([a-z0-9_]+)["']\)"""
)


def _referenced_literals() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for path in sorted(_SRC.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for m in _CALL_RE.finditer(text):
            name = m.group(1) or m.group(2) or m.group(3)
            found.setdefault(name, set()).add(str(path.relative_to(_SRC)))
    return found


REFERENCED = _referenced_literals()


def test_gate_sees_the_call_sites() -> None:
    """Sanity: the regex must actually find the app's icon calls (a silent
    regex mismatch would make this whole gate vacuous)."""
    assert len(REFERENCED) >= 100, len(REFERENCED)
    assert "zoom_in" in REFERENCED and "eye" in REFERENCED and "status_coords" in REFERENCED


@pytest.mark.parametrize("name", sorted(REFERENCED), ids=str)
def test_every_referenced_icon_name_exists(name: str) -> None:
    assert name in available_icons(), (
        f"code requests icon {name!r} (in {sorted(REFERENCED[name])}) but "
        "resources/icons/ui has no such file — vendor it or fix the name"
    )


def test_lookup_tables_name_existing_icons(qtbot) -> None:  # noqa: ARG001 — gallery thumbnails need Qt
    """Every code-side icon table, including the big toolbar/gallery ones."""
    from open_garden_planner.services.weather_service import _WMO_CODE_MAP, wmo_to_icon
    from open_garden_planner.ui.dialogs.seed_inventory_dialog import SeedTableModel
    from open_garden_planner.ui.panels.constraints_panel import _TYPE_ICONS as CONSTRAINT_ICONS
    from open_garden_planner.ui.panels.plant_search_panel import _TYPE_ICONS as PLANT_ICONS

    names = set(CONSTRAINT_ICONS.values()) | set(PLANT_ICONS.values())
    names |= set(SeedTableModel._VIA_ICONS.values())
    names |= {icon for _, icon in _WMO_CODE_MAP.values()} | {wmo_to_icon(-1)}
    # main toolbar / constraint toolbar / category chips / gallery entries: any
    # module-level mapping or dataclass field named *icon* that holds a name
    for module_name in (
        "open_garden_planner.ui.widgets.toolbar",
        "open_garden_planner.ui.widgets.constraint_toolbar",
        "open_garden_planner.ui.widgets.category_toolbar",
    ):
        module = __import__(module_name, fromlist=["_"])
        source = Path(module.__file__).read_text(encoding="utf-8")
        # toolbar rows: `ToolType.X, "icon_name", self.tr(...)`
        names |= set(re.findall(r"""ToolType\.[A-Z_]+,\s*["']([a-z0-9_]+)["']""", source))
        names |= set(re.findall(r"""(?:icon|icon_name)\s*[=:]\s*["']([a-z0-9_]+)["']""", source))
    # gallery: read the built objects, not the source (the tuple's last field is
    # polymorphic per builder — a shape key for containers, an icon name elsewhere)
    from open_garden_planner.ui.widgets.gallery_data import all_items, build_toolbar_categories

    categories = build_toolbar_categories()
    names |= {c.icon_name for c in categories if c.icon_name}
    names |= {i.icon_name for i in all_items(categories) if i.icon_name}
    assert len(names) >= 40, "the table sweep found suspiciously few names"
    missing = names - set(available_icons())
    assert not missing, missing


def test_properties_panel_object_type_icons_exist() -> None:
    """The map that used to request the non-existent `lawn.svg`."""
    source = (_SRC / "ui" / "panels" / "properties_panel.py").read_text(encoding="utf-8")
    names = set(re.findall(r'ObjectType\.[A-Z_]+:\s*"([a-z0-9_]+)"', source))
    assert "lawn" in names, "the lawn entry moved — update this test's anchor"
    missing = names - set(available_icons())
    assert not missing, missing
