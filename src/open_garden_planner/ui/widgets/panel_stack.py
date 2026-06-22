"""Sidebar panel stack with hover-peek and click-to-pin behaviour.

``SidebarController`` owns the sidebar layout and a per-panel state machine
(:class:`PanelState`). Collapsed and peeking bars live directly in a top-level
``QVBoxLayout``; pinned panels are *moved* into a lazily-created vertical
``QSplitter`` that always holds a subset of panels in canonical order, sharing
the available height equally (user-draggable). See ADR-030 / arc42 §8.17.
"""

from __future__ import annotations

import contextlib
from enum import Enum, auto

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QSplitter, QVBoxLayout, QWidget

from open_garden_planner.ui.widgets.collapsible_panel import CollapsiblePanel

# Qt's QWIDGETSIZE_MAX sentinel — assign to maximumHeight to release a clamp.
_QWIDGETSIZE_MAX = 16777215

# Hover debounce (ms). Asymmetric on purpose: opening is snappy, closing is
# forgiving so a fast diagonal sweep toward the canvas does not cascade-peek and
# the pointer can cross into the expanded body without the peek collapsing.
_PEEK_OPEN_MS = 140
_PEEK_CLOSE_MS = 220

# Minimum usable body height for a peeking panel.
_PEEK_MIN_BODY = 200

# Cap on deferred equalize retries while the splitter still has zero height
# (laid out but not yet shown). Prevents an unbounded singleShot(0) busy loop.
_EQUALIZE_MAX_RETRIES = 20


class PanelState(Enum):
    """Lifecycle state of a single panel within the stack."""

    COLLAPSED = auto()
    PEEKING = auto()
    PINNED = auto()


class PinSource(Enum):
    """Why a panel is pinned. Governs who is allowed to unpin it."""

    USER = auto()  # explicit title click — survives selection clearing
    SELECTION = auto()  # auto-pinned because a matching item is selected


class _PanelEntry:
    """Per-panel bookkeeping. One instance per registered panel."""

    __slots__ = ("key", "panel", "state", "pin_source")

    def __init__(self, key: str, panel: CollapsiblePanel) -> None:
        self.key = key
        self.panel = panel
        self.state = PanelState.COLLAPSED
        self.pin_source: PinSource | None = None


