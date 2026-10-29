## 9. Data loss on update — the installer wiped user plans (#199/#204, ADR-027)

Source: §11.4 ("Never default a file dialog into the install directory…"), ADR-027,
CLAUDE.md issue table.

- Symptom: "all my gardens vanished after updating."
- Two independent bugs that combined: (1) file dialogs called with `""` as directory open
  in the process CWD — for a packaged build that is
  `C:\Program Files (x86)\Open Garden Planner`, so users saved `.ogp` plans into the
  install dir; (2) the NSIS upgrade path silently runs the *old* uninstaller, which did
  `RMDir /r "$INSTDIR"` — every update deleted the install dir, plans included.
- Fix, both halves required: app side — `app/paths.py` chokepoint routes every
  save/open/export dialog to the open project's folder or
  `<Documents>/Open Garden Planner`, never CWD; installer side — the uninstall section
  rescues top-level `$INSTDIR\*.ogp` to `Documents\Open Garden Planner\Recovered Plans`
  before `RMDir /r` (`/SD IDOK` keeps silent upgrades from hanging).
- Known limitation: the fix is **forward-protective only** — the pre-fix→fixed upgrade
  still runs the old (destructive) uninstaller.
- Status: closed. Pinned by `tests/unit/test_paths.py` and
  `tests/integration/test_save_location.py`; the NSIS half is Windows-only, verified
  manually.

---

