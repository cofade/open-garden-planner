---
id: ADR-068
title: "Audit boundaries, responsibility extraction and progressive agent context"
status: "Shipped in v1.34.5 (PR #640) after full manual-test confirmation, independent senior review, and protected merge."
refs: ["#392"]
legacy_anchor: adr-068-audit-boundaries-responsibility-extraction-and-progressive-agent-context-392
---

# ADR-068: Audit boundaries, responsibility extraction and progressive agent context

**Status**: Shipped in v1.34.5 (PR #640) after full manual-test confirmation, independent senior review, and protected merge.

**Context**: A4 (#456) precedes A6 (#458) and A7 (#459). Current measurements
replace the historical audit's line/import counts. A9 (#461) needs representative
workloads, A12 (#464) needs smaller loading units without losing knowledge, and
A13 (#465) must describe continuity without assigning privileges.

**Decision**:
1. **Shared leaves preserve identity.** `config.settings` and `config.paths`
   own configuration and safe dialog paths; `app.settings`/`app.paths` alias the
   exact module objects. Mutable isolation bindings therefore reach one factory.
   `models.theme`, `models.parametric_eval` and `models.storage_paths` own the
   Qt-free values/evaluator/data-directory resolver. The old evaluator module
   also aliases its implementation. ADR-041's factory and isolation rules remain
   binding. Core/tool exports are lazy, with explicit static-typing exports.
2. **Static boundary enforcement.** `check_import_boundaries.py` checks eager
   module/class imports, including relative imports, conditionals and try blocks.
   Local and `TYPE_CHECKING` adapters remain permitted. The exception baseline
   is empty. Since #792 it also follows the eager imports of the modules listed
   in `QT_CORE_ONLY` and fails when one reaches `QtWidgets` or `QtGui` (a parent
   package's `__init__` is not followed). The permitted layer graph is acyclic; this does not claim that all
   deferred runtime imports are cycle-free or that dynamic imports are analyzed.
3. **Extract responsibilities through composition.** `ClipboardOperations`,
   `DragConstraints`, `PropertyEdits` and `AgentHost` have an explicit typed host.
   Hosts retain document, widget, bridge and server state and compatibility
   methods. There is no attribute-forwarding proxy or duplicate state. The
   command/serialization/geometry paths remain canonical; the property dispatcher
   delegates to named handlers after its characterization net passes. Shared
   repeat-menu actions retain literal translation contexts and shape-specific
   guards. Handle primitives, vertex/midpoint/curve editing and resize/rotation
   have separate owners; existing imports return the same classes/functions.
4. **Keep the instruments attached.** Source censuses, mutation targets, child
   isolation hooks, spies and cleanup scopes follow defining modules. Real MCP
   transport and pending-hop shutdown tests remain mandatory. Moved UI strings
   use their original explicit Qt translation contexts. No type allowances are
   increased: newly extracted modules pass the existing zero-allowance rule.
5. **Measure performance honestly.** The committed harness records every sample,
   machine/profile, source versus frozen startup, native/headless Qt, traced
   versus untraced execution, RSS and callbacks. Startup means a shown canvas,
   synchronous repaint and an event-loop callback; launch timing includes the
   executable's bootstrap. Fresh processes do not imply a cold filesystem cache.
   Measured repeated theme work justifies a post-show palette/title-bar refresh
   without another stylesheet/listener pass. Targets remain targets when a
   measured machine misses them; no universal flaky timing assertion is added.
6. **Progressive disclosure with provenance.** Large skill bodies move into
   mirrored indexed references, after recursive citation discovery is extended.
   Every original normalized body was reconstructed exactly before citation/link
   repairs. `quality/context-migration.json` records original/current hashes;
   tests pin the retained fragments. Root handoff narrative has a complete
   snapshot. Root context warns at 28 KiB and fails above the 32 KiB soft budget,
   below the configured 64 KiB reader cap; skill entries also cap at 32 KiB.
   New historical lessons get their own references and index rows. Required
   method/runbook rules remain discoverable from each entry point.
7. **Review and authorization are distinct.** Changes touching >30 production
   files, >1000 non-generated lines, several subsystems or new public APIs need
   design-stage review and named semantic slices. Counts trigger scrutiny; they
   never grant approval. Record review rounds, SHA, findings and dispositions.
   `check_delivery_state.py` verifies the actual draft/base/head/closing-keyword
   handoff. Local rules still cannot infer owner approval or private account
   recovery. No host permission hook is invented, no grant is changed, and no
   draft is made ready automatically. Existing manual-test/protected-merge rules
   remain in force.

**Alternatives considered**:
- Re-exporting settings globals by value: rejected because isolation would split
  factory state and could address the owner's real settings store.
- Dynamic host proxies, copied construction/geometry paths, or increasing mypy
  allowances after extraction: rejected; they hide coupling or erase the ratchet.
- Deleting historical skills/pickups or enlarging the citation window: rejected.
  Shared repeated facts instead have one exact-AST record, while line citations
  retain the original 20-line window.
- Claiming a backup maintainer or private recovery setup: rejected without
  explicit nomination and evidence. The runbook identifies owner-only actions.

**Consequences**: No dependency, file-format, permission or release-right change.
The public UI and MCP behavior retain their existing contracts. A9's opt-in
`--benchmark-startup` exits after measurement using its own temporary settings
identity; ordinary startup never takes that path. Evidence and all finding
dispositions live in `audits/2026-10/audit-392-remaining.md`; the historical audit
snapshot remains unchanged. Each package closes only through its complete,
reviewed draft PR and owner acceptance.

## ADR-056 addendum - exact soil-plane receiver exposure (#641, PR #645)

The ground heatmap remains at z=0. Per-plant exposure receives the canonical
`item_base_cm` soil elevation and evaluates caster slices above that plane,
while retaining the existing self and soil-holder exclusions. Equal elevations
share a sweep. Five-centimetre bands were rejected during review: a 38 cm
receiver rounded to 40 cm lost a 39 cm obstacle and gained 210 false minutes
of sun in the boundary regression. No approximation budget authorizes that
change. Vertical-translation equivalence at sub-centimetre and bed-height
boundaries is pinned in `tests/unit/test_sun_exposure_base.py`; the real-window
workflow is in `tests/integration/test_sun_exposure_raised_soil.py`.

## ADR-065 addendum - rounded gravel relief (#605, PR #645 owner pass)

The earlier deferred gravel chord/square-end observation is resolved. The 2D
gravel painter already paints a round stroke rim; changing its outline to
match a chord would change the owner's plan picture. Gravel relief now follows
the canonical `polyline_round_outline` boundary (also used for lawn cut-outs),
with the existing bevelled rim section swept inward around outer and hole
rings. Round joins and end caps are included. Width, height, tint and material
semantics are unchanged; the analytical square/butt caster footprint remains
unchanged too.

Visible rim arcs use 0.01 cm tolerance; existing cut-out callers retain 0.5 cm.
A preflight bounds angular subdivision work and a second guard bounds output
to 4096 outline vertices. Beyond that budget, the accurate flat painted path
remains without raised edging, as for other unbounded relief. Record stroke
width is bounded at 1e6 cm; the maximum admitted width is safely rejected by
the arc budget before outline allocation.

The old nominal-footprint-plus-10-cm gravel gate was the wrong reference. It is
replaced by a <=0.05 cm reach check against the painted round outline, plus
independent Qt round-stroke coverage/exclusion tests for bends, caps, short
legs, duplicates, self-crossings and loops in
`tests/integration/test_gravel_rim_relief.py`. A chord can fit the nominal
footprint while visibly crossing the gravel interior; both coverage and
exclusion are required.
