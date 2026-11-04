## Case study: complete toolbar groups still wrapped to three German rows (US-F4)

**Symptom:** all English layout tests passed at 800 pixels, while the German
native-widget capture put the hidden-plants button alone on a third row.
**Wrong theories:** stale size hints were considered, then rejected by logging
the actual child widths and layout hints before changing layout logic.
**Key log:** `[F4-FLOW] groups=[249,196,321,346,100] sliders=[150,150] width=800`,
with traceback.format_stack() at the unexpected extra-row probe. The first three
groups plus gaps needed 790 pixels; the available content width was 788.
**Root cause:** translated word lengths left a small but real packing deficit;
English sizes were not evidence for German. **Fix:** the adaptive narrow-window
slider width leaves headroom for the measured German controls. Calendar width
remains font-derived; wide windows keep larger sliders. Regression checks cover
both translated languages at 800 pixels; native captures cover EN/DE/ES at wide
and narrow widths, including scaled rendering. No instrumentation remains in
production. **Lesson:** inspect the rendered translated controls and log actual
group geometry before blaming the framework's layout cache.


