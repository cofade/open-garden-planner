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


### PF-E3D-10

- **Rule:** Derived lifetime visibility must preserve the existing throttled 3D clock path while real plan edits still announce revisions.
- **Pinned by:** `tests/integration/test_timeline_quick3d.py`
- **Source:** #315, PR #533, ADR-062
- **Status:** standing; narrative in [archive/14-plan-timeline.md](../archive/14-plan-timeline.md)
- **Legacy:** none (new entry)

Ten planting/removal boundary steps produced ten immediate snapshots through ItemVisibleHasChanged. CanvasScene scopes only derived timeline visibility announcements, restoring the scope in finally. The same probe produces zero immediate snapshots and the trailing clock update reaches the final date. See section 8.31 and ADR-062 for the current lifecycle contract.

### PF-E3D-11

- **Rule:** A GUI-heartbeat measurement must include the time from the last tick to the end of the work, and it must run the real event loop, not `processEvents()`.
- **Pinned by:** `tests/integration/test_view3d_sync_controller.py`
- **Source:** #452, ADR-069.
- **Status:** standing
- **Legacy:** none (new entry).

The first heartbeat reading of the sliced read claimed a max gap of 5.65 ms while the
same run took 2.37 s and applied once. The gaps were computed between timer ticks, and
the 2.1 s apply happened after the last tick: the number that mattered was outside the
list. The tail is now part of the distribution, and the same run reads max 8.05 ms once
the geometry lane moved the builders off the GUI thread. A second trap in the same
measurement: driving it with `QApplication.processEvents()` in a loop lets a chain of
posted events drain inside one call, so the slices never yield. The script that owns
this measurement — `scripts/measure_capture_heartbeat.py` — runs a real `QEventLoop`
and appends the tail; the test above pins the behaviour without timing.

### PF-E3D-12

- **Rule:** A quiet timer that fires proves the GUI thread is alive NOW, not that the scene was still for the whole quiet time; a pass after it must wait for a settle in which a repaint can restart the quiet time.
- **Pinned by:** `tests/integration/test_view3d_sync_controller.py::test_a_quiet_timer_that_fired_after_a_blocked_loop_waits_for_a_settle`
- **Source:** #452, ADR-069, ADR-060.
- **Status:** standing
- **Legacy:** none (new entry).

On hosted CI the preview-move gate read 4.6-5.8x Plan while the same test read 1.0 on a
quiet machine. The net was reconciling after quiet timers that fired LATE: the 2D side
held the GUI thread for about a second, the 400 ms quiet time elapsed inside the block,
and the preview's repaint was still queued. Each reconciliation read 424 records (114 ms
on the runner), and slicing that read put its cost into the moves that followed (16 reads
inside 160 measured moves). A timer's expiry is not an idle signal: `NET_SETTLE_MS` waits
50 ms after it, and a repaint in that window restarts the whole quiet time. Probe with a
600 ms block in every tenth preview turn: 4 mid-round reads before, 1 after (the net's
pass once the tool stops).

### PF-E3D-13

- **Rule:** Since Qt 6.12 the engine's pick honours each material's cull mode: a `NoCulling` part is picked from behind too, a culled one only on its front faces (6.11 picked front faces of every material). A selection oracle must keep every face of the two-sided kinds (`materials.TWO_SIDED_KINDS`, pinned against the QML) and the front faces of the rest.
- **Pinned by:** `tests/unit/test_render_measurement_state.py::test_qt612_selection_honours_the_cull_mode_and_the_general_oracle_keeps_both`; `tests/unit/test_quick3d_qml.py::test_the_two_sided_kinds_are_the_components_that_never_cull`; `tests/integration/test_view3d_selection_render.py`
- **Source:** #391 (Phase 17 L7), ADR-048 addendum L7.
- **Status:** standing
- **Legacy:** none (new entry).

`qssgrenderray.cpp` v6.11.0 accepted only positive Moller-Trumbore determinants (its
back-face branch was commented out); v6.12.0 takes the material's `QSSGCullFaceMode` and accepts
either sign for `Disabled`. Foliage, grass and glass are `NoCulling` here. The render tier's
selection test carried a guard that refused to run on any minor but 6.11 ("recharacterize Qt
picking on upgrade") — that guard is what made the change visible; it now names 6.12. The held
oracle file records, per triangle, whether its material draws both sides.

### PF-E3D-14

- **Rule:** A Qt 6.12 `SkyMaterial` compiles its shader only once EVERY texture it samples exists: hand it texture DATA (`QQuick3DTextureData`), never a texture rendered in the frame (`QuadTextureProvider`) — a provider's texture exists only after its first render, so the first frame after the sky appears is white, and a frame rendered only once (the app's offscreen frames) is white every time. A texture input left empty never compiles, and Qt silently draws its built-in debug sky.
- **Pinned by:** `tests/unit/test_quick3d_qml.py::test_the_atmosphere_is_made_once_and_never_destroyed_nor_re_pointed`; `tests/unit/test_quick3d_selftest.py`; `tests/integration/test_view3d_looks_render.py`
- **Source:** #391 (Phase 17 L7), ADR-048 addendum L7.
- **Status:** standing
- **Legacy:** none (new entry).

