"""The translation contract must fail for missing source OR locale coverage."""

from pathlib import Path

import pytest
from scripts.check_translations import check
from scripts.compile_translations import parse_ts_file
from scripts.i18n_catalog import CatalogError, placeholder_error
from scripts.i18n_sources import inventory

from tests.translation_helpers import catalog_path, catalogs, project


def write_ts(path: Path, translation: str, *, state: str = "", extra: str = "") -> Path:
    path.write_text(
        '<TS language="de_DE"><context><name>Dialog</name><message>'
        "<source>Hello {name}</source>"
        f'<translation type="{state}">{translation}</translation>'
        f"</message>{extra}</context></TS>",
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    "translation,state",
    [
        ("", ""),
        ("  ", ""),
        ("Hallo {name}", "unfinished"),
        ("Hallo", ""),
    ],
)
def test_compiler_refuses_incomplete_target(tmp_path, translation, state):
    path = write_ts(tmp_path / "test_de.ts", translation, state=state)
    with pytest.raises(CatalogError):
        parse_ts_file(path)


def test_compiler_excludes_vanished_translations(tmp_path):
    path = write_ts(tmp_path / "test_de.ts", "Hallo {name}", state="vanished")
    assert parse_ts_file(path) == []


@pytest.mark.parametrize(
    "source,target,error",
    [
        ("{a} {b}", "{b} {a}", False),
        ("{a:.2f}", "{a:.1f}", True),
        ("{a!r}", "{a}", True),
        ("%1 %2", "%2 %1", False),
        ("%1", "%2", True),
        ("Ctrl+S", "Ctrl+S", False),
        ("{{literal}} {a}", "{{literal}} {a}", False),
        ("{a:{width}}", "{a:{height}}", True),
    ],
)
def test_placeholders(source, target, error):
    assert bool(placeholder_error(source, target)) == error


def test_third_language_companion_reason_uses_english(qtbot):
    from open_garden_planner.services.companion_planting_service import (
        CompanionPlantingService,
        CompanionRelationship,
    )

    relationship = CompanionRelationship("tomato", "basil", "beneficial", "English", "Deutsch")
    service = CompanionPlantingService()
    assert service.get_relationship_reason(relationship, "es") == "English"


@pytest.fixture
def checked_project(tmp_path, qtbot):
    return project(tmp_path)


def test_complete_third_locale_is_discovered(checked_project):
    assert check(checked_project) == []


@pytest.mark.parametrize("change", ["missing", "wrong_context", "wrong_comment", "different_key"])
def test_equal_counts_cannot_hide_wrong_keys(checked_project, change):
    import xml.etree.ElementTree as ET

    path = catalog_path(checked_project)
    tree = ET.parse(path)
    if change == "missing":
        tree.getroot().remove(tree.getroot().find("context"))
    elif change == "wrong_context":
        tree.find("context/name").text = "OtherDialog"
    elif change == "wrong_comment":
        ET.SubElement(tree.find("context/message"), "comment").text = "Other meaning"
    else:
        tree.find("context/message/source").text = "Other {name}"
    tree.write(path, encoding="utf-8")
    errors = check(checked_project)
    assert any("es: missing [Dialog] 'Hello {name}'" in error for error in errors)


def test_new_source_requires_every_language(checked_project):
    base = checked_project / "src/open_garden_planner"
    path = base / "dialog.py"
    path.write_text(path.read_text() + '        self.tr("New button")\n', encoding="utf-8")
    errors = check(checked_project)
    assert all(
        any(error.startswith(locale + ": missing") and "New button" in error for error in errors)
        for locale in ("en", "de", "es")
    )
    # Updating German alone must still leave the other locales red.
    previous = {
        locale: catalog_path(checked_project, locale).read_bytes() for locale in ("en", "es")
    }
    catalogs(checked_project)
    for locale, content in previous.items():
        catalog_path(checked_project, locale).write_bytes(content)
    errors = check(checked_project)
    assert not any(error.startswith("de:") for error in errors)
    assert all(
        any(error.startswith(locale + ": missing") and "New button" in error for error in errors)
        for locale in ("en", "es")
    )


