## Case study: the same metadata query returned 5 distributions under pytest and 48 in the shell (#454, 2026-10-13)

**Symptom.** The runtime-closure resolver behind the release's third-party notices and SBOM
returned five names (the project, `Pillow`, and the three `PyQt6*` wheels) when a unit test
called it, but 48 names when the identical module was executed directly with the same
interpreter. No product code ran at all.

**Wrong theories.** First theory: `importlib.metadata` caching inside pytest. It has no such
cache. Second: the frozen bundle's `.dist-info` set differing from the environment's. The
bundle was not involved in the failing call. Third: a marker evaluation difference between
`evaluate()` calls. The same wrong answer repeated verbatim, which is the tell for "a
different object, not a different judgement".

**Evidence.** The decisive line was printing the resolved distribution's own location:

```python
print(metadata.distribution("open-garden-planner")._path)
# C:\...\open-garden-planner\src\open_garden_planner.egg-info
```

and then listing every distribution whose name contains "garden":

```python
[x._path for x in metadata.distributions() if "garden" in x.metadata["Name"].lower()]
# [ ...\src\open_garden_planner.egg-info,
#   ...\venv\Lib\site-packages\open_garden_planner-1.30.2.dist-info,
#   ...\src\open_garden_planner.egg-info ]
```

Two records for one name; the stale one (version `0.1.0`, two dependencies, written years
earlier by a legacy editable install) won under pytest because the editable install's `.pth`
puts `src/` on `sys.path` ahead of site-packages.

**Root cause.** `importlib.metadata.distribution(name)` returns the **first** matching
distribution on `sys.path`, not the newest — and `sys.path` order differs between a plain
`python -c` run and pytest (which inserts test paths). The resolver trusted "the project's own
installed metadata" while an unowned artefact of the project's history shadowed it.

**Fix.** The resolver now anchors on `pyproject.toml`'s `[project].dependencies` and walks
only *third parties* through installed metadata (`installer/runtime_closure.py`); the stale
`*.egg-info` was removed from the dev checkout as well, and a test pins the manifest anchor
with an injected manifest. Same build task, second discovery: PyInstaller's
`hook-importlib_metadata` bundles setuptools' **vendored** `importlib_metadata` (Apache-2.0)
although nothing declares it, so the initial fix added an explicit hook exception. PR #490 superseded that exception
with physical RECORD attribution of actual collected owners (see the preceding case study).

**Lesson.** When a metadata lookup disagrees with a file a human can read, print the
distribution's `_path` before theorising — the answer is usually "you resolved a different
distribution than you meant". And an input that must describe what ships has no business
depending on the environment's copy of yourself: read the manifest.