Qt's skymaterial example renders its two look-up tables with `QuadTextureProvider` every
frame. Ported as is, the atmosphere drew white: `qssgrenderskymaterial.cpp`'s
`skyShaderTexturesReady` defers the compile "since the GLSL sampler type depends on the actual
texture", and nothing reported it — no Qt warning, in any category. A minimal harness
(`SkyMaterial` with no shader, with an inline shader, with ours) told the cases apart: the
debug sky and the inline shader drew, ours drew white on frame 1 and the debug sky after (one
texture input was empty). A second `grabWindow()` on the never-shown offscreen view to "warm
it up" was an access violation — the host's one-offscreen-frame contract stands. The fix
computes the tables in numpy (`core/scene3d/atmosphere_lut.py`) and hands them over as data,
which also made the sky's colour known to Python.

### PF-E3D-15

- **Rule:** A custom material's sky term is compiled when `QSSG_ENABLE_LIGHT_PROBE` is set OR `SAMPLE_PROBE_GLSLLIB` is defined, never on the macro alone: under a Qt 6.12 `SkyMaterial` Qt calls the material's `IBL_PROBE()` and includes the probe samplers while it leaves `QSSG_ENABLE_LIGHT_PROBE` false, so a guard on the macro alone compiles the sky term out and the surface loses the sky's light without a warning.
- **Pinned by:** `tests/unit/test_quick3d_qml.py::test_the_water_samples_the_sky_under_a_sky_material_too`
- **Source:** #391 (Phase 17 L7, `ogp-3d-reviewer` pass), ADR-048 addendum L7.
- **Status:** standing
- **Legacy:** none (new entry).

`water.frag` and `water_door.frag` sampled the sky only `#if QSSG_ENABLE_LIGHT_PROBE`, the
guard L1.2 needed while a scene could have no probe at all. Under the atmosphere sky the pond
went near-black as the sun sank, while the painted sky's pond was fine. Measured on the render
tier's raised pool (`quick3d_render_driver.pond_record`), RTX 4070: water (1, 18, 32) at a 4°
sun against the painted sky's (5, 40, 65); 13 / 75 / 113 against 18 / 85 / 126 at 15°. With
the widened guard the atmosphere's water is within 1.6 codes of the painted sky's at 60°, 15°
and 4°, and the painted sky's frames are identical with either guard. `SAMPLE_PROBE_GLSLLIB`
is the include guard of Qt's `sampleProbe.glsllib`, so it is defined exactly when
`qt_sampleDiffuse` / `qt_sampleGlossy` exist; Qt's own default material reads its probe
through the same include, so it was never affected.

### PF-E3D-16

- **Rule:** On Qt 6.12 destroying an EARLIER sky Texture sets the scene environment's light probe to null although the probe already holds the current sky (the stale destroyed-watcher still fires), so the environment restores its own lightProbe binding in onLightProbeChanged, in the same signal, before any frame renders; a test of the sky must take a frame AFTER the old Textures are deleted.
- **Pinned by:** `tests/unit/test_quick3d_qml.py::test_the_light_probe_is_put_back_when_an_earlier_sky_is_destroyed`; `tests/integration/test_view3d_looks_render.py::test_a_sky_rebuilt_three_times_is_still_the_sky_after_the_old_ones_are_gone`; `tests/integration/test_view3d_looks_render.py::test_the_atmosphere_on_a_live_host_is_the_fresh_hosts_sky`
- **Source:** #391 (Phase 17 L7, found by the render tier after the Qt 6.12 pin), ADR-048 addendum L7.
- **Status:** standing
- **Legacy:** none (new entry).

