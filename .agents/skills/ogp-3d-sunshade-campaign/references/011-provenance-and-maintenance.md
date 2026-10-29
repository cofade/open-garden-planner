## Provenance and maintenance

All repo facts verified 2026-07-04 against the working tree at v1.23.0;
re-verified 2026-07-19 at v1.24.3 (ADR numbering corrected to 037/038, all
other facts held). One-line re-verification commands (run from repo root):

- Solar oracle still green: `python3 .agents/skills/ogp-3d-sunshade-campaign/scripts/solar_reference.py --quiet; echo $?` → expect final `RESULT: ALL CHECKS PASSED`, exit 0.
- Phase 14 roadmap section: `grep -n "Phase 14" docs/roadmap.md` → line ~2447.
- Qt3D open question still open: `grep -n "Qt3D" docs/11-risks-and-technical-debt/README.md` → line ~10 (delete the Phase 5 spike if this row is closed by an ADR).
- Location dict: `grep -n "latitude, longitude, elevation_m" src/open_garden_planner/core/project.py` → ~line 747.
- FILE_VERSION: `grep -n "FILE_VERSION" src/open_garden_planner/core/project.py` → `"1.4"` (if higher, re-read the bumping ADR before trusting the additive-metadata rules).
- pyclipper + numpy deps: `grep -nE "pyclipper|numpy" pyproject.toml`.
- Species height coverage: the python3 one-liner in §0 → `118 / 118` (or more records, same full coverage expected).
- Cosmetic-shadow collision: `grep -n "KEY_SHOW_SHADOWS" src/open_garden_planner/app/settings.py` → `appearance/show_shadows` is a retained compatibility accessor, ignored by the application (ADR-062).
- Next ADR number: `grep -oE "^## ADR-[0-9]+" docs/09-architecture-decisions/README.md | sort -V | tail -1` and take max+1 (036 as of 2026-07-19; campaign reserves 037 + 038). (`grep -c` would miscount if numbering ever gains a gap.)

