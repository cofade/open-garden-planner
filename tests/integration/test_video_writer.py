"""A tour's frames into a file (Phase 17 L6.2, #390): the real Qt Multimedia, read back.

The default tier: encoding needs no GPU and no window. On a system without an MP4 encoder
the MP4 tests skip (``best_codec`` says so; ``--selftest`` and the frozen gate do not
skip: the bundle must have one).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QColor, QImage, QPainter

from open_garden_planner.core.video_yuv import yuv_to_rgb
from open_garden_planner.ui.view3d.video_writer import (
    CODECS,
    Mp4Writer,
    NullWriter,
    PngSequenceWriter,
    VideoError,
    best_codec,
    frame_name,
)

SIZE = (1280, 720)   # HD: below it a player guesses another colour matrix (core/video_yuv.py)
FPS = 30
PLAIN, BLOCK = (200, 60, 30), (30, 180, 90)


def frame(index: int, count: int, size: tuple[int, int] = SIZE) -> QImage:
    width, height = size
    image = QImage(width, height, QImage.Format.Format_RGBX8888)
    image.fill(QColor(*PLAIN))
    left = int(index / max(count, 1) * (width - width // 4))
    painter = QPainter(image)
    painter.fillRect(left, height // 4, width // 4, height // 2, QColor(*BLOCK))
    painter.end()
    return image


def needs_an_encoder() -> None:
    if best_codec() is None:
        pytest.skip("this system has no MP4 encoder")


def write_all(qtbot: Any, writer: Any, count: int, size: tuple[int, int] = SIZE) -> tuple[bool, str]:
    outcome: list[tuple[bool, str]] = []
    writer.finished.connect(lambda ok, message: outcome.append((ok, message)))
    writer.start()
    for index in range(count):
        image = frame(index, count, size)
        qtbot.waitUntil(lambda image=image: writer.write(image), timeout=20000)
    writer.finish()
    qtbot.waitUntil(lambda: bool(outcome), timeout=60000)
    return outcome[0]


def sample(video: Any, x: int, y: int) -> tuple[float, float, float]:
    """A decoded frame's raw Y, Cb and Cr at a pixel — the stream's own numbers. Never through
    ``QVideoFrame.toImage``: for an untagged stream that guesses a matrix, and guesses
    differently by platform (BT.709 through its shader, BT.601 under ``offscreen``, which
    read this writer's correct (200, 60, 30) as (188, 45, 35))."""
    from PyQt6 import QtMultimedia as media

    assert video.map(media.QVideoFrame.MapMode.ReadOnly)
    try:
        def at(plane: int, column: int, row: int, step: int = 1) -> int:
            bits = video.bits(plane)
            bits.setsize(video.mappedBytes(plane))
            return bits[row * video.bytesPerLine(plane) + column * step][0]

        luma = at(0, x, y)
        name = video.pixelFormat().name
        if name == "Format_NV12":
            return (luma, at(1, x // 2, y // 2, 2), bits_next(video, 1, x // 2, y // 2))
        assert name == "Format_YUV420P", name
        return (luma, at(1, x // 2, y // 2), at(2, x // 2, y // 2))
    finally:
        video.unmap()


def bits_next(video: Any, plane: int, column: int, row: int) -> int:
    """NV12's Cr: the byte after its Cb."""
    bits = video.bits(plane)
    bits.setsize(video.mappedBytes(plane))
    return bits[row * video.bytesPerLine(plane) + column * 2 + 1][0]


def colour_at(video: Any, x: int, y: int) -> tuple[float, float, float]:
    """What the pixel is under BT.709, the matrix every player assumes for HD."""
    return yuv_to_rgb(*sample(video, x, y))


def assert_close(got: tuple[float, float, float], wanted: tuple[int, int, int]) -> None:
    """Within what 4:2:0 and a lossy codec leave. The bug this writer's YUV exists for was
    13 levels off (212, 73, 27 for 200, 60, 30)."""
    assert max(abs(a - b) for a, b in zip(got, wanted, strict=True)) <= 5, (got, wanted)


#: Where ``read_back`` looks in each frame: the corner stays plain, the block starts over here.
CORNER, MIDDLE = (SIZE[0] - 20, 20), (SIZE[0] // 8, SIZE[1] // 2)


def read_back(qtbot: Any, path: Path) -> dict[str, Any]:
    """Qt's decoder on the file; each frame's colours read as it arrives (a frame can only be
    mapped while the player holds it)."""
    from PyQt6 import QtMultimedia as media

    player = media.QMediaPlayer()
    sink = media.QVideoSink()
    images: list[dict[str, Any]] = []
    player.setVideoSink(sink)

    def arrived(video: Any) -> None:
        if video.isValid():
            images.append({"size": (video.width(), video.height()),
                           "corner": colour_at(video, *CORNER), "middle": colour_at(video, *MIDDLE)})

    sink.videoFrameChanged.connect(arrived)
    player.setSource(QUrl.fromLocalFile(str(path)))
    player.play()
    qtbot.waitUntil(lambda: player.mediaStatus() == media.QMediaPlayer.MediaStatus.EndOfMedia
                    or player.error() != media.QMediaPlayer.Error.NoError, timeout=60000)
    assert player.error() == media.QMediaPlayer.Error.NoError, player.errorString()
    answer = {"duration_ms": player.duration(), "frames": images}
    player.stop()
    return answer


def test_the_codecs_are_the_documented_ones_in_order() -> None:
    assert CODECS == ("H264", "MPEG4")


def test_an_mp4_has_every_frame_the_right_length_and_the_right_colours(qtbot: Any, tmp_path: Path) -> None:
    """The whole path: frames in, a file on disk, Qt's decoder reading exact frames back,
    and the colours within what 4:2:0 and a lossy codec leave — the bug this writer's YUV
    exists for read (212, 73, 27) for (200, 60, 30), 13 levels off."""
    needs_an_encoder()
    path = tmp_path / "tour.mp4"
    ok, message = write_all(qtbot, Mp4Writer(path, SIZE, FPS), 45)
    assert ok, message
    assert path.is_file() and path.stat().st_size > 0
    assert not (tmp_path / "tour.part.mp4").exists()
    read = read_back(qtbot, path)
    assert read["duration_ms"] == 1500
    assert len(read["frames"]) == 45
    first = read["frames"][0]
    assert first["size"] == SIZE
    assert_close(first["corner"], PLAIN)
    assert_close(first["middle"], BLOCK)


def test_the_block_moves_so_the_frames_are_really_different(qtbot: Any, tmp_path: Path) -> None:
    needs_an_encoder()
    path = tmp_path / "moving.mp4"
    assert write_all(qtbot, Mp4Writer(path, SIZE, FPS), 20)[0]
    frames = read_back(qtbot, path)["frames"]
    assert_close(frames[0]["middle"], BLOCK)
    assert_close(frames[-1]["middle"], PLAIN)


@pytest.mark.parametrize("codec", CODECS)
def test_each_offered_codec_writes_a_file_with_true_colours(qtbot: Any, tmp_path: Path, codec: str,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    """H.264 from the operating system, MPEG-4 from FFmpeg: the fallback must not be a path
    nobody ever walked."""
    needs_an_encoder()
    from PyQt6 import QtMultimedia as media

    wanted = media.QMediaFormat(media.QMediaFormat.FileFormat.MPEG4)
    available = {found.name for found in wanted.supportedVideoCodecs(media.QMediaFormat.ConversionMode.Encode)}
    if codec not in available:
        pytest.skip(f"no {codec} encoder here")
    monkeypatch.setattr("open_garden_planner.ui.view3d.video_writer.best_codec", lambda: codec)
    path = tmp_path / f"{codec}.mp4"
    writer = Mp4Writer(path, SIZE, FPS)
    assert write_all(qtbot, writer, 12)[0]
    assert writer.codec == codec
    assert_close(read_back(qtbot, path)["frames"][0]["corner"], PLAIN)


def test_an_aborted_video_leaves_nothing_and_never_touches_the_good_one(qtbot: Any, tmp_path: Path) -> None:
    needs_an_encoder()
    path = tmp_path / "tour.mp4"
    path.write_bytes(b"the user's earlier video")
    writer = Mp4Writer(path, SIZE, FPS)
    outcome: list[tuple[bool, str]] = []
    writer.finished.connect(lambda ok, message: outcome.append((ok, message)))
    writer.start()
    for index in range(5):
        image = frame(index, 5)
        qtbot.waitUntil(lambda image=image: writer.write(image), timeout=20000)
    writer.abort()
    qtbot.waitUntil(lambda: bool(outcome), timeout=60000)
    assert outcome[0][0] is False
    assert not writer.part_path.exists()
    assert path.read_bytes() == b"the user's earlier video"


def test_a_finished_video_replaces_the_one_the_user_chose_to_overwrite(qtbot: Any, tmp_path: Path) -> None:
    needs_an_encoder()
    path = tmp_path / "tour.mp4"
    path.write_bytes(b"old")
    assert write_all(qtbot, Mp4Writer(path, SIZE, FPS), 6)[0]
    assert path.read_bytes() != b"old"


def test_a_frame_of_the_wrong_size_is_refused_not_stretched(qtbot: Any, tmp_path: Path) -> None:
    needs_an_encoder()
    writer = Mp4Writer(tmp_path / "x.mp4", SIZE, FPS)
    writer.start()
    with pytest.raises(VideoError):
        writer.write(frame(0, 1, (640, 360)))
    writer.abort()
    qtbot.waitUntil(lambda: not writer.part_path.exists() or writer._recorder is None, timeout=30000)


@pytest.mark.parametrize("size", [(1281, 720), (1280, 721)])
def test_an_odd_side_is_refused_before_anything_is_written(tmp_path: Path, size: tuple[int, int]) -> None:
    with pytest.raises(ValueError, match="even"):
        Mp4Writer(tmp_path / "x.mp4", size, FPS)


def test_no_encoder_is_a_sentence_not_a_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("open_garden_planner.ui.view3d.video_writer.best_codec", lambda: None)
    with pytest.raises(VideoError, match="PNG"):
        Mp4Writer(tmp_path / "x.mp4", SIZE, FPS).start()


def test_a_png_sequence_has_every_frame_in_order(qtbot: Any, tmp_path: Path) -> None:
    folder = tmp_path / "frames" / "tour"
    ok, message = write_all(qtbot, PngSequenceWriter(folder), 6, (320, 180))
    assert ok, message
    names = sorted(path.name for path in folder.iterdir())
    assert names == [frame_name(index) for index in range(6)]
    assert names[0] == "frame_000001.png"
    first, last = QImage(str(folder / names[0])), QImage(str(folder / names[-1]))
    assert (first.width(), first.height()) == (320, 180)
    assert first != last
    seen = first.pixelColor(300, 10)
    assert (seen.red(), seen.green(), seen.blue()) == PLAIN, "a PNG is exact"


def test_a_folder_with_the_frames_of_another_tour_is_refused(tmp_path: Path) -> None:
    (tmp_path / frame_name(0)).write_bytes(b"frame")
    with pytest.raises(VideoError):
        PngSequenceWriter(tmp_path).start()


def test_a_sequence_that_cannot_write_says_so(qtbot: Any, tmp_path: Path) -> None:
    folder = tmp_path / "frames"
    writer = PngSequenceWriter(folder)
    outcome: list[tuple[bool, str]] = []
    writer.finished.connect(lambda ok, message: outcome.append((ok, message)))
    writer.start()
    # a folder where the frame's file should go: QImage.save answers False
    (folder / frame_name(0)).mkdir()
    assert writer.write(frame(0, 1, (64, 36)))
    writer.finish()
    qtbot.waitUntil(lambda: bool(outcome), timeout=20000)
    assert outcome[0][0] is False and outcome[0][1]


def test_the_null_writer_takes_everything_and_reports_success(qtbot: Any) -> None:
    writer = NullWriter()
    outcome: list[bool] = []
    writer.finished.connect(lambda ok, _message: outcome.append(ok))
    writer.start()
    assert writer.write(frame(0, 1, (64, 36)))
    writer.finish()
    assert outcome == [True]
