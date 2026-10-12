"""The crash marker of the 3D workspace — every transition (Phase 17 L1.3, ADR-065).

``ui/view3d/init_guard.py`` decides, before the first 3D window of a session is
built, whether to render on the graphics card or on the software rasteriser, and
keeps the two small files that carry that decision across a process that died.
Standard library only: every test here runs it against a temp directory, with the
"is that process still running?" question and the wall clock handed in.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest

from open_garden_planner.ui.view3d import init_guard as guard_module
from open_garden_planner.ui.view3d.init_guard import (
    COMPAT_NAME,
    MAX_INIT_S,
    Init3DGuard,
    ModeReason,
    RenderMode,
    default_directory,
    marker_name,
)

ME = 4242       # "this" process in most tests
OTHER = 7777    # another process: the one that died, or a second running instance


def _guard(directory: Path | None, *, pid: int = ME, running: tuple[int, ...] = (),
           now: float = 1_000_000.0) -> Init3DGuard:
    return Init3DGuard(directory, pid=pid, is_running=lambda other: other in running,
                       now=lambda: now)


def _files(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir())


def _die_in_init(directory: Path, *, pid: int = OTHER, now: float = 1_000_000.0) -> None:
    """A process that began its first 3D start and never came back."""
    _guard(directory, pid=pid, now=now).begin()


class TestAHealthyMachine:
    def test_the_first_start_is_on_the_graphics_card_and_leaves_a_marker(self, tmp_path: Path) -> None:
        guard = _guard(tmp_path)
        assert guard.mode is None and guard.pending is False
        assert guard.begin() is RenderMode.HARDWARE
        assert guard.mode is RenderMode.HARDWARE
        assert guard.reason is ModeReason.NORMAL
        assert guard.pending is True
        assert _files(tmp_path) == [marker_name(ME)]
        written = json.loads((tmp_path / marker_name(ME)).read_text(encoding="utf-8"))
        assert written["pid"] == ME and written["started"] == 1_000_000.0
        assert written["mode"] == "hardware"

    def test_a_confirmed_first_frame_clears_the_marker(self, tmp_path: Path) -> None:
        guard = _guard(tmp_path)
        guard.begin()
        guard.confirm_first_frame()
        assert guard.pending is False
        assert _files(tmp_path) == []
        guard.confirm_first_frame()  # again: nothing to do, nothing raised
        # … and the next session is as healthy as this one
        assert _guard(tmp_path, pid=ME + 1).begin() is RenderMode.HARDWARE

    def test_a_clean_close_during_the_start_is_not_a_crash(self, tmp_path: Path) -> None:
        guard = _guard(tmp_path)
        guard.begin()
        guard.abandon()
        assert _files(tmp_path) == [] and guard.pending is False
        assert _guard(tmp_path, pid=ME + 1).begin() is RenderMode.HARDWARE

    def test_a_graphics_device_that_could_not_be_created_is_not_a_crash(self, tmp_path: Path) -> None:
        """Qt reported it (``sceneGraphError``) and the process lives: the marker goes,
        and nothing switches the next session to software behind the user's back."""
        guard = _guard(tmp_path)
        guard.begin()
        guard.graphics_failed()
        assert _files(tmp_path) == [] and guard.pending is False
        nxt = _guard(tmp_path, pid=ME + 1)
        assert nxt.begin() is RenderMode.HARDWARE and nxt.reason is ModeReason.NORMAL

    def test_an_error_raised_in_process_is_not_a_crash_and_can_be_retried(self, tmp_path: Path) -> None:
        """An ImportError, a QML file that does not load: Python caught it."""
        guard = _guard(tmp_path)
        guard.begin()
        guard.init_failed()
        assert _files(tmp_path) == [] and guard.pending is False
        assert guard.begin() is RenderMode.HARDWARE  # the user tries again, same session
        assert guard.pending is True and _files(tmp_path) == [marker_name(ME)]

    def test_a_session_that_never_opens_3d_touches_nothing(self, tmp_path: Path) -> None:
        before = sorted(tmp_path.iterdir())
        guard = _guard(tmp_path)
        guard.abandon()            # what closing the app calls
        guard.confirm_first_frame()
        guard.graphics_failed()
        guard.init_failed()
        assert sorted(tmp_path.iterdir()) == before == []
        assert guard.mode is None