Every sun change builds a fresh painted-sky Texture and destroys the old one, deferred
(`buildSky`). On Qt 6.12 the frame after that delete showed the clear colour instead of the
sky — on a host's first sun change (the 3D review's run without the fix: the first rebuild, once
also the second; later rebuilds never): the render tier's sky-sequence test read the frame after the old Textures were gone as
(161, 154, 122) flat beige against (97, 126, 137) before. `master`'s own code fails the same way
under the 6.12 wheels and passes under 6.11, so it is the upgrade, not L7's sky. A probe with
two builds told the cases apart: keeping the old Texture alive kept the sky; a counter on the
environment's `lightProbeChanged` read one change to null at the old Texture's delete although
the probe was the new sky; re-assigning the property restored the sky; a re-assign inside the
old Texture's `Component.onDestruction` came too early (the watcher fires after it), and a
zero-interval Timer after it came too late for a frame rendered straight after the delete.
Restoring the binding in `onLightProbeChanged` is synchronous and frame-exact. Qt's
`qquick3dsceneenvironment.cpp` and `attachWatcher` (`qquick3dobject_p.h`) changed only
cosmetically between the tags; the upstream cause is not identified. Fill pictures are re-pointed
and then destroyed too (a recolour): the senior review measured them unaffected on 6.12 (the
recoloured pattern still drawn after the delete rounds). Parts and ground tiles destroy themselves
after detaching. The render tier's live-host atmosphere sequence
(`test_the_atmosphere_on_a_live_host_is_the_fresh_hosts_sky`) fails without the handler in
most runs — 6 of 7 in the senior review's (`painted_160` after the delete: 40.7 against a bound
of 0.5); in the one that passed, that frame's grab took 1.2 ms against ~1,660 ms, so the stale
watcher's firing is timing-dependent: a reproducer for Qt must repeat the sequence.

### PF-E3D-17

- **Rule:** A Qt 6.12.0 `SkyMaterial` never lights the scene and never draws through a cube: Qt builds and pre-filters its cube for image-based light, the Cubemap skybox mode, a reflection probe or a screen texture, and that pre-filter uses a freed QRhi resource and kills the process natively, so the atmosphere backs the view on screen (`enableIBL: false`, a ScreenSpace skybox mode) and the painted sky's texture stays the light probe under both sky models.
- **Pinned by:** `tests/unit/test_quick3d_qml.py::test_the_atmosphere_never_builds_the_cube_that_crashed_qt_6_12_0`; `tests/ui/test_quick3d_host.py::TestSky`
- **Source:** #391 (Phase 17 L7, the owner's manual test of the frozen exe on 2026-11-03), ADR-048 addendum L7.
- **Status:** standing
- **Legacy:** none (new entry).

The owner's frozen exe died about two minutes into testing "Atmosphere with clouds": access
violation `c0000005` in `Qt6Gui.dll`, no Python trace and nothing in `app.log`. Windows had
written a minidump (`%LOCALAPPDATA%\CrashDumps`, because the machine has a `LocalDumps` key).
A stack scan of the faulting thread mapped to the nearest exports read `QSSGRenderer::rhiPrepare`
→ `QSSGLayerRenderData::resolveLayerIblTexture` → `QSSGRenderSkyMaterialManager::resolve` →
`ensureEnvironmentMap` → `runPrefilterCycle`. The faulting function, disassembled from the DLL,
is QRhi's `sanityCheckResourceOwnership`: its warning string is "%s %p (%s) belongs to QRhi %p,
but client code attempted to use it with QRhi %p". It read a resource's owner pointer as
`0x20000000`, so the resource had been freed. The manager deletes its textures at once
(`QSSGRhiContextPrivate::releaseTexture` is a plain `delete`) and detects changes by comparing raw
pointers, so a recycled address can pass its cache check. The exact stale resource is not
identified.

A full-app probe drove the manual checklist's actions on a timer: time of day, weather, walk
mode, reduce motion, the sky model and the layout. Each action was printed before it ran. With one
seed, three of five runs crashed at the same action: a painted to atmosphere switch at night
in snow, right after the weather changed. With the cube off, 0 of 4 runs crashed at that action.
Neither sky switching alone (215 switches) nor the atmosphere without switching crashed in
200 s. After the fix the same seed ran 8 x 240 s with no crash. The painted sky, the default,
never reaches this code.

Three traps when applying the rule. When `lightProbe` is set, Qt does not request the sky
material's IBL pass (`else if (layer.skyMaterial)`), but `SkyMaterialBackgroundPass` still
draws a ScreenSpace sky, so with a probe set the pass that could build the cube never runs.
Without a probe (`sky_probe=False`, or a lost binding) `needCube` decides: `enableIBL`, Cubemap
mode, a `ReflectionProbe`, or a material that needs the screen texture (`SCREEN_TEXTURE`,
`transmissionFactor`) would bring the cube back. The QML test pins that none of them exists.
And the screen path applies no
exposure under our post effects: its main is `qt_tonemap(qt_exposure(FRAGCOLOR, e))`, but
`qt_exposure` is compiled to a pass-through there, while the skybox shader's Custom variant
forces it with `QSSG_FORCE_IBL_EXPOSURE`. So the sky shader applies `1 − exp(−c × e)` itself
(`skyExposed`). Without it the first build of this fix read 1.8× too bright by day and 2.9× at
night with the disc gone, and a plain multiply left 13–14 luma by day. Re-check the rule on every Qt
bump: on 2026-11-03 no QTBUG matched this crash, and Qt 6.12.1 was not on PyPI. The instrument
is `scripts/probe_sky_crash.py`: to ask whether a new Qt fixed it, turn `enableIBL` on and drop
the probe under the atmosphere in a scratch checkout, and run seed 7 several times.

