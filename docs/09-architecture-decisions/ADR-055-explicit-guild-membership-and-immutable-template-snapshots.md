---
id: ADR-055
title: "Explicit guild membership and immutable template snapshots"
status: "Accepted for Package F2, October 2026. Additive `.ogp` version 1.4."
refs: ["#313"]
legacy_anchor: adr-055-explicit-guild-membership-and-immutable-template-snapshots-313
---

# ADR-055: Explicit guild membership and immutable template snapshots

**Status:** Accepted for Package F2, October 2026. Additive `.ogp` version 1.4.

**Decision.** A guild is metadata on plants, not a Qt group or bed. Each plant has at most one `{guild_id, role}` link. The centre additionally stores instance name and the complete versioned template snapshot. Saved instances remain usable without user template files, and library edits affect future insertions only. Membership does not alter parent-bed, child-list or stacking contracts.

Templates validate identities, versions, twelve role tokens, unique role functions, positive integer minima and finite positive centimetre radii (or `canopy_edge`). Stamps are limited to 200 plants including the centre. Bundled files validate eagerly; each user file is an Exception-catching trust boundary with logged filename/reason and visible picker errors. User files may override bundled IDs. Editor saves use fsync plus atomic replacement, and stay open on failure; file edits are outside the plan undo stack.

Layout is deterministic in CAD scene centimetres. Equal-radius slots are spaced evenly in template order. Canopy-edge means mature effective spacing: manual override before database spread/2. Missing spacing requires an explicit radius. Existing saved plants may have rectangular, polygon or path geometry; one base-shape bounds helper supplies centre positioning, footprint preflight and cosmetic badge/preview placement without painted shadow margins. Every species, existing-centre edit, layer and footprint is preflighted; invalid layouts are refused as a whole instead of clamping members independently. `InsertGuildCommand` composes canonical multi-plant creation with targeted membership snapshots in one undo step.

Coverage counts actual recorded functions on explicitly assigned plants, including the centre. A member counts once per function; multifunctional members can cover multiple requirements. Assigned role labels do not create evidence, and nearby unassigned plants do not count. Malformed saved metadata is preserved, excluded and reported as a data warning. Centre deletion preserves surviving plants and dissolves links in the same undo operation. Copy paths share deep-copy/remapping: complete copies get fresh guild IDs, partial copies omit links.

One parented/debounced coordinator computes guild status and applies idempotent runtime badges. Badges are cosmetic child items and do not alter the centre's bounds or rotation pivot. Companion Guilds, Diagnostics and MCP consume the same computed snapshot. A shared Qt-free converter owns all warning-record conversion, keeping API messages English and translating UI messages separately. MCP reads never recompute domain logic.

**Alternatives rejected.** Nearby-radius membership silently changes requirements as plants move; a Qt group would move members together and compete with bed parentage; re-resolving template files on load would mutate existing plans. Fake function coverage from role labels would claim validation without checking facts.

**Evidence.** Guild workflow, layout/trust-boundary, copy/persistence, real MCP, golden eight-parent and rotated badge tests. Agronomic limitations and template authoring are documented in §8.26.
