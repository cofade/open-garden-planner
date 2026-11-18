# Native selection repaint comparison (#879)

- **Symptom** — Native partial and full repaints differed around selected handles. The shed-to-glasshouse conversion had the largest reported difference.
- **Initially plausible** — A difference appearing after a full repaint always means stale canvas pixels.
- **Evidence** — An 80 ms undo capture differed by 810 pixels, all inside the minimap. After its timer settled, the same seven edits matched on v1.40.8. On #838, three edits still differed by four one-level pixels at a handle. A second full frame matched the first.
- **Cause and fix** — The first comparison sampled two thumbnail generations. Compare crops of the owning window after ordinary scene work and minimap painting settle. Keep a second full frame as a repeatability control. The test also records ordinary paint regions.
- **Pinned by** — `tests/integration/test_canvas_native_pixels.py`.
