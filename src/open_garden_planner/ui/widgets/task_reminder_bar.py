"""Dismissible overdue-task reminder bar (US-C2, #188).

Shown at the top of the main window on startup / project-open when the open
project has overdue manual tasks. A persistent, non-modal bar is used instead of
a transient status-bar message: the status bar message was set while the modal
Welcome dialog still covered the window (invisible), and even afterwards a 10 s
status blip is easily missed or clobbered by other writes. See §11.4.
"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)


class TaskReminderBar(QFrame):
    """Horizontal notification bar for overdue tasks.

    Signals:
        show_tasks_requested: Emitted when the user clicks "Show Tasks".
    """

    show_tasks_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()
        self.hide()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_reminder(self, count: int) -> None:
        """Populate and display the bar for ``count`` overdue tasks."""
        if count <= 0:
            self.hide()
            return
        # "manual" is load-bearing: _check_overdue_tasks counts only manual
        # tasks (auto-generated tasks need the scene + an async weather fetch
        # that aren't ready this early), so the wording must stay honest.
        self._label.setText(
            self.tr("You have {n} overdue manual task(s).").format(n=count)
        )
        self.show()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setObjectName("TaskReminderBar")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMaximumHeight(44)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        self._label = QLabel()
        self._label.setWordWrap(False)
        layout.addWidget(self._label, stretch=1)

        show_btn = QPushButton(self.tr("Show Tasks"))
        show_btn.setFixedHeight(28)
        show_btn.clicked.connect(self._on_show_tasks)
        layout.addWidget(show_btn)

        dismiss_btn = QPushButton(self.tr("Dismiss"))
        dismiss_btn.setFixedHeight(28)
        dismiss_btn.clicked.connect(self.hide)
        layout.addWidget(dismiss_btn)

        # Styling lives in theme.py's global stylesheet (#TaskReminderBar
        # rules, warning_bg banner) so a theme switch restyles the bar
        # automatically — no per-widget QSS here.

    def _on_show_tasks(self) -> None:
        self.show_tasks_requested.emit()
        self.hide()
