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


def test_the_readme_shows_every_bundled_example_and_links_to_its_plan():
    from tests.example_specs import SPECS

    for slug in SPECS:
        assert f"docs/images/readme/examples/{slug}.jpg" in README, slug
        assert f"src/open_garden_planner/resources/examples/{slug}.ogp" in README, slug
    assert "resources/examples/PROVENANCE.md" in README, "the attribution is one click away"


def test_the_readme_pictures_are_the_capture_scripts_and_none_is_left_over():
    """Every picture comes out of ``scripts/capture_readme_media.py`` and is used: a
    picture nobody re-shoots goes stale, and one nobody shows is weight in every clone."""
    folder = ROOT / "docs/images/readme"
    shown = {path or html_path for _alt, path, html_path, _html_alt in IMAGES}
    kept = {path.relative_to(ROOT).as_posix() for path in folder.rglob("*") if path.is_file()}
    assert kept == {path for path in shown if path.startswith("docs/images/readme/")}
    for path in sorted(kept):
        assert (ROOT / path).stat().st_size <= 600 * 1024, f"{path}: a README picture loads fast"
    script = (ROOT / "scripts/capture_readme_media.py").read_text(encoding="utf-8")
    for path in sorted(kept - {"docs/images/readme/download-windows.svg"}):
        name = Path(path).stem
        stem = name if "/examples/" not in path else "examples/"
        assert f'"{stem}' in script or f'f"{stem.split("-")[0]}-' in script, f"{path}: no shot writes it"


def test_the_installer_link_names_the_file_the_release_workflow_uploads():
    """The link's pattern and the workflow's asset name are written in two places."""
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert '"dist/OpenGardenPlanner-v${{ steps.version.outputs.version }}-Setup.exe"' in workflow
    assert INSTALLER_LINK.search(
        "https://github.com/cofade/open-garden-planner/releases/download/v1.2.3/OpenGardenPlanner-v1.2.3-Setup.exe")
