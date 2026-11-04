## Case study: compiled catalogs passed while current UI keys were missing (#496)

**Symptom.** A newly registered Russian locale passed existing tests while current UI
labels remained English. The contributor guide incorrectly said all locales were checked.

**Wrong theories.** A successful compile and the absence of unfinished German entries
were not evidence of source coverage. No alternative runtime theory was adopted before
the extraction/compilation probes.

**Evidence.** Fresh standard extraction found 36 keys absent from German; tagged
`[496-INVENTORY] 2631` output included audited helper/table and bundled species sources.
Six regressions failed first: blank/whitespace targets, nonempty unfinished targets,
missing placeholders, vanished output and the third-language German reason fallback.

**Root cause.** Required keys came from stale catalogs rather than independent source.
The compiler synthesized source fallbacks and did not enforce translation state. The
companion service used a binary English/else-German language choice.

**Fix.** Derive source keys, bind finite dynamic sources to their production tables,
validate every registered locale and compiled lookup, and reject unresolved sources.
Compile only completed active records. Select German reasons only for de. Temporary
tagged probes were kept outside production; no debug prints remain in committed code.

**Lesson.** Test both additions to the source axis and additions to the locale axis.
An equal count or a fixture generated from an incomplete catalog cannot prove coverage.
Pinned by the translation gate unit/integration tests and the required Test check.

