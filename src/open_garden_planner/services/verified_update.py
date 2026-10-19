"""Release-bound installer verification; no UI or process launching (AUD-042)."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import tempfile
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from http.client import HTTPMessage
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urlsplit

if TYPE_CHECKING:
    from open_garden_planner.services.update_checker import ReleaseInfo

CHUNK_BYTES = 65_536
MANIFEST_MAX_BYTES = 65_536
_ASSET_HOSTS = frozenset({"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"})


class VerificationError(ValueError):
    """Sanitized failure category, translated by the UI (never a signed URL)."""


class DownloadCancelled(Exception):
    """Cancellation is distinct from download failure."""


@dataclass(frozen=True)
class VerifiedInstaller:
    path: Path
    size: int
    sha256: str

    def check(self) -> None:
        """Recheck persisted bytes immediately before handing them to the OS."""
        if self.path.stat().st_size != self.size:
            raise VerificationError("length")
        with self.path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if not hmac.compare_digest(digest, self.sha256):
            raise VerificationError("digest")


def validate_asset_origin(url: str) -> None:
    """Exact HTTPS origins only, including every redirected request."""
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname not in _ASSET_HOSTS
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 443) or parsed.fragment
                or any(ord(char) <= 32 for char in url) or "\\" in url):
            raise VerificationError("origin")
    except ValueError as exc:
        raise VerificationError("origin") from exc


def validate_release_asset(url: str, tag: str, filename: str) -> None:
    validate_asset_origin(url)
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag) or filename not in {
        f"OpenGardenPlanner-{tag}-Setup.exe", "SHA256SUMS.txt",
    }:
        raise VerificationError("origin")
    parsed = urlsplit(url)
    expected = f"/cofade/open-garden-planner/releases/download/{tag}/{filename}"
    if parsed.hostname != "github.com" or unquote(parsed.path) != expected or parsed.query:
        raise VerificationError("origin")


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Validate before following redirects, and limit the complete chain."""

    max_redirections = 5
    max_repeats = 1

    def redirect_request(
        self, req: urllib.request.Request, fp: Any, code: int, msg: str,
        headers: HTTPMessage, newurl: str,
    ) -> urllib.request.Request | None:
        validate_asset_origin(newurl)
        hops = int(getattr(req, "a1_redirect_hops", 0)) + 1
        if hops > 5:
            raise VerificationError("origin")
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None:
            vars(redirected)["a1_redirect_hops"] = hops
        return redirected


def checksum_for(content: bytes, filename: str) -> str:
    """Require exactly one sha256sum entry for the selected asset basename."""
    try:
        lines = content.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise VerificationError("manifest") from exc
    matching = []
    for line in lines:
        if not line.strip():
            continue
        match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *]([^/\\]+)", line)
        if match is None:
            raise VerificationError("manifest")
        if match[2] == filename:
            matching.append(match[1].lower())
    if len(matching) != 1:
        raise VerificationError("manifest")
    return matching[0]


def _check_cancel(cancelled: Callable[[], bool]) -> None:
    if cancelled():
        raise DownloadCancelled


def _open_asset(opener: urllib.request.OpenerDirector, url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "OpenGardenPlanner-Updater"})
    response = opener.open(request, timeout=15)
    try:
        validate_asset_origin(response.geturl())
    except Exception:
        response.close()
        raise
    return response


def download_verified_installer(
    release: ReleaseInfo, dest: Path, *,
    cancelled: Callable[[], bool] = lambda: False,
    progress: Callable[[int, int], None] = lambda _done, _total: None,
) -> VerifiedInstaller:
    """Download, verify and finalize; every failure removes the partial file."""
    if not release.installable or dest.name != release.installer_name:
        raise VerificationError("manifest")
    assert release.download_url is not None and release.checksum_url is not None
    validate_release_asset(release.download_url, release.tag_name, release.installer_name)
    validate_release_asset(release.checksum_url, release.tag_name, "SHA256SUMS.txt")
    _check_cancel(cancelled)
    opener = urllib.request.build_opener(SafeRedirectHandler())
    with _open_asset(opener, release.checksum_url) as response:
        manifest = bytearray()
        while True:
            _check_cancel(cancelled)
            chunk = response.read(min(CHUNK_BYTES, MANIFEST_MAX_BYTES + 1 - len(manifest)))
            if not chunk:
                break
            manifest.extend(chunk)
            if len(manifest) > MANIFEST_MAX_BYTES:
                raise VerificationError("manifest")
    expected = checksum_for(bytes(manifest), release.installer_name)
    _check_cancel(cancelled)
    if dest.exists():
        raise VerificationError("destination")
    fd, temporary = tempfile.mkstemp(prefix=".installer-", suffix=".part", dir=dest.parent)
    finalized = False
    try:
        digest = hashlib.sha256()
        downloaded = 0
        with os.fdopen(fd, "wb") as stream, _open_asset(opener, release.download_url) as response:
            length = response.getheader("Content-Length")
            if length is not None and int(length) != release.installer_size:
                raise VerificationError("length")
            while True:
                _check_cancel(cancelled)
                chunk = response.read(min(CHUNK_BYTES, release.installer_size + 1 - downloaded))
                if not chunk:
                    break
                downloaded += len(chunk)
                if downloaded > release.installer_size:
                    raise VerificationError("length")
                digest.update(chunk)
                stream.write(chunk)
                progress(downloaded, release.installer_size)
            _check_cancel(cancelled)
            if downloaded != release.installer_size:
                raise VerificationError("length")
            if not hmac.compare_digest(digest.hexdigest(), expected):
                raise VerificationError("digest")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, dest)
        finalized = True
        _check_cancel(cancelled)
        return VerifiedInstaller(dest, downloaded, expected)
    except Exception:
        if finalized:
            dest.unlink(missing_ok=True)
        raise
    finally:
        Path(temporary).unlink(missing_ok=True)
