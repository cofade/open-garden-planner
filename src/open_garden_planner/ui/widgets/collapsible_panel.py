"""Collapsible panel widget for sidebar organization."""

import contextlib

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QPropertyAnimation,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QEnterEvent, QMouseEvent
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

# Qt's QWIDGETSIZE_MAX sentinel — assign to maximumHeight to release a clamp.
_QWIDGETSIZE_MAX = 16777215

# Open/collapse animation duration (ms). Short enough to feel responsive,
# long enough to read as an organic expansion rather than a hard switch.
_PANEL_ANIM_MS = 160


class _HeaderFrame(QFrame):
    """Header bar that reports hover and click as signals.

    Replaces the old ``mousePressEvent = lambda: toggle()`` assignment so the
    owning :class:`~open_garden_planner.ui.widgets.panel_stack.SidebarController`
    can route hover-peek and pin-toggle independently. Child widgets added via
    :meth:`CollapsiblePanel.add_header_widget` (e.g. the Constraints delete-all
    button) consume their own clicks first, so they never reach ``pin_toggled``.
    """

    hover_enter = pyqtSignal()
    hover_leave = pyqtSignal()
    pin_toggled = pyqtSignal(bool)

    def enterEvent(self, event: QEnterEvent) -> None:  # noqa: N802 (Qt override)
        self.hover_enter.emit()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802 (Qt override)
        self.hover_leave.emit()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton:
            self.pin_toggled.emit(True)
        super().mousePressEvent(event)


