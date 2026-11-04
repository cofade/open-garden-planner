## Case study: field limits stopped chronological date/time stepping (PR #565 manual pass)

**Symptom.** Holding Up stopped at 31 October, December, minute 59 or hour 23.
**Wrong theories.** Native wrapping might carry into the next unit; the toolbar
might be the editor's immediate parent; one synthetic repeat event might mean one
native step. Each was tested and rejected before adoption.
**Evidence.** The native spy printed `[565-STEP] DaySection flags=StepDownEnabled`
at 31 October: Qt disabled Up before calling stepBy. With setWrapping(True), the
same key produced 1 October, and minute 59 became minute 0 in the same hour.
The owner-chain probe printed `[565-OWNER] _PlanDateEdit ['QWidget', 'QWidget',
'SunSimToolbar', 'GardenPlannerApp'] flags=StepNone`. A repeat probe including
traceback.format_stack() showed Qt's first auto-repeat calling stepBy twice;
Qt 6.11's qabstractspinbox.cpp keyPressEvent confirms that native cadence.
**Root cause/fix.** Independent native fields neither enable nor carry steps across
larger-unit boundaries. Thin date/time subclasses override stepBy and stepEnabled,
find their toolbar through the actual widget ancestors, and delegate to one naive
wall-reading step. Block widget signals while mirroring date/time, then emit one
complete reading. Month/year steps retain the preferred day; minute/hour arithmetic
is civil and saturates only at the supported absolute date limits.
**Lesson.** Field wrapping is not calendar arithmetic. Validate actual native event
entry points, direction availability, retained section and every delivered reading;
do not impose an invented OS repeat cadence. Midnight must update the shared clock,
plant presence and sun state atomically. Pins: tests/integration/test_plan_sun_stepping.py
and test_minute_rollover_updates_presence_sun_and_3d_once in
 tests/integration/test_timeline_quick3d.py. All temporary probes stayed outside
committed production code.

