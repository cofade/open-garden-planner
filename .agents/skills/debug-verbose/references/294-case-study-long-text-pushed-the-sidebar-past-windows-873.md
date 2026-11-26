## Case study: a long bed name blocked the Windows sidebar (#873, 2026-11-26)

Selecting a bed whose saved name held 1,000,022 characters stalled the window.
Qt attempted sidebar heights above 150,000 pixels. The canvas label already used
a bounded preview, so a canvas-only render did not exercise the failing path.

The native selection trace logged `QLabel.setText length=1000034` from
`CropRotationPanel._display_recommendation`. The same trace recorded a full
1,000,022-character name in `QLineEdit` and 1,000,010 characters in the text
properties editor. Bed selection in that probe took 5.28 s including the wait.

Clip the name before the word-wrapped status label and load only bounded text
into the property editors. Keep the complete stored value as the edit baseline.
Focusing and leaving an untouched preview preserves the record.
In the same probe bed selection took 0.83 s with no oversized geometry warning.
The main-window sidebar case in `tests/integration/test_plan_label_text_bound.py`
pins the bounded height, the untouched values and Undo.