### PF-E3D-18

- **Rule:** A picture beside a shown view comes from a second `View3D` of the same scene (`importScene`, the same camera and environment), read with `grabToImage` driven by one synchronous `grabWindow`; never a `render_records` beside a shown window, never a wait for the window's next frame, and never a `View3D` made and destroyed per picture.
- **Pinned by:** `tests/integration/test_directors_cut_render.py::test_a_capture_at_the_views_size_is_the_view`; `tests/integration/test_directors_cut_render.py::test_another_camera_moves_nothing_on_screen`; `tests/integration/test_view3d_workspace_widget.py::test_the_workspaces_modules_never_ask_a_host_for_a_frame`
- **Source:** #390 (Phase 17 L6), ADR-072 decisions 1 to 4.
- **Status:** standing
- **Legacy:** none (new entry).

`grabToImage` alone waits for the window's next frame, and on Windows the next frame waits for the
display, so with the display asleep it never comes. `grabWindow` needs no display and emits the
signals the item's grab hangs on; then `QCoreApplication.sendPostedEvents(result, 0)` delivers its
completion to that one object, with no nested event loop. Qt multiplies the target size by the
window's ratio again: pass `size / ratio`. A hidden `View3D` keeps its render targets (500 MB after
a 4K picture), and a destroyed one leaves about 20 MB behind each time, linearly on WARP and behind
a plateau on the GPU, whose driver pools hide it. So it stays, and rests after one frame at the
smallest size. A soak on one adapter would have approved the wrong design.

### PF-E3D-19

- **Rule:** With a colour table on, the environment's saturation and contrast are 1 and the table carries them: Qt applies them unclamped right before its table lookup, and that lookup is a `texelFetch` whose column a colour below 0 pushes into the neighbouring slice. Texture DATA for a table runs its rows opposite to a loaded PNG, and a `Texture`'s `flipV` does not reach an effect's sampler.
- **Pinned by:** `tests/integration/test_directors_cut_render.py::test_a_grades_table_is_the_view_through_it_and_turns_nothing_red`; `tests/unit/test_scene3d_photo.py::test_a_table_carries_the_looks_adjustments_exactly_as_qts_shader_does`; `tests/unit/test_scene3d_photo.py::test_as_texture_data_the_rows_run_opposite_to_qts_identity_png`
- **Source:** #390 (Phase 17 L6.1), found by an identity table against the view; ADR-072 decision 6.
- **Status:** standing
- **Legacy:** none (new entry).

The first grades were magenta and green: the strip matched Qt's `identity.png` byte for byte, but
that PNG is flipped on upload (`fixY` in `tonemapper.frag`), and data textures are not; setting
`flipV` changed nothing at all. Then an identity table read mean 0.07, p99 0 and a maximum of 103:
4181 pixels of a 720p frame, all with R = 0 in the view, came out with R up to 57. Saturation 1.06
had taken the darkest leaves below 0 on the red channel, and `ivec2(int(lutSize*b + r), …)` then
read the previous slice's last column, where red is at its maximum. Read the shader out of Qt's
resources (`:/qtquick3d_helpers/shaders/tonemapper.frag`), do not guess it. A related trap in the
same file: `vignetteStrength` is not a strength, a lower value darkens the middle of the picture;
`vignetteRadius` is the exponent that reaches only into the corners; and `vignetteColor` defaults to
grey, which BRIGHTENS whatever is darker: a third of a night's pixels, found by the 3D review after
every daytime test had passed.

### PF-E3D-20

- **Rule:** Frames for Qt's recorder are BT.709 YUV computed by the app, in an HD size: handed RGB it converts with BT.601 and writes no colour tag, and players read an untagged HD stream as BT.709. A test reads a decoded frame's Y, Cb and Cr itself; `QVideoFrame.toImage` guesses the matrix differently by platform.
- **Pinned by:** `tests/integration/test_video_writer.py::test_an_mp4_has_every_frame_the_right_length_and_the_right_colours`; `tests/unit/test_video_yuv.py::test_a_colour_survives_the_round_trip_within_two_levels`; `tests/unit/test_video_yuv.py::test_it_is_the_bt709_matrix_and_not_bt601`
- **Source:** #390 (Phase 17 L6.2), found by reading the first video back; ADR-072 decision 9.
- **Status:** standing
- **Legacy:** none (new entry).

The first encoded test read (200, 60, 30) back as (212, 73, 27), on H.264 and on MPEG-4 alike, while
the frames count, the size and the duration were all right. Nobody compares a promo video with a
colour picker. `QMediaRecorder.errorOccurred` carries an enum PyQt6 cannot connect: use
`errorChanged` and read `error()`. A `QVideoFrame` can be mapped only while the player holds it.

