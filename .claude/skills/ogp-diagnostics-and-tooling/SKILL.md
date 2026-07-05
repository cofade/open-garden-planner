---
name: ogp-diagnostics-and-tooling
description: >
  Catalogue of every diagnostic instrument in Open Garden Planner, with
  interpretation guides — how to MEASURE instead of eyeball. Load when you need
  to: verify a claim about behavior, measure what the code actually does, run or
  interpret quality gates (pytest / ruff / bandit / mypy / i18n gate), inspect a
  LIVE running plan via the Agent API (MCP on 127.0.0.1:8765), check
  translations or exports, detect mojibake, trace a geometry bug numerically,
  find when/why something changed in git history, smoke-test the built exe, or
  simply choose the right instrument for an investigation. Also load when a
  pytest run shows "Fatal Python error: Aborted", "passes alone fails together",
  or you're unsure what a gate can and cannot catch.
---

# OGP Diagnostics & Tooling — measure, don't eyeball

All facts verified 2026-07-04 against the working tree at v1.23.0 (commit
`988c565`) by reading the actual files and running what runs without PyQt6
(which is NOT installed in the Claude web container — anything Qt-importing was
read, not run, and is labeled). Paths are repo-relative from
`/home/user/open-garden-planner`.

**Jargon used below (defined once):**
- **Instrument** — anything that produces an objective reading (a test run, a grep, an HTTP query) instead of an opinion.
- **Gate** — an instrument whose failing reading blocks merge (policy lives in `ogp-validation-and-qa`, not here).
- **Mojibake** — UTF-8 text double-encoded via Latin-1, e.g. `ö` → `Ã¶`.
- **SAST** — static application security testing (here: Bandit).
- **MCP** — Model Context Protocol; the app embeds an MCP server so agents can query the live plan.
- **Offscreen/headless** — Qt rendering without a display (`QT_QPA_PLATFORM=offscreen`).
- **Pickaxe** — `git log -S`, which finds commits that change the *count* of occurrences of a string.

## 0. Instrument chooser

| Question you're asking | Instrument | Section |
|---|---|---|
| "Does the code still do X?" | pytest (targeted `-k` / one file) | §1 |
| "Did my change break anything?" | full pytest + ruff + bandit | §1, §2 |
| "Is every UI string translated?" | i18n gate + `TestNoHardcodedEnglish` (know their blind spots) | §1.3 |
| "Is this file's encoding broken?" | mojibake grep / `check_mojibake.sh` | §4 |
| "What is the plan in the RUNNING app doing right now?" | Agent API (MCP tools) | §5 |
| "What does the live canvas LOOK like?" | `render_canvas_image` tool | §5 |
| "Why does this geometry come out wrong?" | headless numeric tracing | §6 |
| "Does the export actually render correctly?" | `validate_exports.py` + `svg_preview.py` (browser, not QSvgRenderer) | §3 |
| "When/why did this behavior change?" | git pickaxe / squash-merge trails | §7 |
| "Does the frozen build even start?" | exe smoke (`timeout 8`, exit 124) | §8 |
| "Is this code pattern insecure?" | bandit | §2 |
| "Is this annotation/type claim true?" | mypy strict | §2 |

## 1. The test suite as an instrument

Layout (counts verified 2026-07-04): `tests/unit/` (105 files), `tests/integration/` (72 files — end-to-end UI workflows, one per feature, mandatory per §8.10), `tests/ui/` (18 files — widget-level). `tests/conftest.py` sets `QT_QPA_PLATFORM=offscreen` itself, adds `src/` to `sys.path`, and isolates `QSettings` to a `cofade_test` store per session. `pyproject.toml` `addopts = "-v --tb=short"`, `qt_api = "pyqt6"`.

```bash
# Windows (the project's canonical form):
venv/Scripts/python.exe -m pytest tests/ -v                     # whole suite
venv/Scripts/python.exe -m pytest tests/integration -v          # one layer
venv/Scripts/python.exe -m pytest tests/unit/test_geometry.py -v          # one file
venv/Scripts/python.exe -m pytest tests/unit/test_i18n.py::TestTranslationFiles::test_german_ts_has_no_unfinished
venv/Scripts/python.exe -m pytest tests/ -k "rotation and resize"         # by keyword
venv/Scripts/python.exe -m pytest tests/ --lf -x                # only last-failed, stop at first
venv/Scripts/python.exe -m pytest tests/unit/test_foo.py --tb=long        # override the short traceback

# Linux/CI form (conftest already forces offscreen, but harmless to be explicit):
QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest tests/ -v
```

