"""Frost-date parsing and validation — the ONE rule for every reader (#414).

A plan's frost dates are stored as ``'MM-DD'`` strings without a year
(``location["frost_dates"]["last_spring_frost"]``). Every consumer has to turn
that string into a real date for a *specific* year, because the task windows are
anchored on a frost date: the sowing, transplant, harvest and propagation steps
are all frost + a week offset. Before #414 there were **four** independent readers of a frost date —
``services.task_generator._parse_frost``,
``ui.views.planting_calendar_view._parse_frost``, the location dialog's
regex, and ``models.succession.compute_season_segments`` (which sliced the
string and called ``datetime.date`` directly) — and they could disagree, in
both directions.

**This module** is Qt-free and imports nothing above ``core/``, so the
generators, the agent tools, the Qt widgets and the dormant 3D spike all use
the same function (invariant 10).

It sits in ``core/`` rather than ``services/`` because ``models/succession.py``
needs it too, and ``services/`` already imports ``models/`` — putting it in
either would invert the declared direction. ``core/canvas_bounds.py`` is the
existing precedent for a rule shared by both tiers.

Note that ``core/`` as a TIER is *not* dependency-free (``core/project.py``
imports ``app.settings``; ``core/commands.py`` imports ``models.layer`` and,
at function level, ``ui.canvas.items``). What is Qt-free is this module, which
``tests/unit/test_frost_dates.py`` exercises without a ``qtbot`` — so do not
infer the property from the directory.

**29 February.** A ``'02-29'`` frost date is a legitimate stored value but only
exists in leap years. Substituting 1 March in a non-leap year (#414) keeps the
date reachable in every year, so a plan configured with a 29 February frost
never renders an empty task surface and never reports ``no_frost_dates``. The
substitution is deliberately *visible*: it is named
:data:`NON_LEAP_SUBSTITUTE_MONTH_DAY`, documented here and in ADR-029/§11.4, and it
has its own tests, because a substituted date that looks like a real user value is
the failure mode to avoid. The visible consequence in a multi-year listing is
that the non-leap anchor's tasks sit one day later than the leap anchor's.
"""
from __future__ import annotations

import datetime
import re

#: The **(MONTH, DAY)** substituted for a 29-February frost date in a year
#: that has no 29 February — i.e. ``(3, 1)`` for 1 March, NOT ``(1, 3)``.
#: Named so docs and tests can point at one definition instead of repeating a
#: bare literal (#414).
NON_LEAP_SUBSTITUTE_MONTH_DAY = (3, 1)

_MM_DD_RE = re.compile(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")


def is_valid_frost_date(mmdd: str | None) -> bool:
    """Whether ``mmdd`` is a real calendar date in the ``'MM-DD'`` format.

    Accepts ``'02-29'`` (a real date in a leap year, and a legitimate stored
    value — see the module docstring) and rejects the six dates that can never
    exist: ``02-30``, ``02-31``, ``04-31``, ``06-31``, ``09-31`` and ``11-31``.
    Those previously passed the location dialog's regex and then produced a
    ``None`` frost date, i.e. a plan that silently had no tasks (#414).

    An empty string is valid and means "not set".
    """
    if not mmdd:
        return True
    if not _MM_DD_RE.match(mmdd):
        return False
    month, day = (int(part) for part in mmdd.split("-"))
    # Leap-year-aware: probe a leap year so 02-29 is accepted while 02-30 and
    # 02-31 (which the regex above lets through) are not.
    try:
        probe = datetime.date(2000, month, day)
    except ValueError:
        return False
    return (probe.month, probe.day) == (month, day)


def parse_frost(mmdd: str | None, year: int) -> datetime.date | None:
    """Parse a stored ``'MM-DD'`` frost date into a date in ``year``.

    Returns ``None`` only when the string is malformed or names a date that does
    not exist at all. A ``'02-29'`` date in a non-leap ``year`` resolves to
    1 March of that year rather than ``None`` — see the module docstring for why.

    Args:
        mmdd: The stored value, or ``None``/empty when the plan has no such date.
        year: The calendar year the frost date should belong to.
    """
    if not mmdd:
        return None
    try:
        month, day = (int(part) for part in mmdd.split("-"))
    except (ValueError, AttributeError, TypeError):
        return None
    try:
        return datetime.date(year, month, day)
    except ValueError:
        # The only reachable case is 02-29 in a non-leap year (other impossible
        # dates are rejected by is_valid_frost_date at the input boundary).
        if (month, day) == (2, 29):
            return datetime.date(year, *NON_LEAP_SUBSTITUTE_MONTH_DAY)
        return None
