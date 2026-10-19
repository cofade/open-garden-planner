"""Plan text shown and logged as TEXT (L1.3 security add-on, §8.11) — ``core/plain_text.py``.

A plan file is untrusted. A tooltip or an ``AutoText`` label renders markup it
finds in a string, and a line break in a logged name writes a log line of its
own. These helpers stand between an item's name (or an exception that quotes it)
and both — in ONE order: normalise, then cap, then escape. Each claim is checked
against the consumer: Qt's own verdict (``Qt.mightBeRichText``), Qt's own renderer
(``QTextDocument``) and Python's own idea of a line (``str.splitlines``).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextDocument

from open_garden_planner.core import plain_text
from open_garden_planner.core.plain_text import (
    BIDI_CONTROLS,
    ELLIPSIS,
    LINE_BOUNDARIES,
    LOG_MAX_CHARS,
    NAME_MAX_CHARS,
    NOTICE_MAX_CHARS,
    NOTICE_MAX_LINES,
    REPLACEMENT,
    TOOLTIP_MAX_CHARS,
    TOOLTIP_MAX_LINES,
    clip_line,
    clip_text,
    log_text,
    normalise_text,
    plain_tooltip,
)

HOSTILE = '<b>x</b><img src="file:///C:/Windows/win.ini">'
#: Every way to end a line: what ``str.splitlines`` splits at, and the CR LF pair.
SEPARATORS = [*LINE_BOUNDARIES, "\r\n"]


def _rendered(rich: str) -> str:
    """What Qt's rich-text engine makes of a string — the text a tooltip would show."""
    document = QTextDocument()
    document.setHtml(rich)
    return document.toPlainText()


def _old_clip(text: str, max_chars: int, max_lines: int) -> str:
    """The FIRST version of ``clip_text`` (commit d033472), kept as the control: it
    counted lines its own way — at ``"\\n"`` — and the widget counts them another."""
    control = {code: " " for code in (*range(0x00, 0x20), *range(0x7F, 0xA0))
               if code not in (0x09, 0x0A)}
    cut = len(text) > max_chars
    kept = text[:max_chars].replace("\r\n", "\n").replace("\r", "\n").translate(control)
    lines = kept.split("\n")
    if len(lines) > max_lines:
        lines, cut = lines[:max_lines], True
    result = "\n".join(lines).rstrip()
    return result + ELLIPSIS if cut else result


class TestNormalise:
    def test_the_boundaries_are_exactly_what_splitlines_splits_at(self) -> None:
        """The list is not a guess: every character of the Basic Multilingual Plane
        that ``str.splitlines`` treats as a boundary is in it, and nothing else."""
        found = tuple(chr(code) for code in range(0x10000)
                      if len(f"a{chr(code)}b".splitlines()) == 2)
        assert sorted(found) == sorted(LINE_BOUNDARIES)

    @pytest.mark.parametrize("separator", SEPARATORS, ids=lambda s: repr(s))
    def test_every_line_boundary_becomes_the_one_line_break(self, separator: str) -> None:
        assert normalise_text(f"one{separator}two{separator}three") == "one\ntwo\nthree"

    def test_what_is_not_text_becomes_the_replacement_character(self) -> None:
        assert normalise_text("a\x00b\x1bc\x7fd\x9be") == f"a{REPLACEMENT}b{REPLACEMENT}c{REPLACEMENT}d{REPLACEMENT}e"
        assert normalise_text("tab\there") == "tab here"
        for control in BIDI_CONTROLS:
            assert normalise_text(f"invoice{control}fdp.exe") == f"invoice{REPLACEMENT}fdp.exe"
        assert len(BIDI_CONTROLS) == 9  # U+202A-U+202E and U+2066-U+2069

    def test_text_stays_text(self) -> None:
        for text in ("plain words", "ünïcödé — „quotes“ 日本語 עברית", "a < b & c > d", ""):
            assert normalise_text(text) == text
        assert normalise_text(12.5) == "12.5"

    def test_after_it_a_line_is_a_line_to_python_and_to_qt(self, qtbot) -> None:  # noqa: ARG002
        text = normalise_text("".join(f"line{sep}" for sep in SEPARATORS) + "end")
        assert len(text.splitlines()) == text.count("\n") + 1 == len(SEPARATORS) + 1
        document = QTextDocument()
        document.setPlainText(text)
        assert document.blockCount() == len(SEPARATORS) + 1
        assert not any(sep in text for sep in LINE_BOUNDARIES if sep != "\n")


