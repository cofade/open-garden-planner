"""The README as the repository's shop window (#564).

The download button links to the installer of one release, because the release workflow
names the installer after its version and "the latest installer" has no fixed address.
``scripts/prepare_version_sync.py`` moves the link with every release; these tests hold
the link, the package version and the README's pictures together.
"""

import re
from pathlib import Path

import pytest
from scripts.prepare_version_sync import INSTALLER_LINK, SYNC_FILES, replace_installer_link

from open_garden_planner import __version__

ROOT = Path(__file__).resolve().parents[2]
README = (ROOT / "README.md").read_text(encoding="utf-8")
IMAGES = re.findall(r'!\[([^\]]*)\]\(([^)\s]+)\)|<img\s+src="([^"]+)"\s+alt="([^"]*)"', README)


def test_the_download_button_stands_under_the_title_and_links_to_this_versions_installer():
    links = INSTALLER_LINK.findall(README)
    assert len(links) >= 1
    expected = (f"https://github.com/cofade/open-garden-planner/releases/download/v{__version__}/"
                f"OpenGardenPlanner-v{__version__}-Setup.exe")
    assert README.count(expected) == len(links), "every installer link names the package's version"
    title = README.index("# Open Garden Planner")
    button = README.index(expected)
    first_picture = min(README.index(marker, title) for marker in ("![", "<img")
                        if marker in README[title:])
    assert title < button, "the button is under the title"
    # the button's own image is the first picture after the title: nothing stands above it
    assert README[button:first_picture + 200].count("download-windows.svg") == 1
    assert (ROOT / "docs/images/readme/download-windows.svg").is_file()


def test_the_version_sync_moves_every_installer_link():
    assert "README.md" in SYNC_FILES
    moved = replace_installer_link(README, "9.8.7")
    assert moved.count("releases/download/v9.8.7/OpenGardenPlanner-v9.8.7-Setup.exe") == len(
        INSTALLER_LINK.findall(README))
    assert f"v{__version__}/OpenGardenPlanner" not in moved
    # nothing else changed
    assert INSTALLER_LINK.sub("", moved) == INSTALLER_LINK.sub("", README)
    with pytest.raises(ValueError, match="no installer download link"):
        replace_installer_link("# A README without a button\n", "9.8.7")


def test_every_readme_picture_exists_and_says_what_it_shows():
    assert IMAGES
    for markdown_alt, markdown_path, html_path, html_alt in IMAGES:
        path, alt = markdown_path or html_path, markdown_alt or html_alt
        if path.startswith("http"):
            continue                       # a badge served by its own site
        assert (ROOT / path).is_file(), path
        assert len(alt.strip()) >= 12, f"{path}: alt text says what the picture shows"
