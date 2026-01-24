"""Pytest configuration and fixtures."""

import sys
from pathlib import Path

import pytest

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


@pytest.fixture(scope="session")
def qapp_args() -> list[str]:
    """Arguments for QApplication in pytest-qt."""
    return ["--platform", "offscreen"]
