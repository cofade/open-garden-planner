"""Exercise wiki validation, rendering, and comparison through the real CLI."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/sync_wiki.py"
PAGES = {"Home.md", "Roadmap.md", "Installation.md", "Contributing.md",
         "Architecture.md", "_Sidebar.md"}


@pytest.fixture
def source_repo(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    shutil.copytree(ROOT / "docs", root / "docs",
                    ignore=shutil.ignore_patterns("*.png", "*.ogp", "*.json"))
    for name in ("README.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md",
                 "ACCESSIBILITY.md", "LICENSE"):
        shutil.copyfile(ROOT / name, root / name)
    return root


def invoke(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), *args],
                          capture_output=True, text=True, encoding="utf-8", timeout=30,
                          check=False)


def snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob("*") if p.is_file()}


def test_check_is_offline_and_read_only(source_repo: Path) -> None:
    before = snapshot(source_repo)
    for args in ((), ("--check",)):
        result = invoke(source_repo, *args)
        assert result.returncode == 0, result.stderr
        assert "6 wiki pages and 3 roadmap inclusions" in result.stdout
    assert snapshot(source_repo) == before


def test_render_is_deterministic_preserves_other_files_and_tracks_source(source_repo: Path,
                                                                        tmp_path: Path) -> None:
    output = tmp_path / "preview"
    output.mkdir()
    note = output / "Unrelated.md"
    note.write_bytes(b"direct wiki edit to preserve\r\n")
    before = snapshot(source_repo)
    assert invoke(source_repo, "--output", str(output)).returncode == 0
    first = snapshot(output)
    assert set(first) == PAGES | {"Unrelated.md"}
    assert invoke(source_repo, "--output", str(output)).returncode == 0
    assert snapshot(output) == first
    assert snapshot(source_repo) == before

    roadmap = source_repo / "docs/roadmap.md"
    text = roadmap.read_text(encoding="utf-8")
    text = text.replace("| 1 | v0.1 |", "| 1 | v99.123 |", 1)
    roadmap.write_text(text, encoding="utf-8")
    assert invoke(source_repo, "--output", str(output)).returncode == 0
    rendered = (output / "Roadmap.md").read_text(encoding="utf-8")
    start = text.index("| Phase |")
    table = text[start:text.index("\n\n", start)]
    assert table in rendered  # byte-for-byte table content, including check marks
    assert "v99.123" in rendered
    assert "ogp:include" not in rendered
    assert "## Phase 17: Living Garden 3D" in rendered
    assert "shipped 3D view still uses **Qt 3D**" in rendered
    assert "L0 is complete with a GO" in rendered
    assert "\u2705" in rendered
    assert b"\r\n" not in (output / "Roadmap.md").read_bytes()
    assert note.read_bytes() == b"direct wiki edit to preserve\r\n"


def test_published_comparison_reports_changes_and_never_writes(source_repo: Path,
                                                               tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    assert invoke(source_repo, "--output", str(wiki)).returncode == 0
    args = ("--check-published", "--wiki-dir", str(wiki))
    before = snapshot(source_repo), snapshot(wiki)
    assert invoke(source_repo, *args).returncode == 0
    assert (snapshot(source_repo), snapshot(wiki)) == before
    home = wiki / "Home.md"
    home.write_text("# Direct wiki edit\n", encoding="utf-8")
    (wiki / "Installation.md").unlink()
    before = snapshot(source_repo), snapshot(wiki)
    result = invoke(source_repo, *args)
    assert result.returncode == 1
    assert "published/Home.md" in result.stdout
    assert "Missing published page: Installation.md" in result.stdout
    assert (snapshot(source_repo), snapshot(wiki)) == before


@pytest.mark.parametrize("section", ["Overview", "Dev Infrastructure", "Phase 17: Living Garden 3D"])
def test_missing_canonical_section_fails_before_output(source_repo: Path, tmp_path: Path,
                                                      section: str) -> None:
    path = source_repo / "docs/roadmap.md"
    path.write_text(path.read_text(encoding="utf-8").replace(f"## {section}", "## Removed", 1),
                    encoding="utf-8")
    output = tmp_path / "output"
    before = snapshot(source_repo)
    result = invoke(source_repo, "--output", str(output))
    assert result.returncode == 2
    assert "Expected one roadmap section" in result.stderr
    assert not output.exists()
    assert snapshot(source_repo) == before


@pytest.mark.parametrize("replacement", ["", "<!-- ogp:include unknown -->",
                                        "<!-- ogp:include roadmap-overview -->\n" * 2,
                                        "<!-- ogp:include roadmap-overview-->"])
def test_invalid_marker_fails(source_repo: Path, replacement: str) -> None:
    path = source_repo / "docs/wiki/Roadmap.md"
    path.write_text(path.read_text(encoding="utf-8").replace(
        "<!-- ogp:include roadmap-overview -->", replacement, 1), encoding="utf-8")
    result = invoke(source_repo, "--check")
    assert result.returncode == 2
    assert "inclusion marker" in result.stderr


@pytest.mark.parametrize("bad_link", ["[Missing](Missing)", "[Bad heading](Home#not-a-heading)",
                                    "[Absent](https://github.com/cofade/open-garden-planner/blob/master/docs/absent.md)",
                                    "[Outside](https://github.com/cofade/open-garden-planner/blob/master/../outside.md)"])
def test_broken_local_links_fail(source_repo: Path, bad_link: str) -> None:
    path = source_repo / "docs/wiki/Home.md"
    path.write_text(path.read_text(encoding="utf-8") + "\n" + bad_link + "\n", encoding="utf-8")
    result = invoke(source_repo, "--check")
    assert result.returncode == 2
    assert "Broken" in result.stderr


@pytest.mark.parametrize("bad_text", [b"\xff", b"\\u2014", "\ufffd".encode(),
                                     "\u00e2\u20ac\u201c".encode()])
def test_invalid_encoding_and_literal_escape_fail(source_repo: Path, bad_text: bytes) -> None:
    path = source_repo / "docs/wiki/Home.md"
    path.write_bytes(path.read_bytes() + b"\n" + bad_text)
    assert invoke(source_repo, "--check").returncode == 2


def test_output_cannot_overwrite_source_or_directory(source_repo: Path, tmp_path: Path) -> None:
    before = snapshot(source_repo)
    assert invoke(source_repo, "--output", str(source_repo / "docs/wiki")).returncode == 2
    assert snapshot(source_repo) == before
    output = tmp_path / "blocked"
    (output / "Roadmap.md").mkdir(parents=True)
    assert invoke(source_repo, "--output", str(output)).returncode == 2
    assert not (output / "Home.md").exists()


def test_missing_checkout_and_invalid_modes_fail(source_repo: Path, tmp_path: Path) -> None:
    assert invoke(source_repo, "--check-published", "--wiki-dir", str(tmp_path / "absent")).returncode == 2
    assert invoke(source_repo, "--check-published").returncode == 2
    assert invoke(source_repo, "--wiki-dir", str(tmp_path)).returncode == 2
    assert invoke(source_repo, "--check", "--output", str(tmp_path / "out")).returncode == 2
