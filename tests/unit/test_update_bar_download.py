"""Worker/UI tests: only a verified installer can reach process launch."""

import hashlib
from unittest.mock import patch

import pytest

from open_garden_planner.services.update_checker import ReleaseInfo
from open_garden_planner.services.verified_update import (
    DownloadCancelled,
    VerificationError,
    VerifiedInstaller,
)
from open_garden_planner.ui.widgets.update_bar import UpdateBar, _DownloadWorker


def release():
    root = "https://github.com/cofade/open-garden-planner/releases/download/v1.30.2/"
    name = "OpenGardenPlanner-v1.30.2-Setup.exe"
    return ReleaseInfo("v1.30.2", "", root + name, root, name, 4, root + "SHA256SUMS.txt")


def test_worker_emits_only_verified_result(qtbot, tmp_path):
    result = VerifiedInstaller(tmp_path / release().installer_name, 4, "0" * 64)
    worker = _DownloadWorker(release(), result.path)
    received = []
    worker.verified_ready.connect(received.append)
    with patch("open_garden_planner.ui.widgets.update_bar.download_verified_installer", return_value=result):
        worker.run()
    assert received == [result]


@pytest.mark.parametrize("exception", [VerificationError("digest"), TimeoutError("signed-secret-url")])
def test_worker_failure_never_emits_success_or_sensitive_error(qtbot, tmp_path, exception):
    worker = _DownloadWorker(release(), tmp_path / release().installer_name)
    successes, errors = [], []
    worker.verified_ready.connect(successes.append)
    worker.failed.connect(errors.append)
    with patch("open_garden_planner.ui.widgets.update_bar.download_verified_installer", side_effect=exception):
        worker.run()
    assert successes == []
    assert errors == ["digest" if isinstance(exception, VerificationError) else "network"]


def test_cancellation_has_no_failure_dialog_or_success(qtbot, tmp_path):
    worker = _DownloadWorker(release(), tmp_path / release().installer_name)
    successes, errors = [], []
    worker.verified_ready.connect(successes.append)
    worker.failed.connect(errors.append)
    with patch("open_garden_planner.ui.widgets.update_bar.download_verified_installer", side_effect=DownloadCancelled):
        worker.run()
    assert errors == successes == []


def test_missing_checksum_disables_installation_and_theme_keeps_descriptor(qtbot):
    bar = UpdateBar()
    qtbot.addWidget(bar)
    info = ReleaseInfo("v1.30.2", "", None, "https://github.com/cofade/open-garden-planner/releases/tag/v1.30.2")
    bar.show_update(info)
    bar.apply_theme_colors({})
    assert not bar._download_btn.isEnabled()
    assert bar._download_btn.toolTip()
    assert bar._release is info


@pytest.mark.parametrize("tamper", [False, True])
def test_launch_rechecks_the_persisted_file(qtbot, tmp_path, tamper):
    bar = UpdateBar()
    qtbot.addWidget(bar)
    path = tmp_path / "installer.exe"
    path.write_bytes(b"good")
    result = VerifiedInstaller(path, 4, hashlib.sha256(b"good").hexdigest())
    if tamper:
        path.write_bytes(b"evil")
    with patch("open_garden_planner.ui.widgets.update_bar.subprocess.Popen") as launch, \
         patch("open_garden_planner.ui.widgets.update_bar.QApplication.quit") as quit_app, \
         patch("open_garden_planner.ui.widgets.update_bar.QMessageBox.critical") as error:
        bar._launch_installer(result, bar, "https://github.com/cofade/open-garden-planner")
    assert launch.call_count == quit_app.call_count == (0 if tamper else 1)
    assert error.call_count == (1 if tamper else 0)
