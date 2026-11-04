## Case study: a second window that "differed" by 9.8 luma: the comparison was right, the first diagnosis was not (ADR-048 spike, fixed 2026-10-04)

**Symptom**: `--second-window` reported `frame_diff_vs_first` 9.8 mean luma on llvmpipe and
9.75 on D3D11 (Windows v9), so the second window seemed not to render the first window's view.

**Wrong theories**. (1) Temporal anti-aliasing not yet converged in the young window, but
the low preset has no AA at all. (2) `copy_view_from` missing a property, but the state keys
come from the QML meta-object, so nothing was left out by hand. (3) **A stale reference
frame**, grabbed right after the previous probe restored its state, before a redraw. This
one shipped as a fix (a three-frame settle before the reference grab), validated by a run
that **left out `--iou`**, the probe that triggers the defect. Without the trigger the
difference is 0.0 with or without the settle, so that run proved nothing, and the commit's
"17 passed" came from a tree that never held both the assertion and the settle. Senior
review ran the full flag set and read 9.83 again.

**Key evidence** (senior review, pass 4): the first window grabbed before and after
`shadow_iou_probe` alone differed by **13.1** mean luma, 0.0 in the top half and 26.2 in the
bottom half: the plan ground (lawn, paths, pond) was white. No root state key had changed.

```
ground.update() alone                          diff 13.1   (no effect)
ground.setTextureData(textureData()) + update  diff 0.0
a fresh ImageTexture                           diff 0.0
```

**Root cause**: the texture twin of the geometry rule in the case study above. The IoU and
orientation probes set `groundTexture` to null, which detaches the `QQuick3DTextureData` from
its QML `Texture`; `preserved_state()` set the *same* object back, and Qt Quick 3D draws a
re-attached texture data object untextured (white) until its data is uploaded again. The
first window kept a white ground until the soak's next reload; the second window, with its
own texture, drew the right one. `preserved_state`'s identity guard passed throughout: it
checked Python's bookkeeping (the shown texture is the one held), not the engine's pixels.

**Fix**: `preserved_state()` re-uploads the ground whenever it was detached; the settle wait
is gone. Test-first: the runner grabs the first window before the probes and after them
(`probe_restore_frame_diff`), the render tier asserts it below 1.0 (9.83 before the fix, 0.0
after, with `--iou --orient --pick --update-bench --second-window`), and the CI driver checks
it and `frame_diff_vs_first`.

**Lesson**: **a validation run that omits the trigger proves nothing.** Before accepting a
root cause, reproduce the failure with the exact flags that produced it, then show that same
run passing with the fix; a fix validated where the bug cannot occur is a guess with a green
tick. And a guard on bookkeeping (the right object is held) is not a check of the outcome
(the right pixels are drawn): test a contract in the currency it promises.

### Case: the Tasks tab said "you're all caught up" while a harvest was open

**Symptom**: a southern plan (20 September last spring frost) put a tomato harvest at
29 Nov 2026 – 7 Feb 2027. On 1 January 2027 the Tasks tab and the planting-calendar
dashboard listed nothing; a tomato-only plan rendered *"No tasks — you're all caught up."*
The agent's `get_tasks`, over the same plan and the same date, listed it. A garlic plan
(9 April frost) had an autumn sowing on 9-23 Oct 2026 that reached no GUI surface at all.

**Wrong theories, in order**:
1. *The dashboard and the Tasks tab filter differently.* They do not — both called
   `generate_all(build_plan_state(...))` and shared the urgency rule. Reading the two
   call sites "fixed" nothing, because they agreed.
2. *The offset maths is wrong.* It is not. `generate_calendar_tasks` computes
   `last_frost + timedelta(weeks=offset)` and the numbers were right for the year it
   anchored on.
3. *The agent is being generous and showing speculative windows.* No: the agent's
   `generate_for_date_window` derives the set of anchor years from the offsets
   (asparagus harvests 104 weeks after its frost; garlic is sown 26 weeks *before* it),
   and the GUI had exactly one anchor year.

**Key evidence**: `[TASK-MULTI-ANCHOR]` — a sweep applying the GUI's own listing rule
(`classify_urgency(...) is not None`) to **both** sides, over 64 bundled species x 6 frost
dates x every 10th day of 2026 (222 cases):

```
(todo, frost date, day) cases: 222
missed by the GUI on master : 1849
missed by the GUI after fix: 0
tasks the GUI now lists that the 90-day agent window did not: 0
```

