# Pitfalls: 3D engine and scene

Standing rules for this area, one entry each. The heading is the rule. Pins and sources are listed under each entry. Index: [§11.4](../README.md#114-known-development-pitfalls).

### PF-E3D-01

- **Rule:** A reused (hidden→re-shown) `Qt3DWindow` renders a blank/white surface (PyQt6 + RHI)
- **Pinned by:** none — retired with its subject
- **Source:** none recorded
- **Status:** retired; narrative in [archive/13-retired.md](../archive/13-retired.md#archive-l320-a-reused-hiddenre-shown-qt3dwindow-renders-a-blankwhite-surface-pyqt6--rhi)
- **Legacy:** README L320

### PF-E3D-02

- **Rule:** Key events on a `createWindowContainer`-embedded `Qt3DWindow` don't bubble to the ancestor `QMainWindow` (PyQt6)
- **Pinned by:** none — retired with its subject
- **Source:** none recorded
- **Status:** retired; narrative in [archive/13-retired.md](../archive/13-retired.md#archive-l321-key-events-on-a-createwindowcontainer-embedded-qt3dwindow-dont-bubble-to-the-ancestor-qmainwindow-pyqt6)
- **Legacy:** README L321

### PF-E3D-03

- **Rule:** `QFirstPersonCameraController` free-flies (moves along the pitched view vector, no pitch limit, arrows only) — wrong for a ground walk
- **Pinned by:** none — retired with its subject
- **Source:** none recorded
- **Status:** retired; narrative in [archive/13-retired.md](../archive/13-retired.md#archive-l322-qfirstpersoncameracontroller-free-flies-moves-along-the-pitched-view-vector-no-pitch-limit-arrows-only--wrong-for-a-ground-walk)
- **Legacy:** README L322

### PF-E3D-04

- **Rule:** Time a stall with a trusted clock before blaming the engine
- **Pinned by:** `scripts/make_bench_plans.py`; `tests/conftest.py`; `tests/integration/test_bench_plans.py`; `tests/unit/test_gate_commands.py`
- **Source:** #291, #413
- **Status:** standing; narrative in [archive/01-l0-spike.md](../archive/01-l0-spike.md#1145-the-qt-quick-3d-spike-engine-traps-and-a-hang-that-was-a-stopwatch-problem-adr-048-phase-17-l0)
- **Legacy:** README L890 (legacy 11.4.5)

### PF-E3D-05

- **Rule:** A hash is not equality; float dust is an edit; a bound checked after the work is a report
- **Pinned by:** `scripts/measure_region_work.py`; `scripts/mutation_check_scene3d.py`; `tests/integration/test_scene3d_snapshot.py::TestClosedStrokes`; `tests/integration/test_scene3d_snapshot.py::TestHouseRidge`; `tests/unit/test_scene3d_contract.py::TestRecord`; `tests/unit/test_scene3d_polygon.py::TestSimpleRingAtScale`
- **Source:** #385
- **Status:** standing; narrative in [archive/03-l1-1-scene-contract.md](../archive/03-l1-1-scene-contract.md#11414-four-things-measured-while-building-the-3d-scene-contract-phase-17-l11-385)
- **Legacy:** README L1633 (legacy 11.4.14)

### PF-E3D-06

- **Rule:** A judge must not ask the suspect; no Qt window predicate is trusted until measured; a Python message handler beside a shown Qt Quick window deadlocks
- **Pinned by:** `tests/integration/test_quick3d_lifecycle.py`; `tests/ui/test_quick3d_host.py::TestStateMachine`; `tests/ui/test_quick3d_host.py::TestWaitReady`; `tests/unit/test_quick3d_lifecycle_states.py`; `tests/unit/test_quick3d_packaging.py`; `tests/unit/test_quick3d_pure.py::TestClassify`; `tests/unit/test_quick3d_pure.py::test_nested_recorders_both_hear_an_error`
- **Source:** #291, #385
- **Status:** standing; narrative in [archive/04-l1-2-engine-package.md](../archive/04-l1-2-engine-package.md#11415-what-the-engine-taught-while-the-production-package-was-built-phase-17-l12-385)
- **Legacy:** README L1896 (legacy 11.4.15)

### PF-E3D-07

- **Rule:** No frame inside a measured loop; wait for a condition, not a duration
- **Pinned by:** `tests/unit/test_plain_text.py`
- **Source:** #385, #428
- **Status:** standing; narrative in [archive/05-l1-3-workspace.md](../archive/05-l1-3-workspace.md#11416-what-the-3d-workspace-taught-phase-17-l13-385)
- **Legacy:** README L2313 (legacy 11.4.16)

### PF-E3D-08

- **Rule:** What selection, the info card and walk mode taught (Phase 17 L1.8, #385)
- **Pinned by:** `scripts/mutation_check_scene3d.py`
- **Source:** #385, #428
- **Status:** standing; narrative in [archive/10-l1-8-selection-walk.md](../archive/10-l1-8-selection-walk.md#11419-what-selection-the-info-card-and-walk-mode-taught-phase-17-l18-385)
- **Legacy:** README L3042 (legacy 11.4.19)

### PF-E3D-09

- **Rule:** What the default flip and the removal of Qt 3D taught (Phase 17 L1.9 / L1.10, #385)
- **Pinned by:** none — pending Phase 3 review
- **Source:** #385, #496, #534
- **Status:** standing; narrative in [archive/11-l1-9-l1-10-default-removal.md](../archive/11-l1-9-l1-10-default-removal.md#11420-what-the-default-flip-and-the-removal-of-qt-3d-taught-phase-17-l19--l110-385)
- **Legacy:** README L3157 (legacy 11.4.20)
