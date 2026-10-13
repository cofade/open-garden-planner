"""Resource-bound image transfer and cache migration regressions (AUD-047)."""

import io
from unittest.mock import patch

import pytest
from PIL import Image

from open_garden_planner.services import image_download as images
from open_garden_planner.services.plant_api import thumbnail_loader as thumbs


def picture(fmt="PNG", size=(20, 10)):
    stream = io.BytesIO()
    Image.new("RGB", size, "green").save(stream, format=fmt)
    return stream.getvalue()


class Response:
    def __init__(self, content, headers=None, status=200):
        self.content = content
        self.headers = {"Content-Type": "image/png"} if headers is None else headers
        self.status_code = status
        self.closed = False
        self.read_bytes = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def iter_content(self, chunk_size):
        for index in range(0, len(self.content), chunk_size):
            chunk = self.content[index:index + chunk_size]
            self.read_bytes += len(chunk)
            yield chunk


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP", "GIF"])
def test_verified_supported_formats_are_normalized_to_png(tmp_path, monkeypatch, fmt):
    monkeypatch.setattr(thumbs, "get_cache_dir", lambda: tmp_path)
    response = Response(picture(fmt))
    with patch.object(images.requests, "get", return_value=response) as network:
        path = thumbs.fetch_thumbnail("https://example.com/photo")
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert Image.open(path).size == (20, 10)
    assert response.closed
    assert network.call_args.kwargs["stream"] is True


@pytest.mark.parametrize("content,headers", [
    (b"<html>error</html>", {"Content-Type": "image/png"}),
    (picture(), {"Content-Type": "text/html"}),
    (picture()[:30], {"Content-Type": "image/png"}),
    (b"x" * 65537, {"Content-Type": "image/png", "Content-Length": "1"}),
    (b"x", {"Content-Type": "image/png", "Content-Length": "65537"}),
], ids=["html", "wrong-mime", "truncated", "lying-length", "oversized-header"])
def test_bad_response_rejected_and_closed(content, headers):
    response = Response(content, headers)
    with patch.object(images.requests, "get", return_value=response), pytest.raises((ValueError, OSError)):
        images.fetch_image("https://example.com/p", max_bytes=65536, max_pixels=1000, timeout=1)
    assert response.closed


def test_actual_byte_boundary_is_inclusive():
    content = picture()
    for limit in (len(content), len(content) - 1):
        response = Response(content)
        with patch.object(images.requests, "get", return_value=response):
            if limit == len(content):
                assert images.fetch_image("https://example.com/p", max_bytes=limit, max_pixels=1000, timeout=1).size == (20, 10)
            else:
                with pytest.raises(ValueError, match="byte limit"):
                    images.fetch_image("https://example.com/p", max_bytes=limit, max_pixels=1000, timeout=1)
        assert response.closed


def test_pixel_limit_before_full_decode():
    with pytest.raises(ValueError, match="dimensions"):
        images.decode_image(picture(size=(100, 100)), max_pixels=9999)


def test_cache_rejects_corruption_and_migrates_legacy_jpeg(tmp_path, monkeypatch):
    monkeypatch.setattr(thumbs, "get_cache_dir", lambda: tmp_path)
    path = thumbs._cache_path("https://example.com/a")
    path.write_bytes(b"fake png")
    assert thumbs.get_cached_thumbnail("https://example.com/a") is None
    assert not path.exists()
    path.write_bytes(picture("JPEG"))
    assert thumbs.get_cached_thumbnail("https://example.com/a") == path
    assert path.read_bytes().startswith(b"\x89PNG")


def test_partial_cache_publish_preserves_previous_file(tmp_path, monkeypatch):
    path = tmp_path / "cache.png"
    path.write_bytes(b"previous")
    monkeypatch.setattr(thumbs.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("fixture")))
    with pytest.raises(OSError):
        thumbs._publish_cache(path, picture())
    assert path.read_bytes() == b"previous"
    assert list(tmp_path.iterdir()) == [path]


def test_http_error_body_is_bounded_and_response_closes():
    response = Response(b"x" * 1_000_000, status=403)
    with patch.object(images.requests, "get", return_value=response), pytest.raises(ValueError, match="HTTP 403"):
        images.fetch_image("https://example.com/p", max_bytes=1000, max_pixels=1000, timeout=1)
    assert response.read_bytes == 200
    assert response.closed
