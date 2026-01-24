"""Main application window."""

from PyQt6.QtWidgets import QMainWindow


class GardenPlannerApp(QMainWindow):
    """Main application window for Open Garden Planner.

    This is a placeholder that will be expanded in Task #2.
    """

    def __init__(self) -> None:
        """Initialize the main window."""
        super().__init__()
        self.setWindowTitle("Open Garden Planner")
        self.setMinimumSize(800, 600)
