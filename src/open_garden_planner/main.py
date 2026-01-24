"""Main entry point for Open Garden Planner."""

import sys


def main() -> int:
    """Run the Open Garden Planner application."""
    # Import here to avoid slow startup for --help, --version, etc.
    from PyQt6.QtWidgets import QApplication

    from open_garden_planner.app.application import GardenPlannerApp

    app = QApplication(sys.argv)
    app.setApplicationName("Open Garden Planner")
    app.setOrganizationName("cofade")
    app.setOrganizationDomain("github.com/cofade")

    window = GardenPlannerApp()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
