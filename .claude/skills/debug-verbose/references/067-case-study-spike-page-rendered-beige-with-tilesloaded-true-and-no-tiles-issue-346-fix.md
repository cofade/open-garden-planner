## Case study: spike page rendered beige with `tilesloaded=true` and no tiles (Issue #346, fixed 2026-09-01)

**Symptom.** The first map spike inside QtWebEngine painted the Google beige background (`#e8eaed`) everywhere, `tilesloaded` fired, yet the DOM held one `<img>` and `map.getCenter()` returned undefined.

**Wrong theories.** WebGL context failure (proved alive), CSP blocking the tile domain, missing `LocalContentCanAccessRemoteUrls`, an EEA-side tile ban on this project, and a QtWebEngine 6.10.2 rendering bug were each plausible — the last two would have killed the whole feature design.

**Key evidence.** After fixing a self-inflicted nested-`<script>` splice (the first "fix" broke the page worse), the map rendered normally: 58 `<img>`s, 20 tile images, `fetchStatus 200`, WebGL fine, maps `3.65.12f`. The beige run had been a genuinely broken page state, not an engine restriction.

**Root cause.** Harness page bugs (broken script structure) — compounded by an earlier probe that printed tile URLs with the API key embedded (the key lives in every `/maps/vt` URL's query string), which then demanded sanitization discipline across the spike.

**Lesson.** When a WebEngine map shows Google's beige with `tilesloaded`, suspect the page's own script/CSP state before suspecting the engine — and never print or log DOM-derived URLs from a Google page: they carry the credential. The clean probe also became the §11.4 rule: pixels leave the map only via the widget grab; metadata only via the bridge.

