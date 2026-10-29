## 7. Phase 5 — 3D view decision spike (GO/NO-GO) — TO BUILD

This answers §11.1's open question. Timebox: **5 working days**. The
sun/shade features (Phases 1–4) ship regardless of this outcome — that is the
campaign's insurance policy.

**Do not assert the current state of Qt3D from memory.** Qt3D's status in the
Qt 6 series has been in flux (module maintenance, wheel availability for
PyQt6 vs PySide6 differ). Everything in this table is **REQUIRES VERIFICATION
at spike time** — the commands are the deliverable, not remembered claims:

| Criterion | How to verify (exact commands) | GO threshold |
|---|---|---|
| PyQt6 Qt3D availability & maintenance | `venv/Scripts/python.exe -m pip index versions PyQt6-3D` ; then `venv/Scripts/python.exe -m pip install PyQt6-3D` in a THROWAWAY venv; probe `python -c "from PyQt6.Qt3DCore import QEntity; from PyQt6.Qt3DExtras import Qt3DWindow; print('qt3d ok')"`; check the release date/version skew vs installed PyQt6 (`pip show PyQt6 PyQt6-3D`); check Riverbank's roadmap page for deprecation notices | Wheel exists for current PyQt6 minor, imports clean on Windows, release < 12 months old |
| Alternative: PyVista (VTK) | `pip install pyvista pyvistaqt` in throwaway venv; probe `python -c "import pyvista; print(pyvista.__version__)"`; embed test: `QtInteractor` inside a QDialog | Same import + embed bar. **License: PyVista MIT, VTK BSD-3, pyvistaqt MIT — all GPL-3 compatible** (project is GPL-3.0-or-later, pyproject line 10). Note VTK wheel size (~100 MB) → installer-size criterion below |
| Alternative: pyqtgraph.opengl | `pip install pyqtgraph PyOpenGL`; probe `GLViewWidget` | MIT, tiny; weakest feature set (no shadow mapping out of box — you'd project shadows yourself, which Phase 3 already does analytically → genuinely viable for a 2.5D look) |
| Zero-dep fallback: 2.5D isometric | No install — prototype a `QGraphicsScene` isometric projection (items extruded by `object_height_cm`, painter-sorted) | Always available; this is the DEFER outcome, not a failure |
| **Packaging under PyInstaller (MANDATORY, the decisive gate)** | Add the candidate to a spike branch, build the exe and run **both** gate commands per `ogp-change-control` §2.8 (exit 124, then exit 0). Then open the 3D spike window in the frozen exe on a real Windows box | Frozen exe shows a lit, rotating extruded box textured from a real `.ogp`'s items. Precedent for hidden-import pain: the mcp/uvicorn saga (§8.19 packaging note; expect `collect_submodules`/`copy_metadata`/binaries work for VTK especially) |
| Installer size delta | compare `dist/` size before/after | < +150 MB or owner explicitly accepts |
| GPL compatibility of the chosen dep | read its license file, cross-check SPDX | Must be GPL-3-compatible; if a sibling `ogp-external-positioning` skill exists, follow its process |

**Spike deliverable:** ADR-038 "3D engine choice" with the filled-in table,
the frozen-exe screenshot, and the decision.

**Kill criteria (write them in the ADR before starting):**
- Frozen-exe gate not passed for ANY candidate after 5 days → **NO-GO**:
  ship Phases 1–4 as v2.0's sun/shade story + the 2.5D isometric fallback as
  a later US; keep §11.1's row updated with what you learned.
- Candidate imports but needs per-machine GPU driver workarounds in testing →
  NO-GO for that candidate (support burden).
- GO → US-E6 (3D MVP: extruded footprints by `object_height_cm`, orbit
  camera, sun-directional light using Phase 1's vector — elevation/azimuth to
  a 3D light direction is `(cos α·sin Az, cos α·cos Az, sin α)` in
  (E, N, up)), then US-E7 walkthrough (first-person camera on the ground
  plane), US-E8 growth visualization (scale plant height between
  `min_height_cm`→`max_height_cm` from the species DB across a date slider —
  data verified present for 118/118 species).

---

