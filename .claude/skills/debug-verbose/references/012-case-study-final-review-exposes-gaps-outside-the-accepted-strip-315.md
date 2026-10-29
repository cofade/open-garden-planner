## Case study: final review exposes gaps outside the accepted strip (#315)

**Symptom.** Scrolling a lifetime selector could remove an undated legacy plant;
renaming a house invalidated every plant's cached paint. Print and hidden-layer
data also bypassed contracts already enforced by image exports and date presence.
**Wrong theories.** A read-only nested line editor was mistaken for a read-only
spin control; refreshing visibility was mistaken for requiring all geometry caches
to be cleared. No alternate theory was accepted before reproduction.
**Evidence.** Isolated old-head instrumentation printed `[F4-FINAL] unfocused
removal wheel 1900-01-01 -> 1901-01-01`, removal metadata and `visible=False`.
The unexpected invalidation hook printed traceback.format_stack(), tracing an
unrelated house command through stack_changed to refresh_timeline and every
plant's prepareGeometryChange. Fail-first integration tests also measured today's
print legend on a 2030 plan and hidden beds/data disappearing from reports/diagnostics.
**Root cause.** QDateEdit still processes wheel gestures when its line edit is
read-only. Lifetime selectors offered dates outside the shared clock's range;
refresh_timeline always invalidated geometry; isVisible combined drawing layers
with presence in data consumers; Print had its own unguarded render entry.
**Fix.** Ignore calendar wheel gestures, bound new choices while preserving legacy
metadata, update all plant caches only on a date change, use is_present for data,
and hold the shared export readiness/animation lease throughout Print preview with
validation before each paint. Restore stale badge and real MCP assertions while
a controlled exposure worker remains held beyond the debounce.
**Lesson.** Validate every entry point, including printing and legacy controls.
UI acceptance and existing image-export tests do not cover those paths. Pins live
in test_plan_sun_controls.py, test_sun_mismatch.py and test_timeline_quick3d.py.
Instrumentation ran in an isolated external probe and is absent from production.

