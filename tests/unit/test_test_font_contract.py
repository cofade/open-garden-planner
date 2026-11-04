"""The suite's text metrics are measured on a real font engine (PF-TST-26, #562/#573).

Offscreen Qt on Windows has no font database: every family resolves to a box
engine whose glyphs are all one em wide. A row count or a rounding claim measured
there says nothing about a real font, which is why the Plan & Sun strip's layout
tests failed only on the dev box. ``tests/conftest.py`` registers a real Windows
face once and makes it the application font; this test pins that contract, so the
fixture cannot silently stop working.
"""

from __future__ import annotations

from PyQt6.QtGui import QFont, QFontDatabase, QFontMetrics


def test_the_ui_font_engine_is_real(qtbot, qapp, ui_font_family):
    assert ui_font_family in QFontDatabase.families(), ui_font_family
    chosen = QFontMetrics(QFont(ui_font_family, 9))
    assert chosen.horizontalAdvance("i") != chosen.horizontalAdvance("W"), (
        f"{ui_font_family} still resolves to a box font engine; conftest's "
        "deterministic_ui_font fixture did not register a real face"
    )
    inherited = QFontMetrics(qapp.font())
    assert inherited.horizontalAdvance("i") != inherited.horizontalAdvance("W"), (
        f"the application font {qapp.font().family()!r} still resolves to a box "
        "font engine; the Plan & Sun strip would measure the wrong widths"
    )
