"""Sidebar panel stack: hover-peek, click-to-toggle, content-height accordion.

``SidebarController`` owns the sidebar layout and a per-panel state machine
(:class:`PanelState`). All panels live — in a fixed canonical order that never
changes — in a single ``QVBoxLayout`` inside a ``QScrollArea``: a panel is never
reparented, so opening/closing one cannot reorder the list. Opening a panel grows
it to its content height (animated); the sidebar scrolls when the open panels
overflow. See ADR-030 / arc42 §8.17.
"""

from __future__ import annotations

import contextlib
from enum import Enum, auto

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

from open_garden_planner.ui.widgets.collapsible_panel import CollapsiblePanel

# Hover debounce (ms). Asymmetric on purpose: opening is snappy, closing is
# forgiving so a fast diagonal sweep toward the canvas does not cascade-peek and
# the pointer can cross into the expanded body without the peek collapsing.
_PEEK_OPEN_MS = 140
_PEEK_CLOSE_MS = 220


class PanelState(Enum):
    """Lifecycle state of a single panel within the stack."""

    COLLAPSED = auto()
    PEEKING = auto()  # hover-opened; auto-collapses when the pointer leaves
    PINNED = auto()  # click- or selection-opened; stays open until toggled


class PinSource(Enum):
    """Why a panel is pinned. Governs whether a selection change may close it."""

    USER = auto()  # explicit title click — survives selection clearing
    SELECTION = auto()  # auto-opened because a matching item is selected


class _PanelEntry:
    """Per-panel bookkeeping. One instance per registered panel."""

    __slots__ = ("key", "panel", "state", "pin_source", "selection_dismissed")

    def __init__(self, key: str, panel: CollapsiblePanel) -> None:
        self.key = key
        self.panel = panel
        self.state = PanelState.COLLAPSED
        self.pin_source: PinSource | None = None
        # True when the user explicitly closed this panel while a matching item
        # is selected — suppresses auto-reopen until the selection changes.
        self.selection_dismissed = False


