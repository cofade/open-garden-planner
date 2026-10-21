"""Fill in Spanish translations for open_garden_planner_es.ts.

Merges translations from:
- scripts.translations_es.commands_services
- scripts.translations_es.objects_gallery
- scripts.translations_es.canvas_tools
- scripts.translations_es.panels
- scripts.translations_es.dialogs
- scripts.translations_es.app_menus
- scripts.translations_es.view3d
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.i18n_catalog import Key
from scripts.i18n_sources import inventory
from scripts.translations_es.app_menus import TRANSLATIONS as T_APP
from scripts.translations_es.canvas_tools import TRANSLATIONS as T_CT
from scripts.translations_es.commands_services import TRANSLATIONS as T_CS
from scripts.translations_es.dialogs import TRANSLATIONS as T_DIALOGS
from scripts.translations_es.objects_gallery import TRANSLATIONS as T_OG
from scripts.translations_es.panels import TRANSLATIONS as T_PANELS
from scripts.translations_es.view3d import TRANSLATIONS as T_VIEW3D
from scripts.translations_f4 import ES as T_F4

if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
TS_FILE = (
    ROOT
    / "src"
    / "open_garden_planner"
    / "resources"
    / "translations"
    / "open_garden_planner_es.ts"
)

def get_spanish_translations() -> dict[str, dict[str, str]]:
    """Assemble modular Spanish translations into a unified dictionary."""
    assembled: dict[str, dict[str, str]] = {}
    for module_trans in (T_CS, T_OG, T_CT, T_PANELS, T_DIALOGS, T_APP, T_VIEW3D, T_F4):
        for ctx, mapping in module_trans.items():
            assembled.setdefault(ctx, {}).update(mapping)
    return assembled


def fill_spanish_translations() -> None:
    """Fill in Spanish translations in open_garden_planner_es.ts."""
    if not TS_FILE.exists():
        raise FileNotFoundError(f"Translation file not found: {TS_FILE}")

    tree = ET.parse(TS_FILE)
    root = tree.getroot()
    required = inventory(ROOT)

    root.set("language", "es")

    filled = 0
    missing: list[tuple[str, str]] = []
    spanish_translations = get_spanish_translations()

    for context_elem in root.findall("context"):
        name_elem = context_elem.find("name")
        if name_elem is None or not name_elem.text:
            continue
        context_name = name_elem.text
        context_trans = spanish_translations.get(context_name, {})

        for message_elem in context_elem.findall("message"):
            source_elem = message_elem.find("source")
            translation_elem = message_elem.find("translation")

            if source_elem is None or translation_elem is None:
                continue

            source_text = source_elem.text or ""
            comment_elem = message_elem.find("comment")
            comment_text = (comment_elem.text or "") if comment_elem is not None else ""
            if Key(context_name, source_text, comment_text) not in required:
                continue

            if source_text in context_trans:
                translation_elem.text = context_trans[source_text]
                if "type" in translation_elem.attrib:
                    del translation_elem.attrib["type"]
                filled += 1
            else:
                missing.append((context_name, source_text))

    # Format XML nicely and save
    ET.indent(tree, space="    ")
    tree.write(TS_FILE, encoding="utf-8", xml_declaration=True)

    # Post-process to ensure correct DOCTYPE
    content = TS_FILE.read_text(encoding="utf-8")
    content = content.replace(
        "<?xml version='1.0' encoding='utf-8'?>",
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>',
    )
    TS_FILE.write_text(content, encoding="utf-8")

    if missing:
        print(f"Warning: {len(missing)} Spanish translations are missing in {TS_FILE.name}:")
        for ctx, src in missing[:15]:
            print(f"  [{ctx}]: {src!r}")

    print(f"Successfully filled {filled} Spanish translations in {TS_FILE.name} ({len(missing)} missing).")


if __name__ == "__main__":
    fill_spanish_translations()

