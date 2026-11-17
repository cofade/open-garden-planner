## Case study: A nested pytest guard started another worker pool (#921) (2026-11-17)

**Symptom:** A bounded Windows QA run still exhausted commit memory. The broken-QML
positive control expected pytest exit 1 but received internal-error exit 3.

**Theories checked:** Reducing the outer runner to one process was insufficient.
The captured child command had no worker override and read the repository's
`-n auto` again, independently of the outer command.

**Evidence:**

```text
created: 20/20 workers
ImportError: DLL load failed while importing QtTest: ... paging file is too small ...
assert 3 == 1
```

The outer process was already running with `-n 0`. The child started another full
pool, then replaced crashing workers. The same QA session separately recorded
tiny NumPy allocation failures followed by four isolated passes. The nested pool
is a reproduced additional source of commit pressure; the logs do not attribute
every earlier allocation failure to this specific child.

**Fix:** Pass `-n 0` in the broken-scene control's own subprocess argv. Keep its
exit-1 assertion, minimum failed-test count, zero-skips requirement and named
`did not load` cause. The failure must come from the deliberately broken QML.

**Lesson:** A subprocess inherits environment and repository configuration, not
its parent's pytest CLI overrides. Bound every nested pytest invocation explicitly.
The existing negative control pins both the failing-engine semantics and its
ability to finish without a second worker pool.
