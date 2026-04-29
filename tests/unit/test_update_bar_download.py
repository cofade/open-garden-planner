"""Unit tests for _DownloadWorker in update_bar.

Tests the background download thread: successful chunked download, timeout/error
handling, and mid-download cancellation. No real network calls are made.
"""

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

from open_garden_planner.ui.widgets.update_bar import _DownloadWorker


def _make_mock_response(content: bytes, content_length: int | None = None) -> MagicMock:
    """Return a context-manager mock that behaves like urllib's HTTP response."""
    buf = io.BytesIO(content)
    resp = MagicMock()
    resp.getheader.return_value = str(content_length) if content_length is not None else None
    resp.read.side_effect = lambda n: buf.read(n)
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _run_worker(worker: _DownloadWorker) -> None:
    """Run the worker synchronously (call run() directly, bypassing the thread)."""
    worker.run()


class TestDownloadWorkerSuccess:
    """Happy-path: file downloads completely."""

    def test_finished_signal_emitted(self, qtbot, tmp_path: Path) -> None:  # noqa: ARG002
        dest = tmp_path / "setup.exe"
        content = b"fake installer content" * 10

        received: list[Path] = []
        worker = _DownloadWorker("http://example.com/setup.exe", dest)
        worker.finished.connect(received.append)

        resp = _make_mock_response(content, len(content))
        with patch("urllib.request.urlopen", return_value=resp):
            _run_worker(worker)

        assert received == [dest]
        assert dest.read_bytes() == content

    def test_progress_signals_emitted(self, qtbot, tmp_path: Path) -> None:  # noqa: ARG002
        dest = tmp_path / "setup.exe"
        chunk_size = _DownloadWorker._CHUNK_SIZE
        content = b"x" * (chunk_size + 1)  # forces 2 reads

        progress_calls: list[tuple[int, int]] = []
        worker = _DownloadWorker("http://example.com/setup.exe", dest)
        worker.progress.connect(lambda d, t: progress_calls.append((d, t)))

        resp = _make_mock_response(content, len(content))
        with patch("urllib.request.urlopen", return_value=resp):
            _run_worker(worker)

        assert len(progress_calls) == 2
        assert progress_calls[-1][0] == len(content)
        assert progress_calls[-1][1] == len(content)

    def test_progress_total_zero_when_no_content_length(self, qtbot, tmp_path: Path) -> None:  # noqa: ARG002
        dest = tmp_path / "setup.exe"
        content = b"data"

        progress_calls: list[tuple[int, int]] = []
        worker = _DownloadWorker("http://example.com/setup.exe", dest)
        worker.progress.connect(lambda d, t: progress_calls.append((d, t)))

        resp = _make_mock_response(content, content_length=None)
        with patch("urllib.request.urlopen", return_value=resp):
            _run_worker(worker)

        assert all(t == 0 for _, t in progress_calls)

    def test_failed_signal_not_emitted_on_success(self, qtbot, tmp_path: Path) -> None:  # noqa: ARG002
        dest = tmp_path / "setup.exe"
        errors: list[str] = []
        worker = _DownloadWorker("http://example.com/setup.exe", dest)
        worker.failed.connect(errors.append)

        resp = _make_mock_response(b"ok")
        with patch("urllib.request.urlopen", return_value=resp):
            _run_worker(worker)

        assert errors == []


class TestDownloadWorkerFailure:
    """Error path: network errors propagate via the failed signal."""

    def test_failed_signal_on_timeout(self, qtbot, tmp_path: Path) -> None:  # noqa: ARG002
        dest = tmp_path / "setup.exe"
        errors: list[str] = []
        worker = _DownloadWorker("http://example.com/setup.exe", dest)
        worker.failed.connect(errors.append)

        with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            _run_worker(worker)

        assert len(errors) == 1
        assert "timed out" in errors[0]

    def test_failed_signal_on_url_error(self, qtbot, tmp_path: Path) -> None:  # noqa: ARG002
        import urllib.error

        dest = tmp_path / "setup.exe"
        errors: list[str] = []
        worker = _DownloadWorker("http://example.com/setup.exe", dest)
        worker.failed.connect(errors.append)

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("name not resolved")):
            _run_worker(worker)

        assert len(errors) == 1

    def test_finished_not_emitted_on_error(self, qtbot, tmp_path: Path) -> None:  # noqa: ARG002
        dest = tmp_path / "setup.exe"
        received: list[Path] = []
        worker = _DownloadWorker("http://example.com/setup.exe", dest)
        worker.finished.connect(received.append)

        with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
            _run_worker(worker)

        assert received == []


class TestDownloadWorkerCancellation:
    """Cancellation: in-progress download is aborted, no error shown to user."""

    def test_cancel_prevents_finished_signal(self, qtbot, tmp_path: Path) -> None:  # noqa: ARG002
        dest = tmp_path / "setup.exe"
        content = b"x" * (_DownloadWorker._CHUNK_SIZE * 3)

        received: list[Path] = []
        worker = _DownloadWorker("http://example.com/setup.exe", dest)
        worker.finished.connect(received.append)

        call_count = 0

        def cancelling_read(n: int) -> bytes:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                worker.cancel()
            buf = io.BytesIO(content)
            buf.seek((call_count - 1) * n)
            return buf.read(n)

        resp = _make_mock_response(content, len(content))
        resp.read.side_effect = cancelling_read

        with patch("urllib.request.urlopen", return_value=resp):
            _run_worker(worker)

        assert received == []

    def test_cancel_removes_partial_file(self, qtbot, tmp_path: Path) -> None:  # noqa: ARG002
        dest = tmp_path / "setup.exe"
        content = b"x" * (_DownloadWorker._CHUNK_SIZE * 3)

        worker = _DownloadWorker("http://example.com/setup.exe", dest)

        call_count = 0

        def cancelling_read(n: int) -> bytes:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                worker.cancel()
            buf = io.BytesIO(content)
            buf.seek((call_count - 1) * n)
            return buf.read(n)

        resp = _make_mock_response(content, len(content))
        resp.read.side_effect = cancelling_read

        with patch("urllib.request.urlopen", return_value=resp):
            _run_worker(worker)

        assert not dest.exists()

    def test_cancel_suppresses_timeout_error_dialog(self, qtbot, tmp_path: Path) -> None:  # noqa: ARG002
        """After cancel, a subsequent TimeoutError must NOT emit failed."""
        dest = tmp_path / "setup.exe"
        errors: list[str] = []
        worker = _DownloadWorker("http://example.com/setup.exe", dest)
        worker.failed.connect(errors.append)
        worker.cancel()  # cancel before download even starts

        with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            _run_worker(worker)

        assert errors == []
