# Pitfalls: agent API, MCP and security

Standing rules for this area, one entry each. The heading is the rule. Pins and sources are listed under each entry. Index: [§11.4](../README.md#114-known-development-pitfalls).

### PF-API-01

- **Rule:** A CLI's SUCCESS output needs the same treatment as its failure output.
- **Pinned by:** none — pending Phase 3 review
- **Source:** #366
- **Status:** standing
- **Legacy:** README L183

- **A CLI's SUCCESS output needs the same treatment as its failure output.** (Issue #366, owner's manual test): the failure path got a condenser (a CLI that rejects its arguments prints its whole help, and the dialog renders that in a one-line label). The success path did not — and `install_to_client` returns the CLI's **stdout** as `detail`, which the dialog appends to the status line. OpenCode 1.18.x frames its confirmation in a coloured box, so the label showed literal `[]90m` fragments and mojibake, because `│`/`◆` are multi-byte and a `QLabel` is not a terminal. Two things had to be stripped, not one: **ANSI is not only SGR** (`ESC [ 2K` erase-line and cursor moves are just as destructive), and the **box glyphs survive escape removal** and have to go separately. Worth noting *which* client: 2.0.16 prints plain text, so probing only the modern binary showed clean output and the bug looked version-specific when it was version-*detection*-specific. The test now uses the real 1.18.32 bytes verbatim.

### PF-API-02

- **Rule:** An INDETERMINATE answer must never select the more DANGEROUS option.
- **Pinned by:** none — pending Phase 3 review
- **Source:** #366
- **Status:** standing
- **Legacy:** README L185

