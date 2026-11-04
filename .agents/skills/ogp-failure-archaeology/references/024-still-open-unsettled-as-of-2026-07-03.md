## Still open / unsettled (as of 2026-07-03)

- **#206 rebuild-on-repaint firehose smell.** The properties panel is fixed
  (identity + refreshers) and the Find-Plants list has a signature guard, but §11.4
  explicitly calls the guard "a local band-aid, not a structural fix — the firehose
  still re-queries the whole scene every tick". Any list/panel newly wired to
  `scene.changed` will re-fight saga #6 unless it is idempotent from day one.
- **TD-007 — EDGE_* anchor instability** (§11.3 + §11.4): edge anchors on
  polygons/polylines are classified by *current* dominant axis; dragging a vertex far
  enough flips the classification and constraint indicators jump. Workaround in place
  (index-only match block in `_resolve_anchor_position`). Real fix (single
  `EDGE_MIDPOINT` type + stable `anchor_index`) not done. Priority: Medium.
- **TD-008 — numerical Jacobian** (§11.3): Newton refinement uses a central-difference
  Jacobian. **Deliberately not fixed** — microseconds for ≤20-variable systems, no
  user-facing impact. Do not "optimize" this without evidence of a large-scene
  bottleneck.
- ~~**No token auth on the loopback Agent API**~~ — **RESOLVED for writes by US-D2.0**
  (ADR-036 addendum, v1.24.3): every scene-mutating write tool is double-gated
  (registered only when both the toggle and the token are set, plus a
  constant-time per-call check). The entry was written when the server was
  read-only and is retained here only as the historical shape of the problem.
  **What is still open**: *reads* remain loopback-trust with no auth (challenged
  decision C2 in `audits/2026-10/audit-2026-10.md`), and the browser-reachability vector is a
  separate barrier — the Host/Origin (DNS-rebinding) guard, now configured
  explicitly by OGP rather than inherited from the SDK (#396, ADR-033 addendum).
  Do not read "token auth shipped" as "the Agent API is authenticated".
- **Smart Symbols UI deferred** (CLAUDE.md C4 row): the sidebar panel ships hidden
  (`set_panel_visible("smart_symbols", False)` in `application.py`); engine,
  persistence, DXF export, and properties editing are live and tested. The hidden panel
  is intentional, not dead code.
- **§11.1/§11.2 tables** list open questions/risks (Trefle rate limits, texture
  licensing, Qt3D-vs-PyVista for Phase 14 3D, installer signing/SmartScreen, PyInstaller
  bundle size). The 2026-10 audit gave the stale §11.1/§11.2 rows and every §11.3 row a status
  (§11.3 is now the living register, ADR-047): TD-001/TD-002 are closed; read the Status
  column before acting on a row.
- **#199 residual exposure**: the installer fix is forward-protective only; a user
  upgrading from a pre-fix build still runs the old destructive uninstaller once (the
  rescue only exists in the *new* uninstaller going forward).
- **#193 opt-in trap**: still structurally live — every future
  `ItemIgnoresTransformations` handle must be registered in `CanvasView`'s allow-list.

---

