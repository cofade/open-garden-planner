## Case study: canvas preview invalidated the snap index (#847, #848, #877, #878)

**Symptom:** An 853-object plan paid for a whole-plan snap-index rebuild at
each rectangle-drag move; minimap refreshes also discarded live item pictures.
Partial paints after a grid edit never established a new kept layer.

**Wrong theories:** Rebuilding grid covers or label layouts explained neither
the rectangle cost with those features off nor the unchanged paint revision.
Treating every `scene.render` as an export was unnecessary for a thumbnail.

**Key evidence:** A tagged wrapper around `PointSnapper.update_scene`, with
`traceback.format_stack`, showed the view's move dispatcher as the caller:
`[SNAP-BUILD] rebuilds during ten hovers [16456, ...]` (ten entries during the
drag). cProfile assigned 716 ms of 731 ms of input dispatch to `_ensure_snap_index`.
After stamping by paint revision: `[SNAP-BUILD] rebuilds during ten hovers []`,
ten input dispatches 10 ms (Qt 6.12.0, Windows, 2026-11-15). Event-loop painting
was outside those input timings and remained costly; #919 tracks scene queries.

**Root cause:** Qt's generic `changed` invalidated snapping for preview items
that cannot be snap targets. The minimap explicitly toggled cache modes even
though Qt preserves separate device pictures. The grid required a full paint
before rebuilding, so a sequence of partial paints stayed uncached.

**Fix and lesson:** Reuse the shared paint revision, compare it synchronously
at query time, keep cache modes for thumbnails, and rebuild the grid on its
first nonempty paint. Keep up to four exact pan phases within one 64 MB bound.
Polylines share the existing polygon paint threshold; selection and exports
retain geometry and full detail. Tests must paint below a window header and
capture that window; a viewport grab erases the offset. The minimap frame test
must start inside the plan: a pan from x=-400 to x=-200 still clips to zero,
which was the combined-run failure after the implementation tests.

Pinned by `tests/integration/test_canvas_repaint_package.py`,
`tests/integration/test_embedded_canvas_paint.py`, the parametrized sharpness
fixture, and `tests/unit/test_minimap_widget.py`. See §8.37 and PF-CAN-63.

**Review finding:** Keeping cache modes sent a capped thumbnail through the
shadow overlay's live zoom path: the new controller-backed test observed
`_pending = (0.1775, 0, 0, 0.1775)` after the minimap render, previously None.
The overlay now reads the existing capped-render scope and paints exactly
without changing its live stand-in or settle state. The regression was
observed failing before the fix in `test_sun_overlay_cache.py`.

**Test mutation control:** The first selected sprite was 1012 device pixels
wide, just below the 1024-pixel exposed-layer threshold; it could not detect
the old offset defect. A fixed-id tree of radius 260 cm at 200% covers 1196
pixels and paints uncached into the backing store. The corrected test passes
with current bounds and fails with the original zero-offset bounds (226-level
lower-strip difference). Choose a specimen past the actual branch threshold.

**Full-suite control:** The crafted 20,000-point string-light layout test
rendered with a live device cache and expected one full layout walk. The new
interactive outline intentionally makes zero walks. Explicitly disable its
cache, as the full-detail export seam does, so the test still proves that two
full paints share one bounded layout and a moved vertex invalidates it.