def test_deleting_key_from_every_catalog_still_fails(checked_project):
    import xml.etree.ElementTree as ET

    for locale in ("en", "de", "es"):
        ET.ElementTree(ET.Element("TS", language=locale)).write(
            catalog_path(checked_project, locale)
        )
    errors = check(checked_project)
    assert sum("missing [Dialog]" in error for error in errors) == 3


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate",
        "blank",
        "unfinished",
        "obsolete",
        "numerus",
        "malformed",
        "missing_file",
        "stale_binary",
        "missing_binary",
    ],
)
def test_catalog_and_binary_mutations_fail(checked_project, mutation):
    import copy
    import xml.etree.ElementTree as ET

    path = catalog_path(checked_project)
    tree = ET.parse(path)
    message = tree.find("context/message")
    if mutation == "duplicate":
        tree.find("context").append(copy.deepcopy(message))
    elif mutation == "blank":
        message.find("translation").text = "  "
    elif mutation in ("unfinished", "obsolete"):
        message.find("translation").set("type", mutation)
    elif mutation == "numerus":
        message.set("numerus", "yes")
    tree.write(path, encoding="utf-8")
    if mutation == "malformed":
        path.write_text("<broken", encoding="utf-8")
    elif mutation == "missing_file":
        path.unlink()
    elif mutation == "stale_binary":
        path.with_suffix(".qm").write_bytes(b"corrupt")
    elif mutation == "missing_binary":
        path.with_suffix(".qm").unlink()
    errors = check(checked_project)
    assert errors and any(error.startswith("es:") for error in errors)


def test_unicode_disambiguation_and_identical_text(checked_project):
    path = checked_project / "src/open_garden_planner/dialog.py"
    path.write_text(
        'class Dialog:\n    def build(self):\n        self.tr("More…", "menu")\n        self.tr("More…", "button")\n        self.tr("Ctrl+S")\n',
        encoding="utf-8",
    )
    catalogs(checked_project)
    assert check(checked_project) == []


def test_qt_alias_and_simple_wrapper_are_extracted(checked_project):
    path = checked_project / "src/open_garden_planner/labels.py"
    path.write_text(
        'from PyQt6.QtCore import QCoreApplication as Core\ntranslate = Core.translate\ndef label(text):\n    return translate("Labels", text)\nlabel("New {name}")\n',
        encoding="utf-8",
    )
    errors = check(checked_project)
    assert any("es: missing [Labels] 'New {name}'" in error for error in errors)
    path.write_text(path.read_text() + "label(unknown_value)\n", encoding="utf-8")
    with pytest.raises(CatalogError, match="unresolved dynamic source"):
        inventory(checked_project)


def test_finite_table_grows_inventory_and_stale_bindings_fail(checked_project):
    import json

    path = checked_project / "src/open_garden_planner/labels.py"
    source = 'from PyQt6.QtCore import QCoreApplication, QT_TR_NOOP\nLABELS = {"one": QT_TR_NOOP("One")}\ndef label(key):\n    return QCoreApplication.translate("Labels", LABELS[key])\n'
    path.write_text(source, encoding="utf-8")
    directory = checked_project / "scripts"
    directory.mkdir()
    declarations = {
        "sources": {
            "labels": {
                "file": "labels.py",
                "context": "Labels",
                "symbol": "LABELS",
                "selector": "markers",
            }
        },
        "lookups": [
            {
                "file": "labels.py",
                "scope": "label",
                "expression": "LABELS[key]",
                "context": "Labels",
                "sources": ["labels"],
            }
        ],
    }
    (directory / "i18n_bindings.json").write_text(json.dumps(declarations), encoding="utf-8")
    catalogs(checked_project)
    assert check(checked_project) == []
    path.write_text(
        source.replace(
            '"one": QT_TR_NOOP("One")', '"one": QT_TR_NOOP("One"), "two": QT_TR_NOOP("Two")'
        ),
        encoding="utf-8",
    )
    assert any("es: missing [Labels] 'Two'" in error for error in check(checked_project))
    path.write_text(source.replace("LABELS[key]", '"One"'), encoding="utf-8")
    with pytest.raises(CatalogError, match="stale source binding"):
        inventory(checked_project)


