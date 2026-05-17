"""Cursor-anchored floating input overlay (Package A US-A4).

Two QLineEdits (distance, angle) that mirror the shared
``CoordinateInputBuffer``.  The overlay tracks the cursor inside the
:class:`CanvasView` viewport and stays close to the user's eye-line so
typing feels CAD-native.

Visibility rules:
    * Hidden when dynamic input is disabled in the View menu.
    * Hidden when there is no active drawing tool (or only SELECT).
    * Hidden when the tool's ``last_point`` is ``None`` (we have no
      anchor to apply polar/relative input against).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import (
    QEvent,
    QPoint,
    QPointF,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QFocusEvent, QKeyEvent
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
)

from open_garden_planner.core.coordinate_input import CoordinateInputBuffer

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView


class DynamicInputOverlay(QFrame):
    """Floating distance/angle entry near the cursor."""

    commit_requested = pyqtSignal(QPointF)

    OFFSET = QPoint(18, -42)

    def __init__(
        self,
        view: CanvasView,
        buffer: CoordinateInputBuffer,
    ) -> None:
        super().__init__(view.viewport())
        self._view = view
        self._buffer = buffer
        self._suppress_buffer_signal = False

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            "DynamicInputOverlay {"
            "  background-color: rgba(30, 30, 30, 200);"
            "  border: 1px solid rgba(120, 200, 120, 180);"
            "  border-radius: 4px;"
            "}"
            "QLabel { color: white; padding-right: 2px; }"
            "QLineEdit {"
            "  background-color: rgba(60, 60, 60, 220);"
            "  color: white;"
            "  border: 1px solid rgba(120, 200, 120, 100);"
            "  padding: 1px 4px;"
            "}"
        )
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._distance_edit = _DynamicLineEdit(self)
        self._distance_edit.setPlaceholderText(self.tr("dist"))
        self._distance_edit.setMaximumWidth(70)

        self._angle_edit = _DynamicLineEdit(self)
        self._angle_edit.setPlaceholderText(self.tr("ang"))
        self._angle_edit.setMaximumWidth(50)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(4)
        layout.addWidget(self._distance_edit)
        layout.addWidget(QLabel("<"))
        layout.addWidget(self._angle_edit)

        # Wiring
        self._distance_edit.textEdited.connect(self._on_field_changed)
        self._angle_edit.textEdited.connect(self._on_field_changed)
        self._distance_edit.returnPressed.connect(self._on_return)
        self._angle_edit.returnPressed.connect(self._on_return)

        buffer.text_changed.connect(self._on_buffer_text_changed)
        buffer.anchor_changed.connect(self._on_anchor_changed)

        self.adjustSize()
        self.hide()

        # Re-clamp on viewport resize so the overlay doesn't drift off-screen
        # when the user drags the canvas/sidebar splitter.
        view.viewport().installEventFilter(self)
        self._last_anchor_pos: QPoint | None = None

    def eventFilter(  # noqa: N802 (Qt)
        self, _watched: object, event: QEvent
    ) -> bool:
        if (
            event.type() == QEvent.Type.Resize
            and self.isVisible()
            and self._last_anchor_pos is not None
        ):
            self.show_near(self._last_anchor_pos)
        return False

    # --- Visibility ----------------------------------------------------

    def show_near(self, viewport_pos: QPoint) -> None:
        self._last_anchor_pos = QPoint(viewport_pos)
        target = viewport_pos + self.OFFSET
        parent = self.parentWidget()
        if parent is not None:
            # Keep inside the viewport bounds.
            target.setX(
                max(2, min(parent.width() - self.width() - 2, target.x()))
            )
            target.setY(
                max(2, min(parent.height() - self.height() - 2, target.y()))
            )
        self.move(target)
        if not self.isVisible():
            self.show()
        self.raise_()

    def hide_overlay(self) -> None:
        self._distance_edit.clear()
        self._angle_edit.clear()
        self.hide()

    # --- Field <-> buffer sync ----------------------------------------

    def _on_field_changed(self, _text: str) -> None:
        dist = self._distance_edit.text().strip()
        ang = self._angle_edit.text().strip()
        if not dist and not ang:
            self._buffer.set_text("")
            return
        # Build a polar string; user must supply at least the distance for
        # the parser to succeed, but partial input is still mirrored.
        text = f"@{dist or '0'}<{ang or '0'}"
        self._suppress_buffer_signal = True
        try:
            self._buffer.set_text(text)
        finally:
            self._suppress_buffer_signal = False

    def _on_return(self) -> None:
        result = self._buffer.commit()
        if result is None:
            self._flash_error()
            return
        self.commit_requested.emit(result.point)
        self._buffer.clear()

    def _on_buffer_text_changed(self, text: str) -> None:
        if self._suppress_buffer_signal:
            return
        # Try to split a polar string; otherwise reset the fields.
        if "<" in text:
            body = text[1:] if text.startswith("@") else text
            dist, _, ang = body.partition("<")
            if self._distance_edit.text() != dist.strip():
                self._distance_edit.setText(dist.strip())
            if self._angle_edit.text() != ang.strip():
                self._angle_edit.setText(ang.strip())

    def _on_anchor_changed(self, _anchor: object) -> None:
        # Anchor management is owned by CanvasView; the overlay simply
        # listens so it can hide when no anchor exists.
        pass

    # --- Visual --------------------------------------------------------

    def _flash_error(self) -> None:
        self._distance_edit.setStyleSheet(
            "QLineEdit { background-color: rgba(180, 60, 60, 220); }"
        )
        self._angle_edit.setStyleSheet(
            "QLineEdit { background-color: rgba(180, 60, 60, 220); }"
        )

    # --- Focus ---------------------------------------------------------

    def focus_distance(self) -> None:
        self._distance_edit.setFocus(Qt.FocusReason.OtherFocusReason)
        self._distance_edit.selectAll()


class _DynamicLineEdit(QLineEdit):
    """Internal QLineEdit that escapes to the parent canvas on Esc."""

    def __init__(self, parent: DynamicInputOverlay) -> None:
        super().__init__(parent)
        self._overlay = parent

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt)
        if event.key() == Qt.Key.Key_Escape:
            self._overlay.hide_overlay()
            view = self._overlay._view  # noqa: SLF001
            view.setFocus(Qt.FocusReason.OtherFocusReason)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Tab:
            other = (
                self._overlay._angle_edit  # noqa: SLF001
                if self is self._overlay._distance_edit  # noqa: SLF001
                else self._overlay._distance_edit  # noqa: SLF001
            )
            other.setFocus(Qt.FocusReason.TabFocusReason)
            other.selectAll()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event: QFocusEvent) -> None:  # noqa: N802 (Qt)
        self.setStyleSheet("")
        super().focusInEvent(event)