class SidebarController(QWidget):
    """Owns the sidebar layout and the COLLAPSED/PEEKING/PINNED state machine.

    Panels are registered in canonical order via :meth:`add_panel` and live in a
    single scrollable ``QVBoxLayout``; they are never reparented, so a state
    change never reorders the list. An open panel grows to its content height
    (animated); a trailing stretch keeps bars top-aligned and the surrounding
    ``QScrollArea`` scrolls when the open panels overflow the viewport.
    """

    # (key, PanelState) — emitted after every committed transition.
    panel_state_changed = pyqtSignal(str, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Canonical registry. Insertion order == canonical order.
        self._entries: dict[str, _PanelEntry] = {}
        self._order: list[str] = []

        # The pointer leaves only one bar at a time, so a single pending-open /
        # pending-close key is sufficient; the lone timer slot reads the key to
        # know which panel to act on.
        self._pending_open_key: str | None = None
        self._pending_close_key: str | None = None

        # Scrollable inner stack: panels + trailing stretch live in `_layout`.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        inner = QWidget()
        self._inner = inner
        self._layout = QVBoxLayout(inner)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        self._layout.addStretch()  # MUST stay last; inserts go above it
        self._scroll.setWidget(inner)
        outer.addWidget(self._scroll)

        self._open_timer = QTimer(self)
        self._open_timer.setSingleShot(True)
        self._open_timer.setInterval(_PEEK_OPEN_MS)
        self._open_timer.timeout.connect(self._commit_pending_open)

        self._close_timer = QTimer(self)
        self._close_timer.setSingleShot(True)
        self._close_timer.setInterval(_PEEK_CLOSE_MS)
        self._close_timer.timeout.connect(self._commit_pending_close)

    # ----- registration -------------------------------------------------

    def add_panel(self, key: str, panel: CollapsiblePanel) -> None:
        """Register a panel at the next canonical position (starts COLLAPSED).

        Args:
            key: Stable identifier (used by selection wiring + state queries).
            panel: The panel widget to manage.
        """
        if key in self._entries:
            raise ValueError(f"panel key already registered: {key!r}")
        entry = _PanelEntry(key, panel)
        self._entries[key] = entry
        self._order.append(key)

        # Bars sit ABOVE the trailing stretch (which is always last).
        self._layout.insertWidget(self._layout.count() - 1, panel)

        # Take over the header: drop the panel's default self-toggle so the
        # controller drives hover-peek / click-to-toggle instead.
        panel.take_over_header()

        # Default-arg binding so each lambda captures its own key (not the loop var).
        panel.header.hover_enter.connect(lambda k=key: self._on_hover_enter(k))
        panel.header.hover_leave.connect(lambda k=key: self._on_hover_leave(k))
        panel.header.pin_toggled.connect(lambda _c, k=key: self._on_title_click(k))

        self._collapse(entry, animate=False, emit=True)

    def panels(self) -> list[CollapsiblePanel]:
        """All panels in canonical order."""
        return [self._entries[k].panel for k in self._order]

    def panel_keys(self) -> list[str]:
        """All panel keys in canonical order."""
        return list(self._order)

    def panel(self, key: str) -> CollapsiblePanel | None:
        """The panel registered under *key*, or ``None`` if unknown."""
        entry = self._entries.get(key)
        return entry.panel if entry is not None else None

    def pinned_keys(self) -> list[str]:
        """Keys of currently-pinned panels, in canonical order."""
        return [
            k for k in self._order if self._entries[k].state is PanelState.PINNED
        ]

    def state_of(self, key: str) -> PanelState | None:
        """Current state of *key*, or ``None`` if unknown (test/inspection helper)."""
        entry = self._entries.get(key)
        return entry.state if entry is not None else None

    def is_open(self, key: str) -> bool:
        """True if *key* is currently expanded (peeking or pinned)."""
        return self.state_of(key) in (PanelState.PEEKING, PanelState.PINNED)

    # ----- public commands ----------------------------------------------

    def set_selection_pinned(self, key: str, pinned: bool) -> None:
        """Open/close a panel driven by canvas selection (source SELECTION).

        Opening is suppressed if the user has explicitly dismissed the panel for
        the current selection (see :meth:`reset_selection_dismissals`). Closing
        only affects SELECTION-pinned panels; a USER-pinned panel is never torn
        down by a selection change. Idempotent — safe to call from the several
        selection signals that fan in.
        """
        entry = self._entries.get(key)
        if entry is None:
            return
        if pinned:
            if entry.selection_dismissed:
                return  # user closed it for this selection
            if entry.state is not PanelState.PINNED:
                self._cancel_pending_for(key)
                self._open(entry, PanelState.PINNED, PinSource.SELECTION, animate=True)
            # already PINNED (USER or SELECTION) → leave as-is
        else:
            if (
                entry.state is PanelState.PINNED
                and entry.pin_source is PinSource.SELECTION
            ):
                self._collapse(entry, animate=True, emit=True)
            # selection no longer matches → allow auto-open again next time
            entry.selection_dismissed = False

    def reset_selection_dismissals(self) -> None:
        """Clear every per-panel dismissal flag.

        Called on a genuine selection change so a freshly-selected item re-opens
        its contextual panels even if the user had dismissed them for the
        previous selection.
        """
        for entry in self._entries.values():
            entry.selection_dismissed = False

    def collapse_all(self) -> None:
        """Force every panel back to COLLAPSED (startup / reset)."""
        self._cancel_open()
        self._cancel_close()
        for key in self._order:
            entry = self._entries[key]
            entry.selection_dismissed = False
            if entry.state is not PanelState.COLLAPSED:
                self._collapse(entry, animate=False, emit=True)

    # ----- hover routing -------------------------------------------------

    def _on_hover_enter(self, key: str) -> None:
        entry = self._entries.get(key)
        if entry is None or entry.state is PanelState.PINNED:
            return  # pinned panels ignore hover entirely

        # Re-entering the bar that was about to close cancels that close.
        if self._pending_close_key == key:
            self._cancel_close()

        if entry.state is PanelState.PEEKING:
            return  # already open, nothing to schedule

        self._pending_open_key = key
        with contextlib.suppress(RuntimeError):
            self._open_timer.start()

    def _on_hover_leave(self, key: str) -> None:
        entry = self._entries.get(key)
        if entry is None or entry.state is PanelState.PINNED:
            return

        if self._pending_open_key == key:
            self._cancel_open()  # cancel a not-yet-fired open

        if entry.state is PanelState.PEEKING:
            self._pending_close_key = key
            with contextlib.suppress(RuntimeError):
                self._close_timer.start()

    def _commit_pending_open(self) -> None:
        key, self._pending_open_key = self._pending_open_key, None
        if key is None:
            return
        entry = self._entries.get(key)
        if entry is not None and entry.state is PanelState.COLLAPSED:
            self._open(entry, PanelState.PEEKING, None, animate=True)

    def _commit_pending_close(self) -> None:
        key, self._pending_close_key = self._pending_close_key, None
        if key is None:
            return
        entry = self._entries.get(key)
        if entry is not None and entry.state is PanelState.PEEKING:
            self._collapse(entry, animate=True, emit=True)

    def _cancel_open(self) -> None:
        self._pending_open_key = None
        with contextlib.suppress(RuntimeError):
            self._open_timer.stop()

    def _cancel_close(self) -> None:
        self._pending_close_key = None
        with contextlib.suppress(RuntimeError):
            self._close_timer.stop()

    def _cancel_pending_for(self, key: str) -> None:
        if self._pending_open_key == key:
            self._cancel_open()
        if self._pending_close_key == key:
            self._cancel_close()

    # ----- title click (toggle) -----------------------------------------

    def _on_title_click(self, key: str) -> None:
        entry = self._entries.get(key)
        if entry is None:
            return
        self._cancel_pending_for(key)
        if entry.state is PanelState.PINNED:
            # A click always closes an open panel. If it was opened by the
            # selection, remember the dismissal so it does not immediately
            # re-open on the next selection re-notify (scene move, undo, …).
            if entry.pin_source is PinSource.SELECTION:
                entry.selection_dismissed = True
            self._collapse(entry, animate=True, emit=True)
        elif entry.state is PanelState.PEEKING:
            # Promote a hover-peek to a sticky user pin (already open).
            self._open(entry, PanelState.PINNED, PinSource.USER, animate=False)
        else:  # COLLAPSED
            self._open(entry, PanelState.PINNED, PinSource.USER, animate=True)

    # ----- state appliers -----------------------------------------------

    def _open(
        self,
        entry: _PanelEntry,
        new_state: PanelState,
        source: PinSource | None,
        *,
        animate: bool,
    ) -> None:
        panel = entry.panel
        was_open = entry.state in (PanelState.PEEKING, PanelState.PINNED)
        # Reveal the content first so sizeHint() reflects it (it returns the
        # header-only height while the content is hidden).
        if not was_open:
            panel.set_expanded(True, emit=False)
        # An open panel gets a layout stretch factor so it absorbs the surplus
        # sidebar space (instead of leaving an empty gap at the bottom). The
        # factor is weighted by content size so that when several are open the
        # panel with more to show gets proportionally more of the surplus (a
        # content-light panel doesn't claim an equal half it can't fill). They
        # scroll once their combined content overflows.
        self._layout.setStretchFactor(panel, max(1, panel.sizeHint().height()))
        if not was_open:
            if animate:
                panel.animate_expand(self._fill_target(entry))
            else:
                panel.expand_now()
        entry.state = new_state
        entry.pin_source = source
        panel.set_visual_state(new_state)
        self.panel_state_changed.emit(entry.key, new_state)

    def _collapse(self, entry: _PanelEntry, *, animate: bool, emit: bool) -> None:
        panel = entry.panel
        self._layout.setStretchFactor(panel, 0)  # no longer competes for surplus
        if animate:
            panel.animate_collapse()
        else:
            panel.collapse_now()
        entry.state = PanelState.COLLAPSED
        entry.pin_source = None
        panel.set_visual_state(PanelState.COLLAPSED)
        if emit:
            self.panel_state_changed.emit(entry.key, PanelState.COLLAPSED)

    def _fill_target(self, entry: _PanelEntry) -> int:
        """Estimate the height an opening panel will settle at, so the tween ends
        near it (the released clamp + stretch give the exact height afterwards).

        The target is the viewport height minus what the other panels currently
        occupy — i.e. the surplus this panel will absorb — but never below the
        panel's own content height (a taller panel just overflows into the
        sidebar scroll).
        """
        available = self._scroll.viewport().height()
        content = entry.panel.sizeHint().height()
        if available <= 0:
            return content
        used = sum(
            self._entries[k].panel.height() for k in self._order if k != entry.key
        )
        used += self._layout.spacing() * len(self._order)  # inter-item gaps
        fill = available - used
        return max(content, min(fill, available))
