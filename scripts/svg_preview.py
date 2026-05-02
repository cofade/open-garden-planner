"""Quick SVG-to-PNG preview for visual validation of SVG exports.

Uses Microsoft Edge headless (browser-accurate) when available, falls back to
Qt's QSvgRenderer. Edge output matches what users see in any browser.

Usage:
    venv/Scripts/python.exe scripts/svg_preview.py path/to/file.svg [scale]

Saves <file>_preview.png next to the source and prints the path for the Read tool.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


def _render_with_browser(svg_path: Path, out_path: Path, width: int = 1400) -> bool:
    """Render SVG using Edge/Chrome headless. Returns True on success."""
    browser = EDGE if EDGE.exists() else (CHROME if CHROME.exists() else None)
    if not browser:
        return False

    # Headless Chrome/Edge renders to a screenshot PNG
    url = svg_path.as_uri()
    try:
        result = subprocess.run(
            [
                str(browser),
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                f"--window-size={width},1080",
                f"--screenshot={out_path}",
                url,
            ],
            timeout=20,
            capture_output=True,
        )
        return out_path.exists() and out_path.stat().st_size > 1000
    except Exception:
        return False


def _render_with_qt(svg_path: Path, out_path: Path, scale: float = 0.5) -> bool:
    """Render SVG using Qt's QSvgRenderer. Falls back when browser unavailable."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    src = Path(__file__).parent.parent / "src"
    sys.path.insert(0, str(src))

    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtSvg import QSvgRenderer
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    renderer = QSvgRenderer(str(svg_path))
    default_size = renderer.defaultSize()
    w = max(1, int(default_size.width() * scale))
    h = max(1, int(default_size.height() * scale))
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(0xFFFFFFFF)
    p = QPainter(img)
    renderer.render(p)
    p.end()
    img.save(str(out_path))
    return out_path.exists()


def main() -> None:
    svg_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    scale = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5

    if not svg_path or not svg_path.exists():
        print("Usage: svg_preview.py <file.svg> [scale=0.5]")
        sys.exit(1)

    out = svg_path.with_name(svg_path.stem + "_preview.png")

    browser = EDGE if EDGE.exists() else (CHROME if CHROME.exists() else None)
    if browser:
        print(f"[SVG PREVIEW] using {browser.name} headless ...")
        ok = _render_with_browser(svg_path, out, width=int(1400 * scale / 0.5))
        if ok:
            print(f"[SVG PREVIEW] browser render -> {out}")
            return
        print("[SVG PREVIEW] browser render failed, falling back to QSvgRenderer")

    _render_with_qt(svg_path, out, scale)
    print(f"[SVG PREVIEW] QSvgRenderer -> {out}")


if __name__ == "__main__":
    main()
