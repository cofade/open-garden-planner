"""The app's date and time fields take nothing from the locale's territory (#792).

The locale follows the UI language (ADR-077), and an English UI on a system that
speaks another language is ``en_US``. A field left to that locale shows
"3:30 PM" and "6/7/26" and starts its calendar popup on Sunday, for a user who
only asked for English words. So a field decides nothing itself: every
``QDateEdit`` / ``QDateTimeEdit`` / ``QTimeEdit`` of the app is handed to one of
the two functions below where it is built, and nothing else may call
``setDisplayFormat``, ``setCalendarPopup``, ``setCalendarWidget`` or
``setFirstDayOfWeek`` (``tests/unit/test_date_fields.py`` walks the source).

- A date is ISO (``yyyy-MM-dd``), the form the plan file, the Tasks tab and the
  plan-date strip use.
- A time is 24 hours (``HH:mm``).
- A calendar popup starts its week on Monday in every language (ISO 8601).

A date in running TEXT is not a field: ``core/i18n.format_short_date``.
"""

from __future__ import annotations

from typing import TypeVar

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCalendarWidget, QDateEdit, QDateTimeEdit, QTimeEdit

#: A date as a field shows it, in every language.
ISO_DATE_FORMAT = "yyyy-MM-dd"
#: A time as a field shows it, in every language.
TIME_FORMAT = "HH:mm"
#: A day whose year is given elsewhere (a calendar step): the month by NAME, so
#: no order of two numbers can be misread.
DAY_MONTH_FORMAT = "dd MMM"
#: The first column of every calendar popup.
FIRST_DAY_OF_WEEK = Qt.DayOfWeek.Monday

_DateField = TypeVar("_DateField", bound=QDateTimeEdit)
_TimeField = TypeVar("_TimeField", bound=QTimeEdit)


def as_date_field(edit: _DateField, *, without_year: bool = False,
                  calendar: QCalendarWidget | None = None) -> _DateField:
    """Make *edit* one of the app's date fields and return it.

    ISO display, a calendar popup, the week from Monday. *without_year* is for a
    day whose year stands elsewhere (``DAY_MONTH_FORMAT``); *calendar* replaces
    the popup's calendar widget (one with its own date bounds) and gets the same
    week start. A ``QDateTimeEdit`` that is not a ``QDateEdit`` shows the time
    behind the date.
    """
    if without_year:
        pattern = DAY_MONTH_FORMAT
    elif isinstance(edit, QDateEdit):
        pattern = ISO_DATE_FORMAT
    else:
        pattern = f"{ISO_DATE_FORMAT} {TIME_FORMAT}"
    edit.setDisplayFormat(pattern)
    edit.setCalendarPopup(True)   # before the calendar: Qt refuses one without a popup
    if calendar is not None:
        edit.setCalendarWidget(calendar)
    popup = edit.calendarWidget()
    if popup is not None:
        popup.setFirstDayOfWeek(FIRST_DAY_OF_WEEK)
    return edit


def as_time_field(edit: _TimeField) -> _TimeField:
    """Make *edit* one of the app's time fields (24 hours) and return it."""
    edit.setDisplayFormat(TIME_FORMAT)
    return edit
