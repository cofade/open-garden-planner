## Case study: About said 1.2.0 while the manifest said 1.31.1 (#596 manual pass)

**Symptom.** A direct `python -m PyInstaller installer/ogp.spec` build showed Version 1.2.0 in Help → About; `pyproject.toml` and `__init__.py` said 1.31.1.
**Wrong theories.** The About dialog cached a version; the build did not pass `--version`; the update checker displayed the latest release.
**Evidence.** `get_current_version()` reads `open_garden_planner._version` when `sys.frozen`. `_version.py` was tracked, last written 2026-03-01 with 1.2.0. `installer/build_installer.py` rewrites it on the release path; a raw PyInstaller build does not.
**Root cause/fix.** `_version.py` is a build artifact. It is removed from git and gitignored; the release build writes the release version, and a direct build falls back to `__version__`. `tests/unit/test_packaging_metadata.py` monkeypatches `sys.frozen` and removes the module from `sys.modules` to pin the fallback.
**Lesson.** A version shown by the shipped artifact must come from that artifact's build path, not from a file tracked months ago. Build the exact command the gate uses and read About.


