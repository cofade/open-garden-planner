"""Explicitly reconcile catalog structure to live source; never invent target text."""

from __future__ import annotations

import argparse
import copy
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.i18n_catalog import CatalogError, Key  # noqa: E402
from scripts.i18n_sources import inventory, supported_languages  # noqa: E402


def update(root: Path) -> None:
    sources = inventory(root)
    for locale in supported_languages(root):
        path = (
            root
            / "src/open_garden_planner/resources/translations"
            / f"open_garden_planner_{locale}.ts"
        )
        previous: dict[Key, ET.Element] = {}
        if path.exists():
            for context in ET.parse(path).getroot().findall("context"):
                for node in context.findall("message"):
                    key = Key(
                        context.findtext("name", ""),
                        node.findtext("source", ""),
                        node.findtext("comment", ""),
                    )
                    if key in previous:
                        raise CatalogError(f"{path}: duplicate key {key}; resolve before updating")
                    previous[key] = node
        document = ET.Element("TS", version="2.1", language=locale, sourcelanguage="en")
        contexts: dict[str, ET.Element] = {}
        for key in sorted(sources.keys() | previous.keys()):
            if key.context not in contexts:
                contexts[key.context] = ET.SubElement(document, "context")
                ET.SubElement(contexts[key.context], "name").text = key.context
            message = copy.deepcopy(previous[key]) if key in previous else ET.Element("message")
            for location in list(message.findall("location")):
                message.remove(location)
            if key in sources:
                for index, (file, line) in enumerate(sorted(sources[key])):
                    message.insert(
                        index, ET.Element("location", filename="../../" + file, line=line)
                    )
            source = message.find("source")
            if source is None:
                ET.SubElement(message, "source").text = key.source
                if key.comment:
                    ET.SubElement(message, "comment").text = key.comment
            translation = message.find("translation")
            if translation is None:
                translation = ET.SubElement(message, "translation", type="unfinished")
            if key not in sources:
                translation.set("type", "vanished")
            elif locale == "en":
                translation.attrib.pop("type", None)
                translation.text = key.source
            elif translation.get("type") in {"vanished", "obsolete"}:
                translation.set("type", "unfinished")
            contexts[key.context].append(message)
        ET.indent(document, space="    ")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n'
            + ET.tostring(document, encoding="unicode")
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(
            f"Updated {path.name}: {len(sources)} live keys; complete new target translations before compiling."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    update(args.root.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