class TestTheCapCountsWhatTheConsumerSees:
    @pytest.mark.parametrize("separator", SEPARATORS, ids=lambda s: repr(s))
    def test_the_same_text_with_any_separator_is_capped_the_same(self, separator: str) -> None:
        """The differential the scan found: a text of thousands of "lines" that are
        one line to a splitter that only knows ``\\n``."""
        hostile = separator.join(f"row {n}" for n in range(5000))
        reference = "\n".join(f"row {n}" for n in range(5000))
        assert clip_text(hostile) == clip_text(reference)
        assert plain_tooltip(hostile) == plain_tooltip(reference)
        assert log_text(hostile) == log_text(reference)
        assert clip_line(hostile) == clip_line(reference)
        assert len(clip_text(hostile).splitlines()) == NOTICE_MAX_LINES
        assert len(log_text(hostile).splitlines()) == 1

    @pytest.mark.parametrize("separator", ["\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85",
                                           "\u2028", "\u2029"], ids=lambda s: repr(s))
    def test_the_control_the_old_splitter_let_these_through_or_hid_them(self,
                                                                         separator: str) -> None:
        """Positive control: the first version on the same text. It either handed the
        widget more lines than its cap (U+2028, U+2029 passed through untouched) or
        silently glued the lines together with blanks — in both cases its line cap
        counted something else than what is shown."""
        hostile = separator.join(f"row {n}" for n in range(40))
        old = _old_clip(hostile, NOTICE_MAX_CHARS, NOTICE_MAX_LINES)
        new = clip_text(hostile)
        assert len(new.splitlines()) == NOTICE_MAX_LINES
        assert len(old.splitlines()) != NOTICE_MAX_LINES
        assert old != new

    def test_a_tooltip_never_shows_more_lines_than_its_cap(self, qtbot) -> None:  # noqa: ARG002
        for separator in SEPARATORS:
            shown = _rendered(plain_tooltip(separator.join(str(n) for n in range(200))))
            assert shown.count("\n") == TOOLTIP_MAX_LINES - 1, repr(separator)


class TestTooltip:
    def test_markup_in_the_text_is_shown_as_its_characters(self, qtbot) -> None:  # noqa: ARG002
        tooltip = plain_tooltip(HOSTILE)
        assert "<img" not in tooltip and "<b>" not in tooltip
        assert tooltip == ('<qt>&lt;b&gt;x&lt;/b&gt;&lt;img src=&quot;file:///C:/Windows/win.ini'
                           '&quot;&gt;</qt>')
        assert _rendered(tooltip) == HOSTILE

    def test_the_control_the_same_text_unescaped_is_markup_to_qt(self, qtbot) -> None:  # noqa: ARG002
        """Without the helper Qt takes the string for rich text and renders it: the
        bold tag is gone and an image object stands in the text."""
        assert Qt.mightBeRichText(HOSTILE) is True
        assert _rendered(HOSTILE) != HOSTILE
        assert "<b>" not in _rendered(HOSTILE)

    @pytest.mark.parametrize("text", [
        "plain words", "a < b and b > c", "Tom & Jerry", "<qt>nested</qt>", "</qt><h1>Title</h1>",
        "&lt;already escaped&gt;", "ünïcödé — „quotes“", "x" * 50,
    ])
    def test_whatever_goes_in_comes_out_of_the_renderer_unchanged(self, qtbot, text: str) -> None:  # noqa: ARG002
        assert _rendered(plain_tooltip(text)) == text

    def test_line_breaks_are_kept_as_line_breaks(self, qtbot) -> None:  # noqa: ARG002
        assert _rendered(plain_tooltip("ValueError: one\ntwo\nthree")) == "ValueError: one\ntwo\nthree"

    def test_a_huge_text_is_cut_before_it_is_looked_at(self, qtbot) -> None:  # noqa: ARG002
        tooltip = plain_tooltip("<table><tr><td>" * 100_000)
        shown = _rendered(tooltip)
        assert len(shown) == TOOLTIP_MAX_CHARS + 1 and shown.endswith(ELLIPSIS)
        assert len(tooltip) < 6 * TOOLTIP_MAX_CHARS + 20, "escaping grows a character sixfold at most"

    def test_no_text_no_tooltip(self) -> None:
        assert plain_tooltip("") == "" and plain_tooltip("   \n ") == ""

    def test_something_that_is_not_a_string_is_shown_as_its_text(self, qtbot) -> None:  # noqa: ARG002
        assert _rendered(plain_tooltip(ValueError("<i>bad</i>"))) == "<i>bad</i>"


