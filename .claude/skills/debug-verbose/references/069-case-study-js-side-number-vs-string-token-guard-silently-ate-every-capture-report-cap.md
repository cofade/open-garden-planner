## Case study: JS-side number-vs-string token guard silently ate every capture report — "capture times out" with all tests green (Issue #347, fixed 2026-09-02)

**Symptom**: First manual test of the shipped pan-grid view capture: Capture view → after ~20 s a box appeared: "The capture timed out. Check your network or the API key, then try again." — while the map was plainly healthy. All 109 automated tests were green, including the bridge-contract drift guard.

**Wrong theories**:
- Stale QtWebEngine cache serving the old single-frame HTML (new page functions `beginCaptureChrome` etc. undefined → silent `runJavaScript` → watchdog). Disproved: a live API probe printed `{"chrome":"function","frames":"function","map":"object","zoom":18}` — the new page was live.
- Tiles never finishing / `tilesloaded` never firing (the settle would then force-report via its grace timer — and no report arrived at all).
- A JS runtime error in the report path (would have returned `'error: …'` through the `runJavaScript` callback — Python logged `result='ok'`).

**Key log lines** (live harness driving the real dialog + real key + real page, timestamps elided):
```
[CAPTURE] js_result result='ok' gen=1        <- beginCaptureChrome RAN and returned ok
[CAPTURE] failure msg='The capture timed out...'   <- 20 s later, watchdog; NO 'ready' ever arrived
```
So the page accepted the call but its readiness report never crossed the bridge — a guard between the two ate it.

**Root cause**: `map_picker.html` stored the capture generation token as received and later compared it with a stringified echo: `captureState = { token: token, ... }` then `if (!captureState || captureState.token !== String(token)) return;`. Python drives the page with hand-built JS literals — `window.beginCaptureChrome(1)` — so `captureState.token` was the **number** `1`, `String(token)` the **string** `'1'`, and `1 !== '1'` is **always true**. Every capture report (profile frame -1, per-frame ready) died inside that guard; the dialog's 20 s watchdog produced the timeout box. The same bug lay latent in `beginCaptureFrames`' entry guard. Automated tests can't see it: they drive the QtWebEngine-free bridge in-process and never execute the page's JavaScript; the contract drift guard only greps the HTML text, never executes the page's JS.

**Fix**: stringify at storage — `captureState = { token: String(token), ... }` — making the echo comparison string-vs-string (and the same shape in `beginCaptureFrames`). The `TestBridgeContract` drift guard now additionally pins `token: String(token)` in the HTML so the coercion contract can't regress silently. Verified by the live harness: profile -> 3x1 frame settles -> stitch completes (`tile_grid=(1, 3)`). The harness now lives in the repo as `scripts/live_capture_harness.py`.

**Lesson**: (a) Any page-side guard comparing a value echoed from Python must stringify BOTH operands (or store it stringified) — Python hand-builds JS literals, and `1 !== '1'` is a silent always-false guard. This is the second #346/#347 case where **only a live run exercises the page's JavaScript**; pytest-bridge tests and name-grep drift guards are necessary but not sufficient — keep a real-key live harness in the repo and run it before shipping any page choreography change. (b) When "silence" is the symptom (OK returned, nothing after), look for a guard between the OK and the report, and probe the page state directly (`typeof window.fn`, `typeof map`) instead of trusting the cached bundle.

