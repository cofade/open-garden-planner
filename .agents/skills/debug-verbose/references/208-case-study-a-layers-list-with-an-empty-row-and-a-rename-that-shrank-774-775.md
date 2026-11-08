## Case study: a layers list with an empty row and a rename that shrank its row (#774/#775, fixed 2026-11-08)

**Symptom**: with several layers, the list showed an empty band under the lowest row and the highest layer needed a scroll to be seen, although the panel's scroll box had room. Double-clicking a layer name replaced the label with an editor and the row visibly shrank.

**Theories entertained (wrong)**:
- The list's viewport margins or scrollbar policy were reserving space (they were not; the height was simply too small).
- A stylesheet `padding` on the row was being added twice (the row hint was already the source of truth).

**What instrumentation revealed** (a probe printing the widget and item hints):

```
[LAYERS] item.sizeHint().height() = 32   ← the row the widget asked for
[LAYERS] item row height          = 36   ← the fixed constant the panel used
[LAYERS] list.frameWidth()        = 1    ← never added to the height
[LAYERS] count=6, height=180            ← 5*36 (max five rows), no frame, rows clipped
```

The row's real hint (32 px, 36 after the panel's floor) and the list's frame were both ignored: `count * 36` was smaller than the content it had to show, and the leftover band looked like an empty row. During a rename the `QLineEdit`'s hint is shorter still, so the row shrank under the editor.

**Root cause**: one fixed per-row constant (`36`) used both as the list's height and as the row's implicit height; the inline editor swaps a `QLabel` for a `QLineEdit` whose size hint is smaller.

**Fix** (`ui/panels/layers_panel.py`): `ROW_HEIGHT` names the constant, `LayerListItem` sets it as a minimum height, `_refresh_list` uses `max(row.sizeHint().height(), ROW_HEIGHT)`, and `_adjust_list_height` measures the rows it shows and adds `2 * frameWidth()` — the same fixed height in the "all rows" and "scroll at five" branches. Pinned by `tests/integration/test_layers_panel_height.py`.

**Lesson**: a list's height is a function of its rows and its frame, never of a constant. When a widget can swap a child for another widget, pin the row's height at the widget that owns the row, not at the list that displays it.
