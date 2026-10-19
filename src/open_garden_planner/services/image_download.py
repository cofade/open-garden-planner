"""Bounded streamed image ingestion shared by thumbnails and Static Maps."""

from __future__ import annotations

import io
from collections.abc import Callable

import requests
from PIL import Image

CHUNK_BYTES = 65_536
THUMBNAIL_MAX_BYTES = 16 * 1024 * 1024
THUMBNAIL_MAX_PIXELS = 16_777_216
STATIC_MAP_MAX_BYTES = 8 * 1024 * 1024


def decode_image(content: bytes, *, max_pixels: int, max_edge: int | None = None) -> Image.Image:
    """Check the header, verify structure, then fully decode frame zero."""
    with Image.open(io.BytesIO(content)) as probe:
        width, height = probe.size
        if (probe.format not in {"PNG", "JPEG", "WEBP", "GIF"} or width <= 0 or height <= 0
                or width * height > max_pixels
                or (max_edge is not None and max(width, height) > max_edge)):
            raise ValueError("Image dimensions or format exceed the permitted limits")
        probe.verify()
    with Image.open(io.BytesIO(content)) as image:
        image.load()
        return image.convert("RGBA" if image.mode == "RGBA" or "transparency" in image.info else "RGB")


def fetch_image(
    url: str, *, max_bytes: int, max_pixels: int, timeout: float,
    max_edge: int | None = None, check_cancel: Callable[[], None] = lambda: None,
) -> Image.Image:
    """Count actual decoded transfer bytes, never buffering an unbounded body."""
    check_cancel()
    with requests.get(url, timeout=timeout, stream=True) as response:
        if response.status_code != 200:
            excerpt = bytearray()
            for chunk in response.iter_content(chunk_size=200):
                check_cancel()
                excerpt.extend(chunk[:200 - len(excerpt)])
                if len(excerpt) >= 200:
                    break
            raise ValueError(f"HTTP {response.status_code}: {bytes(excerpt).decode('utf-8', errors='replace')}")
        length = response.headers.get("Content-Length")
        if length is not None:
            try:
                declared = int(length)
            except ValueError as exc:
                raise ValueError("Invalid image response length") from exc
            if declared < 0 or declared > max_bytes:
                raise ValueError("Image response exceeds the permitted byte limit")
        media_type = response.headers.get("Content-Type", "").lower().split(";", 1)[0].strip()
        if not media_type.startswith("image/"):
            raise ValueError("The response is not an image")
        content = bytearray()
        for chunk in response.iter_content(chunk_size=CHUNK_BYTES):
            check_cancel()
            if len(content) + len(chunk) > max_bytes:
                raise ValueError("Image response exceeds the permitted byte limit")
            content.extend(chunk)
        check_cancel()
        return decode_image(bytes(content), max_pixels=max_pixels, max_edge=max_edge)


def thumbnail_png(image: Image.Image) -> bytes:
    """A real PNG with bounded dimensions; cached images are display thumbnails."""
    image.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
