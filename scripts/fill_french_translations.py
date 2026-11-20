"""Fill in French translations for open_garden_planner_fr.ts.

Merges the modular French catalogs in ``scripts.translations_fr``. The catalog
was first brought upstream from Sevoiger/open-garden-planner PR #2, rebased on
the current source by ``scripts/update_translations.py``; this module completes
the keys added after that fork branched.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.i18n_catalog import Key
from scripts.i18n_sources import inventory
from scripts.translations_fr.app import TRANSLATIONS as T_APP
from scripts.translations_fr.canvas import TRANSLATIONS as T_CANVAS
from scripts.translations_fr.reference_points import TRANSLATIONS as T_REFERENCE
from scripts.translations_fr.workspace import TRANSLATIONS as T_WORKSPACE

if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
TS_FILE = (
    ROOT
    / "src"
    / "open_garden_planner"
    / "resources"
    / "translations"
    / "open_garden_planner_fr.ts"
)


def get_french_translations() -> dict[str, dict[str, str]]:
    """Assemble the modular French translations into one dictionary."""
    assembled: dict[str, dict[str, str]] = {}
    for module_trans in (T_WORKSPACE, T_APP, T_CANVAS, T_REFERENCE):
        for context, mapping in module_trans.items():
            assembled.setdefault(context, {}).update(mapping)
    return assembled


def fill_french_translations() -> None:
    """Fill the current French catalog from the modular translations."""
    if not TS_FILE.exists():
        raise FileNotFoundError(f"Translation file not found: {TS_FILE}")

    tree = ET.parse(TS_FILE)
    root = tree.getroot()
    required = inventory(ROOT)

    root.set("language", "fr")

    filled = 0
    missing: list[tuple[str, str]] = []
    french_translations = get_french_translations()

    for context_elem in root.findall("context"):
        name_elem = context_elem.find("name")
        if name_elem is None or not name_elem.text:
            continue
        context_name = name_elem.text
        context_trans = french_translations.get(context_name, {})

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
            elif translation_elem.get("type") in {"unfinished", "vanished", "obsolete"}:
                missing.append((context_name, source_text))

    ET.indent(tree, space="    ")
    tree.write(TS_FILE, encoding="utf-8", xml_declaration=True)

    content = TS_FILE.read_text(encoding="utf-8")
    content = content.replace(
        "<?xml version='1.0' encoding='utf-8'?>",
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>',
    )
    TS_FILE.write_text(content, encoding="utf-8", newline="\n")

    if missing:
        print(f"Warning: {len(missing)} French translations are missing in {TS_FILE.name}:")
        for context, source in missing[:15]:
            print(f"  [{context}]: {source!r}")

    print(
        f"Successfully filled {filled} French translations in {TS_FILE.name} "
        f"({len(missing)} missing)."
    )


if __name__ == "__main__":
    fill_french_translations()
