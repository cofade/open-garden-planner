"""Real update UI/worker and local HTTP image ingestion workflows for A1."""

import gzip
import hashlib
import io
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import pytest
from PIL import Image
from PyQt6.QtWidgets import QMessageBox

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.services.image_download import fetch_image
from open_garden_planner.services.update_checker import ReleaseInfo


@pytest.mark.parametrize("corrupt", [False, True])
def test_application_update_worker_verifies_before_launch(qtbot, tmp_path, monkeypatch, corrupt):
    monkeypatch.setattr(GardenPlannerApp, "_show_welcome_dialog", lambda *_: None)
    app = GardenPlannerApp()
    qtbot.addWidget(app)
    name = "OpenGardenPlanner-v1.30.2-Setup.exe"
    root = "https://github.com/cofade/open-garden-planner/releases/download/v1.30.2/"
    release = ReleaseInfo("v1.30.2", "", root + name, root, name, 4, root + "SHA256SUMS.txt")
    manifest = f"{hashlib.sha256(b'good').hexdigest()}  {name}\n".encode()

    class Response(io.BytesIO):
        def __init__(self, content, url):
            super().__init__(content)
            self.url = url

        def geturl(self):
            return self.url

        def getheader(self, _key):
            return None

    class Opener:
        def open(self, request, timeout):
            assert timeout == 15
            content = manifest if request.full_url.endswith("SHA256SUMS.txt") else (b"evil" if corrupt else b"good")
            return Response(content, request.full_url)

    directory = tmp_path / "installer"
    directory.mkdir()
    with patch("urllib.request.build_opener", return_value=Opener()), \
         patch("open_garden_planner.ui.widgets.update_bar.tempfile.mkdtemp", return_value=str(directory)), \
         patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), \
         patch.object(QMessageBox, "critical") as error, \
         patch("open_garden_planner.ui.widgets.update_bar.subprocess.Popen") as launch, \
         patch("open_garden_planner.ui.widgets.update_bar.QApplication.quit") as quit_app:
        app._on_update_available(release)
        app._update_bar.apply_theme_colors({})
        app._update_bar._on_download()
        qtbot.waitUntil(lambda: error.called if corrupt else launch.called, timeout=5000)
        app._update_bar._worker.wait()
    assert launch.call_count == quit_app.call_count == (0 if corrupt else 1)
    if corrupt:
        assert not directory.exists() or list(directory.iterdir()) == []
    else:
        assert (directory / name).read_bytes() == b"good"
    app._project_manager.mark_clean()
    app.close()


def test_real_http_stream_enforces_limit_after_gzip_decoding():
    stream = io.BytesIO()
    Image.new("RGB", (40, 20), "green").save(stream, "PNG")
    png = stream.getvalue()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            content = gzip.compress(png if self.path == "/valid" else b"x" * 100000)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_port}"
    try:
        assert fetch_image(root + "/valid", max_bytes=1000, max_pixels=1000, timeout=1).size == (40, 20)
        with pytest.raises(ValueError, match="byte limit"):
            fetch_image(root + "/poison", max_bytes=1000, max_pixels=1000, timeout=1)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