class TestClipping:
    def test_a_short_text_is_returned_as_it_is(self) -> None:
        assert clip_text("Failed to initialize graphics backend for D3D11.") == (
            "Failed to initialize graphics backend for D3D11.")
        assert clip_text("<b>kept: this is for a PLAIN text widget</b>") == (
            "<b>kept: this is for a PLAIN text widget</b>")

    def test_the_caps(self) -> None:
        assert clip_text("y" * 10_000) == "y" * NOTICE_MAX_CHARS + ELLIPSIS
        assert clip_text("y" * NOTICE_MAX_CHARS) == "y" * NOTICE_MAX_CHARS
        tall = clip_text("\n".join(str(n) for n in range(50)))
        assert tall.split("\n") == [*map(str, range(NOTICE_MAX_LINES - 1)),
                                    f"{NOTICE_MAX_LINES - 1}{ELLIPSIS}"]
        assert clip_text("abcdef", max_chars=3) == "abc" + ELLIPSIS
        assert clip_text("abc", max_chars=3) == "abc"

    def test_a_cr_lf_pair_is_one_character_of_the_cap(self) -> None:
        text = "\r\n".join("ab" for _ in range(4))      # ab, ab, ab, ab on four lines
        assert clip_text(text, max_chars=11, max_lines=10) == "ab\nab\nab\nab"
        assert clip_text(text, max_chars=10, max_lines=10) == "ab\nab\nab\na" + ELLIPSIS
        assert clip_text("\r\n" * 5000, max_chars=10, max_lines=3) == ELLIPSIS

    def test_a_name_is_one_clipped_line(self) -> None:
        assert clip_line("North bed") == "North bed"
        assert clip_line("North\nbed\r\n\twith  breaks") == "North bed with breaks"
        assert clip_line("n" * 500) == "n" * NAME_MAX_CHARS + ELLIPSIS
        assert clip_line(HOSTILE) == HOSTILE, "a row is plain text: nothing to escape"
        assert clip_line(None) == "None" and clip_line("") == ""
        assert clip_line(" " * 100_000 + "hidden") == ELLIPSIS

    def test_the_cost_does_not_grow_with_the_input(self) -> None:
        """Each function reads a prefix whose length depends on its cap alone."""
        huge = "<" * 100_000_000
        assert len(clip_text(huge)) == NOTICE_MAX_CHARS + 1
        assert len(clip_line(huge)) == NAME_MAX_CHARS + 1
        assert len(log_text(huge)) == LOG_MAX_CHARS + 1

    def test_no_function_works_on_the_whole_input(self) -> None:
        """Without a clock: a string that refuses every whole-string operation. Only a
        SLICE of it (a plain ``str``) may be normalised, split or escaped."""

        class Whole(str):
            __slots__ = ()

            def _refuse(self, *_arguments: object, **_options: object) -> str:
                raise AssertionError("the whole input was worked on, not a prefix of it")

            replace = translate = split = splitlines = join = strip = rstrip = _refuse  # type: ignore[assignment]

        text = Whole("row one\r\nrow two <b>bold</b>\N{LINE SEPARATOR}" * 50_000)
        assert clip_text(text).startswith("row one\nrow two <b>bold</b>\nrow one")
        assert clip_line(text).startswith("row one row two <b>bold</b> row one")
        assert log_text(text).startswith("row one row two")
        assert plain_tooltip(text).startswith("<qt>row one<br>row two &lt;b&gt;bold&lt;/b&gt;<br>")
        with pytest.raises(AssertionError, match="whole input"):
            normalise_text(text)        # the one function that says it reads everything