class TestADeathDuringTheFirstStart:
    def test_the_next_start_is_in_software_mode_and_says_why(self, tmp_path: Path) -> None:
        _die_in_init(tmp_path)
        assert _files(tmp_path) == [marker_name(OTHER)]
        guard = _guard(tmp_path)
        assert guard.begin() is RenderMode.SOFTWARE
        assert guard.reason is ModeReason.PREVIOUS_START_DIED
        assert guard.pending is True
        # the dead process's marker is spent; the decision is on file; our own start is marked
        assert _files(tmp_path) == sorted([COMPAT_NAME, marker_name(ME)])

    def test_the_marker_survives_a_session_that_never_opens_3d(self, tmp_path: Path) -> None:
        """"Marker present, 3D never opened": that session reads and writes nothing, so
        the session after it still learns of the death."""
        _die_in_init(tmp_path)
        idle = _guard(tmp_path, pid=ME + 1)
        idle.abandon()
        assert _files(tmp_path) == [marker_name(OTHER)]
        assert _guard(tmp_path, pid=ME + 2).begin() is RenderMode.SOFTWARE

    def test_software_mode_is_kept_until_the_user_asks_for_hardware(self, tmp_path: Path) -> None:
        _die_in_init(tmp_path)
        first = _guard(tmp_path)
        first.begin()
        first.confirm_first_frame()            # software rendering works
        assert _files(tmp_path) == [COMPAT_NAME]
        second = _guard(tmp_path, pid=ME + 1)
        assert second.begin() is RenderMode.SOFTWARE
        assert second.reason is ModeReason.KEPT_FROM_AN_EARLIER_SESSION
        second.confirm_first_frame()
        assert _files(tmp_path) == [COMPAT_NAME]

    def test_try_hardware_again_takes_effect_at_the_next_start(self, tmp_path: Path) -> None:
        _die_in_init(tmp_path)
        guard = _guard(tmp_path)
        guard.begin()
        guard.confirm_first_frame()
        assert guard.software_requested() is True
        guard.try_hardware_next_time()
        assert guard.software_requested() is False
        assert guard.mode is RenderMode.SOFTWARE, "this session's window is already built"
        assert _files(tmp_path) == []
        nxt = _guard(tmp_path, pid=ME + 1)
        assert nxt.begin() is RenderMode.HARDWARE and nxt.reason is ModeReason.NORMAL

    def test_a_machine_whose_hardware_start_dies_again_is_back_in_software(self, tmp_path: Path) -> None:
        _die_in_init(tmp_path)
        guard = _guard(tmp_path)
        guard.begin()
        guard.confirm_first_frame()
        guard.try_hardware_next_time()
        _die_in_init(tmp_path, pid=OTHER + 1)   # the retry on hardware dies too
        again = _guard(tmp_path, pid=ME + 1)
        assert again.begin() is RenderMode.SOFTWARE
        assert again.reason is ModeReason.PREVIOUS_START_DIED

    def test_a_death_in_software_mode_keeps_software_mode(self, tmp_path: Path) -> None:
        _die_in_init(tmp_path)
        _die_in_init(tmp_path, pid=OTHER + 1)   # began in software, died as well
        guard = _guard(tmp_path)
        assert guard.begin() is RenderMode.SOFTWARE
        assert _files(tmp_path) == sorted([COMPAT_NAME, marker_name(ME)])

    @pytest.mark.parametrize("content", [b"", b"not json", b"\xff\xfe\x00", b"[1, 2]", b'{"pid": "x"}'])
    def test_a_marker_nobody_can_read_is_still_a_marker(self, tmp_path: Path, content: bytes) -> None:
        (tmp_path / marker_name(OTHER)).write_bytes(content)
        assert _guard(tmp_path).begin() is RenderMode.SOFTWARE


