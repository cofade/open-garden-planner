# 6. Runtime View

## Explicit sun evaluation and document replacement (ADR-056)

```mermaid
sequenceDiagram
    participant U as User
    participant A as Application / SimClock
    participant H as Heatmap controller
    participant W as Worker
    participant C as Sun coordinator
    participant D as Shared Diagnostics / MCP
    U->>A: Optional 21 June shortcut
    U->>H: Hours of Sun
    H->>W: Immutable document snapshot + receivers
    W-->>H: Grid and own-shadow-excluded receiver minutes
    H->>H: Check generation and complete signature
    H-->>C: Exposure changed
    C->>D: Cached mismatch / unavailable records
    U->>A: Move caster or edit geometry
    A-->>C: Scene or command change
    C->>H: Invalidate within 60 ms (keep visual snapshot)
    C->>D: Clear warnings; publish unavailable state
    U->>A: New / validated Open / recovery / agent lifecycle
    A->>H: document_replaced before item teardown
    H->>W: Cancel; retain ownership until finished
    H->>H: Clear overlay and cached results
    W-->>H: Possible queued old success
    H->>H: Reject unwanted / old-generation result
```

Prevalidation load failure emits no document replacement and preserves the active valid result. Time-only changes preserve daily exposure; date changes clear it. Diagnostics and canopy reads never launch a worker.

## 6.1 Drawing Workflow

```mermaid
flowchart TD
    A([User selects tool<br/>e.g. Rectangle Tool])
    A1[ToolManager activates RectangleTool]
    A2[Canvas cursor changes to crosshair]
    B([User clicks first point on canvas])
    B1[Tool captures start coordinate<br/>scene coords]
    B2[Preview rectangle drawn<br/>rubber band]
    C([User clicks second point<br/>or drags])
    C1[Tool calculates final geometry]
    C2[Creates AddObjectCommand<br/>with Rectangle data]
    C3[Command pushed to UndoStack]
    C4[Command.execute creates<br/>RectangleItem in scene]
    C5[Scene emits objectAdded signal]
    C6[Properties panel updates<br/>if auto-select enabled]

    A --> A1 --> A2 --> B
    B --> B1 --> B2 --> C
    C --> C1 --> C2 --> C3 --> C4 --> C5 --> C6
```

## 6.2 Save/Load Flow

### Save

```mermaid
flowchart TD
    S0([User triggers Save<br/>Ctrl+S])
    S1[ProjectManager.save]
    S2[Serialize all scene objects to JSON]
    S3["Include: layers, objects, metadata,<br/>background images (base64)"]
    S4[Write to .ogp file<br/>atomic write via temp file]
    S5[Status bar shows 'Saved']

    S0 --> S1 --> S2 --> S3 --> S4 --> S5
```

### Load

```mermaid
flowchart TD
    L0([User opens .ogp file])
    L1[ProjectManager.load]
    L2[Parse JSON, validate version]
    L3[Clear current scene]
    L4[Reconstruct layers]
    L5[Reconstruct objects<br/>create QGraphicsItems]
    L6[Reconstruct background images]
    L7[Fit view to content]
    L8[UndoStack cleared<br/>fresh session]

    L0 --> L1 --> L2 --> L3 --> L4 --> L5 --> L6 --> L7 --> L8
```

## 6.3 Plant API Integration Flow

```mermaid
flowchart TD
    Start([User searches for plant species])
    Custom{Custom library<br/>has any matches?}
    Trefle{Trefle.io<br/>returned results?}
    Perenual{Perenual<br/>returned results?}
    Perma{Permapeople<br/>returned results?}
    Bundled{{Found in bundled DB?<br/><i>not yet implemented</i>}}
    Return([Return combined<br/>search results])
    Confirm{User confirms<br/>a result?}
    Detail[Fetch full detail record<br/>via get_by_id per provider]
    Assign([Assign to plant])

    Start --> Custom
    Custom -->|limit reached, stop| Return
    Custom -->|room left| Trefle
    Trefle -->|yes| Return
    Trefle -->|no| Perenual
    Perenual -->|yes| Return
    Perenual -->|no| Perma
    Perma -->|yes| Return
    Perma -->|no| Bundled
    Bundled --> Return
    Return --> Confirm
    Cancelled([Dialog closed,<br/>no plant assigned])
    Confirm -->|cancel| Cancelled
    Confirm -->|yes| Detail
    Detail --> Assign
```

