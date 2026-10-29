## 2. Phase 0 — Prerequisites & scope contract

**Required reading (in order):**
1. `docs/roadmap.md` line ~2447 (Phase 14 goals — the 5 bullets).
2. `docs/08-crosscutting-concepts/README.md` §8.1 (coordinates) and the
   §8.10 "Coordinate system reminder" — read BOTH; the Y-up/Y-down split is
   the campaign's central trap. The reconciliation (which one the data path
   follows) is owned by `ogp-qt-cad-reference` §1 — read it too.
3. `docs/09-architecture-decisions/README.md`: ADR-002 (Y-up), ADR-019
   (satellite geo), ADR-031 (predicate split — height interacts with
   plant-parents), ADR-034 (agent API — your validation instrument).
4. `docs/11-risks-and-technical-debt/README.md` §11.1 (the Qt3D open
   question, line 10) and §11.4 (pitfall chronicle).
5. Sibling skill `ogp-change-control` (the gates you will pass at each PR).

**Verify the assets** (Windows dev machine, Git-Bash; Linux second form):

| # | Command (Windows / Linux) | Expected | If not → |
|---|---|---|---|
| 0.1 | `venv/Scripts/python.exe -c "import pyclipper, numpy; print('deps ok')"` / `venv/bin/python -c "..."` | `deps ok` | `pip install -e .` in the venv; if pyclipper missing from pyproject, STOP — inventory table is stale, re-verify everything. |
| 0.2 | `grep -n "FILE_VERSION" src/open_garden_planner/core/project.py` | `FILE_VERSION = "1.4"` (or later) | If bumped since 2026-07: read the bump's ADR before assuming additive-metadata rules still hold. |
| 0.3 | `python3 .agents/skills/ogp-3d-sunshade-campaign/scripts/solar_reference.py` (stdlib only — works in any Python ≥3.11, venv not required) | `RESULT: ALL CHECKS PASSED`, exit 0 | The oracle itself is broken or Python's math changed (it didn't) — debug the script BEFORE writing `core/solar.py`; the campaign's numbers all flow from it. |
| 0.4 | `venv/Scripts/python.exe -m pytest tests/ -x -q` (Linux: `venv/bin/python -m pytest tests/ -x -q`) | All green on `master` | Fix master first (`ogp-debugging-playbook`); never start a campaign on a red base. |

**Deliverable (gate to exit Phase 0):** a US breakdown proposal for
`docs/roadmap.md`, filed through `ogp-change-control` (issue or roadmap PR),
e.g.:

- US-E1 Solar position engine (Qt-free) — Phase 1
- US-E2 Object height property — Phase 2
- US-E3 Shadow overlay + time-of-day/date control — Phase 3
- US-E4 Hours-of-sun heatmap — Phase 4
- US-E5 3D view spike (GO/NO-GO) — Phase 5
- US-E6 (conditional on E5 GO) 3D view MVP; US-E7 walkthrough; US-E8 growth vis

Each US = its own feature branch, senior-reviewer pass, draft PR. Do not
megabranch the campaign.

---

