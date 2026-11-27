---
id: ADR-015
title: "Multi-nutrient Amendment Composition + User-toggleable Library"
status: "Accepted (Phase 12 — US-12.11)"
legacy_anchor: adr-015-multi-nutrient-amendment-composition--user-toggleable-library
---

# ADR-015: Multi-nutrient Amendment Composition + User-toggleable Library

**Status**: Accepted (Phase 12 — US-12.11)
**Context**: US-12.10c shipped a calculator that walked deficits in priority order and picked the *first matching unused* substance for each fix tag. This worked for single-nutrient organics (blood meal → N, bone meal → P, greensand → K) but silently mishandled real-world commercial fertilizers, where one bag carries N + P + K + Mg + S in a single product. The old "consume substance, decrement secondaries by 1 step" rule under-credited compound fertilizers and produced over-long lists. Users also wanted to disable substances they don't have on hand, and to add structural amendments (sand, perlite, vermiculite, diatomaceous earth) driven by a soil-texture rating.
**Decision**: Replace the pick-once-per-fix loop with a **deficit-map + greedy max-coverage** loop. Each iteration scores every unused candidate by the number of currently-outstanding nutrient deficits it touches; the breadth-leader is picked, its primary nutrient is fully closed (quantity scales with deficit), and co-fixed nutrients are credited at the same dose factor and recorded in `AmendmentRecommendation.credits`. The pool is filtered by a per-project `enabled_amendments` allowlist that the user manages from a checkbox panel embedded in the existing Amendment Plan dialog. A `prefer_organic` flag biases tie-breaks. A new `SoilTestRecord.soil_texture` field drives a structural-pick phase that runs after the nutrient phase.
**Alternatives considered**:
- *Linear-program optimal solver* (e.g. scipy.optimize.linprog) — would minimise total grams across all substances. Rejected: ≤24 substances × ≤7 nutrients is too small to justify a numpy/scipy build dependency, the greedy pick is provably optimal for the breadth metric, and users prefer "one bag covers most" reasoning over "two-half-bags covers slightly less".
- *Two-pass: organic first, then mineral* — clean conceptually but loses the "one compound substance covers multiple deficits" insight that motivated the rewrite.
- *Per-substance application_rate scaled by chemistry mass-balance (NPK %)* — would let the calculator do exact label-percentage math. Deferred: keeps the calculator's domain to "Rapitest level steps", avoids per-substance NPK% data entry on JSON, and the +1 step credit suffices for end-user purchasing decisions.
**Consequences**: Compound NPK fertilizers (Blaukorn, Tomatendünger, etc.) emit one row instead of three. Users see an honest "Raises N 1→3 + also raises P 1→3, K 1→3" rationale. Disabling substances changes both the inline preview and the cross-bed plan and shopping-list materials in real time. Soil-texture-driven structural picks add up to two rows for clayey soil (drainage + aeration), one row for sandy or compacted soil. Bundle data file grows by 12 entries (12 → 23 substances). No file-format bump; legacy projects load with `enabled_amendments=None` (= all enabled) and `soil_texture=None` (no structural picks).