**Custom library first, then Trefle → Perenual → Permapeople (issue #297,
corrected 2026-08-10):** `PlantAPIManager.search()` always searches the
user's local custom-plant library first (the `Custom` node) -- if it alone
meets the result limit, the search stops right there with no API call at
all; otherwise each provider is tried in order and the first to return any
results wins, with results concatenated onto whatever the custom library
already contributed. **Custom-library results are never deduplicated against
API results** -- a stale or bogus custom entry sharing a name with a real
species is returned (and, before this fix, displayed identically) alongside
it; every result row in `PlantSearchDialog` now carries a visible
data-source label (`plant_source_label()`, shared with the properties
panel) so the two can be told apart. See the #297 update in
`docs/11-risks-and-technical-debt/README.md` §11.4 for the incident this
corrected. The `Bundled` branch predates this fix and remains aspirational --
see `manager.py`'s `# TODO: Add bundled database client` and the #296 entry
in the same §11.4.

**Search vs. detail data (issue #297):** `search()` results (the `Return`
node above) are sparse for most providers -- Trefle's in particular omits
`growth`/`specifications`/`foliage` entirely, leaving sun/water/pH/nutrient/
foliage at UNKNOWN/None. `PlantSearchDialog` fetches the richer per-species
record via `PlantAPIManager.get_by_id()` only once the user **confirms** a
result (the `Confirm`/`Detail` nodes) -- not per browsed row, to avoid one
extra request per visible search result against rate-limited free tiers. A
failed detail fetch falls back to the sparse result rather than blocking the
assignment -- **quietly** (no warning) when the provider signals "no richer
detail exists for this record" (Perenual's free-tier paywall, or a Trefle
record with a null `main_species`), **with a user-facing warning** for a
genuine failure, so a real error can't silently reproduce #297's own
symptom. A successful fetch is **merged** onto the search result (a generic
field-by-field overlay: the detail response's value wins unless it's at the
field's default or `None`) rather than swapped in wholesale. The `Confirm
-->|yes| Detail` edge is simplified: a result whose `data_source` isn't one
of the three online providers (`custom`, or a future `bundled`) skips the
fetch entirely, since neither has an online detail endpoint.

### 6.3.1 Satellite Background Loading

The File → Load Satellite Background… path resolves its credential at the application boundary: a non-empty Preferences value (`api_keys/google_maps_key`) wins, otherwise `OGP_GOOGLE_MAPS_KEY` from the process environment is used. `main.py` supports the project-root `.env` in source runs and an adjacent `.env` in packaged runs. The menu action is enabled from this same resolver and is refreshed after Preferences is accepted. When the dialog opens, the resolved key is passed explicitly to the JavaScript bridge and the background fetch worker; it is never part of the project snapshot or serialized image metadata.

While the Static Maps request is in flight, closing or rejecting the picker requests worker interruption and leaves the dialog alive until the worker's terminal signal has been processed; the GUI thread never joins a network-bound worker. The main window also tracks the modal picker so application shutdown follows the same asynchronous path. Unexpected worker failures stay generic in the dialog, while a traceback scrubbed of the resolved key is written to the module logger for diagnosis.

When the Static worker fails with a classifiable EEA 403 (issue #346), the dialog offers the **JS-API view capture** path; a “Capture view” button also makes it available at any time with a drawn rectangle. Capture is a GUI-thread choreography with no worker (issues #346/#347): Python picks the best integer zoom + pan grid (`pick_capture_zoom_and_grid`, 0.85 viewport margin, 3×3 cap) and drives a two-phase page choreography. Phase 1 (`window.beginCaptureChrome` → hides toolbar/hint, `disableDefaultUI`, hides Google's attribution element for the capture only) reports the **capture profile** through the bridge (`captureReady(token, −1, dpr, cssW, cssH)` — frame index −1), pinning the real viewport + dpr. Phase 2 (`window.beginCaptureFrames` with the derived frame centres) settles one frame at a time (`setCenter`+`setZoom`, wait for `idle` + `tilesloaded`, 15 s JS timeout); the page reports readiness per frame (`captureReady(token, i, z, dpr, cssW, cssH)`, token first — the echo of the capture generation) and Python grabs the `QWebEngineView` widget — metadata crosses the bridge, pixels never do. Each grab is blank-checked (per-cell luminance analysis — a partial tile strip counts as a failure) and retried up to `FRAME_RETRIES = 2` (`retryCaptureFrame`); a mid-capture window resize is refused; the frame-0 grab is additionally ruler-gated against the profile dpr (`layout.dpr`) — the value the mosaic geometry and result scale are actually built from — so a falsy profile report or a cross-monitor DPI change between profile and first frame is refused, never silently mis-scaled. After the last frame the grabs are stitched (`stitch_frames` — whole css-pixel steps, integer grabbed-pixel paste offsets, seam-free by construction), the mosaic is cropped to the bbox through the same `crop_image_to_bbox` seam the Static path uses, exactly one attribution strip is baked (`bake_attribution`), and the result flows to the application as a standard `FetchResult` with `tile_grid=(cols, rows)`, `source="google_js_view_capture"` and `attribution`; `BackgroundImageItem.from_fetch_result` persists both as additive `geo_metadata` keys. The single-frame flow is the same choreography with a 1×1 grid. A 20 s Python watchdog (re-armed at every choreography step) and the generation counter guard against a lost page/bridge.

## 6.3.2 Agent API reads/writes: layers, shapes, geometry, and history

```mermaid
sequenceDiagram
    participant A as MCP client
    participant S as Agent API server thread
    participant B as MainThreadBridge
    participant Q as Qt main thread
    participant U as Undo stack

    A->>S: get_geometry / create_object / geometry write / history
    S->>S: authenticate write calls (get_geometry reads stay open)
    S->>B: run_on_main(provider)
    B->>Q: queued callable
    Q->>Q: inspect live Qt state or validate + load
    Q->>U: execute one existing command (or pop/push one)
    U-->>Q: result / undo metadata
    Q-->>B: GeometryResult or WriteResult / HistoryResult
    B-->>S: result or exception
    S-->>A: curated schema / tool error
```

Layer reads are unauthenticated and expose stable UUIDs. Layer mutations use
the existing command classes, so moving an object or deleting a layer is one
undo step and undo restores the original layer assignment. Switching the
active layer is session state and has no undo entry. `create_object` validates
the shape family off the Qt thread, then invokes the loader's
`_deserialize_item_core` on the Qt thread and submits the item to the same
creation command used by the GUI. A `HOUSE` also receives its linked ridge in
the same `CreateItemsCommand`; a following Ctrl+Z removes both. Plant
parenting and active-layer assignment happen inside that same create operation.
The authenticated `undo`/`redo` tools use the same `CommandManager` as the GUI:
one call pops or reapplies exactly one command, returns the command description
and post-call stack state, and refuses an empty stack explicitly. Project load
uses a centralized serialized-document-item predicate, so a same-scene reload
cannot retain a stale callout/curve while compare and dimension overlays keep
their own cleanup owners.

For D2.6, `get_geometry` takes the same main-thread hop but performs no command:
it resolves the live item, maps current vertices/curve points through
`mapToScene`, and returns the constraint graph records that reference it. The
absolute-position and vertex writes validate on that same main-thread provider
before touching `CommandManager`. `set_object_position` converts the requested
centre to a delta and enters the complete move orchestration; vertex writes build
the canonical `MoveVertexCommand`/`AddVertexCommand`/`DeleteVertexCommand`.
A constrained item returns at the shared preflight with its constraint type/id
and therefore produces no command, no dirty signal, and no partial scene change.

## 6.4 Export Flow

```mermaid
flowchart TD
    Start(["User triggers Export<br/>File → Export as PNG/SVG"])
    Dlg[Export dialog shown<br/>format, DPI, options]
    Conf[User configures and confirms]
    Fmt{Format?}

    PNG["QGraphicsScene.render → QImage → PNG<br/>options: DPI 72/150/300, grid on/off"]
    SVG["QSvgGenerator renders scene<br/>options: annotations on/off"]
    CSV[Iterate plant objects<br/>extract metadata → write CSV]

    Done([File written])

    Start --> Dlg --> Conf --> Fmt
    Fmt -->|PNG| PNG --> Done
    Fmt -->|SVG| SVG --> Done
    Fmt -->|CSV| CSV --> Done
```

## 6.5 Undo/Redo Flow

```mermaid
flowchart TD
    A([User performs action<br/>e.g. move object])
    A1["Tool creates MoveObjectCommand<br/>(obj, old_pos, new_pos)"]
    A2[UndoStack.push command]
    A3[command.execute applies the change]
    A4[Redo stack cleared<br/>new branch]

    B([User presses Ctrl+Z<br/>Undo])
    B1[UndoStack.undo]
    B2[command.undo reverses the change]
    B3[Command moved to redo stack]

    C([User presses Ctrl+Y<br/>Redo])
    C1[UndoStack.redo]
    C2[command.execute re-applies the change]
    C3[Command moved back to undo stack]

    A --> A1 --> A2 --> A3 --> A4
    A4 --> B
    B --> B1 --> B2 --> B3
    B3 --> C
    C --> C1 --> C2 --> C3
```

## 6.6 Auto-Save Flow

```mermaid
flowchart TD
    T([Timer fires every N seconds<br/>configurable])
    Dirty{Unsaved<br/>changes?}
    Skip([Skip])
    Ser["Serialize current state to temp file<br/>~/.open-garden-planner/autosave/&lt;project-hash&gt;.ogp"]
    Manual[On next successful manual save<br/>remove auto-save file]

    T --> Dirty
    Dirty -->|no| Skip
    Dirty -->|yes| Ser --> Manual
```

```mermaid
flowchart TD
    Boot([On startup])
    Check{Auto-save<br/>files found?}
    Prompt["Prompt user:<br/>'Recover unsaved changes?'"]
    Load[Load auto-save]
    Del[Delete auto-save<br/>proceed normally]
    Done([Continue])

    Boot --> Check
    Check -->|no| Done
    Check -->|yes| Prompt
    Prompt -->|Yes| Load
    Prompt -->|No| Del
```

## 6.7 Agent Task and Soil Requests (US-D3.3/D3.4)

```mermaid
sequenceDiagram
    participant Client as MCP client
    participant Server as MCP/asyncio thread
    participant App as Qt main thread
    participant Service as Task/soil service
    participant Commands as CommandManager
    Client->>Server: Read tool or guided prompt
    Server->>App: anyio worker -> MainThreadBridge
    App->>Service: Snapshot/generate requested period or resolve effective soil
    Service-->>App: Tasks or record + source + matching history
    App-->>Server: Curated plain payload
    Server-->>Client: Typed result envelope or rendered prompt
    Client->>Server: Manual-task or soil-test write
    Server->>Server: Check write token
    Server->>App: MainThreadBridge
    App->>App: Validate all inputs before mutation
    App->>Commands: execute one existing command
    Commands-->>App: Mark dirty and refresh views
    App-->>Client: Result; one undo reverses the write
```

The soil prompt extracts one bed from the status/mismatch envelopes. Calendar
generation selects a year independently of `today`; urgency uses `today` after
the full requested period is generated. Refused writes return an error without
changing project data or either undo/redo stack.

## 6.8 Sim clock fan-out (Phase 17 L1.0, ADR-053)

One write path from the sun toolbar into the one `SimClock`, and one fan-out. A
time-of-day change takes only the right-hand path; a date change takes both, the
date path first.

```mermaid
flowchart TD
    U([User drags the time slider,<br/>picks a date, or Animate ticks])
    T["SunSimToolbar.datetime_changed(naive wall reading:<br/>picker date + slider time)"]
    W["GardenPlannerApp._on_sun_sim_datetime<br/>→ SimClock.set_datetime(wall) — stored as given"]
    N{"Instant changed?"}
    X([No-op: nothing emitted])
    D{"plan_date changed?"}
    DC["date_changed(plan_date)<br/>_on_sim_date_changed"]
    H["Heatmap for another day shown OR result pending<br/>→ clear(); button unchecked"]
    R["3D shown → Scene3DController regrows the dated plants<br/>(growth at plan_date; at most once per 500 ms<br/>while the date keeps changing, L1.9)"]
    IC["instant_changed(SimChange)"]
    O["SunShadowController._on_clock_changed<br/>enabled → recompute (sun at utc, growth at plan_date)"]
    M["_on_sim_instant_changed:<br/>toolbar mirrors wall time (signals blocked);<br/>Scene3DController: a light-only pass (sun at utc)"]

    U --> T --> W --> N
    N -- no --> X
    N -- yes --> D
    D -- yes --> DC --> H --> R --> IC
    D -- no --> IC
    IC --> O --> M
```

A write from inside any listener raises `RuntimeError`: the remaining listeners
would otherwise receive a stale change. Every listener runs even when one raises,
and `instant_changed` is delivered even when a `date_changed` listener failed; the
first error is re-raised afterwards.

## 6.9 The 3D workspace: an edit, the first open, a new document, the close (Phase 17 L1.3 / L1.9, ADR-065)

The 3D view of every main window since L1.9 (there is no switch). Four flows; in all of them the GUI
thread is the only thread of ours (Qt renders the 3D window on its own).

**An edit while 3D is visible** — one pass per turn of the event loop, whatever announced it:

```mermaid
sequenceDiagram
    participant U as User / tool
    participant C as CommandManager
    participant S as CanvasScene
    participant K as Scene3DController
    participant Y as SceneSync
    participant E as Quick3DSink → host
    U->>C: execute(command)
    C->>S: the command changes items
    C-->>K: stack_changed → mark_dirty()
    Note over K: posts ONE pass event (normal priority)
    S-->>K: changed (queued by Qt) → mark_dirty(): rides with it
    K->>K: pass event → snapshot_records(scene, plan_date)
    K->>Y: apply(records, sun, ground)
    Y->>E: begin · the minimal calls · commit
    K-->>K: applied(TickReport: diff, times, retired)
    Note over E: Qt draws the next frame on its render thread
```

A time-of-day change takes a shorter path: `instant_changed` → one `set_sun`, no snapshot. With
the 3D pane hidden, `mark_dirty()` sets a flag and nothing else happens.

**The first switch to 3D or Split** — nothing of 3D exists before it:

```mermaid
flowchart TD
    A([View → Sun & 3D → 3D View (Plan → Split) / Alt+2 / Alt+3 /<br/>the mode buttons / View → Workspace])
    B["Workspace.set_mode: build the 3D pane (strip + stacked body)"]
    G["Init3DGuard.begin(): a marker of a dead process?<br/>→ compatibility flag on. Own marker written"]
    F["engine_factory(prefer_software): import quick3d,<br/>Quick3DHost + Quick3DSink; container into the pane"]
    X{"raised?"}
    M1["message in place of the view + 'Try Again';<br/>marker removed; state FAILED"]
    N["pane shown → 'Building the 3D view…'"]
    P["the label PAINTS → controller.set_active(True)<br/>(fallback 250 ms)"]
    T["catch-up pass: snapshot → apply;<br/>document_shown → the camera frames the plan"]
    H{"health poll (200 ms)"}
    R["first presented frame → marker removed;<br/>state RUNNING; poll every 2 s"]
    D["scene_graph_error → host closed; message<br/>'unavailable on this graphics device'"]

    A --> B --> G --> F --> X
    X -- yes --> M1
    X -- no --> N --> P --> T --> H
    H -- frames_presented ≥ 1 --> R
    H -- no graphics device --> D
```

A process that dies between "own marker written" and "first presented frame" leaves the marker:
the next session that opens 3D starts in compatibility mode and says so.

**A new or opened plan while 3D is visible:**

```mermaid
sequenceDiagram
    participant A as GardenPlannerApp
    participant S as CanvasScene
    participant W as Workspace
    participant K as Scene3DController
    participant E as engine
    A->>S: clear() / the committing phase of a load (never for an open that failed its validation)
    S-->>A: document_replaced → hours-of-sun map cleared, button unchecked (#428, ADR-056)
    S-->>W: document_replaced → document_changed()
    W->>K: document_changed(): plant shapes and outline memories dropped, dirty
    A->>S: the new document's items
    W->>K: set_active(False) — the pass is HELD
    W->>W: "Building the 3D view…" — the label paints
    W->>K: set_active(True) → one pass: a plain apply (remove what is gone, add what is new)
    K-->>W: document_shown → the camera frames the new plan, once
    K-->>W: applied(retired = the old plan's items)
    Note over W,E: the health poll, the pipeline quiet for 0.5 s:<br/>host.release_cached_resources()
```

**The ground of an edit** (L1.5, §8.32.5) — the bake rides the edit's pass; what its time
budget leaves is painted in ground passes, one per turn of the event loop:

```mermaid
sequenceDiagram
    participant K as Scene3DController
    participant Y as SceneSync
    participant B as GroundBaker
    participant E as Quick3DSink → host
    K->>Y: apply(records, sun, ground)
    Y->>B: bake(records, the diff, solid ids, plan) — 10 ms, at least one tile
    Y->>E: begin · the item calls · set_ground(tiles) · commit
    Note over K: ground_pending → a GROUND pass is owed (posted, like any pass)
    loop while tiles are pending (the view visible, no edit waiting)
        K->>Y: continue_ground() — no snapshot, no diff
        Y->>B: bake(records, no change) — the next tiles, nearest to the edit first
        Y->>E: begin · set_ground(tiles) · commit
        K-->>K: applied(TickReport: ground_pass, retired = replaced tile Models)
    end
```

**Closing the app with 3D visible** (or hidden, or never opened — the same path; L1.9 made it
the product's):

```mermaid
sequenceDiagram
    participant A as GardenPlannerApp.closeEvent
    participant W as Workspace
    participant K as Scene3DController
    participant L as LookController
    participant H as Quick3DHost
    A->>A: unsaved changes? (Discard / Save / Cancel) · Agent API stopped · heatmap worker joined
    A->>W: shutdown() — while the main window still exists
    W->>W: Split position saved · start marker removed (a clean close is not a crash)
    W->>L: shutdown() (its timers stopped; the host is not touched)
    W->>K: shutdown() — no pass, no timer, plan memories dropped, scene signals disconnected
    W->>H: close() — every Model destroyed, the window closed
    A->>A: UI state saved · autosave stopped and cleared · accept
```

Nothing of 3D is built on that path when 3D was never opened (no engine import at all), and it
ends with no Qt warning and no ERROR line in `app.log` in all three cases, from source and frozen
(`tests/integration/test_view3d_workspace_render.py`, G5).

## Guild insertion and computed warning refresh

```mermaid
sequenceDiagram
    Owner->>Picker: Select template/species/centre and preview
    Picker->>Preflight: Resolve catalog, spacing, layers and boundaries
    Preflight-->>Picker: Valid command or actionable refusal
    Owner->>Commands: InsertGuildCommand (one history entry)
    Commands->>Scene: Canonical multi-plant creation and membership snapshots
    Scene->>Coordinator: Schedule debounced refresh
    Coordinator->>GuildService: Plain saved member snapshots
    GuildService-->>Coordinator: Required/present/missing function counts
    Coordinator->>Canvas: Idempotent cosmetic centre badge
    Coordinator->>Panels: Shared status and converted warnings
    MCP->>Scene: Read last computed warning snapshot
    Scene-->>MCP: Shared converter, English message and details
```

Cancel/refusal never executes the command. Undo restores an existing centre snapshot and removes new plants. Template-file saves replace only user files, not placed plan snapshots or undo history. Species search resolves filtered offline records before starting a background provider request; obsolete generations and closed dialogs discard completed responses.

Gallery drag/drop and gallery-click circle placement both construct plants through `ui/plant_creation.py::build_plant`. It resolves species metadata before semantic layer assignment, reads the current per-plan preference and uses the active layer when the matching layer is hidden, locked or absent. The existing creation command owns parentage and the single undo entry. Guild picker/editor/member rows translate catalog common names at display time through the shared `GalleryData` translation context; saved species keys, names and template snapshots remain language-independent. Explicit user object names take precedence over the translated catalog label.

### Constraint panel and pinned feasibility (#457)

Panel refresh resolves the current graph's object labels and satisfaction state,
then each ConstraintListItem selects an immutable presentation descriptor, translates
its templates and formats the target in metres or degrees. Delete still enters
RemoveConstraintCommand through the application signal; stack_changed refreshes rows
on execute, undo and redo. Templates are translated at rendering time, never cached
in a selected language.

Feasibility runs the existing Gauss-Seidel/Newton sequence. If every positional
variable is pinned, Newton evaluates the residual on that fixed state and returns
its actual error; it cannot overwrite an incompatible warm-start error with zero.
The probe preserves graph, input geometry and history. See ADR-012 and the A5 evidence.

### Constraint edge-length creation (#406)

A single click picks an edge, then the distance modal supplies the target. Polygon/polyline
edges use the existing endpoint solver. Rectangle edges bundle the existing canonical size
applier on AddConstraintCommand, preserving the scene center/pivot. Feasibility sees the
proposed canonical rectangle geometry; refusal or a probe error restores the exact snapshot.
The synchronous probe restores its snapshot before any modal event loop, so autosave cannot
see uncommitted geometry. Resizes that move a FIXED position, change an EQUAL dimension or
conflict with existing rows are refused; this path does not offer destructive Override.
Unrelated equal-height relations survive width changes. The normal trial solve,
command execution and graph row use one history entry; undo restores size and graph, redo
restores the same constraint identity. Cancellation/refusal creates no history entry.

## A1 input and download refusal paths (#453)

```mermaid
sequenceDiagram
    participant UI
    participant ProjectManager
    participant PlanIO
    participant Scene
    UI->>ProjectManager: open(candidate)
    ProjectManager->>PlanIO: strict read and numeric preflight
    alt invalid input
        PlanIO-->>UI: rejection before document replacement
    else valid input
        ProjectManager->>ProjectManager: prepare items, layers, constraints
        ProjectManager->>Scene: apply prepared document
    end
```

Save builds a detached candidate including journal positions, validates/encodes,
writes a sibling temporary file and replaces the destination. Only then do filename,
clean state, recent files and journal metadata advance. Autosave and season writes
reuse the same persistence boundary.

The update checker passes a complete release descriptor to the update bar. Its worker
downloads the bounded manifest, streams and hashes the installer, checks size/digest,
then emits a verified result. The UI rechecks cancellation and persisted bytes before
launch. Rejection and cancellation never reach process launch.

Linux startup creates QApplication, secures the settings backend, loads preferences
and constructs the main window. An ownership/permission failure exits with a visible
error before the preference and window steps.