Harness: `scripts/measure_task_window_sweep.py` (committed with this case). It
prints the same three figures under its own labels — `cases swept`,
`missed by the GUI now`, `listed now but not by the agent` — not the labels
used above, which were written for readability. The first number to print was **0 surplus**, not 0 missed. Without it you cannot tell a
correct fix from one that simply lists everything — and this bug's fix passes straight
through the exact place that mistake is made: the shared date-window path runs with
`actionable_only=False`, so a wrapper that forgets to re-apply its own filter turns the
Tasks tab into the next decade. That mistake actually happened during the work (an empty
task list and a blank Gantt) and was caught only because the surplus count was asserted.

**Root cause**: three surfaces each built their own list. The Tasks tab and the dashboard
passed the snapshot to `generate_all`, which anchors on `state.year` alone; the Gantt went
further and re-derived every bar from `self._last_frost` plus the raw species offsets — a
*second* implementation of "offset to date" — the agent's `generate_for_date_window` and the dashboard's `generate_all` both *call* `generate_calendar_tasks` rather than reimplementing it, so the generator itself is the first implementation and the Gantt's re-derivation the second; the old count included the callers. `generate_for_date_window` (the engine
behind the agent's task tools) was already correct.

**Fix**: one shared entry point, `task_generator.generate_actionable_for_surface`, which
*wraps* `generate_for_date_window` (does not reimplement it) and re-applies the GUI's
urgency filter at the edge. The Gantt consumes the generated windows instead of
recomputing them. ADR-029 addendum.

**Lesson**: **two surfaces calling the same generator can still disagree about the inputs
they hand it.** The functions were shared; the arguments were not. Find that class of bug
by comparing the two outputs under one rule applied to both, and always print what the fix
*added* as well as what it removed — for a "we were hiding too much" bug the added count is
the one that catches the over-correction.

---

### Case: a date field that reformatted for display corrupted saved plans

**Symptom**: the planting calendar's propagation editor moved each displayed step date into
the current year, start and end independently ("for readability"). A step crossing New Year
was persisted into the `.ogp` as `start 2026-12-24 / end 2026-01-22` — an inverted step —
and `compute_propagation_plan` applied stored overrides verbatim, so the corruption was
permanent for any plan already saved. 1,036 (species, frost-date) pairs in 2026 had at least
one such step.

**Wrong theories**:
1. *The defect is in the writer, so fixing the editor repairs existing files.* No — the
   reader applies the stored pair without validation, so a file written by the buggy build
   stays wrong forever. The two halves have to be fixed separately, and only the writer fix
   is invisible in a fresh plan.
2. *The helpful repair is to swap the pair on load.* That silently rewrites what the user
   typed; if they meant an overnight or wrap-around step, we have corrupted their intent.
3. *It is only a display issue because the stored value is what the user sees.* The stored
   value is what every other surface reads (the Gantt's propagation sub-row, the dashboard,
   `get_tasks`).

**Key evidence**: `[TASK-PROP-EDITOR-YEARS]` — the repro is the *stored dict*, not the
screen. Leek with a 1 April last frost and no override has an indoor sowing of
24 Dec 2025 - 21 Jan 2026; the editor showed "24 Dec - 21 Jan" and moving the end by one day
stored `{'start': '2026-12-24', 'end': '2026-01-22'}`. The 29-February corners were the
tell that the year rewrite was conditional: `except ValueError: display = s` kept the REAL
year for the 29-Feb date while the other date moved into the current one, so the step
stretched or inverted *depending on leap-ness* — a shape no single "wrong year" theory
predicts.

**Root cause**: the populate method rebuilt the displayed date from month/day rather than
using the step's date. Two further defects sat in the same 40-line function and were
covered by the same tests: the editor wrote an override on every `dateChanged` and ran the
calendar's full `refresh()` each time — one gesture, one write and one refresh per keystroke, and the refresh re-fetches the weather. It now commits **once per gesture**. (Not an *undo* step: a propagation override never reaches the `CommandManager`, so it is not undoable at all — a pre-existing gap this change does not close.),
and the species detail line was five hardcoded English f-strings the i18n gate is
structurally blind to.

**Fix**: the editor shows each step's real dates; an override whose end precedes its start
is **ignored on read and refused on write**, leaving the stored value in the file untouched.
The commit is now once per gesture (600 ms debounce plus immediate on focus-out, mirroring
`properties_panel._TEXT_COMMIT_DEBOUNCE_MS`).