class TestASecondRunningInstance:
    def test_another_instances_start_in_progress_is_not_a_crash(self, tmp_path: Path) -> None:
        other = _guard(tmp_path, pid=OTHER, running=(OTHER,))
        other.begin()
        mine = _guard(tmp_path, running=(OTHER,))
        assert mine.begin() is RenderMode.HARDWARE
        assert mine.reason is ModeReason.NORMAL
        assert _files(tmp_path) == sorted([marker_name(ME), marker_name(OTHER)])
        mine.confirm_first_frame()
        assert _files(tmp_path) == [marker_name(OTHER)], "each instance clears its own marker only"
        other.confirm_first_frame()
        assert _files(tmp_path) == []

    def test_a_start_cannot_be_in_progress_for_ever(self, tmp_path: Path) -> None:
        """A process id is reused: a marker whose process "runs" but which is older than
        any start can take belongs to a process that died."""
        _die_in_init(tmp_path, now=1_000_000.0)
        young = _guard(tmp_path, pid=ME, running=(OTHER,), now=1_000_000.0 + MAX_INIT_S - 1.0)
        assert young.begin() is RenderMode.HARDWARE
        young.abandon()
        old = _guard(tmp_path, pid=ME + 1, running=(OTHER,), now=1_000_000.0 + MAX_INIT_S + 1.0)
        assert old.begin() is RenderMode.SOFTWARE

    def test_our_own_marker_from_a_retry_is_never_taken_for_a_crash(self, tmp_path: Path) -> None:
        guard = _guard(tmp_path, running=(ME,))
        guard.begin()
        assert guard.begin() is RenderMode.HARDWARE  # called twice without an outcome in between
        assert guard.reason is ModeReason.NORMAL
        assert _files(tmp_path) == [marker_name(ME)]


class TestTheUsersSwitch:
    def test_software_can_be_asked_for_without_any_crash(self, tmp_path: Path) -> None:
        guard = _guard(tmp_path)
        guard.use_software_next_time()
        assert _files(tmp_path) == [COMPAT_NAME]
        nxt = _guard(tmp_path, pid=ME + 1)
        assert nxt.begin() is RenderMode.SOFTWARE
        assert nxt.reason is ModeReason.KEPT_FROM_AN_EARLIER_SESSION

    def test_both_switches_are_idempotent(self, tmp_path: Path) -> None:
        guard = _guard(tmp_path)
        guard.try_hardware_next_time()
        guard.try_hardware_next_time()
        assert _files(tmp_path) == []
        guard.use_software_next_time()
        guard.use_software_next_time()
        assert _files(tmp_path) == [COMPAT_NAME]


class TestAFolderThatCannotBeUsed:
    def test_without_a_folder_3d_starts_on_hardware_and_keeps_no_books(self) -> None:
        guard = _guard(None)
        assert guard.begin() is RenderMode.HARDWARE
        assert guard.pending is False
        guard.confirm_first_frame()
        guard.use_software_next_time()
        assert guard.software_requested() is False

    def test_a_folder_that_is_a_file_never_raises_into_the_app(self, tmp_path: Path) -> None:
        not_a_folder = tmp_path / "app.log"
        not_a_folder.write_text("x", encoding="utf-8")
        guard = _guard(not_a_folder)
        assert guard.begin() is RenderMode.HARDWARE
        assert guard.pending is False
        guard.confirm_first_frame()
        guard.graphics_failed()
        guard.init_failed()
        guard.abandon()
        guard.try_hardware_next_time()
        guard.use_software_next_time()
        assert not_a_folder.read_text(encoding="utf-8") == "x"

    def test_an_error_is_one_quoted_log_line(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                             caplog: pytest.LogCaptureFixture) -> None:
        """§8.11: no traceback, and the message quoted — whatever a file system says
        stays inside one log record."""

        def refuse(*_arguments: object, **_options: object) -> None:
            raise OSError("no space left\n2026-10-12 ERROR root: FORGED LINE")

        monkeypatch.setattr(Path, "mkdir", refuse)
        guard = _guard(tmp_path / "log")
        with caplog.at_level("DEBUG", logger=guard_module.__name__):
            assert guard.begin() is RenderMode.HARDWARE
            guard.use_software_next_time()
        records = [record for record in caplog.records if record.name == guard_module.__name__]
        for record in records:
            assert record.exc_info is None
            assert len(record.getMessage().splitlines()) == 1, record.getMessage()
        quoted = "OSError: 'no space left\\n2026-10-12 ERROR root: FORGED LINE'"
        assert sum(quoted in record.getMessage() for record in records) == 2

    def test_a_folder_that_does_not_exist_yet_is_made(self, tmp_path: Path) -> None:
        target = tmp_path / "cofade" / "Open Garden Planner"
        guard = _guard(target)
        assert guard.begin() is RenderMode.HARDWARE
        assert guard.pending is True and _files(target) == [marker_name(ME)]


