"""Showing and logging text from a plan file as TEXT (L1.3 security add-on; §8.11).

A plan file is untrusted input. Two consumers treat a string as more than its
characters:

- **Qt's rich-text sniffing.** Tooltips, ``QLabel`` with its default
  ``AutoText`` format, ``QMessageBox`` texts and "What's This" decide by LOOKING
  at a string whether it is rich text (``Qt.mightBeRichText``). An item name, a
  species string or an exception message that carries one —
  ``<img src="file:///…">``, a table a hundred thousand cells long — is then
  MARKUP there: it is rendered, it can pull a local file into the layout, it can
  imitate the app's own wording, and laying it out can stall the GUI thread.
- **The log file.** ``app.log`` is line-oriented and is what a user sends to
  support. A name with a line break in it writes a line of its own —
  ``2026-10-12 ERROR …`` — that nothing in the app ever logged.

The rule (§8.11): text that can come from a plan, a file path or an exception
never reaches either as it is. ONE order, in one place — **normalise, then cap,
then escape**:

1. ``normalise_text``: every character ``str.splitlines()`` treats as a line
   boundary becomes ``"\\n"`` (so the line a cap counts is the line a widget
   breaks: ``\\r``, ``\\x0b``, ``\\x0c``, ``\\x1c``–``\\x1e``, ``\\x85``, U+2028 and
   U+2029 are line breaks to Qt as well), a tab becomes a blank, and every other
   C0 / C1 control character, the bidirectional overrides and isolates
   (U+202A–U+202E, U+2066–U+2069: they reorder what is DISPLAYED) and every lone
   surrogate (U+D800–U+DFFF: legal in a JSON string, impossible to encode — a
   log handler that meets one writes nothing at all) become U+FFFD.
2. the caps — lines and characters — are applied to the normalised text, which
   is what the consumer will see;
3. only then, for a rich-text consumer, the markup characters are escaped.

Which function for which consumer:

=====================  ======================================================
a label, a message     ``label.setTextFormat(Qt.TextFormat.PlainText)`` and
                       ``clip_text``
a name in a row or     ``clip_line`` (one line)
a sentence
a tooltip              ``plain_tooltip`` — a tooltip has no format switch
a log record           ``log_text`` (one line), or ``%r``; never ``exc_info``
                       at a level the log file records when the exception can
                       quote the plan — the traceback's last line is the raw
                       message
=====================  ======================================================

Standard library only, and bounded: each function reads a prefix of its input
whose length depends on the cap alone, so a text of a hundred megabytes costs
what the cap costs.
"""

from __future__ import annotations

import html
from typing import Final

#: A tooltip shows at most this much of a plan-derived text …
TOOLTIP_MAX_CHARS: Final = 400
TOOLTIP_MAX_LINES: Final = 8
#: … a notice or message label this much …
NOTICE_MAX_CHARS: Final = 600
NOTICE_MAX_LINES: Final = 6
#: … a name inside a row or a sentence this much, on one line …
NAME_MAX_CHARS: Final = 80
#: … and a log record this much, on one line.
LOG_MAX_CHARS: Final = 300
ELLIPSIS: Final = "…"
REPLACEMENT: Final = "\N{REPLACEMENT CHARACTER}"

#: What ``str.splitlines()`` splits at — and what Qt's text layout breaks at.
LINE_BOUNDARIES: Final = ("\n", "\r", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85",
                          "\N{LINE SEPARATOR}", "\N{PARAGRAPH SEPARATOR}")
#: Explicit bidirectional embeddings, overrides and isolates: they change the
#: ORDER in which the characters after them are displayed.
BIDI_CONTROLS: Final = tuple(chr(code) for code in (*range(0x202A, 0x202F), *range(0x2066, 0x206A)))


#: Lone surrogates. ``"\\ud800"`` is legal JSON, so a plan file can put one into a
#: name — and it is not text: no UTF-8 encoder takes it. A ``FileHandler`` without
#: ``errors=`` then fails on the whole record, and the one log line about the hostile
#: item is the line that is missing from ``app.log`` (measured: 0 bytes written).
SURROGATES: Final = range(0xD800, 0xE000)


def _table() -> dict[int, str]:
    table: dict[int, str] = dict.fromkeys(
        (*range(0x00, 0x20), *range(0x7F, 0xA0), *SURROGATES), REPLACEMENT)
    table.update(dict.fromkeys(map(ord, BIDI_CONTROLS), REPLACEMENT))
    table.update(dict.fromkeys(map(ord, LINE_BOUNDARIES), "\n"))
    table[0x09] = " "
    return table


_NORMALISE: Final = _table()


def normalise_text(text: object) -> str:
    """``text`` with ONE kind of line break and nothing that is not text (module
    docstring, step 1). A ``\\r\\n`` pair is one line break. Unbounded: it reads
    all of its input — the clipping functions hand it a prefix."""
    raw = text if isinstance(text, str) else str(text)
    return raw.replace("\r\n", "\n").translate(_NORMALISE)


def clip_text(text: object, max_chars: int = NOTICE_MAX_CHARS,
              max_lines: int = NOTICE_MAX_LINES) -> str:
    """``text`` normalised and capped — at most ``max_lines`` lines and
    ``max_chars`` characters, with an ellipsis where something was cut. For a
    widget whose format is PLAIN text."""
    raw = text if isinstance(text, str) else str(text)
    # two raw characters make at least one normalised one ("\r\n"), so this prefix
    # decides the first max_chars characters AND whether anything follows them
    normalised = normalise_text(raw[:2 * max_chars + 2])
    cut = len(normalised) > max_chars
    lines = normalised[:max_chars].split("\n")
    if len(lines) > max_lines:
        lines, cut = lines[:max_lines], True
    result = "\n".join(lines).rstrip()
    return result + ELLIPSIS if cut else result


def clip_line(text: object, max_chars: int = NAME_MAX_CHARS) -> str:
    """``text`` normalised onto ONE line (line breaks and runs of blanks become one
    blank) and capped — a name inside a list row or a sentence.

    It reads the first ``4 x max_chars + 16`` characters: a name that begins with
    more blanks than that is shown as an ellipsis.
    """
    raw = text if isinstance(text, str) else str(text)
    reach = 4 * max_chars + 16
    line = " ".join(normalise_text(raw[:reach]).split())
    cut = len(line) > max_chars or len(raw) > reach
    return line[:max_chars] + ELLIPSIS if cut else line


def log_text(text: object, max_chars: int = LOG_MAX_CHARS) -> str:
    """``text`` for ONE log record on ONE line: ``clip_line`` with the log's cap.
    For an exception: ``log_text(error)`` is its message, made harmless."""
    return clip_line(text, max_chars)


def plain_tooltip(text: object, max_chars: int = TOOLTIP_MAX_CHARS,
                  max_lines: int = TOOLTIP_MAX_LINES) -> str:
    """A tooltip that shows ``text`` LITERALLY, whatever it contains.

    A tooltip has no format switch: Qt looks at the string. So the answer is rich
    text on purpose — the normalised, capped text with every markup character
    escaped, in an explicit ``<qt>`` element — which Qt renders as the characters
    given (runs of blanks collapse, as in any rich text). An empty text gives an
    empty tooltip (none is shown).
    """
    clipped = clip_text(text, max_chars, max_lines)
    if not clipped:
        return ""
    return "<qt>" + html.escape(clipped, quote=True).replace("\n", "<br>") + "</qt>"