def test_update_preserves_targets_and_marks_new_ones_unfinished(checked_project):
    from scripts.i18n_catalog import active_messages, read_catalog
    from scripts.update_translations import update

    path = checked_project / "src/open_garden_planner/dialog.py"
    path.write_text(path.read_text() + '        self.tr("New button")\n', encoding="utf-8")
    update(checked_project)
    messages = {
        m.key.source: m for m in active_messages(read_catalog(catalog_path(checked_project))[1])
    }
    assert messages["Hello {name}"].translation == "es Hello {name}"
    assert messages["New button"].state == "unfinished"
    assert messages["New button"].translation == ""
    first = catalog_path(checked_project).read_bytes()
    update(checked_project)
    assert catalog_path(checked_project).read_bytes() == first


@pytest.mark.parametrize(
    "statement",
    [
        'from PyQt6.QtCore import QCoreApplication\nQCoreApplication.translate("Labels", unknown_value)',
        'from PyQt6.QtWidgets import QApplication\nQApplication.translate("Labels", unknown_value)',
        "class Dialog:\n    def build(self):\n        self.tr(unknown_value)",
        'class Dialog:\n    def build(self):\n        self.tr("Count %n", None, n=2)',
        'from PyQt6.QtCore import QT_TR_NOOP as mark\nmark("Hidden")',
        'class Dialog:\n    def build(self):\n        mark = self.tr\n        mark("Hidden")',
    ],
)
def test_unresolved_sources_and_unsupported_plural_fail_closed(checked_project, statement):
    (checked_project / "src/open_garden_planner/unsupported.py").write_text(
        statement, encoding="utf-8"
    )
    with pytest.raises(CatalogError):
        inventory(checked_project)


def test_obsolete_plural_record_is_ignored(tmp_path):
    path = tmp_path / "test_de.ts"
    path.write_text(
        '<TS language="de"><context><name>Dialog</name><message numerus="yes"><source>%n old</source><translation type="vanished"><numerusform>alt</numerusform></translation></message></context></TS>',
        encoding="utf-8",
    )
    assert parse_ts_file(path) == []


def test_wrapper_keyword_source_is_checked(checked_project):
    path = checked_project / "src/open_garden_planner/labels.py"
    path.write_text(
        'from PyQt6.QtCore import QCoreApplication\ndef _tr(source):\n'
        '    return QCoreApplication.translate("Labels", source)\n'
        '_tr(source="Keyword label")\n', encoding="utf-8"
    )
    assert any("es: missing [Labels] 'Keyword label'" in e for e in check(checked_project))


@pytest.mark.parametrize("usage", [
    'from labels import _tr\n_tr("New label")',
    'import labels as helper\nhelper._tr("New label")',
    'from labels import _tr as label\nlabel("New label")',
    'from open_garden_planner import labels\nlabels._tr("New label")',
    'from . import labels\nlabels._tr("New label")',
    'import labels\ntranslate = labels._tr\ntranslate("New label")',
    'import labels\nforward = labels\nforward._tr("New label")',
])
def test_cross_module_wrappers_require_explicit_calls(checked_project, usage):
    base = checked_project / "src/open_garden_planner"
    (base / "labels.py").write_text(
        'from PyQt6.QtCore import QCoreApplication\ndef _tr(source):\n'
        '    return QCoreApplication.translate("Labels", source)\n', encoding="utf-8"
    )
    (base / "consumer.py").write_text(usage, encoding="utf-8")
    with pytest.raises(CatalogError, match="imported translation"):
        inventory(checked_project)