#: (what is on disk before, what happens) → (mode, reason, what is on disk after begin()).
#: The whole decision of ``begin()`` as one table — "dead" / "alive" is the OTHER marker.
_BEGIN_TABLE = [
    ("nothing",            RenderMode.HARDWARE, ModeReason.NORMAL,                       {"own"}),
    ("compat",             RenderMode.SOFTWARE, ModeReason.KEPT_FROM_AN_EARLIER_SESSION, {"own", "compat"}),
    ("dead",               RenderMode.SOFTWARE, ModeReason.PREVIOUS_START_DIED,          {"own", "compat"}),
    ("dead+compat",        RenderMode.SOFTWARE, ModeReason.PREVIOUS_START_DIED,          {"own", "compat"}),
    ("alive",              RenderMode.HARDWARE, ModeReason.NORMAL,                       {"own", "other"}),
    ("alive+compat",       RenderMode.SOFTWARE, ModeReason.KEPT_FROM_AN_EARLIER_SESSION, {"own", "other", "compat"}),
]


@pytest.mark.parametrize(("before", "mode", "reason", "after"), _BEGIN_TABLE,
                         ids=[row[0] for row in _BEGIN_TABLE])
def test_begin_decides_from_what_is_on_disk(tmp_path: Path, before: str, mode: RenderMode,
                                            reason: ModeReason, after: set[str]) -> None:
    running: tuple[int, ...] = ()
    if "dead" in before or "alive" in before:
        _die_in_init(tmp_path)
    if "alive" in before:
        running = (OTHER,)
    if "compat" in before:
        (tmp_path / COMPAT_NAME).write_text("", encoding="utf-8")
    guard = _guard(tmp_path, running=running)
    assert (guard.begin(), guard.reason) == (mode, reason)
    names = {"own": marker_name(ME), "other": marker_name(OTHER), "compat": COMPAT_NAME}
    assert _files(tmp_path) == sorted(names[key] for key in after)


#: Every way a start can end, from PENDING: the marker goes, the compat flag is untouched.
@pytest.mark.parametrize("outcome", ["confirm_first_frame", "graphics_failed", "init_failed", "abandon"])
@pytest.mark.parametrize("compat", [False, True])
def test_every_outcome_of_a_start_removes_the_marker_and_nothing_else(
        tmp_path: Path, outcome: str, compat: bool) -> None:
    if compat:
        (tmp_path / COMPAT_NAME).write_text("", encoding="utf-8")
    guard = _guard(tmp_path)
    guard.begin()
    getattr(guard, outcome)()
    assert guard.pending is False
    assert _files(tmp_path) == ([COMPAT_NAME] if compat else [])


class TestWhereTheFilesLive:
    def test_the_marker_is_named_after_its_process(self) -> None:
        assert marker_name(123) == "view3d-init-123.marker"
        assert guard_module.marker_pid("view3d-init-123.marker") == 123
        assert guard_module.marker_pid("view3d-init-.marker") is None
        assert guard_module.marker_pid("app.log") is None

    def test_under_pytest_the_default_folder_is_inside_the_test_root(self, qtbot) -> None:  # noqa: ARG002
        """The marker lives beside ``app.log``. A test that builds the real workspace
        must never write it into the developer's own log folder: conftest redirects
        that location, and this pins that the guard follows it."""
        from tests.conftest import TEST_DATA_ROOT

        folder = default_directory()
        assert folder is not None
        assert TEST_DATA_ROOT in folder.resolve().parents

    def test_the_real_process_questions_have_real_answers(self) -> None:
        assert guard_module.process_is_running(os.getpid()) is True
        assert guard_module.process_is_running(0) is False
        assert guard_module.process_is_running(-5) is False
        guard = Init3DGuard(None)
        assert guard.pid == os.getpid()

    def test_the_guard_is_standard_library_only(self) -> None:
        """It runs before anything of Qt Quick exists and must not be what breaks."""
        source = Path(guard_module.__file__).read_text(encoding="utf-8")
        top_level: set[str] = set()
        for node in ast.parse(source).body:
            if isinstance(node, ast.Import):
                top_level.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                top_level.add(node.module.split(".")[0])
        assert top_level <= {"__future__", "collections", "contextlib", "enum", "json", "logging",
                             "os", "pathlib", "sys", "time", "typing"}, top_level
