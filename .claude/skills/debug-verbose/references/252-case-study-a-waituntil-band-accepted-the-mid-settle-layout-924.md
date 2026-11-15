## Case study: a waitUntil band accepted the mid-settle layout (#924, fixed 2026-11-15)

**Symptom:** master's Coverage partition (1) failed one test in the same run that lost the
forecast-holder workers (#898):

```text
FAILED tests/integration/test_chrome_layout.py::test_todays_tasks_shows_whole_rows_not_one_and_a_half
E   assert 100 == (92 + (2 * 0))
E    where 100 = <_FittedScrollArea>.height()
E    and 92 = <QWidget>.sizeHint().height()
E    and 0 = <_FittedScrollArea>.frameWidth()
```

The identical tree passed in run 43646470225 thirty minutes earlier, and the chore commit
changed only version strings and documentation.

**Wrong theories:** font metrics or platform frame width (the difference is 8 px, not 1); the
content's `sizeHint` being stale (that is exactly what `_FittedScrollArea` exists to prevent);
a scrollbar taking the space (its later assertion would also be wrong).

**Key trace:** the test waited with

```python
qtbot.waitUntil(lambda: scroll.height() < calendar._DASHBOARD_MIN_H + 20, timeout=3000)
assert scroll.height() == scroll.widget().sizeHint().height() + 2 * scroll.frameWidth()
```

`_DASHBOARD_MIN_H` is 84, so the wait accepted anything below 104 px. It returned at 100 px while
the content's hint was already 92 px; the next line read the still-settling 100 px. The first
wait had the same shape (`> floor`, then exactly the cap).

**Root cause:** the wait predicate named a neighbouring band, while the assertion named the
exact final value. The wait could return during the layout transition it was supposed to drain.

**Fix:** both waits now wait for the exact expression they assert, with the same 3000 ms bound.

**Lesson:** when a test knows the final layout value, the `waitUntil` predicate must carry that
value, not a band around it. A band does not make the wait more robust; it moves the failure to
the next line, where the report no longer names the race. Pins:
`tests/integration/test_chrome_layout.py::test_todays_tasks_shows_whole_rows_not_one_and_a_half`.
Pitfall: PF-TST-37.
