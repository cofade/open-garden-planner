"""Unit tests for the thumbnail loader service (US-G2, issue #317)."""

from __future__ import annotations

from open_garden_planner.services.plant_api.thumbnail_loader import (
    _cache_key,
    _cache_path,
    clear_cache,
    get_cached_thumbnail,
    is_cached,
)


class TestThumbnailLoader:
    def test_cache_key_is_deterministic(self) -> None:
        url = "https://example.com/plant.jpg"
        assert _cache_key(url) == _cache_key(url)

    def test_cache_key_differs_for_different_urls(self) -> None:
        assert _cache_key("https://example.com/a.jpg") != _cache_key(
            "https://example.com/b.jpg"
        )

    def test_cache_path_uses_cache_key(self) -> None:
        url = "https://example.com/plant.jpg"
        path = _cache_path(url)
        assert path.name == f"{_cache_key(url)}.png"

    def test_is_cached_returns_false_for_missing(self) -> None:
        url = "https://example.com/nonexistent.jpg"
        assert not is_cached(url)

    def test_get_cached_thumbnail_returns_none_for_missing(self) -> None:
        url = "https://example.com/nonexistent.jpg"
        assert get_cached_thumbnail(url) is None

    def test_clear_cache_returns_zero_when_empty(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "open_garden_planner.services.plant_api.thumbnail_loader.get_cache_dir",
            lambda: tmp_path,
        )
        assert clear_cache() == 0

    def test_clear_cache_removes_files(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "open_garden_planner.services.plant_api.thumbnail_loader.get_cache_dir",
            lambda: tmp_path,
        )
        (tmp_path / "abc123.png").write_bytes(b"fake")
        (tmp_path / "def456.png").write_bytes(b"fake")
        assert clear_cache() == 2
