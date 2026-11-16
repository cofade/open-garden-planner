## Case study: The translation gate walked each AST nine times (#922) (2026-11-16)

**Symptom:** The full source/catalog/binary check used 92 s under CI coverage.

**Theories checked:** Catalog parsing and compiled Qt lookups were the suspected bottleneck. The profile instead spent almost all time in source inventory.

**Evidence:**

```text
[I18N-922] baseline=192279127 calls/61.561s; indexed=63710952 calls/26.921s (branch coverage + cProfile)
```

**Root cause:** Each source audit and import-wrapper audit walked the same immutable tree repeatedly.

**Fix:** Build one node/parent index per inventory. The counting guard failed at nine walks per file and passes at one; missing keys, stale bindings and actual compiled lookups remain checked.

**Lesson:** Profile before splitting a gate; share immutable work within the invocation without caching stale source globally.