`qtbot` is required in every Qt-touching test even if unused (Qt init); ruff per-file ignores `ARG001`/`ARG002` for `tests/**` cover this (`pyproject.toml`).

### 1.1 Reading pytest-qt failures

pytest-qt **captures any exception raised inside a Qt slot and fails the
current test** — even if the exception's origin is a widget from an *earlier*
test that leaked an app-global signal connection. Documented case (§11.4):
`GlobalSearchField`'s `app.focusChanged` slot outliving its widget failed the
unrelated later test `test_harvest.py::TestHarvestNavigation`.

| Reading | Meaning |
|---|---|
| Failure names a slot/widget the test never touches | leaked connection from an earlier test's torn-down widget — suspect app-global signals (`focusChanged`, `aboutToQuit`) |
| `Fatal Python error: Aborted` mid-suite, run stops | **teardown crash**: a `RuntimeError` ("wrapped C/C++ object … deleted") inside a Qt slot, escalated to interpreter abort. Canonical cause (#230, §11.4): a `scene.changed` slot calling `.start()` on a deleted `QTimer`. The *previous* test (one that builds the full `GardenPlannerApp`) is usually the origin, not the test named at the abort |
| Test passes alone, fails in the full run, and every wrong value is exactly a *default* | process-global `QSettings` poison (§11.4 `setDefaultFormat`/`setPath` case) — shared global/singleton state, not the code under test |
| Timing-dependent local pass, reliable CI Linux failure | teardown-order race; same #230 family |

### 1.2 What the i18n gate CAN catch

`tests/unit/test_i18n.py::TestTranslationFiles::test_german_ts_has_no_unfinished`
(verified, line 48): asserts `'type="unfinished"' not in` the German `.ts`
file. Catches: any string that pylupdate6/`fill_translations.py` **registered**
but that has no German translation yet. Run it after every string change.

### 1.3 What the i18n gate CANNOT catch — and its partner

*(This §1.2/1.3 pair is the **canonical home** of the i18n-gate blind-spot fact
— the instrument catalogue owns instrument mechanics. Other skills state it in
one line and point here.)*

It cannot see a string that never reached the `.ts` file at all — hardcoded
English f-strings (`f"{a} overlaps {b}"`) bypass `tr()` and are invisible to
it. That is what `tests/unit/test_i18n.py::TestNoHardcodedEnglish` (verified,
line 143) is for: it greps `src/**/*.py` for a **curated** phrase list
(`SUSPICIOUS_PHRASES` — e.g. `" overlaps "`, `": antagonist"`) and fails if a
phrase sits in a string literal on a line without `tr(`/`QT_TR_NOOP`/
`translate(`. Escapes: `# i18n-source` per-line comment, `ALLOWED_FILES`
(`fill_translations.py`, `test_i18n.py`).

**Its blind spot in turn:** it only knows phrases someone already added after a
leak was observed. A *novel* untranslated string passes both tests. Net: green
on both gates ≠ "fully translated"; it means "no known regression". When you
find a new leak, add the phrase to `SUSPICIOUS_PHRASES`.

## 2. Static analysis

All config verified in `pyproject.toml` (2026-07-04).

```bash
# Windows                                            # Linux
venv/Scripts/python.exe -m ruff check src/           venv/bin/python -m ruff check src/
venv/Scripts/python.exe -m bandit -r src/ --severity-level high
venv/Scripts/python.exe -m mypy src/                 venv/bin/python -m mypy src/
```

- **ruff** — rule families ON: `E`,`W` (pycodestyle), `F` (Pyflakes), `I` (isort, first-party `open_garden_planner`), `B` (bugbear), `C4` (comprehensions), `UP` (pyupgrade), `ARG` (unused args), `SIM` (simplify). Ignored: `E501` (line length — but `line-length = 100` still drives the formatter), `B008`. `tests/**` additionally ignores `ARG001`/`ARG002`. Healthy: `All checks passed!`.
- **bandit** — CI's `security` job fails **only on HIGH severity** (`--severity-level high`); MEDIUM/LOW are printed for awareness (run without the flag to see them). §8.11 documents the known non-findings: the Agent API binds `127.0.0.1` only, so **B104 (bind-all-interfaces) does not apply**, and the pre-bind `socket.bind` port probe is not a high-severity finding. Suppress a true false positive with `# nosec B603 — <justification>`, sparingly. Scope is `src/` only; tests are excluded by design.
- **mypy** — `strict = true` plus explicit `disallow_untyped_defs`, `no_implicit_optional`, `warn_unused_ignores`, etc.; `follow_imports = "silent"`, `ignore_missing_imports = true`; `tests.*` override relaxes `disallow_untyped_defs`. Note: mypy is in the dev extras but is NOT in the CLAUDE.md quick-reference gate list — treat a clean run as extra signal, not a formal gate. (Not runnable in this container; config read, not executed.)

## 3. Project scripts (`scripts/`) — what each really does

All six read in full 2026-07-04. "Stdlib" = runs without PyQt6.

| Script | Needs | What it truthfully does |
|---|---|---|
| `fill_translations.py` | stdlib (xml.etree) | Reads the pylupdate6-generated `open_garden_planner_de.ts`, fills German translations from its own in-file `TRANSLATIONS: dict[context][source] = german` mapping, adds contexts pylupdate6 can't extract (e.g. `Commands` — non-QObject command classes), writes the `.ts` back. **New strings must be added to this dict** or the i18n gate fails. Run with `PYTHONUTF8=1` (Windows defaults to cp1252; without it the umlaut-laden file I/O corrupts). |
| `compile_translations.py` | stdlib | Pure-Python `lrelease` replacement: parses every `.ts` in `resources/translations/`, emits binary `.qm` (Qt magic `0x3CB86418…`, ELF-hash lookup table, UTF-16BE translations). Prints `<name>.ts -> <name>.qm (N messages)` per file; nonzero exit on any compile error. Always run after `fill_translations.py`. |
| `svg_preview.py` | Windows browser or PyQt6 | Renders an SVG to `<file>_preview.png` using **Edge headless** (`--headless=new --screenshot=`; Chrome fallback), falling back to `QSvgRenderer` offscreen only if no browser. WHY browser-first (§11.4): `QSvgGenerator` never serializes painter clip paths, so texture fills bleed across the canvas in real browsers while **QSvgRenderer is too forgiving and hides the bug**. Browser paths are hardcoded Windows paths — on Linux substitute `chromium --headless=new --screenshot=out.png file.svg` (untested here, no browser in container). |
| `validate_exports.py` | PyQt6 | End-to-end export validator template: loads a `.ogp`, prints item/plant counts, exports PNG + SVG + PDF via the real `ExportService`/`PdfReportService`, then renders each PDF page to PNG via `QtPdf` for visual inspection. **Input/output paths are hardcoded to a developer machine** (`C:\Users\wienh\Downloads\...`) — edit `OGP_FILE`/`OUT` before use. Sets `QT_QPA_PLATFORM=offscreen` itself. |
| `generate_plant_svgs.py` | stdlib (math/random) | Regenerates the top-down plant species SVG illustrations (viewBox 0 0 100 100, seeded-random foliage blobs) into `resources/plants/species/`. Deterministic per seed. |
| `generate_textures.py` | PyQt6 | Regenerates the tileable 256 px PNG fill textures in `resources/textures/` with `QPainter`. |

```bash
# The canonical translation refresh (CLAUDE.md quick ref):
PYTHONUTF8=1 venv/Scripts/python.exe scripts/fill_translations.py
PYTHONUTF8=1 venv/Scripts/python.exe scripts/compile_translations.py
# then the gate from §1.2
```

## 4. Mojibake detector

Root cause (§11.4): PowerShell 5.1 `Set-Content -Encoding UTF8` mis-decodes
UTF-8-without-BOM as Latin-1 and re-encodes — `ö`→`Ã¶`, `ä`→`Ã¤`, `ü`→`Ã¼`,
`ß`→`ÃŸ`. One find/replace can mojibake the whole German UI.

```bash
# Single file — any non-zero count means double-encoded:
grep -c "Ã¶\|Ã¤\|Ã¼\|ÃŸ" src/open_garden_planner/resources/translations/open_garden_planner_de.ts

# Whole repo (.ts + .py, capitals included), shipped and tested here:
bash .claude/skills/ogp-diagnostics-and-tooling/scripts/check_mojibake.sh
```

Tested output shapes (actual runs, 2026-07-04):

```text
OK: no mojibake in *.ts/*.py under: /home/user/open-garden-planner     # exit 0
# — or —
MOJIBAKE FOUND (double-encoded UTF-8). Restore with: git checkout HEAD -- <file>
<path>:1:msg = "GrÃ¶ÃŸe Ã¤ndern"
-- 1 offending line(s) --                                              # exit 1
```

The script deliberately scans only `*.ts`/`*.py` — `docs/11-…/README.md`
*quotes* the mojibake sequences when documenting this pitfall and would
false-positive. Recovery is always `git checkout HEAD -- <file>` and redo the
edit with Python/`Edit` tool, never PowerShell. Adjacent instrument: Excel
shows mojibake for correct UTF-8 CSVs without a BOM — CSV writers use
`encoding="utf-8-sig"` (§11.4).

## 5. The Agent API — inspecting a LIVE plan without touching code

With the GUI running, an embedded read-only MCP server (on by default,
loopback only) exposes the open plan at **`http://127.0.0.1:8765/mcp`**
(streamable HTTP, stateless; port = `AppSettings.agent_api_port`, default
8765; Preferences toggle disables). This is the fastest way to observe live
state during a debugging session — no print instrumentation, no restart.

**The 10 tools** (verified against `src/open_garden_planner/agent_api/server.py`, 2026-07-04):

| Tool | Reading it gives you |
|---|---|
| `get_plan_summary` | object counts, canvas size, layers, filename, dirty flag |
| `list_objects(type?, layer?, parent?, raw?)` | top-level objects; `type` accepts ObjectType name, category (`bed`/`plant`/`shape`), or geometry kind |
| `get_object(item_id, raw?)` | full detail for one UUID |
| `objects_in_region(x, y, width, height, raw?)` | bbox-intersecting objects (scene cm) |
| `objects_in(parent_id, raw?)` / `plants_in_bed(bed_id, raw?)` | containment |
| `nearest_objects(x, y, k?, type?, raw?)` | k closest centres to a point |
| `measure_distance(id_a, id_b)` | centre-to-centre distance in cm |
| `get_diagnostics(kind?)` | the plan's **already-computed** canvas warnings (`companion_conflict`, `spacing_overlap`, `soil_mismatch`, `capacity_overrun`, `crop_rotation`) |
| `render_canvas_image(x?, y?, width?, height?, layers?, image_width_px?)` | PNG of the live canvas + `RenderMeta` |

Debugging patterns:
- **Verify geometry claims**: `measure_distance` / `nearest_objects` give you the app's own numbers for "these plants are 32 cm apart" — compare against what a badge or your code claims. Coordinates are the raw native scene frame in cm (the nominal Qt "origin top-left, +y down" labeling; the data path consumes these numbers directly as CAD Y-up — see `ogp-qt-cad-reference` §1, the Y-axis owner).
- **`get_diagnostics` is a mirror, not an oracle**: it harvests the badge flags the app already computed (may lag a debounce tick; positive states like spacing `"ideal"` are not reported). If `get_diagnostics` disagrees with the canvas badges, THAT disagreement is the bug.
- **`raw=True`** on the object tools returns the underlying `.ogp` serializer dicts — use it to see exactly what would be saved.
- **`render_canvas_image` pixel-Y is FLIPPED** vs the raw scene numbers (`y_flip=True` for parity with the CAD view). The canonical formula and its derivation live in **`ogp-qt-cad-reference` §1** (the Y-axis owner); inline for convenience: `px_x = (x_cm - region_x_cm) * px_per_cm`; `px_y = image_height_px - (y_cm - region_y_cm) * px_per_cm` (from `RenderMeta.px_per_cm`, pinned by `tests/unit/test_agent_api_render_coordinate_frame.py`). `layers` is a full override — a layer the user toggled off is shown anyway if requested; original visibility is restored after.

Access from this container / any shell (stdlib probe, shipped and tested here
against a mock SSE server — the live-app path could not be exercised in this
container since PyQt6 is absent):

```bash
python3 .claude/skills/ogp-diagnostics-and-tooling/scripts/probe_agent_api.py            # lists tools
python3 .claude/skills/ogp-diagnostics-and-tooling/scripts/probe_agent_api.py \
    --call nearest_objects --args '{"x":100,"y":200,"k":3}'
# exit 3 + "CANNOT CONNECT ... Is the app running?" = app not running / API disabled / wrong port
```

Or register it with an MCP client (UNVERIFIED here — no live app in container):
`claude mcp add --transport http ogp http://127.0.0.1:8765/mcp`. Note
`render_canvas_image` has no `structuredContent` (its `RenderMeta` arrives as a
JSON `TextContent` block — parse that). The server is read-only; write tools
are gated on token auth (§8.11/§8.19).

## 6. Headless numeric tracing for geometry bugs

The instrument that cracked #218 (rotated-circle resize drift): don't stare at
the canvas — **drive the scene headlessly and print the numbers per step**.
The worked, checked-in pattern is
`tests/integration/test_rotation_aware_resize.py`:

- Build `CanvasScene(width_cm=8000, height_cm=6000)` + `CanvasView`, `qtbot.addWidget(view)`, `view.set_snap_enabled(False)`.
- Seed the drag state exactly as `mousePressEvent` does, then call the real `ResizeHandle._apply_resize(delta)` once per simulated mouse-move.
- After each step, read `item.rect()`, `item.pos()`, `item.transformOriginPoint()`, the mapped scene centre — and assert (or print) them. The parametrization that exposed the bug: angles `[0, 45, 215]` × handles `{corner, h-edge, v-edge}` × shapes `{circle, rect, ellipse}` — 45° is where scene-frame vs rotated-frame confusion shows up.

For a throwaway trace outside pytest, `scripts/validate_exports.py` is the
loader template (offscreen `QApplication`, `ProjectManager.load`, iterate
items, print positions). For instrumenting a **live interactive** run with
`[TAG]`-prefixed prints and `traceback.format_stack()` at unexpected-call
sites, use the existing `debug-verbose` skill instead — that's its job.

## 7. Git archaeology — when did behavior change?

Squash-merge discipline means **every PR is exactly one commit on master**,
titled `type(scope): Description (#NNN)`, usually followed by a
`chore: sync version to vX.Y.Z after ... PR #NNN` commit (format verified in
`git log`, e.g. `feat(US-D1.3): Agent API vision tool (render_canvas_image) (#242)`).
Consequences: `git show <commit>` displays the *entire* PR diff, and version
tags map 1:1 to PRs via the paired chore commit.

```bash
git log -S "effective_spacing_radius" --oneline        # pickaxe: commits changing the COUNT of a string
git log -G "def _apply_resize" --oneline               # regex against diff content (catches moves too)
git log --oneline -- src/open_garden_planner/ui/canvas/items/resize_handle.py   # file history
git log --follow --oneline -- <renamed-file>           # survive renames
git log --oneline --grep "#218"                        # find the PR trail for an issue
git blame -L 40,60 <file>                              # who last touched these lines
git show 5e6a267 --stat                                # whole-PR diff summary
gh pr view 242 --json title,body                       # PR body = the design discussion (needs gh auth)
```

`-S` vs `-G`: `-S` misses a line that merely *moved* (count unchanged); `-G`
matches any diff line, so use `-G` when hunting refactors and `-S` when
hunting introductions/removals. Deeper context per incident lives in
`ogp-failure-archaeology`.

## 8. Exe smoke instrument (Windows only)

```bash
venv/Scripts/python.exe -m PyInstaller installer/ogp.spec --noconfirm
timeout 8 dist/OpenGardenPlanner/OpenGardenPlanner.exe
echo $?
```

Exit **124** (killed by `timeout` after 8 s) = the frozen app was still alive
and running = **healthy**. Any prompt exit is unhealthy: nonzero-fast = crash
at startup (classic cause: a module PyInstaller didn't collect — the
`mcp`/`uvicorn` stack needs `collect_submodules` + `copy_metadata` in
`ogp.spec`, §8.19); exit 0 before the timeout = the app quit by itself =
equally suspicious; **127** = the exe doesn't exist (build failed/not run).
Not runnable in this container (no Windows, no `dist/`). Build mechanics:
`ogp-build-and-run`.

## 9. Interpretation table — instrument → healthy → unhealthy

| Instrument | Healthy reading | Unhealthy readings → implication |
|---|---|---|
| `pytest tests/ -v` | all pass, run completes | one red test → read its assert; `Fatal Python error: Aborted` → teardown QTimer/slot crash, suspect the *previous* full-app test (§1.1); fails-together-passes-alone with default values → QSettings global poison |
| i18n gate (§1.2) | passes | fails → a registered string lacks German: add to `fill_translations.py` dict, re-run both scripts |
| `TestNoHardcodedEnglish` | passes | fails → a known-leak phrase is in a string literal outside `tr()` — wrap it (green here still ≠ fully translated, §1.3) |
| `ruff check src/` | `All checks passed!` | findings list → fix; never blanket-disable a family |
| `bandit -r src/ --severity-level high` | `No issues identified.` | HIGH finding → real gate failure; MEDIUM/LOW (no flag) → awareness only; B104 on the Agent API bind → known non-issue, it's loopback-only |
| `mypy src/` | no errors | errors → type drift; not a formal CI gate, still worth fixing |
| `compile_translations.py` | `... -> ....qm (N messages)` per file, exit 0 | `ERROR compiling ...` → malformed `.ts` (often a hand-edit; check mojibake next) |
| `check_mojibake.sh` | `OK: no mojibake...`, exit 0 | exit 1 + file:line list → file is double-encoded; `git checkout HEAD -- <file>`, redo edit without PowerShell |
| Agent API probe | tool list / JSON result, exit 0 | exit 3 → app not running, API disabled in Preferences, or port ≠ 8765; exit 4 → server up but request malformed (check tool name/args) |
| `get_diagnostics` vs canvas | matches the badges | mismatch → the harvest/badge pipeline is the bug (or you're one debounce tick early) |
| `render_canvas_image` sanity | known object appears where the §5 formula predicts | object at mirrored height → you forgot the pixel-Y flip, not a render bug |
| numeric trace (§6) | radii/centres invariant where they should be | centre drifts across steps → pivot/`transformOriginPoint` bug; value snaps at 45° → scene-frame vs rotated-frame confusion |
| exe smoke | exit 124 | fast nonzero → frozen import crash; fast 0 → app self-exited; 127 → no exe |
| `git log -S` | pinpoints the introducing PR commit | no hits but you know it changed → line moved not added; retry with `-G` |

## 10. When NOT to use this skill

- **You have a bug and want a step-by-step diagnosis path** → `ogp-debugging-playbook` (this skill tells you what each instrument reads, not which to reach for in what order of triage).
- **You want to print-instrument a live interactive run** → the `debug-verbose` skill (owns the `[TAG]`/`format_stack` methodology and its case studies).
- **You're deciding whether a reading passes or blocks a merge** → `ogp-validation-and-qa` (pass/fail policy) and `ogp-change-control` (gates & workflow).
- **The build itself won't produce an exe / app won't launch from source** → `ogp-build-and-run`.
- **You need the historical WHY behind a failure mode** → `ogp-failure-archaeology`; architecture invariants → `ogp-architecture-contract`; Qt/CAD concepts behind the numbers → `ogp-qt-cad-reference`; domain semantics of a diagnostic (companion/rotation rules) → `ogp-garden-domain-reference`; settings/flags being measured → `ogp-config-and-flags`; statistical/analysis method on top of readings → `ogp-proof-and-analysis-toolkit`.

## Provenance and maintenance

Verified 2026-07-04 in the Claude web container (Linux, Python 3.11.15, PyQt6 absent). Re-verify each volatile fact with one line:

- i18n gate + hardcoded-English test still exist: `grep -n "test_german_ts_has_no_unfinished\|class TestNoHardcodedEnglish" tests/unit/test_i18n.py`
- ruff/mypy/pytest config: `grep -n "select\|strict\|addopts" pyproject.toml`
- Agent API tool set + port: `grep -c '^    @mcp.tool' src/open_garden_planner/agent_api/server.py` → expect `10` (a bare `grep -c "@mcp.tool"` reads 11 — the module docstring mentions the decorator); default port: `grep -n DEFAULT_AGENT_API_PORT src/open_garden_planner/app/settings.py` → 8765
- pixel-Y formula: `grep -n "px_y" docs/08-crosscutting-concepts/README.md`
- scripts inventory: `ls scripts/`
- bandit stance & known non-findings: `grep -n "8.11\|B104" docs/08-crosscutting-concepts/README.md`
- mojibake pitfall + teardown-crash pitfall: `grep -n "Set-Content\|Fatal Python error" docs/11-risks-and-technical-debt/README.md`
- squash-trail format: `git log --oneline -5`
- test-layer counts: `ls tests/unit/test_*.py tests/integration/test_*.py tests/ui/test_*.py | wc -l`
- shipped helpers still work: `bash .claude/skills/ogp-diagnostics-and-tooling/scripts/check_mojibake.sh && python3 .claude/skills/ogp-diagnostics-and-tooling/scripts/probe_agent_api.py --port 1; echo $?` (expect `OK...` then exit 3)
