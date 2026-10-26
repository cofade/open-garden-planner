"""No tracked text file has CR CR LF line endings (#614).

Commit fee03ea3 stored five files (``CLAUDE.md``, ``AGENTS.md``, the building block view
and both ``ogp-docs-and-writing`` skills) with ``\\r\\r\\n`` on every line. A Markdown
renderer may read the doubled CR as a blank line, splitting tables and lists, and every
branch touching the files met a whole-file merge conflict. Nothing noticed: the agent
context parity gate compares the two pickup files, and both were corrupted alike.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
#: Binary files a doubled CR may legitimately appear in.
BINARY_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".ico", ".qm", ".ttf", ".otf", ".woff", ".woff2",
                             ".pdf", ".zip", ".exe", ".dll", ".pyd", ".so", ".npz", ".npy", ".bin", ".icns",
                             ".webp", ".svgz", ".mp4", ".wav"})


def _tracked() -> list[Path]:
    listed = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True).stdout
    return [REPO / name for name in listed.decode("utf-8").split("\0") if name]


def test_no_tracked_text_file_has_doubled_carriage_returns() -> None:
    files = _tracked()
    assert len(files) > 500, "the listing of tracked files is broken"
    doubled = []
    for path in files:
        if path.suffix.lower() in BINARY_SUFFIXES or not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data[:8000]:   # binary after all
            continue
        if b"\r\r\n" in data:
            doubled.append(str(path.relative_to(REPO)))
    assert not doubled, f"CR CR LF line endings: {doubled}"
