---
id: ADR-066
title: "Offline examples and portable .ogp templates"
status: "Accepted; owner executable acceptance confirmed on 27 October 2026; shipped in [v1.33.0](https://github.com/cofade/open-garden-planner/releases/tag/v1.33.0) via [PR #610](https://github.com/cofade/open-garden-planner/pull/610)."
refs: ["US-F5", "#316", "#379"]
legacy_anchor: adr-066-offline-examples-and-portable-ogp-templates-us-f5-316-379
---

# ADR-066: Offline examples and portable .ogp templates

**Status:** Accepted; owner executable acceptance confirmed on 27 October 2026; shipped in [v1.33.0](https://github.com/cofade/open-garden-planner/releases/tag/v1.33.0) via [PR #610](https://github.com/cofade/open-garden-planner/pull/610).
**Date:** 2026-10-26. The number follows ADR-065 (Phase 17 L4, #388), written at the same time on another branch.

**Context.** A saved plan includes site and history data. Reusing it as a starting
point must never attach Save or autosave to the bundled file. A new file format,
second loader or community server would add unnecessary compatibility seams.

**Decision.** A template is the existing version-1.4 JSON format filtered through
`core/templates.py::template_plan`. Keep canvas dimensions, geometry (including
species, plant dates, guild snapshots and smart symbols), layers, constraints,
guides, succession plans and the layer-assignment flag. Explicitly classify every
`ProjectData` field as keep/strip; a test fails on future unclassified fields.
Drop unknown top-level keys, site/history/preferences, top-level metadata,
background-image and journal-pin records (also inside groups), georeferencing,
photos and path-bearing fields. Recursively remove absolute Windows/POSIX paths,
UNC and drive-relative paths and file URIs. Names and free-form annotations are
retained: the export explanation asks users to review them before sharing.

`ProjectManager.load(as_template=True)` validates the original file version,
filters the document and uses the normal prepare/apply/metadata restoration path.
It finishes untitled and dirty, without adding the source to Recent Files.
`GardenPlannerApp._load_project_file` remains the only UI replacement path,
including history/autosave/compare cleanup. Export uses the normal snapshot and
atomic `write_plan`, flushes pending editors, never changes the current file or
cleans the document, and refuses to overwrite the live project or bundled files.

Three CC-BY-SA-4.0 learning layouts ship with localized sidecars and rendered PNGs.
The catalog lists local `<app-data>/templates/*.ogp` by filename without parsing
untrusted files. Opening a corrupt local template follows normal load recovery.
The read-only `garden://examples` resource lists bundled content only. GUI actions
open copies. No agent-open tool, network gallery or community server is added.
The later community-sharing phase can reuse this template subset.

**Verified spec correction.** `SuccessionEntry` stores absolute ISO calendar dates,
not frost-relative offsets. Preserve them without rebasing; the raised-bed example
and descriptions explicitly label its 2027 dates as illustrative. No climate or
companion benefit is inferred from an absence of antagonistic rules.

**Alternatives rejected.** A new extension/schema; a temporary-file loader; direct
scene construction per gallery entry; silently rewriting crop dates; sanitizing
arbitrary prose as if this were a complete anonymizer. No new dependency or file
version bump. A pre-F reader can ignore additive F keys and retain geometry.

**Evidence.** `tests/unit/test_templates.py`,
`tests/integration/test_templates_gallery.py`, `tests/ui/test_welcome_dialog.py`.
`generate_examples.py` uses production constructors, creation commands, serializer
and renderer with isolated stores. `dogfood_agent_api.py --emit-sample` copies the
maintained raised-bed example and preview instead of constructing another schema.

**Review hardening.** Record-type filtering applies only to structural objects and
children lists; custom dictionaries may contain arbitrary type values. The gallery
reclaims the banner space and scrolls details so the minimum-size viewport holds
a complete card. Sample emission short-circuits before exe/settings/server work.

**Owner-feedback addendum, 2026-10-27.** A teaching example needs an actual sun
study and soil workflow. `example_copy_plan` therefore retains only location and
soil tests for known bundled paths, including locale variants authorized by their
canonical sidecar. Coordinates describe public northern-hemisphere cities, not a
private garden. Soil and frost dates are explicitly fictional teaching inputs.
External templates and every template export still use the strict portable subset.
No history exemption is added (*one was added for the fictional harvest history:
#795 addendum below*). The load path, untitled identity and Save As remain
unchanged. Observed-failing load tests pin the demo-state exception and the
same-filename external refusal in `test_example_demo_state.py`.

All three layouts ship in English, German and Spanish, with identical object IDs
and geometry. Gallery thumbnails are rendered separately from each saved locale
plan, so tutorial text inside previews follows the language too. Display names,
annotations, notes, guild labels and credits follow
the selected language; canonical species and artwork identifiers stay stable.
Known edible-part terms translate at the editor/search display boundary and an
unchanged translated field preserves the exact raw list. This prevents an
unrelated property edit from rewriting species metadata in the UI language.

The 21 September 2026 teaching date is explicit in notes, never silently installed
in SimClock (*superseded by the #795 addendum below: an example opens at its
date*). Mature perennials have historical planting dates and nursery-size
anchors. Spacing is measured against actual plant circles and the shipped 2D bed
sprite's soil rectangle, which is narrower than its 3D soil. Guild membership
describes nearby plants, while missing roles remain honest diagnostics. Production
scene rendering and real-font annotation bounds supplement structural assertions.

## ADR-066 addendum: a showcase example (#390)

The fourth example, `family-garden`, is not a teaching plan: it is the plan of every Beauty Board
(`tests/fixtures/plans/bench_small.ogp`), shipped at the owner's request and the subject of the
project's visual material. It is built by the same `make_bench_plans.build_small` and keeps the
fixture's item ids, because a plant's procedural shape is seeded by its id; a test fails when the
two drift. It keeps the fixture's layout and its 6 to 10 cm path widths (*the widths, the
place of four objects and the cherry's age are superseded by the #795 addendum below*). One
difference: what takes
a year or more to mature is planted on 1 March, not on the fixture's 15 April, so a default
time-lapse shows the birch leafing out instead of popping in (949 cm against the fixture's 929 cm
on 21 June). It needs no
tutorial annotation or soil sample (the teaching plans' gates keep theirs), and its botanical
fields stay canonical in `de/` and `es/`: the localizer now translates only a species' common
name, since "Iris" is both a plant's name and a genus.

## ADR-066 addendum - File > Open of a bundled example is a copy (#865, 2026-11-11)

**Status**: Shipped in v1.39.1 (PR #903; owner's manual test 2026-11-12).

**Decision.** A shipped example opened by its path through **File > Open** takes the
same identity as one opened from the gallery: an untitled, dirty copy. The one load
path (`_load_project_file`) asks `core.templates.is_bundled_example` — the sidecar
trust predicate — and routes a known bundled path through `as_template=True`. The
result is `current_file is None`, Save goes to Save As, autosave cannot land in the
install tree, the file does not enter Recent, the showcase moment applies, and
`display_name` is the sidecar's translated name rather than the file stem. The
bundled bytes are never written. The gallery and File > Open now share one identity
rule instead of two.

Cross-refs: §8.33; FR-EXAMPLE-04, FR-EXAMPLE-08, FR-EXAMPLE-11.

## ADR-066 addendum: examples open in a showcase state (#795)

**Date:** 2026-11-10. **Status:** shipped in v1.38.0 (PR #838); the owner confirmed the decisions marked
*owner* in the manual test of 2026-11-10.

**Context.** The 2D survey for the promo material found that an example opened in the evening is
drawn at night, on today's date; its Harvest and Seed Inventory tabs are empty; Plant Details show
a seedling emoji; its paths are 6 and 8 cm hairlines. The teaching date lived in prose only.

**Decisions.**

1. **An example opens at its own moment** *(owner; supersedes "never silently installed in
   SimClock" above and "Neither opening a demonstration ... changes SimClock" in the runtime
   view)*. The sidecar names it: `showcase_date` (the reference date) and `showcase_utc_time`.
   `core/showcase_moment.ShowcaseMoment` writes the one `SimClock` when `_load_project_file` has
   loaded a shipped example as a template. It is not a clock: it holds one remembered reading.
   Both the date and the time are set. The time alone would leave today's date, on which the
   plants of an example are a season older or, before their planting date, absent (ADR-062).
2. **The user's reading comes back when the example stops being the document** *(owner)*.
   New, Open and a recovery put the clock back to the wall reading the user had before the
   first example, also when the user scrubbed inside the example: a date picked while looking
   at an example belongs to the example. **A successful Save or Save As of the copy ends the
   showcase too** *(owner; review round 1, replaces "Saving the copy changes nothing on
   screen")*: the copy is the user's file from then on, so the clock returns to their reading,
   the held reading is dropped, and the status bar says that the plan now follows their own
   date and time. The reason is the plan-date rule (ADR-062): a new plant is stamped with the
   date the clock shows. With the showcase left running, a plant added to the saved plan in
   November was planted on 21 June, and a clock setting the user made in their saved plan was
   replaced by the older remembered reading when the next document opened. Now a clock setting
   made after the save is the user's and no later document replaces it. `ShowcaseMoment`
   forgets the reading before it writes the clock, so a raising listener cannot leave one
   behind. The agent's `save_plan` ends the showcase through the same
   `GardenPlannerApp._end_showcase_after_save`; an autosave and "Save as template" do not,
   because neither makes the open document the user's file, and a recovered autosave opens at
   the user's reading like any document that is no example.
   **What a file can carry**: the moment itself is never persisted, in settings or in the plan
   (ADR-062: the viewed date is never saved), so a saved copy opens at the user's "now". A
   plant the user adds while the copy is still UNSAVED is planted on the example's date,
   because that is the date on screen, and it keeps that planting date in the saved file.
   That is accepted: the example's own plants carry the same dates.
   **Order of the writes**: the showcase writes the clock as the last step of a document
   change, after the history, the autosave, the layers panel and the status bar are the new
   document's, because `SimClock` re-raises a listener's error (ADR-053). A camera tour that
   moves the clock holds a reading as well. The showcase is the outer holder and the tour the
   inner one (`core/showcase_moment.InnerClockHold`): when the document changes under a
   running tour (only an agent can do that), the showcase takes the user's reading from the
   tour's hold and not from the frame, and re-bases the hold after its write, so the tour's
   finish returns the clock to the document that is open then.
3. **The moment is a UTC time of day on the local reference date**, applied with
   `SimClock.set_utc_time_on`, the operation a camera tour already uses. The clock originally
   displayed wall time in the computer's zone. The ADR-053 addendum for #945 supersedes
   that behavior for plans with a named time zone. The plan date is the reference date
   in every zone, and the sun stands where it does at 13:00 in the example's own place
   (11:00 UTC, all four).
4. **Example copies keep a fictional harvest history** *(owner; supersedes "No history exemption
   is added" above for this one field)*. `EXAMPLE_DEMO_FIELDS` is `location`, `soil_tests`,
   `harvest_logs`. The records sit on one plant per species, lie between planting date and
   reference date, carry the canonical species key (ADR-016) and say in their note that they are
   fictional. Journal notes, tasks, pest logs and every other history stay stripped; a template
   that is not a shipped example keeps none of the three.
5. **The seed inventory stays empty** *(owner)*. It is the user's cross-project store; an example
   must not write user data, and a per-example fake inventory would need a second store. The
   empty tab now explains itself.
6. **Plant Details draw the plant.** A species without a photo shows its canvas sprite through
   the existing `render_plant_pixmap`. No third-party image is added (asset provenance).
7. **The cover title.** `ProjectManager.display_name` (#788) already titles a report with the
   example's name. Added: the base copy, which serves every language without a translated plan,
   is named in the interface language when the sidecar has that name (Russian).
8. **Path widths** *(supersedes "its 6 to 10 cm path widths" in the showcase addendum)*. The
   showcase's "Gravel path" is 80 cm and its "Stepping stones" 50 cm. Only the example changes:
   the bench fixture keeps its widths, and the test that holds the two together compares
   geometry, ids, names and species, not stroke widths.
   **What stood in the widened walk moved out of it** *(review round 1; supersedes "keeps the
   fixture's layout" for four objects)*. As a 50 cm walk the stepping stones ran over the bird
   bath (48 % of it), a chrysanthemum (43 %) and a geranium (8 %). The bird bath stands at
   (620, 450), east of the walk; in the perennial border the geranium is at x 612, the
   chrysanthemum at x 746 and the lily at x 811 (it makes room for the chrysanthemum). The
   path's points do not move, because test data is pinned to them, and the fixture is
   untouched: the generator moves the four items (`FAMILY_MOVED_CM`), and the test that
   holds example and fixture together lists the four centres. The walk still crosses the
   perennial border bed, which is the ground it is laid through, like the lawn and the
   terrace. The birch's crown reaches over the gravel path; its trunk is a metre from it.
   **The cherry is a tree of several years** *(review round 1)*. It has 6.5 kg of harvest
   in June 2026 and was planted on 1 March 2026 like every established plant. It is now
   planted on 5 November 2022 as a nursery tree (1.5 m tall, 1.3 m crown: the growth model's
   low end is the size at planting). On the reference date its crown is 373 cm as before
   and it is 640 cm tall, where it was 511 cm. Every other harvest entry of the four examples
   was checked against its plant's age (`test_a_harvest_fits_the_age_of_the_plant_that_gave_it`):
   none needed a change.
9. **A seasonal 2D look is not built.** Trees in full leaf on 21 December are a project of their
   own; a follow-up issue carries it.
10. **Unevaluated sun rows fold in the panel.** With Hours of Sun off, every plant with a known
    requirement has a `sun_evaluation` record; the Diagnostics panel listed 61 / 114 / 174 / 14
    identical rows for the four examples. The panel shows the records of one reason as one row
    that counts and selects them. Switching the map on for an example was rejected: it paints
    the plan and changes the user's opt-in. The records, and so the Agent API, are unchanged.
11. **The generator is the only author.** Regenerating an unchanged tree moved the balcony
    chairs, changed one Spanish name and dropped the Russian attribution. `example_content` is
    the one place the shipped data comes from; `--check` and
    `tests/integration/test_example_generation.py` compare the files with it.

**Rejected.** A sim date saved in the plan (ADR-062 rejects a persisted viewed date); a second
clock for examples; restoring the reading only when the user had not touched the clock (the
tutorial's own "set 17:30" step would then carry 21 September into the user's next plan); a
wall-clock time in the sidecar; a harvest history on beds (a bed's history has no species key
and would show the bed's name as a species).

**Evidence.** `tests/integration/test_example_showcase.py`, `tests/unit/test_showcase_moment.py`,
`tests/unit/test_example_content.py`, `tests/integration/test_example_generation.py`,
`tests/integration/test_example_demo_state.py`.

## ADR-066 addendum: thirteen examples that are the showcase material (#940, 2026-11-19)

**Context.** The pictures and the video of the repository showcase (#564, #939) were to come
from plans made for the capture. The owner decided against throwaway plans: what is shown
ships. The four examples all lay in Germany and opened at noon on 21 June or 21 September;
together they left unused 16 object types, 14 of the 24 fill textures, three roof styles, a
rotated north, stored camera tours and 61 of the 118 species.

**Decisions.**

1. **Nine new plans, and the food forest enlarged** (owner). Each new plan shows one side of
   the app: allotment (planning), cottage garden (drawing to measure), terraced-house garden
   (sun and a rotated north), roof terrace (containers), spring garden (time), wildlife garden
   (the lush 3D view), Mediterranean courtyard (another sun), modern garden (light at night),
   Japanese garden (surfaces). The food forest grows an orchard meadow instead of a tenth plan:
   a dense half beside an open half, and no second card of the same kind in the gallery.
2. **The hint lies on its own layer** (owner). A plan that explains itself and a plan that is
   ready for a picture are the same plan with one layer shown or hidden. The first three plans'
   notes moved there too; the family garden stays without one.
3. **A fixed gallery order, no filter** (owner). The sidecar's `order`. A filter row was
   weighed and not built: thirteen cards scroll.
4. **No plan opens after sunset** (owner). The 2D canvas shows its night overlay then, and an
   example must open readable. The modern garden opens at golden hour; dusk is its stored tour.
5. **What an example keeps stays** (owner, decision 4 of the #795 addendum). The allotment
   shows planning through a succession plan, which a template keeps, not through a crop
   rotation history.
6. **Every plan stores an orbit.** A promo video is then a button press in a shipped plan and
   any user can make the same one. Framed from the plan's bounds as the Camera Tour dialog
   frames one, started with the showcase sun behind the camera, every number rounded.
7. **The examples share Central European clock time.** The Japanese garden was placed in Düsseldorf
   when the clock and tours only used the computer's zone. The ADR-053 addendum for #945
   now governs how the clock and tours use the plan's named zone.
8. **One thumbnail per plan.** It shows the plan at its showcase moment without the hint
   layer, so it has no text to translate. A picture per language cost 8 MB for one image.
9. **A harvest history is not mandatory.** The modern and the Japanese garden have no honest
   harvest. FR-EXAMPLE-09 names the rule.
10. **The table of `tests/example_specs.py` is a second statement by hand.** The generator
    authors; the table says what each plan is meant to be. A meta-test keeps the table, the
    shipped files and the generator the same set, so a plan cannot ship unchecked.
11. **Five species were added first** (owner): Japanese maple, bamboo, miscanthus, windmill
    palm, grape vine. The windmill palm and not a dwarf fan palm, because the palm look has
    only a tall-trunk form (#949).
12. **Two look fixes ship with the plans** (owner: fix what the pictures need). Hardy plants
    flower by their own months and only tender ones wait for the frost-free season; a lawn
    with the wildflower fill is a flower meadow in 3D. Everything else found became an issue:
    #941 to #949, and #839 for the seasonal 2D look.
13. **An independent 3D review judged every plan before the pictures were taken.** Its plan
    findings were fixed in the plans: an orbit pitch per plan, hedges in runs, plants in
    containers instead of on planter pots, a young walnut, sown annuals at a seedling's size,
    a dusk tour that ends in twilight. Its engine findings became #953 to #966, except two
    that the pictures needed: flowers that can be seen at garden scale, and decision 14.
14. **A bundled example opens in 3D on the side its stored orbit starts from**
    (`core/camera_tours.opening_side`, `Workspace.set_opening_side`). The default side looks into an
    afternoon sun and, over a garden wall, at the wall. The distance stays the pane's own;
    "Reset 3D View" and every plan that is not a bundled example keep the default side.
15. **The README's pictures come from the shipped plans through a script** (#564):
    `scripts/capture_readme_media.py`. A picture that cannot be re-shot goes stale with the
    next change to the look. The download button links to the installer of one release and
    the version sync moves it, because "the latest installer" has no fixed address.

**Rejected.** Hand-drawn plans saved from the app (the generation gate compares every shipped
file with the generator, and three languages cannot be kept in step by hand); a per-plan
picture per language; widening `EXAMPLE_DEMO_FIELDS` for a crop-rotation history; a plan that
opens at dusk; places outside Central European Time; a separate plan for the orchard meadow.

**Consequences.** The examples folder grows from 6.6 MB to about 12 MB. A new example needs a
module, a table row and a provenance row, and is then checked by every generic rule. The
season in the 2D picture is still missing (#839): the spring garden flowers only in 3D.

**Evidence.** `tests/example_specs.py`, `tests/unit/test_example_specs.py`,
`tests/integration/test_example_plans.py`, `tests/integration/test_example_generation.py`,
`tests/unit/test_example_content.py`.
