"""What the 3D view could not show, as a list the user can act on (L1.3, ADR-060).

The record layer refuses some outlines the 2D canvas draws without trouble (a
closed fence traced with thousands of points, a height nobody can build, …), and
a builder can fail. Such an item is simply ABSENT from 3D, so the workspace says
so: a quiet count in its strip and, on demand, this list — one row per item, with
the reason in the user's language. Activating a row selects the item on the plan.

The ground bake (L1.5, §8.29.5) adds two kinds of row: an ITEM whose paint on the
3D ground failed (it is cut off there — shown, so it is not counted among the
objects 3D does not show; it makes the ground incomplete), and NOTES about the
ground as a whole — places that hold more surfaces than the ground can show (the
smallest are left out), pieces that could not be painted, a bake that failed,
ground work given up until the next change. A note belongs to no item: it comes
first, and activating it does nothing.

Engine-free: plain widgets and the reason codes of ``ui/view3d/snapshot.py``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

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

if TYPE_CHECKING:
    from .sync_controller import GroundProblems

#: The code of an item whose BUILDER failed (the record layer's codes are ``SkipReason``).
BUILD_FAILED: Final = "build_failed"
#: An item whose PAINT on the 3D ground failed (``GroundBaker.failures``).
GROUND_PAINT_FAILED: Final = "ground_paint_failed"
#: Notes about the ground as a whole (no item; ``Problem.count`` says how many tiles).
GROUND_CAPPED: Final = "ground_capped"
GROUND_TILES_FAILED: Final = "ground_tiles_failed"
GROUND_FAILED: Final = "ground_failed"
#: The ground passes were given up until the next change (``GroundProblems.unfinished``).
GROUND_UNFINISHED: Final = "ground_unfinished"
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
        GROUND_PAINT_FAILED: QCoreApplication.translate(
            "View3DProblemsDialog", "it could not be painted completely on the 3D ground"),
    }
    return texts.get(code) or QCoreApplication.translate(
        "View3DProblemsDialog", "it could not be shown")


@dataclass(frozen=True, slots=True)
class Problem:
    """One item that is missing from the 3D view (or shown without its solid)."""

    item_id: str  # "" for a note about the ground as a whole
    kind: str    # an ``ObjectType`` name ("" for a note)
    code: str    # a ``SkipReason`` value, ``BUILD_FAILED`` or a ``GROUND_*`` code
    detail: str = ""  # the exception's type and message — for the tooltip, as logged
    count: int = 0    # a note's number of ground tiles


def problems_of(skipped: Iterable[SkippedItem], failures: Mapping[str, BuildFailure],
                ground: GroundProblems | None = None) -> tuple[Problem, ...]:
    """The controller's reports as one list: the ground's notes first (they belong to
    no item, and must not fall under a row cap), then refused records in paint order,
    failed builders, and items whose paint on the ground failed."""
    rows: list[Problem] = []
    if ground is not None:
        if ground.unfinished is not None:
            rows.append(Problem("", "", GROUND_UNFINISHED, _detail(*ground.unfinished)))
        if ground.failure is not None:
            rows.append(Problem("", "", GROUND_FAILED, _detail(*ground.failure)))
        if ground.failed_tiles:
            rows.append(Problem("", "", GROUND_TILES_FAILED, count=ground.failed_tiles))
        if ground.capped_tiles:
            rows.append(Problem("", "", GROUND_CAPPED, count=ground.capped_tiles))
    rows += [Problem(item.item_id, item.kind, str(item.reason.value),
                     _detail(item.error_type, item.error_message)) for item in skipped]
    rows += [Problem(failure.item_id, failure.kind, BUILD_FAILED,
                     _detail(failure.error_type, failure.error_message))
             for failure in failures.values()]
    if ground is not None:
        rows += [Problem(item_id, kind, GROUND_PAINT_FAILED, _detail(error_type, message))
                 for item_id, kind, error_type, message in ground.items]
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

    def note_text(self, problem: Problem) -> str:
        """The row of a note about the ground as a whole (``problem.item_id == ""``)."""
        if problem.code == GROUND_CAPPED:
            if problem.count == 1:
                return self.tr("3D ground: in one place the plan puts more surfaces than the "
                               "ground can show; the smallest are left out")
            return self.tr(
                "3D ground: in {count} places the plan puts more surfaces than the ground "
                "can show; the smallest are left out").format(count=problem.count)
        if problem.code == GROUND_TILES_FAILED:
            if problem.count == 1:
                return self.tr("3D ground: one piece could not be painted and shows an older "
                               "picture")
            return self.tr(
                "3D ground: {count} pieces could not be painted and show an older "
                "picture").format(count=problem.count)
        if problem.code == GROUND_UNFINISHED:
            return self.tr("3D ground: it could not be finished; it is tried again with the "
                           "next change")
        return self.tr("3D ground: it could not be painted; it shows an older picture")

    def kind_text(self, kind: str) -> str:
        try:
            return get_translated_display_name(ObjectType[kind])
        except KeyError:
            return kind

    def set_problems(self, problems: Iterable[Problem],
                     name_of: Callable[[str], str], *, max_rows: int | None = None) -> None:
        """Show ``problems``; ``name_of(item_id)`` is the item's own name ("" if none).

        ``max_rows``: show at most that many, and say in a last row how many more
        there are (that row belongs to no item: activating it does nothing). A plan
        can refuse thousands of items, and this runs on the GUI thread."""
        self._list.clear()
        rows = list(problems)
        more = 0 if max_rows is None else max(0, len(rows) - max_rows)
        if more:
            rows = rows[:max_rows]
        for problem in rows:
            if not problem.item_id:  # a note about the ground: no name, no kind
                note = QListWidgetItem(self.note_text(problem))
                note.setData(_ITEM_ID_ROLE, "")
                note.setToolTip(plain_tooltip(problem.detail))
                self._list.addItem(note)
                continue
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
        if more:
            last = QListWidgetItem(self.tr("… and {count} more").format(count=more))
            last.setFlags(Qt.ItemFlag.NoItemFlags)  # not selectable, not activatable
            self._list.addItem(last)

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
