## Case study: Autosave recovered only scene geometry (#797) (2026-11-16)

**Symptom:** A recovered plan lost its non-scene records.

**Theories checked:** Recovery might merge the original file's stores. Reading the loader showed it loads the autosave alone.

**Evidence:**

```text
[AUTOSAVE-797] temporary_manager=True saved_location=None live_location={...Berlin...}
```

**Root cause:** A fresh ProjectManager serialized only the scene, bypassing the live metadata builder.

**Fix:** Bind the live manager and call recovery_dict, with Save's pending-edit flush and complete builder. Pin every ProjectData field and compare recovery to normal Save.

**Lesson:** Snapshot the document through its canonical owner; a scene is only part of a plan.
