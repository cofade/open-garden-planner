"""The before/after wipe of a growth jump (Phase 17 L2.3, #386). Engine-free.

Two pictures of the same 3D view — before a jump of the plan date and after it —
one over the other, split by a divider the user drags: left of it the garden as it
was, right of it as it will be. It REPLACES the 3D view in its pane while it is
shown (nothing may be drawn over the view: it is a native window, ADR-060) and
gives it back on "Back to 3D View", Escape or a jump that is undone.

The pictures are ordinary ``QImage``s the workspace took from the view
(``growth_jump.py``); this widget only paints them, scaled together to its size.
"""

from __future__ import annotations

from typing import Final

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QSizePolicy, QVBoxLayout, QWidget

#: Where the divider starts (share of the width).
START_SPLIT: Final = 0.5
#: An arrow key moves the divider by this share of the width.
KEY_STEP: Final = 0.05
_LABEL_MARGIN: Final = 8
_HANDLE_RADIUS: Final = 9


class BeforeAfterWipe(QWidget):
    """The wipe (module docstring). ``closed``: the user asked for the 3D view back."""

    closed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setMouseTracking(False)
        self._before = QImage()
        self._after = QImage()
        self._labels = ("", "")
        self._split = START_SPLIT
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        row = QHBoxLayout()
        row.addStretch(1)
        self._back = QPushButton(self.tr("Back to 3D View"), self)
        self._back.setToolTip(self.tr("Close the comparison and show the 3D view (Esc)"))
        self._back.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._back.clicked.connect(self.closed)
        row.addWidget(self._back)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)

    # ── content ──────────────────────────────────────────────────────────────

    def show_pair(self, before: QImage, after: QImage, before_label: str, after_label: str) -> None:
        """The two pictures and their captions; the divider back in the middle."""
        self._before, self._after = QImage(before), QImage(after)
        self._labels = (before_label, after_label)
        self._split = START_SPLIT
        self.update()

    def labels(self) -> tuple[str, str]:
        return self._labels

    def after_image(self) -> QImage:
        """The after-picture shown (a null image while none is)."""
        return QImage(self._after)

    def split(self) -> float:
        """Where the divider is, as a share of the width (0: all "after")."""
        return self._split

    def set_split(self, share: float) -> None:
        share = min(max(float(share), 0.0), 1.0)
        if share != self._split:
            self._split = share
            self.update()

    def has_pictures(self) -> bool:
        return not self._before.isNull() and not self._after.isNull()

    # ── painting ─────────────────────────────────────────────────────────────

    def _target(self) -> QRectF:
        """Where the pictures go: as large as fits, aspect kept, centred."""
        if self._after.isNull():
            return QRectF(self.rect())
        image_w = self._after.width() / max(self._after.devicePixelRatio(), 1e-6)
        image_h = self._after.height() / max(self._after.devicePixelRatio(), 1e-6)
        scale = min(self.width() / max(image_w, 1.0), self.height() / max(image_h, 1.0))
        width, height = image_w * scale, image_h * scale
        return QRectF((self.width() - width) / 2.0, (self.height() - height) / 2.0, width, height)

    def paintEvent(self, _event: QPaintEvent | None) -> None:  # noqa: N802 - Qt's name
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), self.palette().window())
            if not self.has_pictures():
                return
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            target = self._target()
            cut = target.left() + self._split * target.width()
            painter.save()
            painter.setClipRect(QRectF(target.left(), target.top(), cut - target.left(), target.height()))
            painter.drawImage(target, self._before)
            painter.restore()
            painter.save()
            painter.setClipRect(QRectF(cut, target.top(), target.right() - cut, target.height()))
            painter.drawImage(target, self._after)
            painter.restore()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            pen = QPen(QColor(255, 255, 255, 230), 2.0)
            painter.setPen(pen)
            painter.drawLine(QPointF(cut, target.top()), QPointF(cut, target.bottom()))
            painter.setBrush(QColor(255, 255, 255, 230))
            painter.drawEllipse(QPointF(cut, target.center().y()), _HANDLE_RADIUS, _HANDLE_RADIUS)
            self._caption(painter, self._labels[0], target, left=True)
            self._caption(painter, self._labels[1], target, left=False)
        finally:
            painter.end()

    def _caption(self, painter: QPainter, text: str, target: QRectF, *, left: bool) -> None:
        if not text:
            return
        metrics = painter.fontMetrics()
        width = metrics.horizontalAdvance(text) + 2 * _LABEL_MARGIN
        height = metrics.height() + _LABEL_MARGIN
        x = target.left() + _LABEL_MARGIN if left else target.right() - _LABEL_MARGIN - width
        box = QRectF(x, target.bottom() - _LABEL_MARGIN - height, width, height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 150))
        painter.drawRoundedRect(box, 4.0, 4.0)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(box, int(Qt.AlignmentFlag.AlignCenter), text)

    # ── input ────────────────────────────────────────────────────────────────

    def _split_at(self, x: float) -> None:
        target = self._target()
        if target.width() > 0.0:
            self.set_split((x - target.left()) / target.width())

    def mousePressEvent(self, event: QMouseEvent | None) -> None:  # noqa: N802 - Qt's name
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            self._split_at(event.position().x())
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:  # noqa: N802 - Qt's name
        if event is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._split_at(event.position().x())
            event.accept()

    def keyPressEvent(self, event: QKeyEvent | None) -> None:  # noqa: N802 - Qt's name
        if event is None:
            return
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.closed.emit()
        elif key == Qt.Key.Key_Left:
            self.set_split(self._split - KEY_STEP)
        elif key == Qt.Key.Key_Right:
            self.set_split(self._split + KEY_STEP)
        else:
            super().keyPressEvent(event)
            return
        event.accept()
