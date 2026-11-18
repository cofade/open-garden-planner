"""Unit tests for application resources (US-1.8 and US-1.9)."""

from pathlib import Path

import pytest


class TestResourceFiles:
    """Tests for resource file existence and README banner integration."""

    @pytest.fixture
    def project_root(self) -> Path:
        """Get the project root directory."""
        return Path(__file__).parent.parent.parent

    @pytest.fixture
    def resources_dir(self, project_root: Path) -> Path:
        """Get the resources directory."""
        return project_root / "src" / "open_garden_planner" / "resources"

    def test_icons_directory_exists(self, resources_dir: Path) -> None:
        """Test that the icons directory exists."""
        icons_dir = resources_dir / "icons"
        assert icons_dir.exists()
        assert icons_dir.is_dir()

    def test_logo_icon_exists(self, resources_dir: Path) -> None:
        """Test that OGP_logo.png exists (US-1.8)."""
        logo_path = resources_dir / "icons" / "OGP_logo.png"
        assert logo_path.exists(), "OGP_logo.png not found"
        assert logo_path.is_file()

    def test_banner_image_exists(self, resources_dir: Path) -> None:
        """Test that banner.png exists (US-1.9)."""
        banner_path = resources_dir / "icons" / "banner.png"
        assert banner_path.exists(), "banner.png not found"
        assert banner_path.is_file()

    def test_logo_is_valid_image(self, resources_dir: Path) -> None:
        """Test that OGP_logo.png is a valid image file."""
        logo_path = resources_dir / "icons" / "OGP_logo.png"
        # Check file size > 0 (non-empty file)
        assert logo_path.stat().st_size > 0
        # Check PNG magic bytes
        with open(logo_path, "rb") as f:
            header = f.read(8)
            # PNG files start with these bytes
            assert header[:4] == b"\x89PNG"

    def test_banner_is_valid_image(self, resources_dir: Path) -> None:
        """Test that banner.png is a valid image file."""
        banner_path = resources_dir / "icons" / "banner.png"
        # Check file size > 0 (non-empty file)
        assert banner_path.stat().st_size > 0
        # Check PNG magic bytes
        with open(banner_path, "rb") as f:
            header = f.read(8)
            # PNG files start with these bytes
            assert header[:4] == b"\x89PNG"


class TestReadmeTop:
    """What the README opens with. US-1.9 put the static banner first; #564 replaced it
    with the title, the download button and a picture of the app itself
    (``tests/unit/test_readme_showcase.py`` holds the button and the pictures)."""

    @pytest.fixture
    def readme_path(self) -> Path:
        """Get the README.md path."""
        return Path(__file__).parent.parent.parent / "README.md"

    def test_readme_exists(self, readme_path: Path) -> None:
        """Test that README.md exists."""
        assert readme_path.exists()

    def test_readme_opens_with_the_title_and_shows_the_app_not_the_banner(self, readme_path: Path) -> None:
        content = readme_path.read_text(encoding="utf-8")
        assert content.lstrip().startswith("# Open Garden Planner\n")
        assert "banner.png" not in content, "the hero picture stands where the banner stood"
        assert "](docs/images/readme/hero.jpg)" in content