- **An INDETERMINATE answer must never select the more DANGEROUS option.** (Issue #366, the final pre-merge review's only P0): the client-CLI capability probe returned an empty flag set when it could not read a binary's help, and the caller read empty as "this CLI is too old" — which selected `legacy_cli_argv`, the argv *without* `--global`. On a MODERN CLI that writes a **project** config into the user's current working directory and returns `success=True`; reproduced end to end, with the user config never touched and the dialog row then contradicting the success message it had just shown. The reasoning was backwards because it asked "which answer is absent" instead of "which failure is dangerous": **the modern argv fails loudly (the CLI prints its help), the legacy one fails silently and writes the wrong file.** So the probe is tri-state — `supported` / `unsupported` / `unknown` — and only a *definitive* absence of the flag may take the legacy path. The same review found the probe's `except` still enumerated `(OSError, subprocess.SubprocessError)` at a trust boundary, which invariant 14 forbids and which this module's own `registered_url` comment explains; it is now broad, and `errors="replace"` keeps a single undecodable byte in someone else's help from becoming an exception on POSIX (where `subprocess` decodes in the calling thread, so it would escape into the dialog's `__init__`) or an empty string on Windows (where it kills the reader thread — the silent path that caused this very bug). **A capability check is a three-valued question, and "I could not tell" is an answer.**

### PF-API-03

- **Rule:** "Unparseable" and "empty" are different failures, and only one of them is dangerous.
- **Pinned by:** none — pending Phase 3 review
- **Source:** #366
- **Status:** standing
- **Legacy:** README L186

- **"Unparseable" and "empty" are different failures, and only one of them is dangerous.** (Issue #366, the owner's manual test): the onboarding merge's fail-closed rule is "an unreadable file we don't own is left byte-for-byte untouched". The owner's `~/.gemini/config/mcp_config.json` was **0 bytes** — which is what several clients ship before their first MCP server — and the merge reported `Could not read existing … (Expecting value: line 1 column 1 (char 0)); left untouched`. That message is `json.loads("")`. So a fail-closed rule written as "if we cannot use it, do not touch it" quietly answers a question the safety rule never asked: it protects *content*, and a 0-byte file provably has none. The general shape: **a guard phrased around the parser's opinion of the file inherits every quirk of that parser, including its opinion of an empty one.** The fix is a positive notion of emptiness (`_is_effectively_empty`) applied *before* parsing, in both the JSON/JSONC and TOML paths, and it must be applied under the STRICT `replace_on_parse_error=False` policy — otherwise "we protect your file" still quietly excludes "a file you have not written yet". The companion test asserts one byte of junk still fails closed, because the distinction that matters is empty vs corrupt, not lenient vs strict.

### PF-API-04

- **Rule:** A refusal nobody asked for is a capability removal wearing a safety hat.
- **Pinned by:** none — pending Phase 3 review
- **Source:** #366
- **Status:** standing
- **Legacy:** README L187

- **A refusal nobody asked for is a capability removal wearing a safety hat.** (Issue #366, same manual test, and a decision reversal recorded in ADR-035): a too-old client CLI was made to refuse rather than be handled, on the reasoning that its flags and config shape were unverified. The consequence was not a clear error — it was `install_method="manual"`, so **the Add button silently disappeared from the dialog**, and the owner reported the button missing. The refusal was also unnecessary: running the older binary against a throwaway config showed it writes the *user* config when the newer flag is absent, i.e. the fallback was not merely tolerable but correct. Three lessons. (1) **When a guard changes what the UI offers, check what the UI now offers** — a refusal that demotes a control to a snippet is a feature removal, and it will be reported as "the button is missing" rather than as the error it actually is. (2) **The blast radius of a safety decision is wider than the code it guards**: one `install_method` value moved a button. (3) **A CLI's config shape can differ between generations, not just its flags** — 1.18.x stores servers flat as `mcp.<name>` where 2.x nests them, so supporting both generations means the *reader* must accept both too, or it reports a working registration as absent. The manual snippet must follow the installed generation for the same reason: a snippet in the wrong shape is silently ignored, which reads as "OGP is broken".

### PF-API-05

- **Rule:** Verify the installed binary's CAPABILITY, not the product's documented interface — and check that a stub cannot stand in for a real binary.
- **Pinned by:** none — pending Phase 3 review
- **Source:** #366
- **Status:** standing
- **Legacy:** README L189

- **Verify the installed binary's CAPABILITY, not the product's documented interface — and check that a stub cannot stand in for a real binary.** (Issue #366, found by the owner's manual test, not by review): the OpenCode row's argv (`mcp add <name> --url <url> --global`) was verified by *running* `opencode mcp add --help` — but only against **one** of the two OpenCode installs on the machine. `~/.opencode/bin/opencode.exe` is **2.0.16** and has `--global`; an npm `opencode-ai` on the same box is **1.18.32** and has **no `--global`** at all (it writes the user config by default, and stores servers FLAT as `mcp.<name>` rather than nested under `mcp.servers`). `shutil.which` returns whichever comes first on `PATH`, and which one that is depends on **how the process was launched** — the owner's shell resolved 2.0.16, the GUI resolved 1.18.32, so the same button succeeded in one and failed in the other. The failure was not clean: a CLI handed an unknown flag answers with **its entire help text** and a non-zero exit, and the dialog renders `detail` in a one-line status label, so the user saw a wall of flag descriptions and no explanation. Two lessons. (1) **When argv is verified against one version, either verify the version or require the flag** — `ClientTarget.cli_required_flags` now does the latter, probing the resolved binary's own `mcp add --help` and refusing before anything is written; a *version string* was measured and deliberately not used, because parsing a help for a flag is evidence the binary accepts it, while `--version` output is a naming convention. (2) **A `shutil.which` stub returns a path that does not exist, which correct code reads as "cannot probe, therefore cannot use"** — so a stub-based test cannot detect this class of bug and in fact *depends* on the stricter behaviour. The only thing that found it was clicking the button on a machine that had two installs. Note also that the 1.18.x help has **no `USAGE:` line at all** (it opens with the command line and goes straight to `Positionals:`), so a "is this a help dump?" heuristic keyed on `USAGE:` alone would have missed the exact case it was written for; a test with the real help text as a fixture is what caught that.

### PF-API-06

- **Rule:** A refusal must leave the filesystem exactly as it found it — so take the backup as late as possible.
- **Pinned by:** none — pending Phase 3 review
- **Source:** #366
- **Status:** standing
- **Legacy:** README L191

- **A refusal must leave the filesystem exactly as it found it — so take the backup as late as possible.** (Issue #366, senior-review round 4): the onboarding merge copied a `.bak` *before* deciding whether to write. Every refusal therefore littered a second file next to a config OGP had just declined to touch, and the module's whole safety rule is about foreign files (`~/.claude.json` holds OAuth and project trust; `~/.codex/config.toml` holds the user's model choice). The trigger is mundane: it surfaced only because a test asserted the whole directory listing rather than "the file is unchanged" — which is the lesson. **Assert on the directory, not just the target file**, when a failure mode is "we declined to act"; a `.bak` beside an untouched file is invisible to `read_text()` assertions and reads as correct. The corollary is user-facing: when a write *does* happen, the backup path now goes into `InstallResult.detail`, because a backup that is made but never reported is not a safety feature, it is litter the user cannot find.

### PF-API-07

- **Rule:** "Unparseable" and "parseable but the wrong shape" are different failures and must not share a policy.
- **Pinned by:** none — pending Phase 3 review
- **Source:** #366
- **Status:** standing
- **Legacy:** README L192

- **"Unparseable" and "parseable but the wrong shape" are different failures and must not share a policy.** (Issue #366, senior-review round 4): the onboarding merge's fail-closed rule reads "an unreadable `foreign` file is left byte-for-byte untouched". But the code also treated a *readable* file whose `mcpServers` key was the wrong type (`{"mcpServers": "oops"}`) as replaceable — it did `servers = data.get(...); if not isinstance(servers, dict): servers = {}`, which **overwrote the wrong-typed container even when `replace_on_parse_error=False`**, i.e. it clobbered a file it had just promised to protect, and took the user's unrelated top-level keys with it. The distinction: a **parse** error means we understood nothing and a replace is defensible for a file we own; a **shape** error means we read the document perfectly well and only one key is the wrong type, so replacing discards data for no reason. Shape errors now fail closed whatever the ownership says — a deliberate narrowing of the one `own` target's contract. A backstop that is written as "if we cannot use it, start again" quietly answers a question the safety rule never asked.

### PF-API-08

- **Rule:** A "best-effort, never raises" reader must own its failure type — and, more importantly, must not enumerate.
- **Pinned by:** none — pending Phase 3 review
- **Source:** #366
- **Status:** standing
- **Legacy:** README L193

- **A "best-effort, never raises" reader must own its failure type — and, more importantly, must not enumerate.** (Issue #366, senior-review rounds 2 and 3): the JSONC reader was made to *raise* on an unterminated `/*` rather than silently swallow the rest of the file (swallowing is how a user's server entry gets eaten). Round 2 gave it a module-owned exception; round 3 found the *enumerated* `except` tuple underneath was the actual bug, when `RecursionError` — which both `json.loads` and `tomllib.loads` raise on a deeply nested document — escaped `registered_url` → `detect_clients` → the dialog's `__init__`, and PyQt6 turned the unhandled exception into `qFatal()`/`abort()`. The user-visible symptom: put a deeply nested config where a client keeps its settings, click Help → "Connect AI Assistant…", and the application dies. The general rule is invariant 14's: **one broad `except Exception` at the ingestion chokepoint for untrusted input, and never a list of families** — every family added is a family still missing, and the correct reading is that the broad catch *is* the fix, not a concession. Corollary: a docstring claiming "yields `None` … never an error" is only true if some test drives the function through its *real* caller.

### PF-API-09

- **Rule:** A guard checked on some paths is not a guard.
- **Pinned by:** none — pending Phase 3 review
- **Source:** #366
- **Status:** standing
- **Legacy:** README L194

- **A guard checked on some paths is not a guard.** (Issue #366, senior-review rounds 2 and 3): `ClientTarget.merge_supported=False` was meant to guarantee "OGP will not rewrite your OpenCode config". Round 2 found it checked on the no-CLI path but not on the CLI's "already exists" self-heal — the path a user reaches after a **port change or token rotation**, the case the whole issue exists for — and the merge there re-serialised the file and reported success. Round 3 found a third seam that bypassed it entirely (a record with a `cli_name` on `PATH` but no `cli_argv`). The check now lives **inside** the merge. The general shape: a flag that gates a destructive operation wants to be enforced at the seam, not at the call sites its author happened to think of. Ask, for every guard, "name the path that reaches the dangerous operation *without* passing my check" — and note that the code and the ADR can agree with each other and both contradict the flag, which is how this survived a review that had already read both.

### PF-API-10

- **Rule:** A required dataclass field is a contract with an explicit consumer list, not a struct you can extend freely.
- **Pinned by:** none — pending Phase 3 review
- **Source:** #277, #291, #365
- **Status:** standing
- **Legacy:** README L195

- **A required dataclass field is a contract with an explicit consumer list, not a struct you can extend freely.** (Issue #365): adding `new_plan`/`open_plan` to `agent_api.providers.AgentProviders` is two lines that five test harnesses and one production path pick up automatically *only if you go and edit them*. The one that bites is `main.py`'s `--selftest`, which builds its own throwaway `AgentProviders` to prove the Agent API can bind. All 6304 ordinary tests passed while `--selftest` failed with `TypeError: missing 2 required positional arguments` — the product path constructs the real providers from the application, and every harness that touches it had been updated. Same class as #277 and #291: a subsystem dead while the process is alive. When you extend it, run `--selftest` (exit 0) rather than trusting a green `pytest`.

### PF-API-11

- **Rule:** A tool's declared return model is part of its contract, and testing the provider is not the same as testing the tool.
- **Pinned by:** none — pending Phase 3 review
- **Source:** #365
- **Status:** standing
- **Legacy:** README L197

- **A tool's declared return model is part of its contract, and testing the provider is not the same as testing the tool.** (Issue #365): `new_plan` and `open_plan` first shipped returning `ExportResult(**result)` while their providers returned a dict with no `format` key and a `None` `file_path` against a `str` field. Both therefore raised a pydantic `ValidationError` on **every successful call over the wire** — after the document had already been replaced — while all 22 body-level tests passed, because the main-thread body builds a plain dict and never constructs the model. The two lines between provider and tool were the untested part. A `BaseModel` on a tool's return type is a contract, and it needs coverage at the same level as the handler.

### PF-API-12

- **Rule:** A third-party config file is a *superset* of the format you assume, and fail-closed turns that into a dead end.
- **Pinned by:** none — pending Phase 3 review
- **Source:** #366
- **Status:** standing
- **Legacy:** README L198

- **A third-party config file is a *superset* of the format you assume, and fail-closed turns that into a dead end.** (Issue #366): the onboarding module's safety rule is "an unreadable `foreign` file is left byte-for-byte untouched rather than replaced" (`~/.claude.json` also holds OAuth and project trust). OpenCode's `~/.config/opencode/opencode.jsonc` is a **JSONC** file — comments and trailing commas are legal — and the merge path read it with `json.load()`, which *raises* on a comment. Combine the two and the feature is not merely degraded but **impossible**: every real user's commented config fails to parse, fail-closed refuses to touch it, and OGP can never register. A fail-closed rule is not automatically the safe choice; it is only safe while the *read* can actually understand what it is refusing to clobber. Two lessons: (a) a tolerant reader must be **scoped to the format that needs it** — the strict `json` reader still raises, pinned by a negative test, because leniency leaking into the fail-closed path would turn genuine corruption into silent replacement; and (b) comment stripping has to be a **character scan, not a regex**, since `//` and `#` inside a string literal are data. Note also that this file is named `.jsonc`, so a detector that globs for `opencode.json` misses every real installation.

### PF-API-13

- **Rule:** Never re-serialise a file you do not own.
- **Pinned by:** none — pending Phase 3 review
- **Source:** #366
- **Status:** standing
- **Legacy:** README L199

- **Never re-serialise a file you do not own.** (Issue #366): writing Codex's `~/.codex/config.toml` with `tomli_w` would be the obvious way to add a `[mcp_servers.<name>]` table, and it would silently **discard every comment and the user's own formatting** in a config file they maintain by hand. The surgical alternative is barely more code: `tomllib` (stdlib, read-only) parses and validates, then only the one table's line span between its header and the next header is rewritten. It also removes the dependency the obvious approach would have added. The general form of the mistake: a "rewrite the document" API is safe for *your own* file and destructive for someone else's, and the difference is invisible in the code.

### PF-API-14

- **Rule:** A CLI's default scope can write into the user's project directory.
- **Pinned by:** none — pending Phase 3 review
- **Source:** #366
- **Status:** standing
- **Legacy:** README L200

- **A CLI's default scope can write into the user's project directory.** (Issue #366): `opencode mcp add` writes the **project** config unless `--global` is passed. Omitting the flag does not fail — it silently drops an `opencode.json` into whatever directory the user happened to be in, and the registration appears to work while applying to nothing. Verify a CLI's flags by *running* `--help` (this one was verified by running it), and pin any scope/flag that is load-bearing with a test asserting its presence in the argv.

### PF-API-15

- **Rule:** At a trust boundary that ingests untrusted files, catch `Exception` at the ingestion seam — do NOT enumerate exception families
- **Pinned by:** `tests/unit/test_smart_symbol_library.py`
- **Source:** #236
- **Status:** standing
- **Legacy:** README L244

- **At a trust boundary that ingests untrusted files, catch `Exception` at the ingestion seam — do NOT enumerate exception families** (US-C4 smart symbols, PR #236, found over three senior-review rounds). The smart-symbol library loads user-dropped JSON (`<app-data>/smart_symbols/*.json`). The contract — "a bad user file must never crash the app" — was first enforced by catching `(OSError, JSONDecodeError, ValueError)`. That broke three times in a row, each a different exception family escaping the too-narrow catch: (1) `from_dict`'s dry-run `generate()` raised `ArithmeticError`/`TypeError` (divide-by-zero, `9**9**9` overflow, `round(x, float)`) — none subclass `ValueError`; (2) a deeply-nested expression (`"+".join(["1"]*5000)`) raised `RecursionError` (a `RuntimeError`) *during `ast.parse`*; (3) a non-dict `parameters` entry (`[42]`) raised `AttributeError` in `from_dict`'s **structural** phase, which runs *before* the dry-run and so bypassed `generate()`'s wrapper entirely. Each "fix" added the family that bit it, then re-declared victory — the losing game. The real fix is structural: the **user-file load loop catches `Exception`** (log-and-skip), so *any* failure of `from_dict` on untrusted input is non-fatal **by construction** (`smart_symbol_library.py`); the **bundled** load loop stays narrow (`ValueError`/`OSError`/`JSONDecodeError` → crash-loud) so our own packaging bugs still surface and stay tested. `BaseException` (Ctrl-C/`SystemExit`) deliberately still propagates. Defense in depth: `generate()` also wraps its body in `except Exception → SmartSymbolError` (for the *runtime* regeneration path — param edits, deserialization — which doesn't go through the loader), the evaluator caps AST node count (`parametric_eval._MAX_NODES`) so its recursion surface is bounded, and `from_dict` guards `isinstance(data, dict)`. Rule: when code ingests untrusted data, put **one broad catch at the ingestion seam**; keep narrow typed catches only for trusted/first-party input (where a surprise exception *should* be loud). Enumerating exception families at a trust boundary is a recurring bug, not a safety measure. Pinned by `tests/unit/test_smart_symbol_library.py` (arithmetic/recursion/structural/non-object poison all skipped; malformed *bundled* still crashes loud).

### PF-API-16

- **Rule:** Agent API described the compass backwards (issue #267, fixed)
- **Pinned by:** `tests/unit/test_agent_api_auth.py::test_move_object_description_uses_y_up_compass_frame`
- **Source:** #267
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l282-agent-api-described-the-compass-backwards-issue-267-fixed)
- **Legacy:** README L282

### PF-API-17

- **Rule:** **Agent creation must share the loader's construction path and its undo
- **Pinned by:** none — pending Phase 3 review
- **Source:** #329
- **Status:** standing
- **Legacy:** README L442

**Agent creation must share the loader's construction path and its undo
boundary (US-D2.5, #329).** The tempting implementation is to instantiate each
shape class directly from its geometry parameters, but that creates a second
set of defaults and serialization assumptions beside
`ProjectManager._deserialize_item_core`. The safer contract is a Qt-free
validation/dict builder followed by the loader on the Qt main thread;
integration tests then prove the saved snapshot and live geometry agree. The
same boundary matters for composites: a `HOUSE`'s derived `ROOF_RIDGE` is
created in the same `CreateItemsCommand`, so one agent call has one Ctrl+Z
step and cannot leave an orphaned ridge. Callout UUIDs are persisted explicitly
because a visually correct callout whose id changes on save/load breaks every
subsequent agent reference. The durable lesson is to test create -> read ->
save/load -> read, not only the immediate canvas item, and to make every
deliberate unsupported type visible through the discovery tool and a drift
guard.

### PF-API-18

- **Rule:** A stable geometry API must read live transforms, and a constrained write must refuse rather than half-run the solver
- **Pinned by:** `tests/integration/test_agent_api_geometry.py::test_rotated_polygon_geometry_is_live_scene_space_and_round_trips_exactly`; `tests/integration/test_agent_api_writes.py::test_constrained_geometry_read_succeeds_but_every_d26_write_refuses`
- **Source:** #330
- **Status:** standing
- **Legacy:** README L464

**A stable geometry API must read live transforms, and a constrained write must refuse rather than half-run the solver** (US-D2.6, #330, 2026-09-25): the tempting shortcut was to reuse `get_object(raw=True)` and the serializer's polygon points. That is wrong for an edit contract — serializer points are pre-rotation storage, while the agent needs the vertices' current scene positions; at 215° the two frames visibly diverge. The inverse shortcut is equally subtle: `mapToScene` followed by `mapFromScene` moved a rotated polyline by about `5.7e-14 cm`, enough to make an unchanged request look like a real mutation even though the drift was invisible. `ui/canvas/geometry_inspect.py` therefore maps live vertices with `mapToScene`, and `geometry_apply.local_vertex_for_scene` reuses the exact local `QPointF` for an unchanged request within `1e-9 cm`. `set_vertex` then refuses that unchanged request as a no-op before any command is built, so the read/write pair cannot pollute history. The second trap is policy: the live constraint solver can move several connected items, so a one-shot agent tool that moved only the addressed object would silently violate intent. `_agent_require_unconstrained` now refuses every geometry write with the blocking constraint type/UUID, while unauthenticated `get_geometry` lists those constraints. Refusals happen before command execution, so scene, graph, history, and dirty state stay untouched. Pinned by `tests/integration/test_agent_api_geometry.py::test_rotated_polygon_geometry_is_live_scene_space_and_round_trips_exactly`, `tests/integration/test_agent_api_writes.py::test_constrained_geometry_read_succeeds_but_every_d26_write_refuses`, and the default-on orchestration tests. Lesson: for geometry APIs, document and test the coordinate frame at the transform boundary; for multi-item solvers, a refusal with an inspectable reason is safer than a partial mutation.

### PF-API-19

- **Rule:** Three guards in the wrong place (US-D3.2 final pre-merge review, #374)
- **Pinned by:** `tests/unit/test_agent_succession_review_fixes.py`
- **Source:** #366, #374
- **Status:** standing
- **Legacy:** README L519 (legacy 11.4.1)

The `set_succession_plan` work passed 6635 tests, an out-of-process dogfood
harness, and a real manual test in the built exe. The final review still found
three defects, and all three are the same mistake: **a guard that sits at the
wrong boundary**. Each one was fixed and pinned by
`tests/unit/test_agent_succession_review_fixes.py` (21 tests, each failing
against the pre-fix code).

1. **A guard around the parse does not cover the parse's consequences.**
   `PlantingRecord.from_dict` does `data["year"]` and never type-checks, so a
   `.ogp` carrying `{"year": "2025"}` produced a record whose `year` was the
   *string* `"2025"`. Both readers caught four enumerated exception types around
   the `from_dict` call - and the row sailed through, because nothing had thrown
   *yet*. The `TypeError` arrived later, inside `get_records_for_area`'s sort:
   outside the loop the guard was protecting, and inside a Qt signal handler
   whose own handler catches only `RuntimeError`. That is an uncaught exception
   in the event loop, the `qFatal()`/abort shape #366 recorded. **Enumerating
   exception types at an ingestion seam is a guess about a parser you do not
   control; catch broadly (invariant 14: a `.ogp` is untrusted input) AND
   validate the field you actually depend on** - here
   `_read_crop_rotation_record` in `app/application.py` catches `Exception` and
   requires `isinstance(rec.year, int)`. A list year, a `None` year and a
   missing year are now all dropped instead of detonating later.

2. **Re-resolving a name through the bundled DB silently drops every
   non-bundled species.** The write validator collected species *names* from the
   bundled database plus the plants placed on the canvas, then pushed all of
   them back through `lookup_species` to get keys. A Permapeople or custom
   species has no bundled record, so it resolved to `None` and was skipped: the
   roster missed every custom plant, and `set_succession_plan` refused a species
   the app had just shown the agent - while the sibling tool `set_species`
   accepted it. **Three agent tools disagreeing about one plant is a worse
   failure than any one of them being wrong**, and it was invisible because
   every bundled species worked. The validator now derives keys directly,
   `_agent_known_species_keys()` calling `species_key(dict)` (ADR-016) on the
   plant's own `metadata["plant_species"]`, never a round trip through the
   bundled index. Same class as the `species_key` corollary above: **derive the
   key; do not resolve a name back to the thing you already had.**

3. **A stored object that holds one year must not answer a question about
   another year.** `get_succession_plan(bed_id, year=2027)` on a bed holding a
   2026 plan returned `has_plan: true`, 2026 entry dates, and `season: null` on
   every entry - because the season is derived from the requested year and the
   dates are not. `null` reads as a data fault, not as "that is next year's
   question", so the agent had no way to tell a mismatch from corruption. The
   view now reports `has_plan: false` and carries a `plan_year` field naming the
   year the bed actually has. **When a store is keyed by a dimension the caller
   supplies, an explicit parameter that does not match the store is a miss, not
   a hint to return the wrong row** - and the miss must be legible in the
   response shape.

The common thread: each guard was written where the *code* was, not where the
*trust boundary* or the *key space* is. Review found all three; the suite and the
dogfood harness found none of them.

### PF-API-20

- **Rule:** Six defects a single package found, and what each one was really about (US-D3.3 #332 + US-D3.4 #333)
- **Pinned by:** none — pending Phase 3 review
- **Source:** #332, #333
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l737-six-defects-a-single-package-found-and-what-each-one-was-really-about-us-d33-332--us-d34-333)
- **Legacy:** README L737 (legacy 11.4.3)

### PF-API-21

- **Rule:** Review and frozen-client findings in D3.3/D3.4 (#332/#333)
- **Pinned by:** `tests/integration/test_agent_task_soil_tools.py`
- **Source:** #332, #333
- **Status:** standing
- **Legacy:** README L820 (legacy 11.4.4)

- **Call the public tool with the production provider graph.** The first
  handover reported 6951 passing tests, but a real MCP client against the frozen
  exe found `get_soil_status` failing with six missing model fields,
  `get_soil_mismatches` failing with missing `total`, and the soil prompt failing
  likewise. Providers returned aggregate `beds` envelopes while the server
  constructed single-bed models. The purported real-client suite only called
  provider methods and prompt renderers directly. Explicit aggregate schemas
  now preserve per-bed coverage; the prompt extracts its requested bed.
  `TestRealMcpTransport` in `tests/integration/test_agent_task_soil_tools.py`
  calls all nine tools and both prompts using `app._build_agent_providers()`.
  Four status/prompt tests and a separate mismatch test were observed failing
  before the fix. Stub registration and direct provider success are evidence
  about different boundaries.
- **Generate a requested period before applying urgency.** A plant with April
  sowing and June/July harvest returned an empty, fully-covered annual calendar
  when queried in October. Future years were also empty because `year` never
  reached generation. `actionable_only=False` retains the schedule for agent
  annual/explicit-window reads while GUI reminders keep their existing default.
  A December-to-January task was dropped from both years; intervals are now
  clipped to year boundaries. Pinned by
  `test_calendar_generates_the_full_requested_year`,
  `test_explicit_task_window_generates_its_calendar_tasks` and
  `test_calendar_clips_cross_year_tasks`, all observed failing first. Propagation
  was absent because no plans were supplied to its generator. The extracted
  `build_propagation_plans` is now shared with the GUI and honors seed data and
  user overrides; `test_propagation_tasks_use_the_gui_calculator` failed for both
  current and future years before the fix.
- **Provenance and staleness must follow the same selected record.** An old
  global test was reported with `record_source=global` and
  `is_test_overdue=false` because staleness checked the bed's empty history.
  The service now resolves record/source/history together, and the existing
  record-only method delegates to it. Pinned by
  `test_global_fallback_uses_global_history_for_staleness` (failed first).
- **Language and input types must be checked at the actual boundary.** A
  German amendment test pinned English names, contrary to the API contract.
  Recommendation names now use the existing `Amendment.display_name(language)`;
  `test_amendment_names_follow_the_ui_language` failed first with English
  `Dolomite lime`/`Compost` versus `Dolomitkalk`/`Kompost`. MCP's permissive
  numeric validation also converted booleans and numeric strings into soil
  readings before the stricter domain validator saw them. Strict numeric
  annotations prevent that; three malformed-input transport cases failed first.
  The translator unit test now requests `qtbot`: it previously depended on an
  unrelated test creating QApplication, so a targeted run failed while the full
  run passed.

- **The requested year is not necessarily a task's frost-anchor year.** Round
  two reproduced bundled garlic sowing on October 15–29, 2026 only when the
  request extended into 2027. Bundled asparagus harvest uses offsets 104–156
  weeks, so a 2026 calendar must also consider prior anchors. Period generation
  now derives an anchor range from the actual calendar and propagation offsets,
  filters overlapping dates and preserves canonical anchor-year IDs. Annual
  calendars and task windows share this path. Both the garlic integration test
  and `test_bundled_multiyear_harvest_includes_prior_frost_anchors` failed first.
- **No recommendation is not a soil-health assessment.** An existing lab-only
  record (`n_ppm=100`, no kit levels) correctly returned unknown health and no
  amendments, yet the prompt claimed every measured value was near target.
  Neutral prompt/tool prose now states the engine's limited conclusion and
  names the unconverted lab readings. The real-client
  `test_lab_only_reading_is_not_presented_as_near_target` failed first.
- **Absolute dates need an absolute identity.** Wider frost-anchor generation
  reapplied a saved March 10 propagation override for every anchor, making three
  tasks in an annual read and five in a three-year read. The dates agreed but
  anchor-year IDs differed, so deduplication failed. The shared propagation
  generator now assigns overridden steps to their start-date year; relative
  steps retain anchor-year IDs. GUI and agent therefore agree.
  `test_absolute_propagation_override_has_one_shared_identity` failed first and
  checks identity, one result, GUI convergence and annual month counts.

### PF-API-22

- **Rule:** A product surface can be "protected" by a library default nobody pinned.
- **Pinned by:** none — pending Phase 3 review
- **Source:** none recorded
- **Status:** standing
- **Legacy:** README L1086

- **A product surface can be "protected" by a library default nobody pinned.** Symptom: the Agent API's only barrier against a web page reaching it through DNS rebinding was the mcp SDK's Host/Origin validation, and the declared floor (`mcp>=1.12`) admitted SDKs that leave it **off** — measured: on 1.22.0 a crafted `Host: evil.example` initialize returned HTTP 200 with a full MCP result, where the 1.30.0 wheel answers 421. No shipped exe was known to be exposed, because every release happened to bundle a 1.30-era wheel. Root cause: the property belonged to *whichever wheel resolved at build time*, not to the product. Fix: `build_server` now takes the host/port it binds and passes explicit `TransportSecuritySettings`, and the floor rises to `mcp>=1.23`. The instructive part is the test design: with mcp 1.30.0 installed, the black-box 421/403 tests **pass even with our settings deleted** (measured). So does a naive object-level assertion that the settings are not None and the flag is True — the SDK auto-enable returns exactly such an object. What actually detects the removal is asserting something the default cannot satisfy: that `allowed_hosts` names the **bound port** and that no entry is a wildcard. Measured: deleting the `transport_security=` argument fails 3 of the 4 object-level tests. *A test that passes because of a library default is not testing your code; assert the configuration object as well as the behaviour it produces.*