class SidebarController(QWidget):
    """Owns the sidebar layout and the COLLAPSED/PEEKING/PINNED state machine.

    Panels are registered in canonical order via :meth:`add_panel`. Collapsed and
    peeking bars live directly in the top-level ``QVBoxLayout``; pinned panels are
    *moved* into a lazily-created vertical ``QSplitter`` that holds a subset of
    panels in canonical order. A trailing stretch keeps bars top-aligned while no
    panel is pinned.
    """

    # (key, PanelState) — emitted after every committed transition.
    panel_state_changed = pyqtSignal(str, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Canonical registry. Insertion order == canonical order.
        self._entries: dict[str, _PanelEntry] = {}
        self._order: list[str] = []

        self._splitter: QSplitter | None = None

        # The pointer leaves only one bar at a time, so a single pending-close
        # (and pending-open) key is sufficient; the lone timer slot reads the key
        # to know which panel to act on.
        self._pending_open_key: str | None = None
        self._pending_close_key: str | None = None

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        self._layout.addStretch()  # MUST stay the last item; inserts go above it

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

        # Default-arg binding so each lambda captures its own key (not the loop var).
        panel.header.hover_enter.connect(lambda k=key: self._on_hover_enter(k))
        panel.header.hover_leave.connect(lambda k=key: self._on_hover_leave(k))
        panel.header.pin_toggled.connect(lambda _c, k=key: self._on_title_click(k))

        self._apply_collapsed(entry, emit=True)

    def panels(self) -> list[CollapsiblePanel]:
        """All panels in canonical order."""
        return [self._entries[k].panel for k in self._order]

    def pinned_keys(self) -> list[str]:
        """Keys of currently-pinned panels, in canonical order."""
        return [
            k for k in self._order if self._entries[k].state is PanelState.PINNED
        ]

    def state_of(self, key: str) -> PanelState | None:
        """Current state of *key*, or ``None`` if unknown (test/inspection helper)."""
        entry = self._entries.get(key)
        return entry.state if entry is not None else None

    # ----- public commands ----------------------------------------------

    def set_selection_pinned(self, key: str, pinned: bool) -> None:
        """Pin/unpin a panel driven by canvas selection (source SELECTION).

        Unpinning only affects SELECTION-pinned panels; a USER-pinned panel is
        never torn down by selection clearing. Idempotent — safe to call from the
        several selection signals that fan in.
        """
        entry = self._entries.get(key)
        if entry is None:
            return
        if pinned:
            if entry.state is not PanelState.PINNED:
                self._pin(entry, PinSource.SELECTION)
        elif (
            entry.state is PanelState.PINNED
            and entry.pin_source is PinSource.SELECTION
        ):
            self._unpin(entry)

    def collapse_all(self) -> None:
        """Force every panel back to COLLAPSED (startup / reset)."""
        self._cancel_open()
        self._cancel_close()
        for key in self._order:
            entry = self._entries[key]
            if entry.state is PanelState.PINNED:
                self._unpin(entry)
            elif entry.state is PanelState.PEEKING:
                self._apply_collapsed(entry, emit=True)

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
            self._apply_peeking(entry)

    def _commit_pending_close(self) -> None:
        key, self._pending_close_key = self._pending_close_key, None
        if key is None:
            return
        entry = self._entries.get(key)
        if entry is not None and entry.state is PanelState.PEEKING:
            self._apply_collapsed(entry, emit=True)

    def _cancel_open(self) -> None:
        self._pending_open_key = None
        with contextlib.suppress(RuntimeError):
            self._open_timer.stop()

    def _cancel_close(self) -> None:
        self._pending_close_key = None
        with contextlib.suppress(RuntimeError):
            self._close_timer.stop()

    # ----- title click (pin toggle) -------------------------------------

    def _on_title_click(self, key: str) -> None:
        entry = self._entries.get(key)
        if entry is None:
            return
        if entry.state is PanelState.PINNED:
            if entry.pin_source is PinSource.SELECTION:
                # A USER click UPGRADES a selection-pin to USER; stays pinned so
                # it survives the selection clearing.
                entry.pin_source = PinSource.USER
                return
            self._unpin(entry)
        else:
            self._pin(entry, PinSource.USER)

    # ----- state appliers -----------------------------------------------

    def _apply_collapsed(self, entry: _PanelEntry, *, emit: bool) -> None:
        panel = entry.panel
        panel.set_expanded(False, emit=False)
        panel.setMinimumHeight(0)  # drop any pin-era minimum first
        panel.setMaximumHeight(panel.header_height())
        panel.set_visual_state(PanelState.COLLAPSED)
        entry.state = PanelState.COLLAPSED
        if emit:
            self.panel_state_changed.emit(entry.key, PanelState.COLLAPSED)

    def _apply_peeking(self, entry: _PanelEntry) -> None:
        panel = entry.panel
        panel.set_expanded(True, emit=False)
        available = max(0, self.height())
        cap = min(panel.sizeHint().height(), max(_PEEK_MIN_BODY, available))
        panel.setMinimumHeight(0)
        panel.setMaximumHeight(cap)
        panel.set_visual_state(PanelState.PEEKING)
        entry.state = PanelState.PEEKING
        self.panel_state_changed.emit(entry.key, PanelState.PEEKING)

    def _pin(self, entry: _PanelEntry, source: PinSource) -> None:
        # Neutralise any pending timer referencing this key.
        if self._pending_open_key == entry.key:
            self._cancel_open()
        if self._pending_close_key == entry.key:
            self._cancel_close()

        splitter = self._ensure_splitter()
        panel = entry.panel

        # 1) Detach the LAYOUT ITEM from the vbox (widget still parented to self).
        self._layout.removeWidget(panel)

        # 2) Release the peek/collapse clamp BEFORE handing to the splitter, else
        #    the splitter cannot grow the panel past its header height.
        panel.set_expanded(True, emit=False)
        panel.setMaximumHeight(_QWIDGETSIZE_MAX)
        panel.setMinimumHeight(panel.header_height())

        # 3) Insert at the canonical index WITHIN the pinned subset. Computed
        #    BEFORE flipping state to PINNED so the panel does not count itself.
        index = self._splitter_insert_index(entry.key)
        splitter.insertWidget(index, panel)  # reparents into the splitter
        panel.show()  # insertWidget may leave it hidden

        panel.set_visual_state(PanelState.PINNED)
        entry.state = PanelState.PINNED  # set AFTER insert (see index note)
        entry.pin_source = source

        self._equalize_splitter()
        self.panel_state_changed.emit(entry.key, PanelState.PINNED)

    def _unpin(self, entry: _PanelEntry) -> None:
        panel = entry.panel
        splitter = self._splitter
        if splitter is not None:
            panel.setParent(None)  # QSplitter has no removeWidget; reparent away

        self._layout.insertWidget(self._vbox_insert_index(entry.key), panel)
        panel.show()

        entry.pin_source = None
        self._apply_collapsed(entry, emit=True)  # also resets min/max height

        if splitter is not None:
            if splitter.count() == 0:
                self._destroy_splitter()
            else:
                self._equalize_splitter()

    # ----- splitter lifecycle & indexing --------------------------------

    def _ensure_splitter(self) -> QSplitter:
        if self._splitter is None:
            sp = QSplitter(Qt.Orientation.Vertical, self)
            sp.setObjectName("pinnedSplitter")  # QSS targets a grabbable handle
            sp.setChildrenCollapsible(False)  # no pane draggable to 0 px
            sp.setHandleWidth(5)  # grabbable, vs the 1 px main splitter
            # Insert above the trailing stretch and let it (not the stretch)
            # absorb leftover vertical space.
            self._layout.insertWidget(self._layout.count() - 1, sp)
            self._layout.setStretchFactor(sp, 1)
            self._splitter = sp
        return self._splitter

    def _destroy_splitter(self) -> None:
        sp, self._splitter = self._splitter, None
        if sp is not None:
            self._layout.removeWidget(sp)
            sp.deleteLater()

    def _splitter_insert_index(self, key: str) -> int:
        """Index inside the splitter that preserves canonical order.

        The splitter holds a SUBSET of panels; the correct index is the count of
        already-pinned panels that precede ``key`` in canonical order.
        """
        index = 0
        for other_key in self._order:
            if other_key == key:
                break
            if self._entries[other_key].state is PanelState.PINNED:
                index += 1
        return index

    def _vbox_insert_index(self, key: str) -> int:
        """Index in the vbox for a non-pinned bar (canonical order among bars).

        The vbox also contains the splitter (when present) and the trailing
        stretch, but a returned index N still lands the bar after N earlier
        non-pinned bars, which is the canonical position relative to its peers.
        """
        index = 0
        for other_key in self._order:
            if other_key == key:
                break
            if self._entries[other_key].state is not PanelState.PINNED:
                index += 1
        return index

    # ----- equalize -----------------------------------------------------

    def _equalize_splitter(self) -> None:
        if self._splitter is None or self._splitter.count() == 0:
            return

        # Bounded retry: a fresh insert has height 0 until layout runs, so we
        # re-defer a few ticks. The cap stops an unbounded singleShot(0) busy
        # loop if the controller is laid out at zero height (e.g. sidebar hidden
        # while something pins) — without it the retry would spin the event loop
        # until the sidebar is shown.
        def _apply(attempts: int = 0) -> None:
            sp = self._splitter
            if sp is None or sp.count() == 0:
                return  # torn down before this deferred tick fired
            total = sp.height()
            if total <= 0:
                if attempts < _EQUALIZE_MAX_RETRIES:
                    QTimer.singleShot(0, lambda: _apply(attempts + 1))
                return
            n = sp.count()
            share = total // n
            sizes = [share] * n
            sizes[-1] += total - share * n  # absorb integer-division remainder
            sp.setSizes(sizes)

        QTimer.singleShot(0, _apply)  # defer so a fresh insert has real geometry
