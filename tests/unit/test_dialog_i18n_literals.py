"""Pin the root cause of the %1 P1, at the layer where it is actually decidable.

The three broken strings paired Qt's positional ``%1`` with Python's
``str.format()``. That combination is a silent no-op: ``.format()`` has no
``%N`` field, so it returned the literal and the value was never shown. The
German dialog was also half-translated, because the registered keys use
``{named}`` and therefore matched neither the code literal nor its output --
and ``test_german_ts_has_no_unfinished`` was structurally blind to it, since
that gate only inspects messages ALREADY in the table.

Note what is NOT the defect: ``tr("Companions for: %1").replace("%1", name)``
at companion_panel.py:96 is the correct house idiom for a positional literal.
The invariant is therefore about the PAIRING, not about the placeholder:

    positional ``%N``  -> must be interpolated with .replace()
    named ``{field}``  -> must be interpolated with .format()

Literals are extracted with ``ast`` so implicit string concatenation is read the
way Python reads it, and cannot drift when someone rewords a string. Needs no
QTranslator and no built .qm, so it cannot silently rot.
"""
import ast
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest

from open_garden_planner.core.i18n import _TRANSLATIONS_DIR

PANEL = Path("src/open_garden_planner/ui/panels/companion_panel.py")
SOURCE = PANEL.read_text(encoding="utf-8")


def _is_tr_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "tr"
        and bool(node.args)
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    )


def _tr_pairings(class_name: str) -> list[tuple[str, str]]:
    """(literal, interpolation method) for every ``tr(...)<method>(...)``."""
    tree = ast.parse(SOURCE)
    for cls in ast.walk(tree):
        if isinstance(cls, ast.ClassDef) and cls.name == class_name:
            pairs: list[tuple[str, str]] = []
            for node in ast.walk(cls):
                # `self.tr("...").format(...)` parses as
                # Attribute(value=Call(func=Attribute(attr='tr')), attr='format')
                if isinstance(node, ast.Attribute) and _is_tr_call(node.value):
                    literal = node.value.args[0].value  # type: ignore[union-attr]
                    pairs.append((literal, node.attr))
            return pairs
    raise AssertionError(f"class {class_name} not found in {PANEL}")


def _tr_literals(class_name: str) -> list[str]:
    """Every tr() literal in a class, interpolated or not."""
    tree = ast.parse(SOURCE)
    for cls in ast.walk(tree):
        if isinstance(cls, ast.ClassDef) and cls.name == class_name:
            return [
                n.args[0].value  # type: ignore[union-attr]
                for n in ast.walk(cls)
                if _is_tr_call(n)
            ]
    raise AssertionError(f"class {class_name} not found in {PANEL}")


def _de_messages() -> dict[tuple[str, str], str]:
    """(context, source) -> German translation, read from the real .ts."""
    root = ET.parse(_TRANSLATIONS_DIR / "open_garden_planner_de.ts").getroot()
    out: dict[tuple[str, str], str] = {}
    for ctx in root.findall("context"):
        name_node = ctx.find("name")
        ctx_name = name_node.text if name_node is not None else ""
        for msg in ctx.findall("message"):
            src = msg.find("source")
            tr_node = msg.find("translation")
            if src is not None and tr_node is not None:
                out[(ctx_name, src.text or "")] = tr_node.text or ""
    return out


DIALOG_LITERALS = _tr_literals("CompatibleSetDialog")
PANEL_LITERALS = _tr_literals("CompanionPanel")
DIALOG_PAIRINGS = _tr_pairings("CompatibleSetDialog")
PANEL_PAIRINGS = _tr_pairings("CompanionPanel")


class TestPlaceholderAndInterpolationPairing:
    """The P1, enforced mechanically over the whole panel."""

    def test_positional_literals_use_replace_named_use_format(self) -> None:
        """The invariant: the placeholder style and the interpolation style agree.

        ``%N`` + ``.format()`` silently returns the literal (the P1).
        ``{named}`` + ``.replace()`` silently returns the literal (the mirror
        image, equally broken, and not yet observed but just as cheap to write).
        """
        offenders: list[str] = []
        for literal, method in DIALOG_PAIRINGS + PANEL_PAIRINGS:
            has_positional = "%1" in literal
            has_named = "{" in literal and "}" in literal
            if has_positional and method != "replace":
                offenders.append(f"{literal!r} uses %N but is interpolated with .{method}()")
            if has_named and method != "format":
                offenders.append(
                    f"{literal!r} uses {{named}} but is interpolated with .{method}()"
                )
        assert not offenders, "placeholder/interpolation mismatch:\n  " + "\n  ".join(
            offenders
        )

    def test_extraction_is_not_vacuous(self) -> None:
        """Guard the guard -- an empty extraction would make the tests vacuous."""
        assert len(DIALOG_LITERALS) >= 8, DIALOG_LITERALS
        assert "Already in bed: {plants}" in DIALOG_LITERALS
        # Both idioms must be present, or the pairing test proves nothing.
        assert any("%1" in lit for lit in PANEL_LITERALS), (
            "expected at least one correctly-paired %1 literal to exist"
        )
        assert len(DIALOG_PAIRINGS) >= 4, DIALOG_PAIRINGS

    def test_no_tr_literal_paired_with_format_contains_a_percent(self) -> None:
        """A narrower, source-grep form of the same invariant."""
        import re

        offenders = re.findall(r'tr\(\s*"[^"]*%[0-9][^"]*"\s*\)\s*\.\s*format\(', SOURCE)
        assert not offenders, offenders


class TestTrLiteralsAreRegistered:
    """Every dialog tr() literal must be a real, translated key in the .ts."""

    @pytest.mark.parametrize("literal", DIALOG_LITERALS)
    def test_dialog_literal_is_registered_and_translated(self, literal: str) -> None:
        messages = _de_messages()
        hits = [(ctx, text) for (ctx, src), text in messages.items() if src == literal]
        assert hits, (
            f"{literal!r} is not registered in the German .ts under any context, so "
            f"it renders untranslated. A tr() literal that is never registered is "
            f"INVISIBLE to test_german_ts_has_no_unfinished, which only inspects "
            f"messages already in the table -- this is the blind spot the %1 P1 hid in."
        )
        for ctx, text in hits:
            assert text.strip(), f"{literal!r} in [{ctx}] has an empty translation"
            assert text.strip() != literal, (
                f"{literal!r} in [{ctx}] is registered with the ENGLISH text as its "
                f"German translation, so it renders untranslated at runtime"
            )


@pytest.fixture(autouse=True)
def _qt(qtbot: Any) -> None:  # pragma: no cover - Qt init only
    """PyQt6 test modules need qtbot even where unused."""
