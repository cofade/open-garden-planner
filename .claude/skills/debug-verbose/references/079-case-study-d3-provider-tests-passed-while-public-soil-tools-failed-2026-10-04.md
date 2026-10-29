## Case study: D3 provider tests passed while public soil tools failed (2026-10-04)

**Symptom.** A handover reported 6951 passing tests. A real MCP client against the
frozen executable returned errors from both soil reads and the soil-planning
prompt. Annual task calendars also returned empty, fully-covered years.

**Rejected explanations.** A frozen-only hidden import problem and a broken
main-thread bridge were plausible before the probe. Neither explained successful
manual-task writes, undo and amendment recommendations in that same client.

**Key evidence.** The scratch client printed the actual results:

```
[D3-LIVE] get_soil_status ERROR: 6 validation errors for SoilStatus
[D3-LIVE] get_soil_mismatches ERROR: total Field required
[D3-LIVE] plan-soil-amendments ERROR: 6 validation errors for SoilStatus
[D3-CALENDAR] requested=2027 reference=2026-10-03 months=[]
```

Status providers returned `beds` lists; the server constructed a single-bed
model. Mismatch providers returned per-bed mappings; their server model required
an unrelated top-level `total`. The integration suite never made those public
calls. Separate failing probes found that an old global soil reading checked an
empty bed history, German names remained English, and MCP validation coerced
booleans/strings into numeric readings before the domain guard could refuse them.
Propagation generated nothing because the provider supplied no plans.

**Root cause.** The tests stopped before the boundary their prose claimed to
exercise. Calendar generation also discarded inactive tasks before the requested
period filter, and the requested year reached only bucketing, not generation.

**Fix.** Typed soil envelopes, explicit per-bed extraction in the prompt, and
real HTTP integration workflows using the production provider graph. The shared
engine now separates year from reference date and has an explicit actionable-only
option; cross-year intervals are clipped. Propagation uses the extracted GUI
calculator. The soil service resolves record/source/history together; names use
its existing bilingual display method; MCP soil numbers use strict annotations.
Every defect has a regression observed failing first. Instrumentation stayed in
the scratch probe and temporary test prints were removed before commit.

**Lesson.** A green provider test cannot validate server schema construction.
Drive the public call with the production graph. Generate a period before
classifying urgency, preserve the chosen record's provenance through derived
checks, and test refusal before and after framework argument coercion.


### Case study: D3 frost anchors and unassessed lab readings (2026-10-04)

**Symptom.** Extending a task window into the next year changed its earlier-year
results; an unknown lab-only soil record was described as near target.

**Wrong theory.** Matching the requested calendar years was sufficient after
year bucketing was fixed; an empty engine result implied healthy measured soil.

**Key evidence.** Temporary regression prints showed [D3-ANCHOR] lacked
llium sativum:direct_sow:2027 in the 2026-only result even though its dates
were 2026-10-15 through 2026-10-29. [D3-LAB] showed unknown health and an empty
plan beside the near-target prompt claim. Three regressions failed first.

**Root cause.** Negative and multi-year frost offsets cross anchor-year
boundaries; existing GUI lab ppm records are not converted to kit levels.

**Fix.** Derive anchor years from the actual calendar/propagation offsets, then
filter date overlaps through the same path for both annual and window reads.
Keep empty-result prose neutral and explicitly mention unassessed lab readings.
Temporary prints were removed.

**Lesson.** Generate from dates, not matching year labels. An empty result
establishes only what the engine assessed, not what the caller hopes it means.

