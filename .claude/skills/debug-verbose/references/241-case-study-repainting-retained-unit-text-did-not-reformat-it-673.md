## Case study: repainting retained text did not reformat it (#673, fixed 2026-11-13)

**Symptom**: the Constraints panel, open vertex-edit coordinates/edges and a
completed measure-tool readout retained metric text after switching to Imperial.

**Wrong theory**: repainting after replacing each formatter would refresh the text.
The labels stored strings, so a paint only drew the same old string again.

**Evidence**: independent real-widget review kept a 243.84 × 121.92 cm rectangle
in vertex-edit mode and a completed 365.76 cm measurement open, then switched.
The visible labels stayed metric. The expanded integration tests failed before
fixing the notification paths, including an actual Constraints row's QLabel.

**Root cause**: the scene refreshed area and dimension labels only; the panel had
no units subscription; completed measurements retained their QGraphicsTextItem.

**Fix**: the scene calls the garden item's retained-measurement refresh; the view
refreshes its active MeasureTool's readout from the original endpoints; the Qt
Constraints panel rebuilds rows while preserving the selected constraint. Plain
tools/items do not connect directly to the global notifier. No geometry or undo
write occurs. `tests/integration/test_unit_system.py::test_retained_vertex_and_measure_labels_refresh_without_edit`
covers rectangles, polygons, polylines and circles; the whole-window workflow
asserts the real Constraints row as well.

**Lesson**: a retained text surface needs a notification path as well as a formatter.
Test already-open overlays, and put Qt subscriptions on objects with a Qt lifetime.
