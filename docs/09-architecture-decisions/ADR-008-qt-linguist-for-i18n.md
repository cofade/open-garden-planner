---
id: ADR-008
title: "Qt Linguist for i18n"
status: "Accepted (Phase 6)"
legacy_anchor: adr-008-qt-linguist-for-i18n
---

# ADR-008: Qt Linguist for i18n

**Status**: Accepted (Phase 6)
**Context**: Need multi-language support (English + German initially).
**Decision**: Use Qt Linguist translation system (tr() calls, .ts/.qm files).
**Rationale**: Native Qt integration, industry standard for Qt apps, supports plurals and context, good tooling.
**Consequences**: All strings must be wrapped in tr(). Requires pylupdate6/lrelease build steps. Translation memory maintained in .ts XML files.

## Addendum - source-derived completeness for every registered locale (#496)

**Decision:** Keep Qt Linguist and the existing pure-Python singular compiler. Fresh
locked PyQt6 extraction plus bounded source AST declarations define required keys;
translation tables/catalogs cannot define their own required coverage. Source and
locale additions are symmetric: each registered target locale must complete every key.
The English template contains identities; retired records remain translation memory.

`i18n_catalog.py` shares strict state/key/format rules between checker and compiler.
Compilation rejects blanks and nonempty unfinished targets rather than substituting
English. The read-only gate compares compiled bytes and real Qt lookups. Active
numerus/variant entries fail explicitly until the compiler has tested plural support;
no second Qt binding or unpinned system lrelease dependency is introduced.

**Alternatives rejected:** catalog/word counts, German as source authority, trusting
the old English template, a union of all historical catalog keys, per-locale coverage
allowances, and an advisory CI job. All can hide omissions. `i18n_bindings.json` selects
actual finite source symbols/data fields and binds exact dynamic consumers; unresolved
or stale bindings fail rather than silently excluding a file.

**Consequences:** every new wrapped UI key needs all supported target translations in
the same PR. Existing English/German/Spanish catalogs were reconciled without grandfathered
gaps. Developer diagnostics remain English; linguistic quality, visual fit and truly
unwrapped text still require review. The existing required Test check owns enforcement.
Pinned by the translation gate unit/integration tests and registry-driven menu tests.
