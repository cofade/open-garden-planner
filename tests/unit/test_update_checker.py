"""Tests for US-8.3: update checker pure functions."""

from typing import Any

import pytest

from open_garden_planner.services.update_checker import (
    ReleaseInfo,
    compare_versions,
    parse_release_info,
)


# ---------------------------------------------------------------------------
# compare_versions
# ---------------------------------------------------------------------------


class TestCompareVersions:
    """Tests for compare_versions()."""

    def test_newer_minor(self) -> None:
        assert compare_versions("1.5.1", "v1.6.0") is True

    def test_newer_patch(self) -> None:
        assert compare_versions("1.5.0", "v1.5.1") is True

    def test_newer_major(self) -> None:
        assert compare_versions("1.9.9", "v2.0.0") is True

    def test_same_version(self) -> None:
        assert compare_versions("1.5.1", "v1.5.1") is False

    def test_older_latest(self) -> None:
        assert compare_versions("1.6.0", "v1.5.9") is False

    def test_no_v_prefix_on_current(self) -> None:
        assert compare_versions("v1.5.1", "v1.6.0") is True

    def test_both_without_prefix(self) -> None:
        assert compare_versions("1.0.0", "2.0.0") is True

    def test_invalid_version_returns_false(self) -> None:
        assert compare_versions("not-a-version", "v1.0.0") is False

    def test_empty_latest_returns_false(self) -> None:
        assert compare_versions("1.0.0", "") is False


# ---------------------------------------------------------------------------
# parse_release_info
# ---------------------------------------------------------------------------


def _make_asset(name: str, url: str) -> dict[str, str]:
    return {"name": name, "browser_download_url": url}


class TestParseReleaseInfo:
    """Tests for parse_release_info()."""

    def test_full_payload(self) -> None:
        data: dict[str, Any] = {
            "tag_name": "v1.6.0",
            "body": "## What's New\n- Feature A\n- Feature B",
            "html_url": "https://github.com/cofade/open-garden-planner/releases/tag/v1.6.0",
            "assets": [
                _make_asset("OpenGardenPlanner-v1.6.0-Setup.exe", "https://example.com/setup.exe"),
                _make_asset("OpenGardenPlanner-v1.6.0-symbols.zip", "https://example.com/syms.zip"),
            ],
        }
        info = parse_release_info(data)
        assert info.tag_name == "v1.6.0"
        assert "What's New" in info.body
        assert info.download_url == "https://example.com/setup.exe"
        assert info.html_url == "https://github.com/cofade/open-garden-planner/releases/tag/v1.6.0"

    def test_no_setup_asset(self) -> None:
        data: dict[str, Any] = {
            "tag_name": "v1.6.0",
            "body": "release notes",
            "assets": [_make_asset("source.tar.gz", "https://example.com/src.tar.gz")],
        }
        info = parse_release_info(data)
        assert info.download_url is None

    def test_empty_assets(self) -> None:
        data: dict[str, Any] = {"tag_name": "v1.6.0", "body": "", "assets": []}
        info = parse_release_info(data)
        assert info.download_url is None

    def test_body_truncated_to_300_chars(self) -> None:
        long_body = "x" * 500
        data: dict[str, Any] = {"tag_name": "v1.0.0", "body": long_body, "assets": []}
        info = parse_release_info(data)
        assert len(info.body) == 300

    def test_missing_fields_use_defaults(self) -> None:
        info = parse_release_info({})
        assert info.tag_name == ""
        assert info.body == ""
        assert info.download_url is None
        assert info.html_url == ""

    def test_none_body_treated_as_empty(self) -> None:
        data: dict[str, Any] = {"tag_name": "v1.0.0", "body": None, "assets": []}
        info = parse_release_info(data)
        assert info.body == ""

    def test_first_setup_exe_asset_wins(self) -> None:
        data: dict[str, Any] = {
            "tag_name": "v1.6.0",
            "body": "",
            "assets": [
                _make_asset("OpenGardenPlanner-v1.6.0-Setup.exe", "https://example.com/first.exe"),
                _make_asset("OpenGardenPlanner-v1.6.0-Setup.exe", "https://example.com/second.exe"),
            ],
        }
        info = parse_release_info(data)
        assert info.download_url == "https://example.com/first.exe"

    def test_returns_release_info_instance(self) -> None:
        info = parse_release_info({"tag_name": "v1.0.0", "body": "hi", "assets": []})
        assert isinstance(info, ReleaseInfo)

    def test_html_url_extracted(self) -> None:
        data: dict[str, Any] = {
            "tag_name": "v1.0.0",
            "body": "",
            "assets": [],
            "html_url": "https://github.com/cofade/open-garden-planner/releases/tag/v1.0.0",
        }
        info = parse_release_info(data)
        assert info.html_url == "https://github.com/cofade/open-garden-planner/releases/tag/v1.0.0"
