# Pitfalls: 3D engine and scene

One entry per lesson, each under its permanent `PF-<AREA>-<NN>` ID. Each entry gives its rule, the test that pins it, its sources and its status. Index: [§11.4](../README.md#114-known-development-pitfalls).

### PF-E3D-01

- **Rule:** Retired: each open of the 3D view built a fresh `Qt3DWindow`, because a hidden and re-shown one rendered blank, and the code no longer follows this since the Qt 3D window is gone.
- **Pinned by:** none — retired with its subject: the body names no test, and the Qt 3D window it describes no longer exists in the code.
- **Source:** none recorded
- **Status:** retired; narrative in [archive/13-retired.md](../archive/13-retired.md#archive-l320-a-reused-hiddenre-shown-qt3dwindow-renders-a-blankwhite-surface-pyqt6--rhi)
- **Legacy:** b1faaa9 README L320

### PF-E3D-02

- **Rule:** Retired: the Qt 3D walk read keys through an event filter on the embedded `Qt3DWindow`, whose key events never reach the `QMainWindow`, and the code no longer follows this since that window is gone.
- **Pinned by:** none — retired with its subject: the body names no test, and the embedded Qt 3D window it describes no longer exists in the code.
- **Source:** none recorded
- **Status:** retired; narrative in [archive/13-retired.md](../archive/13-retired.md#archive-l321-key-events-on-a-createwindowcontainer-embedded-qt3dwindow-dont-bubble-to-the-ancestor-qmainwindow-pyqt6)
- **Legacy:** b1faaa9 README L321

### PF-E3D-03

- **Rule:** Retired: the Qt 3D walk used `QFirstPersonCameraController` for mouse-look only and moved the walker itself, because the controller free-flies, and the code no longer follows this since Qt 3D is gone.
- **Pinned by:** none — retired with its subject: the body names no test, and the Qt 3D walk camera it describes no longer exists in the code.
- **Source:** none recorded
- **Status:** retired; narrative in [archive/13-retired.md](../archive/13-retired.md#archive-l322-qfirstpersoncameracontroller-free-flies-moves-along-the-pitched-view-vector-no-pitch-limit-arrows-only--wrong-for-a-ground-walk)
- **Legacy:** b1faaa9 README L322

### PF-E3D-04

- **Rule:** Tooling that must run headless writes its own timestamped log, per-phase metrics and a `faulthandler` watchdog, because without timestamps a slow run and a hung run look the same.
- **Pinned by:** none — the body names no test for this rule; the gate-command test and the bench-plan fixture test it names belong to other items of the narrative.
- **Source:** #291, #413
- **Status:** standing; narrative in [archive/01-l0-spike.md](../archive/01-l0-spike.md#1145-the-qt-quick-3d-spike-engine-traps-and-a-hang-that-was-a-stopwatch-problem-adr-048-phase-17-l0)
- **Legacy:** b1faaa9 README L890 (legacy 11.4.5)

### PF-E3D-05

- **Rule:** Every scene-record length is snapped to 1e-7 cm and every signature match is confirmed by comparing the values, so float dust cannot invent an edit and a hash collision cannot hide one.
- **Pinned by:** `tests/unit/test_scene3d_contract.py::test_a_signature_is_only_an_accelerator`; `tests/unit/test_scene3d_contract.py::test_every_geometry_value_is_compared_not_only_hashed`; `tests/unit/test_scene3d_contract.py::test_a_transform_and_a_material_are_compared_too`; `tests/integration/test_scene3d_snapshot.py::test_a_thousand_moves_never_leak_float_dust_into_the_geometry`
- **Source:** #385
- **Status:** standing; narrative in [archive/03-l1-1-scene-contract.md](../archive/03-l1-1-scene-contract.md#11414-four-things-measured-while-building-the-3d-scene-contract-phase-17-l11-385)
- **Legacy:** b1faaa9 README L1633 (legacy 11.4.14)

### PF-E3D-06

- **Rule:** Whether a Qt Quick frame can be had is read from the frame itself, its size within half a device pixel of the window's, not inferred from Qt's window predicates, and no Python Qt message handler runs beside a shown window.
- **Pinned by:** `tests/unit/test_quick3d_lifecycle_states.py`; `tests/ui/test_quick3d_host.py::TestStateMachine`; `tests/ui/test_quick3d_host.py::TestWaitReady`; `tests/integration/test_quick3d_lifecycle.py::test_after_wait_ready_the_frame_has_the_windows_new_size`; `tests/integration/test_quick3d_lifecycle.py::test_a_seeded_random_order_never_yields_a_wrong_frame`; `tests/integration/test_quick3d_lifecycle.py::test_a_view_that_nothing_draws_is_refused_promptly_and_answers_when_painting_resumes`; `tests/integration/test_quick3d_lifecycle.py::test_the_same_walk_where_a_small_screen_leaves_the_pane_beyond_the_edge`; `tests/integration/test_quick3d_lifecycle.py::test_a_pane_beyond_the_screens_edge_gets_a_frame_or_a_prompt_refusal_and_answers_when_it_is_back`; `tests/integration/test_quick3d_lifecycle.py::test_at_125_percent_a_pane_one_pixel_wider_does_not_get_its_old_frame`; `tests/integration/test_quick3d_lifecycle.py::test_the_judge_knows_a_wrong_frame_when_it_sees_one`; `tests/integration/test_quick3d_lifecycle.py::test_a_python_message_handler_beside_a_shown_window_deadlocks`
- **Source:** #291, #385
- **Status:** standing; narrative in [archive/04-l1-2-engine-package.md](../archive/04-l1-2-engine-package.md#11415-what-the-engine-taught-while-the-production-package-was-built-phase-17-l12-385)
- **Legacy:** b1faaa9 README L1896 (legacy 11.4.15)

### PF-E3D-07

- **Rule:** A memory soak takes no frame inside its measured loop, only one before and one after, and a test waits for the condition the product itself waits for, never for a guessed duration.
- **Pinned by:** none — the body names no test for this rule; the tests it names pin other items, such as the invisible-character scan, or mark where a symptom appeared.
- **Source:** #385, #428
- **Status:** standing; narrative in [archive/05-l1-3-workspace.md](../archive/05-l1-3-workspace.md#11416-what-the-3d-workspace-taught-phase-17-l13-385)
- **Legacy:** b1faaa9 README L2313 (legacy 11.4.16)
- **Note:** §8.10.9 corrects the original entry's bullets 2–4, which describe earlier versions of the rule; read the correction there before relying on them.

### PF-E3D-08

- **Rule:** Anything that comes and goes in the 3D pane is a resize of the view, so its room is reserved, and a walk-mode key filter owns a key only if it claims it at `ShortcutOverride`.
- **Pinned by:** none — the body names no test for this rule; its one named test, `test_every_mutant_still_matches_its_file_exactly_once`, guards the mutation scripts' patterns and is defined in three files.
- **Source:** #385, #428
- **Status:** standing; narrative in [archive/10-l1-8-selection-walk.md](../archive/10-l1-8-selection-walk.md#11419-what-selection-the-info-card-and-walk-mode-taught-phase-17-l18-385)
- **Legacy:** b1faaa9 README L3042 (legacy 11.4.19)

### PF-E3D-09

- **Rule:** Measure the unchanged code before crediting a change with a difference, and after merging into a removal scan the whole merged tree for every removed name, not only the files that conflicted.
- **Pinned by:** none — the body names no test by name or path for this rule and refers to section 8.10.13 for its tests.
- **Source:** #385, #496, #534
- **Status:** standing; narrative in [archive/11-l1-9-l1-10-default-removal.md](../archive/11-l1-9-l1-10-default-removal.md#11420-what-the-default-flip-and-the-removal-of-qt-3d-taught-phase-17-l19--l110-385)
- **Legacy:** b1faaa9 README L3157 (legacy 11.4.20)
