"""Every string of the 3D workspace reaches the translator (Phase 17 L1.3, §8.3).

``test_german_ts_has_no_unfinished`` only inspects messages that are already in the
table: a ``tr()`` literal nobody registered is invisible to it. So the literals are
read from the SOURCE here (``ast``: implicit concatenation is read the way Python
reads it) and each must have a German entry under the context Qt will ask for —
the class name — and the interpolation must fit the placeholder style.
"""

from __future__ import annotations

import ast
import string
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PyQt6.QtCore import QCoreApplication, QTranslator

from open_garden_planner.core.i18n import _TRANSLATIONS_DIR

SRC = Path(__file__).resolve().parents[2] / "src" / "open_garden_planner" / "ui" / "view3d"
#: module → the classes whose ``self.tr`` it uses (the context is the class name)
MODULES = {"workspace.py": ("Workspace",), "problems_dialog.py": ("View3DProblemsDialog",)}


def _tr_literals(module: str) -> list[tuple[str, str, str]]:
    """(context, literal, how it is interpolated: "format" / "replace" / "")."""
    tree = ast.parse((SRC / module).read_text(encoding="utf-8"))
    found: list[tuple[str, str, str]] = []
    for cls in (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)):
        interpolated = {}
        for node in ast.walk(cls):
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Attribute)
                    and node.value.func.attr == "tr"):
                interpolated[id(node.value)] = node.attr
        for node in ast.walk(cls):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "tr"):
                assert len(node.args) == 1 and isinstance(node.args[0], ast.Constant), (
                    f"{module}:{node.lineno}: tr() must be given ONE string literal")
                found.append((cls.name, str(node.args[0].value), interpolated.get(id(node), "")))
    return found


def _german() -> dict[tuple[str, str], tuple[str, str | None]]:
    table = {}
    root = ET.parse(_TRANSLATIONS_DIR / "open_garden_planner_de.ts").getroot()
    for context in root.findall("context"):
        name = context.findtext("name") or ""
        for message in context.findall("message"):
            translation = message.find("translation")
            assert translation is not None
            table[(name, message.findtext("source") or "")] = (
                translation.text or "", translation.get("type"))
    return table


LITERALS = [entry for module in MODULES for entry in _tr_literals(module)]


def test_the_scan_finds_the_strings_it_is_for() -> None:
    assert len(LITERALS) >= 35
    contexts = {context for context, _literal, _how in LITERALS}
    assert contexts == {name for names in MODULES.values() for name in names}, (
        "a tr() call in a helper class would be asked for under ANOTHER context")
    assert ("Workspace", "&Split", "") in LITERALS
    assert ("View3DProblemsDialog", "{kind}: {reason}", "format") in LITERALS


@pytest.mark.parametrize(("context", "literal", "how"), LITERALS,
                         ids=[f"{c}:{t[:40]}" for c, t, _h in LITERALS])
def test_every_literal_has_a_finished_german_translation(context: str, literal: str,
                                                         how: str) -> None:
    german, state = _german()[(context, literal)]
    assert german.strip() and state is None, f"unfinished: {literal!r}"
    fields = {name for _text, name, _spec, _conv in string.Formatter().parse(literal) if name}
    translated = {name for _text, name, _spec, _conv in string.Formatter().parse(german) if name}
    assert translated == fields, f"the German text of {literal!r} has other placeholders"
    assert "%1" not in literal, "this module's house style is {named} with .format()"
    if fields:
        assert how == "format", f"{literal!r} has {{fields}} and is not .format()-ed"
    else:
        assert how in ("", "format"), literal
    assert german.endswith(literal[-1]) or literal[-1].isalnum(), (
        f"{literal!r} and its translation end differently")


#: German possessives and pronouns that agree with the GENDER of what they refer to.
_GENDERED = ("sein ", "seine ", "seinen ", "seiner ", "seines ", "seinem ", "es ")


def test_no_german_reason_guesses_the_gender_of_the_object() -> None:
    """A reason is shown after ANY kind of object — "Hochbeet (neutral): sein Umriss …"
    reads right, "Hecke (feminine): sein Umriss …" does not. The English "its" has no
    gender; the German says "der Umriss", "die Form", "das 3D-Modell" instead
    (review 1, P2-14)."""
    german = _german()
    reasons = [literal for context, literal, _how in LITERALS
               if context == "View3DProblemsDialog" and literal.startswith(("its ", "it ", "one of its"))]
    assert len(reasons) >= 6, "the scan finds the reason sentences"
    for literal in reasons:
        text = german[("View3DProblemsDialog", literal)][0]
        lowered = f" {text.lower()}"
        assert not any(f" {word}" in lowered for word in _GENDERED), (literal, text)


def test_the_compiled_catalogue_answers_for_both_contexts(qtbot) -> None:  # noqa: ARG001
    """Through Qt itself: the .qm that ships, asked the way ``self.tr`` asks."""
    translator = QTranslator()
    assert translator.load(str(_TRANSLATIONS_DIR / "open_garden_planner_de.qm"))
    app = QCoreApplication.instance()
    assert app is not None
    app.installTranslator(translator)
    try:
        assert QCoreApplication.translate("Workspace", "&Split") == "&Geteilt"
        assert QCoreApplication.translate("Workspace", "1 object is not shown in 3D") == (
            "1 Objekt wird in 3D nicht angezeigt")
        assert QCoreApplication.translate(
            "View3DProblemsDialog", "its outline has too many points for the 3D view") == (
            "der Umriss hat zu viele Punkte für die 3D-Ansicht")
    finally:
        app.removeTranslator(translator)


def test_no_other_module_of_the_story_shows_a_string_of_its_own() -> None:
    """The controller, the guard, the input filter and the camera are not widgets:
    they hold no user-visible text (their log lines are English, for ``app.log``)."""
    for module in ("sync_controller.py", "init_guard.py", "orbit_input.py"):
        tree = ast.parse((SRC / module).read_text(encoding="utf-8"))
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute)
                 and node.func.attr in {"tr", "translate"}]
        assert calls == [], module
