"""Stream/identity/redirect/cancellation tests at the real verification seam."""

import hashlib
import io
import urllib.request
from dataclasses import replace
from http.client import HTTPMessage
from unittest.mock import patch

import pytest

from open_garden_planner.services.update_checker import ReleaseInfo, parse_release_info
from open_garden_planner.services.verified_update import (
    DownloadCancelled,
    SafeRedirectHandler,
    VerificationError,
    checksum_for,
    download_verified_installer,
    validate_asset_origin,
)

ROOT = "https://github.com/cofade/open-garden-planner/releases/download/v1.30.2/"
NAME = "OpenGardenPlanner-v1.30.2-Setup.exe"


class Response(io.BytesIO):
    def __init__(self, content, url, length=None):
        super().__init__(content)
        self.url, self.length = url, length

    def geturl(self):
        return self.url

    def getheader(self, key):
        return self.length if key == "Content-Length" else None

    def read(self, size=-1):
        assert 0 < size <= 65536
        return super().read(size)


def descriptor(size=4):
    return ReleaseInfo("v1.30.2", "", ROOT + NAME, ROOT, NAME, size, ROOT + "SHA256SUMS.txt")


def manifest(content=b"good"):
    return f"{hashlib.sha256(content).hexdigest()}  {NAME}\n".encode()


def run_download(tmp_path, content=b"good", checksum=None, size=4, cancelled=lambda: False, progress=lambda *_: None, length=None):
    responses = [Response(manifest() if checksum is None else checksum, ROOT + "SHA256SUMS.txt"),
                 Response(content, ROOT + NAME, length)]

    class Opener:
        def open(self, request, timeout):
            assert timeout == 15
            response = responses.pop(0)
            assert request.full_url == response.url
            return response

    with patch("urllib.request.build_opener", return_value=Opener()):
        return download_verified_installer(descriptor(size), tmp_path / NAME,
                                           cancelled=cancelled, progress=progress)


def test_verified_bytes_and_size(tmp_path):
    result = run_download(tmp_path)
    result.check()
    assert result.path.read_bytes() == b"good"
    assert list(tmp_path.iterdir()) == [result.path]


@pytest.mark.parametrize("changes,category", [
    ({"content": b"evil"}, "digest"), ({"content": b"goo"}, "length"),
    ({"content": b"good!"}, "length"), ({"checksum": b""}, "manifest"),
    ({"checksum": b"x" * 65537}, "manifest"),
    ({"checksum": manifest() * 2}, "manifest"),
    ({"checksum": b"not-a-checksum\n"}, "manifest"),
    ({"length": "123"}, "length"),
])
def test_poison_downloads_leave_no_installer_or_partial(tmp_path, changes, category):
    with pytest.raises(VerificationError, match=category):
        run_download(tmp_path, **changes)
    assert list(tmp_path.iterdir()) == []


def test_cancel_during_installer_cleans_partial(tmp_path):
    stopped = False

    def progress(*_):
        nonlocal stopped
        stopped = True

    with pytest.raises(DownloadCancelled):
        run_download(tmp_path, cancelled=lambda: stopped, progress=progress)
    assert list(tmp_path.iterdir()) == []


def test_cancel_before_network(tmp_path):
    with patch("urllib.request.build_opener") as network, pytest.raises(DownloadCancelled):
        download_verified_installer(descriptor(), tmp_path / NAME, cancelled=lambda: True)
    network.assert_not_called()


@pytest.mark.parametrize("url", ["http://github.com/file", "file:///installer.exe",
    "https://github.com.evil.example/file", "https://evil.example/file",
    "https://user:password@github.com/file", "https://github.com:444/file",
    "https://github.com/file#fragment", "https://github.com/file\n"])
def test_forbidden_origin_and_redirect_refused_before_following(url):
    with pytest.raises(VerificationError, match="origin"):
        validate_asset_origin(url)
    with pytest.raises(VerificationError, match="origin"):
        SafeRedirectHandler().redirect_request(None, None, 302, "", {}, url)


@pytest.mark.parametrize("host", ["github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"])
def test_permitted_https_asset_origin(host):
    validate_asset_origin(f"https://{host}/asset?signature=opaque")


def test_redirect_chain_is_bounded_to_five_actual_hops():
    handler = SafeRedirectHandler()
    request = urllib.request.Request(ROOT + NAME)
    for hop in range(5):
        request = handler.redirect_request(request, None, 302, "", HTTPMessage(),
                                           f"https://release-assets.githubusercontent.com/{hop}")
    with pytest.raises(VerificationError, match="origin"):
        handler.redirect_request(request, None, 302, "", HTTPMessage(),
                                 "https://release-assets.githubusercontent.com/sixth")


def test_manifest_exact_basename_and_binary_marker():
    digest = "A" * 64
    assert checksum_for(f"{digest} *{NAME}\n".encode(), NAME) == digest.lower()
    with pytest.raises(VerificationError):
        checksum_for(f"{digest}  ../{NAME}\n".encode(), NAME)


@pytest.mark.parametrize("bad", ["https://evil.example/file", ROOT.replace("v1.30.2", "v1.30.1") + NAME])
def test_descriptor_is_checked_even_when_built_outside_parser(tmp_path, bad):
    with pytest.raises(VerificationError), patch("urllib.request.build_opener") as network:
        download_verified_installer(replace(descriptor(), download_url=bad), tmp_path / NAME)
    network.assert_not_called()


def test_parser_requires_matching_manifest_and_rejects_unsafe_urls():
    assets = [{"name": NAME, "size": 4, "browser_download_url": ROOT + NAME},
              {"name": "SHA256SUMS.txt", "browser_download_url": ROOT + "SHA256SUMS.txt"}]
    assert parse_release_info({"tag_name": "v1.30.2", "assets": assets}).installable
    assets[1]["browser_download_url"] = "https://evil.example/SHA256SUMS.txt"
    assert not parse_release_info({"tag_name": "v1.30.2", "assets": assets}).installable
