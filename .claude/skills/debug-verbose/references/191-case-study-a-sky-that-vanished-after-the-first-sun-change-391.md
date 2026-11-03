## Case study: a sky that vanished after the first sun change (#391)

- **Symptom:** after the Qt 6.12 pin, the render tier's sky-sequence test failed: the frame taken
  after the old sky Textures were deleted showed a flat beige (the clear colour) instead of the
  painted sky. Every board gate was green — the board renders a fresh host per frame, one sky
  each. In the app it would have hit the DEFAULT sky after the first sun change.
- **Wrong theories:** a uint8 wrap-around in the test's difference (the signed means moved from
  (97, 126, 137) to (161, 154, 122): a real change); L7's new background-mode binding (`master`'s
  code failed identically on the 6.12 wheels and passed on 6.11); a change to
  `QQuick3DSceneEnvironment::setLightProbe` or `attachWatcher` (both only cosmetic between the
  tags).
- **Key evidence:** a two-build probe on the shown host, each variant a scratch copy of
  `Garden.qml` through `--qml-dir`: keeping the old Texture alive kept the sky; a counter on the
  environment's `lightProbeChanged` read one change to null at the old Texture's delete; a direct
  re-assign restored the sky. A re-assign in the old Texture's `Component.onDestruction` ran
  (`reasserts=1`) and did nothing — the watcher fires after it; a 0 ms Timer fired after the
  frame that the test grabbed. `[SKYPROBE] after pump (A destroyed): probeChanges=3 probeNulls=1`.
- **Root cause:** on 6.12 the destroyed-watcher of a Texture the environment held EARLIER still
  fires and sets the light probe to null, although the probe has moved on to the current sky.
  The upstream cause is not identified.
- **Fix:** the environment restores its own binding in `onLightProbeChanged` — synchronous, so no
  frame renders without the sky (PF-E3D-16).
- **Lesson:** after a framework upgrade, run the tests that exercise LIFETIME (rebuild, delete,
  re-frame) on the new version before trusting any one-frame gate; and when a fix depends on
  WHEN a callback runs, count the callbacks and read the frame right after them — "it ran" and
  "it ran in time" are different facts.
