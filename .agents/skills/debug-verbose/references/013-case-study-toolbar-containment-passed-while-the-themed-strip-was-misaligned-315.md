## Case study: toolbar containment passed while the themed strip was misaligned (#315)

**Symptom.** Owner review found sliders at different heights, Today twice, a repeated
map date, a large gap before hidden plants, a short time field and a blank calendar arrow.
**Wrong theories.** Passing bounds and font-width checks had been treated as visual
acceptance. No alternate runtime theory was adopted before rendering the actual theme.
**Evidence.** `[STRIP-VISUAL]` from a real themed main window recorded month slider
at y=6, daily slider at y=13, date height 31, time height 19, and an empty visible
map label 220 pixels wide. The unexpected-offset probe included traceback.format_stack().
The same widget without apply_theme did not reproduce the production appearance.
**Root cause.** The flow placed every group at the row's top before knowing the row
height, fixed-size group layouts could not grow to centre controls, independent labels
repeated the current date/context and a fixed empty label always reserved width.
QTimeEdit had no theme selectors; the date arrow had no image.
**Fix.** Measure each complete row before assigning equal-height group boxes; use
minimum-size group constraints. Hide redundant/empty labels, reproject retained map
status when the calendar changes, style time controls and supply centred arrow images.
Themed integration workflows cover both themes and EN/DE/ES at wide/narrow widths;
captures also exercise 150 percent scaling. All instrumentation stays outside production.
**Lesson.** Geometry containment does not establish visual quality. Render with the
startup theme and inspect alignment, redundant content and empty space explicitly.

