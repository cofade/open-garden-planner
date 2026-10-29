## Index — scan this first

| # | Saga | Issues / PRs | One-line lesson | Status |
|---|------|--------------|-----------------|--------|
| 1 | Rotated-geometry saga | #213/#217, #219/#220, #218/#221 | Every geometry mutation must end with `transformOriginPoint == rect().center()`; don't post-correct an incoherent geometry step — fix the step | Closed |
| 2 | Panel-rebuild saga | #200/#205, #206/#222, #206/#223, #225/#230 | Never rebuild a form on every command signal; identity-gated rebuild + per-widget refreshers | Closed (smell remains, see Open) |
| 3 | Undo/dirty data loss | #209/#211 | Exactly two ways onto the undo stack (`execute`, `register_applied`); both must dirty | Closed |
| 4 | Free-text commit granularity | #210/#214 | Debounce + focus-out commit, and flush pending commits before any form rebuild | Closed |
| 5 | Task dual-store convergence | #227, #228/#230 | Two surfaces sharing an id-keyed store must share the *entire* id derivation; dual-write invariants rot — converge to one write path | Closed |
| 6 | Find Plants selection flakiness | #212/#215 (two rounds) | Store ids not item refs, defer the selection, and a debounce is not idempotence — diff before rebuild | Closed (band-aid, see Open) |
| 7 | Smart-symbol exception enumeration | PR #236 (3 review rounds) | At a trust boundary, one broad `except Exception` at the ingestion seam; enumerating families is a losing game | Closed |
| 8 | Release workflow races | (pre-#209 chore race), #229 | Skip releases for chore commits; wait for releases by *tag transition*, never by date matching | Closed |
| 9 | Data loss on update | #199/#204, ADR-027 | User data must never live under `$INSTDIR`; dialogs must never default to CWD | Closed (forward-protective only) |
| 10 | i18n incidents | (US-12.8 era, ongoing) | `tr()` must be on the call path (registration alone is useless); never PowerShell `Set-Content` on UTF-8 | Closed, recurring class |
| 11 | CI-only teardown crashes | #230, PR #235 | `scene.changed` timer slots and app-global-signal slots must be teardown-safe | Closed |
| 12 | Agent API render (D1.3) | PR #242 | `layers` must force-show, not only hide; two mcp-1.28.1 facts are empirical, don't "clean them up" | Closed |
| 13 | Retired: US-B7 Paper Space | PR #191 review | Feature dropped — pdf_report_service already covered it; `paper_layouts` key silently ignored on load | Retired |
| 14 | Export Y-flip saga | US-12.10-era, 4 case studies | QSvgGenerator/QPdfWriter are not faithful painter serializers; validate SVG in a real browser | Closed |
| 15 | Tangent-constraint degeneracy | "make snap-constraints real" PR #198 | Residual *formulation* decides solver conditioning — parallel gradients = rank-deficient | Closed |
| 16 | Inert `ItemIgnoresTransformations` handles | #193/#202 | New drag handles must join `CanvasView`'s allow-list; synthetic QMouseEvents don't reach these children | Closed (opt-in trap remains) |
| 17 | Label editor auto-close | (2026-04-22) | The minimap hid overlay items incl. the focused editor; stack traces at unexpected call sites find external culprits | Closed |
| 18 | QSettings global-static test poison | (test-suite isolation) | Never call `QSettings.setDefaultFormat/setPath` in a test; "passes alone, fails together, value = default" ⇒ global state | Closed |
| 19 | Stale-trigger family | #173/#175 | `scene.changed` fires only on *visual* change — attribute writes need explicit refresh triggers inside commands | Closed |
| 20 | Ghost-field family (US-12.10d) | #170, dataclass round-trip | New dataclass fields need `to_dict`/`from_dict` AND a UI row; construct-and-test ≠ serialize-and-test | Closed |
| 21 | UNKNOWN-enum display corruption | #231/#232 | Combos need a neutral entry for UNKNOWN; `setSpecialValueText("")` is a silent no-op | Closed |
| 22 | Same-z stacking flip on save/load | US-12.10/F2.7 | Equal zValues tie-break on insertion order, which is not stable across save/load — encode parent+1 explicitly | Closed |
| 23 | Bed-menu wiring recurrence | #173, US-12.8 | Four bed shape classes ⇒ hand-wiring per class regressed twice; now centralised + parametrised test | Closed |
| 24 | `max()` left-biased ties | US-12.10/F2.10a | `max(key=date)` returns the FIRST maximal record — design tie-breaks explicitly | Closed |

Cross-references: forward-looking invariants → `ogp-architecture-contract`; live-bug
triage → `ogp-debugging-playbook`; instrumentation method → project skill
`debug-verbose`; release mechanics → `ogp-change-control` / `finalize-us`.

---