class CollapsiblePanel(QWidget):
    """A collapsible panel with a header and content area.

    The panel can be collapsed/expanded by clicking the header.
    """

    expanded_changed = pyqtSignal(bool)

    def __init__(
        self,
        title: str,
        content: QWidget | None = None,
        parent: QWidget | None = None,
        expanded: bool = True,
    ) -> None:
        """Initialize the collapsible panel.

        Args:
            title: Panel title displayed in header
            content: Widget to display in the content area
            parent: Parent widget
            expanded: Initial expanded state
        """
        super().__init__(parent)
        self._title = title
        self._expanded = expanded
        self._content_widget = content
        self._info_label: QLabel | None = None
        self._anim: QPropertyAnimation | None = None

        self._setup_ui()
        self.set_expanded(expanded, emit=False)

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header frame with background. _HeaderFrame emits hover/pin signals;
        # the SidebarController decides what a header click/hover does (peek vs
        # pin), so no toggle handler is wired here.
        self._header = _HeaderFrame()
        self._header.setFrameShape(QFrame.Shape.StyledPanel)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)

        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(6, 4, 6, 4)

        # Expand/collapse indicator
        self._indicator = QLabel()
        self._indicator.setFixedWidth(16)
        header_layout.addWidget(self._indicator)

        # Title label
        title_label = QLabel(self._title)
        title_label.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        # Info icon (hidden by default, shown when set_info_tooltip is called)
        self._info_label = QLabel("ℹ️")
        self._info_label.setStyleSheet("""
            QLabel {
                border: none;
                font-size: 14pt;
            }
            QToolTip {
                background-color: white;
                color: black;
                border: 1px solid palette(mid);
                padding: 4px;
                font-size: 10pt;
            }
        """)
        self._info_label.setVisible(False)
        header_layout.addWidget(self._info_label)

        layout.addWidget(self._header)

        # Content area
        if self._content_widget:
            layout.addWidget(self._content_widget)

    def set_content(self, widget: QWidget) -> None:
        """Set the content widget.

        Args:
            widget: Widget to display in content area
        """
        if self._content_widget:
            self._content_widget.setParent(None)

        self._content_widget = widget
        if widget:
            self.layout().addWidget(widget)
            widget.setVisible(self._expanded)

    def is_expanded(self) -> bool:
        """Check if panel is expanded.

        Returns:
            True if expanded, False if collapsed
        """
        return self._expanded

    def set_expanded(self, expanded: bool, emit: bool = True) -> None:
        """Set the expanded state.

        Args:
            expanded: True to expand, False to collapse
            emit: Whether to emit the expanded_changed signal
        """
        self._expanded = expanded

        # Update indicator
        self._indicator.setText("▼" if expanded else "▶")

        # Show/hide content
        if self._content_widget:
            self._content_widget.setVisible(expanded)

        if emit:
            self.expanded_changed.emit(expanded)

    def toggle(self) -> None:
        """Toggle the expanded state."""
        self.set_expanded(not self._expanded)

    def expand(self) -> None:
        """Expand the panel."""
        self.set_expanded(True)

    def collapse(self) -> None:
        """Collapse the panel."""
        self.set_expanded(False)

    def add_header_widget(self, widget: QWidget) -> None:
        """Add a widget to the right side of the header (e.g. an action button).

        The widget is inserted before the info icon at the end of the header row.
        Clicks on the widget do NOT toggle the panel (child widgets consume their
        own mouse events before the QFrame's mousePressEvent fires).

        Args:
            widget: Widget to add to the header
        """
        layout = self._header.layout()
        # Insert before the info label (last item)
        layout.insertWidget(layout.count() - 1, widget)

    def set_info_tooltip(self, tooltip: str) -> None:
        """Set tooltip text for the info icon.

        Args:
            tooltip: Tooltip text to display on hover. Empty string hides the icon.
        """
        if self._info_label:
            if tooltip:
                self._info_label.setToolTip(tooltip)
                self._info_label.setVisible(True)
            else:
                self._info_label.setVisible(False)

    @property
    def header(self) -> _HeaderFrame:
        """The header bar (exposes ``hover_enter``/``hover_leave``/``pin_toggled``)."""
        return self._header

    def header_height(self) -> int:
        """Natural pixel height of the header row (the COLLAPSED clamp target)."""
        return self._header.sizeHint().height()

    def set_visual_state(self, state: object) -> None:
        """Drive a dynamic ``panelState`` QSS property + re-polish the header.

        Args:
            state: A ``PanelState`` enum member; ``state.name.lower()`` becomes the
                property value so QSS can target each state. Duck-typed on
                ``.name`` to avoid a cyclic import of ``panel_stack``.
        """
        name = state.name.lower()  # type: ignore[attr-defined]
        self.setProperty("panelState", name)
        # Tooltip hints the click affordance for the current state.
        if name == "pinned":
            self._header.setToolTip(self.tr("Click to collapse"))
        elif name == "peeking":
            self._header.setToolTip(self.tr("Click to keep open"))
        else:
            self._header.setToolTip(self.tr("Click to open"))
        # Dynamic-property changes require an unpolish/polish cycle to repaint
        # (Qt does not re-evaluate property selectors otherwise). The header is
        # styled via `CollapsiblePanel[panelState=...] > QFrame`, so re-polish it
        # too — re-polishing only the parent leaves the child header stale.
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
            style.unpolish(self._header)
            style.polish(self._header)

    # ----- geometry primitives (driven by SidebarController) -------------
    #
    # The panel's open/closed geometry is a height clamp on ``maximumHeight``:
    # collapsed clamps to the header height (content hidden); open releases the
    # clamp so the layout sizes the panel to its content. The ``animate_*``
    # variants tween the clamp for an organic expansion; the ``*_now`` variants
    # snap (used at startup / bulk reset).

    def _set_indicator(self, expanded: bool) -> None:
        """Flip the ▼/▶ chevron + logical state without touching content."""
        self._expanded = expanded
        self._indicator.setText("▼" if expanded else "▶")

    def _ensure_anim(self) -> QPropertyAnimation:
        if self._anim is None:
            anim = QPropertyAnimation(self, b"maximumHeight", self)
            anim.setDuration(_PANEL_ANIM_MS)
            anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
            self._anim = anim
        return self._anim

    def _restart_anim(self, start: int, end: int, on_finished) -> None:
        anim = self._ensure_anim()
        anim.stop()
        with contextlib.suppress(TypeError):
            anim.finished.disconnect()
        anim.setStartValue(int(start))
        anim.setEndValue(int(end))
        anim.finished.connect(on_finished)
        anim.start()

    def expand_now(self) -> None:
        """Snap to open: content visible, height clamp released."""
        if self._anim is not None:
            self._anim.stop()
        self.set_expanded(True, emit=False)
        self.setMinimumHeight(0)
        self.setMaximumHeight(_QWIDGETSIZE_MAX)

    def collapse_now(self) -> None:
        """Snap to collapsed: content hidden, height clamped to the header."""
        if self._anim is not None:
            self._anim.stop()
        self.set_expanded(False, emit=False)
        self.setMinimumHeight(0)
        self.setMaximumHeight(self.header_height())

    def animate_expand(self) -> None:
        """Tween open: reveal content as the height clamp grows to content size."""
        self.set_expanded(True, emit=False)  # show content so sizeHint is valid
        self.setMinimumHeight(0)
        start = self.height()
        end = max(self.header_height(), self.sizeHint().height())
        self._restart_anim(start, end, self._after_animate_expand)

    def _after_animate_expand(self) -> None:
        # Release the clamp so the panel tracks its content size from now on
        # (e.g. when a list populates after the open animation).
        self.setMaximumHeight(_QWIDGETSIZE_MAX)

    def animate_collapse(self) -> None:
        """Tween closed: shrink the height clamp to the header, then hide content."""
        # Flip the chevron + logical state immediately for responsiveness, but
        # keep the content widget visible so it is drawn (clipped) during the
        # shrink; it is hidden when the animation finishes.
        self._set_indicator(False)
        self.setMinimumHeight(0)
        start = self.height()
        end = self.header_height()
        self._restart_anim(start, end, self._after_animate_collapse)

    def _after_animate_collapse(self) -> None:
        if self._content_widget is not None:
            self._content_widget.setVisible(False)
        self.setMaximumHeight(self.header_height())
