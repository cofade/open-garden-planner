"""Per-task status resolution (US-C2 — task management).

Generated tasks (see :mod:`open_garden_planner.services.task_generator`) are
recomputed every refresh and carry no persistent state of their own. The user's
interactions with a task — snoozing, completing, dismissing — are stored
separately, keyed by ``task_id``, as small dicts of the form::

    {"status": "done", "done_date": "2026-06-20"}
    {"snooze_until": "2026-07-01"}

:func:`effective_status` collapses such a stored dict plus "today" into a single
display state. The module is pure: no Qt, no I/O, defensive ISO parsing.
"""
from __future__ import annotations

import datetime


def _parse_iso(value: object) -> datetime.date | None:
    """Parse an ISO date string defensively (non-string / invalid → None)."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def effective_status(state: dict | None, today: datetime.date) -> str:
    """Collapse a stored per-task state dict into a single display status.

    Resolution order (first match wins):

    1. ``None`` or empty dict           → ``"open"``.
    2. ``snooze_until`` in the future    → ``"snoozed"`` (a past snooze falls
       through, so the task re-surfaces as ``"open"``).
    3. ``status == "dismissed"``         → ``"dismissed"``.
    4. ``status == "done"``              → ``"done"`` when ``done_date`` is
       present and within the last 7 days, otherwise ``"archived"``. A done task
       with no (or an unparseable) ``done_date`` is treated as ``"archived"`` —
       there is no date to keep it surfaced, which is exactly what legacy
       ``task_completions`` folded on load want (hidden, never resurfacing).
    5. anything else                     → ``"open"``.

    Args:
        state: Stored per-task state dict, or ``None``.
        today: Reference date for snooze/age comparisons.

    Returns:
        One of ``"open" | "snoozed" | "done" | "dismissed" | "archived"``.
    """
    if not state:
        return "open"

    snooze_until = _parse_iso(state.get("snooze_until"))
    if snooze_until is not None and snooze_until > today:
        return "snoozed"

    status = state.get("status")
    if status == "dismissed":
        return "dismissed"

    if status == "done":
        done_date = _parse_iso(state.get("done_date"))
        if done_date is not None and (today - done_date).days <= 7:
            return "done"
        return "archived"

    return "open"


def is_visible_active(effective: str) -> bool:
    """Return True for statuses that belong in the active (non-archived) view.

    ``"open"`` and ``"done"`` are shown in the main list (a freshly-done task
    stays visible for up to a week before it ages into ``"archived"``);
    ``"snoozed"``, ``"dismissed"`` and ``"archived"`` are hidden from it.
    """
    return effective in ("open", "done")