def test_annotated_qt_alias_dynamic_source_fails_closed(checked_project):
    path = checked_project / "src/open_garden_planner/labels.py"
    path.write_text(
        'from PyQt6.QtCore import QCoreApplication\n'
        'translate: object = QCoreApplication.translate\n'
        'translate("Labels", unknown_source)\n', encoding="utf-8"
    )
    with pytest.raises(CatalogError, match="unresolved dynamic source"):
        inventory(checked_project)


@pytest.mark.parametrize("file,definition,usage", [
    ("labels.py", "label = QCoreApplication.translate", 'from open_garden_planner.labels import label\nlabel("Labels", "New label")'),
    ("labels/__init__.py", 'def _tr(source):\n    return QCoreApplication.translate("Labels", source)', 'from open_garden_planner.labels import _tr\n_tr("New label")'),
    ("labels/__init__.py", 'label: object = QCoreApplication.translate', 'from . import labels\nlabels.label("Labels", "New label")'),
    ("labels.py", '', 'from open_garden_planner.labels import QCoreApplication as Core\nCore.translate("Labels", "New label")'),
])
def test_local_translation_binding_imports_fail_closed(checked_project, file, definition, usage):
    base = checked_project / "src/open_garden_planner"
    path = base / file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('from PyQt6.QtCore import QCoreApplication\n' + definition + '\n', encoding="utf-8")
    (base / "consumer.py").write_text(usage, encoding="utf-8")
    with pytest.raises(CatalogError, match="imported translation"):
        inventory(checked_project)


def test_other_receiver_requires_explicit_context(checked_project):
    path = checked_project / "src/open_garden_planner/labels.py"
    path.write_text(
        'class Tool:\n    def build(self):\n        self._view.tr("View label")\n',
        encoding="utf-8",
    )
    with pytest.raises(CatalogError, match="explicit QObject context"):
        inventory(checked_project)


def test_table_consumer_preserves_disambiguation(checked_project):
    import json

    path = checked_project / "src/open_garden_planner/labels.py"
    path.write_text(
        'from PyQt6.QtCore import QCoreApplication\nLABELS = {"one": "One"}\n'
        'def label(key):\n    return QCoreApplication.translate("Labels", LABELS[key], "button")\n',
        encoding="utf-8",
    )
    directory = checked_project / "scripts"
    directory.mkdir()
    (directory / "i18n_bindings.json").write_text(json.dumps({
        "sources": {"labels": {"file": "labels.py", "context": "Labels", "symbol": "LABELS"}},
        "lookups": [{"file": "labels.py", "scope": "label", "expression": "LABELS[key]",
                     "context": "Labels", "sources": ["labels"]}],
    }), encoding="utf-8")
    catalogs(checked_project)
    path.write_text(path.read_text().replace('"button"', '"different meaning"'), encoding="utf-8")
    assert any("es: missing" in e and "different meaning" in e for e in check(checked_project))


def test_production_trait_table_plain_member_cannot_escape(checked_project):
    import json

    root = Path(__file__).resolve().parents[2]
    relative = "ui/widgets/trait_filters.py"
    path = checked_project / "src/open_garden_planner" / relative
    path.parent.mkdir(parents=True)
    source = (root / "src/open_garden_planner" / relative).read_text(encoding="utf-8")
    path.write_text(source, encoding="utf-8")
    declarations = json.loads((root / "scripts/i18n_bindings.json").read_text())
    directory = checked_project / "scripts"
    directory.mkdir()
    (directory / "i18n_bindings.json").write_text(json.dumps({
        "sources": {"traits": declarations["sources"]["traits"]},
        "lookups": [b for b in declarations["lookups"] if b["file"] == relative],
    }), encoding="utf-8")
    catalogs(checked_project)
    path.write_text(source.replace('labels = {', 'labels = {"review_test": "New trait",'),
                    encoding="utf-8")
    assert any("es: missing [Permaculture] 'New trait'" in e for e in check(checked_project))
