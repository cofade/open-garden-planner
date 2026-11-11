## Case study: the same file had two identities — the gallery made a copy, File > Open attached Save to the installed example (#865, fixed 2026-11-11)

**Symptom**: a bundled example opened from the Welcome gallery was an untitled copy;
the same `.ogp` opened through File > Open in the app's install tree was the shipped
file itself. Editing and pressing Ctrl+S wrote into `resources/examples/`, autosave
landed beside it, Recent listed the install path, and the PDF cover said
`family-garden` instead of the example's name. No error, no dirty-state surprise: the
data was simply going somewhere nobody intended.

**Wrong theories**:
- *"The loader has a read-only flag."* It has none: identity is one assignment,
  `self._current_file = None if as_template else file_path`, in `ProjectManager.load`.
- *"`display_name` should prefer the template title."* True for the report, but the
  same `current_file` also drives Save, autosave, Recent and the dialog directory;
  fixing the name alone would have left four write paths pointing at the bundle.
- *"File > Open must ask the user to copy the file first."* The gallery already
  proved the copy can be in memory; a dialog would be a second, weaker policy.

**Key evidence**: `core/templates._bundled_sidecar` already returned a trusted
sidecar for exactly the shipped path (used by `example_copy_plan`, the showcase
moment and the title). The gallery passed `as_template=True`; `_on_open_project`
never asked. The one load path was therefore branching on the CALLER instead of on
the FILE. A test at `test_templates_gallery.py` could not see it: it compared the
identity after an export with whatever the loader had chosen, so it tolerated the
gallery's `None` and File > Open's bundled path alike.

**Root cause**: two entry points for one file made two identities. The truth is a
property of the file (is its sidecar trusted?), not of the menu item that opened it.

**Fix**: `core.templates.is_bundled_example(path)` exposes the trusted predicate;
`_load_project_file` routes a bundled path through `as_template=True` for every
caller (gallery, File > Open, agent `open_plan`). The new test saves the copy to a
temp path and asserts the bundle's bytes and mtime are unchanged, the title is the
sidecar name, and Recent is untouched.

**Lesson**: when the same artifact can arrive by two doors, put the identity decision
at the artifact, not at the door. A test that asserts "the export did not move the
identity" can be green while the identity itself is wrong.
