"""Small source projects for exercising the real translation gate in isolation."""

import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.compile_translations import compile_ts_file
from scripts.i18n_sources import inventory, supported_languages


def project(root: Path) -> Path:
    base = root / "src/open_garden_planner"
    (base / "core").mkdir(parents=True)
    (base / "core/i18n.py").write_text(
        'SUPPORTED_LANGUAGES: dict[str, str] = {"en": "English", "de": "Deutsch", "es": "Español"}\n',
        encoding="utf-8",
    )
    (base / "dialog.py").write_text(
        'class Dialog:\n    def build(self):\n        self.tr("Hello {name}")\n', encoding="utf-8"
    )
    catalogs(root)
    return root


def catalogs(root: Path) -> None:
    base = root / "src/open_garden_planner/resources/translations"
    base.mkdir(parents=True, exist_ok=True)
    for locale in supported_languages(root):
        document = ET.Element("TS", language=locale)
        contexts: dict[str, ET.Element] = {}
        for key in sorted(inventory(root)):
            if key.context not in contexts:
                contexts[key.context] = ET.SubElement(document, "context")
                ET.SubElement(contexts[key.context], "name").text = key.context
            message = ET.SubElement(contexts[key.context], "message")
            ET.SubElement(message, "source").text = key.source
            if key.comment:
                ET.SubElement(message, "comment").text = key.comment
            ET.SubElement(message, "translation").text = (
                "" if locale == "en" else locale + " "
            ) + key.source
        path = base / f"open_garden_planner_{locale}.ts"
        ET.ElementTree(document).write(path, encoding="utf-8", xml_declaration=True)
        compile_ts_file(path)


def catalog_path(root: Path, locale: str = "es") -> Path:
    return root / f"src/open_garden_planner/resources/translations/open_garden_planner_{locale}.ts"