class TestLogText:
    @pytest.mark.parametrize("separator", SEPARATORS, ids=lambda s: repr(s))
    def test_a_forged_line_stays_inside_its_record(self, separator: str) -> None:
        forged = f"North bed{separator}2026-10-12 00:00:00 ERROR root: disk is failing"
        line = log_text(forged)
        assert line == "North bed 2026-10-12 00:00:00 ERROR root: disk is failing"
        assert len(line.splitlines()) == 1

    def test_an_exception_is_logged_as_its_message_on_one_capped_line(self) -> None:
        error = ValueError("cannot build 'x'\nTraceback (most recent call last):\n  forged")
        assert log_text(error) == "cannot build 'x' Traceback (most recent call last): forged"
        assert log_text("m" * 5000) == "m" * LOG_MAX_CHARS + ELLIPSIS

    def test_terminal_escapes_and_bidi_do_not_survive(self) -> None:
        assert log_text("ok\x1b[2J\x1b[31mred") == f"ok{REPLACEMENT}[2J{REPLACEMENT}[31mred"
        assert log_text("abc\u202edef") == f"abc{REPLACEMENT}def"


def test_the_helper_needs_no_qt() -> None:
    source = Path(plain_text.__file__).read_text(encoding="utf-8")
    imported = {alias.name.split(".")[0] for node in ast.walk(ast.parse(source))
                if isinstance(node, ast.Import) for alias in node.names}
    imported |= {node.module.split(".")[0] for node in ast.walk(ast.parse(source))
                 if isinstance(node, ast.ImportFrom) and node.module}
    assert imported <= {"__future__", "html", "typing"}, imported


def _hidden_characters(text: str) -> list[tuple[int, int, str]]:
    """(line, column, name) of every character a reader of the SOURCE cannot see or
    that breaks a line other than LF: line / paragraph separators, format and
    control characters (but tab and CR LF), and the replacement character."""
    import unicodedata

    found = []
    for number, line in enumerate(text.split("\n"), 1):
        if line.rstrip("\r").isprintable() and chr(0xFFFD) not in line:
            continue  # the fast path: nearly every line of every file
        for column, char in enumerate(line.rstrip("\r"), 1):
            if char != "\t" and (unicodedata.category(char) in {"Zl", "Zp", "Cf", "Cc"}
                                 or ord(char) == 0xFFFD):
                found.append((number, column, f"U+{ord(char):04X}"))
    return found


def test_no_source_file_of_the_product_or_its_tests_hides_a_character() -> None:
    """Found while this module was written: an editing tool had turned three
    backslash-u escapes into the characters themselves, so the file that defines the
    line separators CONTAINED two — invisible in every diff, and a line break to
    half the tools that read a source file. A character that must not be seen is
    spelled as an escape (``\\N{LINE SEPARATOR}``, ``chr(0x2028)``); a bidirectional
    override in a source file is the "Trojan Source" trick (CVE-2021-42574)."""
    root = Path(__file__).resolve().parents[2]
    offenders = {}
    for folder in ("src", "tests"):
        for path in sorted((root / folder).rglob("*.py")):
            hidden = _hidden_characters(path.read_text(encoding="utf-8"))
            if hidden:
                offenders[path.relative_to(root).as_posix()] = hidden[:5]
    assert offenders == {}


def test_the_hidden_character_scan_sees_what_it_is_for() -> None:
    assert _hidden_characters("plain = 'text'\r\n\tindented = 'ä — ok'\n") == []
    for code in (0x2028, 0x2029, 0x202E, 0x2066, 0x200B, 0xFEFF, 0x00, 0x0C, 0x85, 0xFFFD):
        assert _hidden_characters(f"x = 'a{chr(code)}b'") == [(1, 7, f"U+{code:04X}")], hex(code)
