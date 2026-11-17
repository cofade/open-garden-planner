## Case study: One diagnostic click emitted 174 selections (#921) (2026-11-16)

**Symptom:** A showcase navigation test spent over 215 s under coverage and still reported XFAIL.

**Theories checked:** A ten-second wait alone explained the runtime; profiling instead located synchronous work inside navigation.

**Evidence:**

```text
[SELECT-921] wanted=174 signals=174 elapsed=17.009s
```

**Root cause:** replace_selection refreshed all consumers after every intermediate selected plant; unrestricted xfail also accepted the timeout.

**Fix:** Block intermediate scene signals, emit one final selectionChanged, and restrict the surviving defect markers to AssertionError. The counting test failed at 174 and passes at one.

**Lesson:** Count publications for a batch operation; never let an expected assertion absorb the hang guard.
