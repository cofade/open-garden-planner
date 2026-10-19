"""Poison-response regressions for A1; no network or real profile writes."""

from unittest.mock import MagicMock, patch

from open_garden_planner.services import image_download
from open_garden_planner.services.plant_api import thumbnail_loader
from open_garden_planner.services.update_checker import parse_release_info


def test_image_content_type_does_not_make_html_an_image(tmp_path, monkeypatch):
    monkeypatch.setattr(thumbnail_loader, "get_cache_dir", lambda: tmp_path)
    response = MagicMock()
    response.headers = {"Content-Type": "image/png"}
    response.status_code = 200
    response.content = b"<html>not an image</html>"
    response.iter_content.return_value = [response.content]
    response.__enter__.return_value = response
    with patch.object(image_download.requests, "get", return_value=response):
        assert thumbnail_loader.fetch_thumbnail("https://example.com/photo.png") is None
    assert list(tmp_path.iterdir()) == []


def test_duplicate_installer_assets_are_refused():
    asset = {
        "name": "OpenGardenPlanner-v1.30.2-Setup.exe",
        "browser_download_url": "https://github.com/cofade/open-garden-planner/releases/download/v1.30.2/OpenGardenPlanner-v1.30.2-Setup.exe",
        "size": 10,
    }
    info = parse_release_info({"tag_name": "v1.30.2", "assets": [asset, asset]})
    assert info.download_url is None