**Lesson**: **a date field that reformats what it holds for display is a data-corruption
site.** Before choosing a repair for a persisted bad value, find out who reads it back: the
writer's bug and the reader's missing validation are two defects, and fixing only the writer
leaves every existing file broken. When the value is untrustworthy, *ignoring* it (keeping the
file intact) beats *repairing* it (rewriting the user's intent).

### Case: the wrapper broke the tabs it was written to fix

**Symptom**: two regressions in the *same eight lines* of the new
`generate_actionable_for_surface`, both invisible to the suite that shipped the
multi-anchor fix. (1) Opening either task tab on a plan with an **undated** manual
task raised `TypeError: '<=' not supported between instances of 'NoneType' and
'datetime.date'` — a state the agent's own `add_manual_task` produces on purpose
("omit `date` for an undated task"), so an agent-written plan bricked both tabs
on next open. (2) A manual task due in **December** disappeared from the Tasks tab
when read in **June**.

**Wrong theories**:
1. *The multi-anchor change broke the urgency filter.* No — the filter was correct;
   it was being applied to tasks it was never written for.
2. *`classify_urgency` should tolerate `None`.* Possible, but it papers over the
   real mistake: manual tasks should never reach an urgency test at all.
3. *The date-window span is too narrow.* This was the actual second cause, and it
   only appeared *after* fixing the first: narrowing the span from ±10 years to the
   urgency window (a ~50x speedup) silently dropped absolute-date manual tasks
   before the exemption could apply. A fix for one P0 caused a second P0.

**Key evidence**: `[TASK-MANUAL-REGRESSION]` — the same plan, the same date, the
two code paths:

```
master  (generate_all): ['far', 'longpast', 'undated']
branch  (surface fn)  : ['undated']          # then TypeError once more cases run
```

and the crash, from the real widget, not a unit test:

```
TasksView.__init__ -> refresh() -> generate_actionable_for_surface
  -> task_generator.py:757 -> task_generator.py:151
TypeError: '<=' not supported between instances of 'NoneType' and 'datetime.date'
```

The lesson about *where* to look: the reviewer's reproducer was "add one undated
manual task". My own tests for the multi-anchor change had all used **frost-derived**
tasks, because that was the thing under change. The bug lived in the population I
never varied.

**Root cause**: the wrapper assumed every generator below it behaves alike. Two
deliberately do not — `generate_manual_tasks` documents "a manual task is never
filtered out by urgency", and `TasksView._bucket` re-derives a bucket for exactly
those cases including a `no_date` bucket that exists only for undated tasks. The
wrapper imposed a fourth rule without reconciling the three below it.

**Fix**: undated tasks pass through unclassified; manual tasks are merged in from
their own generator (they carry absolute dates, so the date span drops them) and
are never urgency-filtered. Three regression tests, run against the **real
`TasksView`**, not the helper.

**Lesson**: **a shared generator's flags and its filters are inherited by every
caller.** When you wrap one, enumerate what sits below it before applying a uniform
rule — and when a bug appears only in a population you did not vary, widen the
fixture before you widen the theory. A speed fix that narrows an input span is a
behaviour change and must be swept like one.

### Case study: a dead status route hid two untranslated strings until it was fixed

**Symptom.** #415 made the propagation-date refusal "refuse visibly". It delivered
nothing: the field snapped back and no message appeared anywhere.

**Wrong theories, in order.** (1) The panel was not emitting the rejection. (2) The
slot was not connected. (3) The signal had no receiver. All three were verified
correct — the emit fired, the slot ran, and the message was constructed.

**The key log line.** `[STATUS] set_status_message -> parent=QSplitter has_statusBar=False`,
which is what made it obvious the route terminated at a widget that cannot display
anything. Twenty-four other callers shared that route.

**Root cause.** `set_status_message` did a parent lookup instead of a signal. The
canvas's parent is the splitter, so the `hasattr` guard made the miss silent.

**Lesson, and the part worth keeping.** The interesting half is not the bug — it is
that the bug was a *hiding place*. A dead code path looks harmless, and fixing it
does not reveal what it was hiding; it publishes it, to every user, at once. Two of
the twenty-four suppressed strings were not translatable, and a German user saw
`Calibration complete` in English. Before repairing a silent no-op, enumerate what
it was suppressing. The guard that followed walks every `set_status_message` call
site by AST — because a bare literal is invisible to any scan for translations, and
that is how this survived one round of scanning.

Related: PF-UI-21, `tests/unit/test_status_literals_are_translated.py`.


