"""What the 3D view could not show, as a list the user can act on (L1.3, ADR-065).

The record layer refuses some outlines the 2D canvas draws without trouble (a
closed fence traced with thousands of points, a height nobody can build, …), and
a builder can fail. Such an item is simply ABSENT from 3D, so the workspace says
so: a quiet count in its strip and, on demand, this list — one row per item, with
the reason in the user's language. Activating a row selects the item on the plan.

Engine-free: plain widgets and the reason codes of ``ui/view3d/snapshot.py``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Final

from PyQt6.QtCore import QCoreApplication, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.core.object_types import ObjectType, get_translated_display_name
from open_garden_planner.core.plain_text import clip_line, plain_tooltip
from open_garden_planner.core.scene3d import BuildFailure

from .snapshot import SkippedItem, SkipReason

#: The code of an item whose BUILDER failed (the record layer's codes are ``SkipReason``).
BUILD_FAILED: Final = "build_failed"
_ITEM_ID_ROLE: Final = Qt.ItemDataRole.UserRole


def reason_text(code: str) -> str:
    """The user's words for a reason code; an unknown code gets the general text. A
    function, not only the dialog's method: the 3D info card (L1.8) says the SAME words
    without building the dialog. Context ``View3DProblemsDialog`` — the dialog's own."""
    texts = {
        SkipReason.RECORD_FAILED.value: QCoreApplication.translate(
            "View3DProblemsDialog", "its shape could not be worked out"),
        SkipReason.DUPLICATE_ID.value: QCoreApplication.translate(
            "View3DProblemsDialog", "another object on the plan has the same internal id"),
        SkipReason.OUTLINE_UNBUILDABLE.value: QCoreApplication.translate(
            "View3DProblemsDialog", "its outline cannot be turned into a solid"),
        SkipReason.OUTLINE_TOO_LARGE.value: QCoreApplication.translate(
            "View3DProblemsDialog", "its outline has too many points for the 3D view"),
        SkipReason.OUT_OF_RANGE.value: QCoreApplication.translate(
            "View3DProblemsDialog", "one of its sizes is outside what the 3D view can show"),
        BUILD_FAILED: QCoreApplication.translate(
            "View3DProblemsDialog", "its 3D model could not be built"),
    }
    return texts.get(code) or QCoreApplication.translate(
        "View3DProblemsDialog", "it could not be shown")


@dataclass(frozen=True, slots=True)
class Problem:
    """One item that is missing from the 3D view (or shown without its solid)."""

    item_id: str
    kind: str    # an ``ObjectType`` name
    code: str    # a ``SkipReason`` value, or ``BUILD_FAILED``
    detail: str = ""  # the exception's type and message — for the tooltip, as logged


def problems_of(skipped: Iterable[SkippedItem],
                failures: Mapping[str, BuildFailure]) -> tuple[Problem, ...]:
    """The controller's two reports as one list: refused records first, in paint order."""
    rows = [Problem(item.item_id, item.kind, str(item.reason.value),
                    _detail(item.error_type, item.error_message)) for item in skipped]
    rows += [Problem(failure.item_id, failure.kind, BUILD_FAILED,
                     _detail(failure.error_type, failure.error_message))
             for failure in failures.values()]
    return tuple(rows)


def _detail(error_type: str, message: str) -> str:
    return f"{error_type}: {message}" if error_type and message else (error_type or message)


class View3DProblemsDialog(QDialog):
    """The list (module docstring). Non-modal: the plan stays editable beside it."""

    #: A row was activated (double-click, Enter): the item's id.
    item_chosen = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Not Shown in 3D"))
        self.setModal(False)
        self.resize(520, 320)
        layout = QVBoxLayout(self)
        self._intro = QLabel(self.tr(
            "These objects are on the plan but cannot be shown in the 3D view. "
            "Double-click an entry to select the object on the plan."))
        self._intro.setTextFormat(Qt.TextFormat.PlainText)
        self._intro.setWordWrap(True)
        layout.addWidget(self._intro)
        # the DEFAULT delegate, on purpose: it draws a row's text as plain text. A
        # rich-text delegate here would turn an item's name into markup (pinned).
        self._list = QListWidget(self)
        self._list.itemActivated.connect(self._on_activated)
        layout.addWidget(self._list)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

    def reason_text(self, code: str) -> str:
        """The user's words for a reason code (``reason_text``)."""
        return reason_text(code)

    def kind_text(self, kind: str) -> str:
        try:
            return get_translated_display_name(ObjectType[kind])
        except KeyError:
            return kind

    def set_problems(self, problems: Iterable[Problem],
                     name_of: Callable[[str], str]) -> None:
        """Show ``problems``; ``name_of(item_id)`` is the item's own name ("" if none)."""
        self._list.clear()
        for problem in problems:
            # A name comes from the plan file and a detail from an exception that may
            # quote it: both are untrusted (core/plain_text.py, §8.11). The row is plain
            # text by the default delegate — a name is shown as its characters — and
            # only clipped; the tooltip, which Qt would sniff for markup, is escaped.
            kind = clip_line(self.kind_text(problem.kind))
            name = clip_line(name_of(problem.item_id))
            reason = self.reason_text(problem.code)
            if name and name != kind:
                text = self.tr("{name} ({kind}): {reason}").format(
                    name=name, kind=kind, reason=reason)
            else:
                text = self.tr("{kind}: {reason}").format(kind=kind, reason=reason)
            row = QListWidgetItem(text)
            row.setData(_ITEM_ID_ROLE, problem.item_id)
            row.setToolTip(plain_tooltip(problem.detail))
            self._list.addItem(row)

    def row_count(self) -> int:
        return self._list.count()

    def row_text(self, index: int) -> str:
        item = self._list.item(index)
        return item.text() if item is not None else ""

    def activate_row(self, index: int) -> None:
        """What a double-click on row ``index`` does."""
        item = self._list.item(index)
        if item is not None:
            self._on_activated(item)

    def _on_activated(self, item: QListWidgetItem) -> None:
        item_id = item.data(_ITEM_ID_ROLE)
        if isinstance(item_id, str) and item_id:
            self.item_chosen.emit(item_id)
