## Package F1/F2 seams (ADR-054/055)

The canonical plant construction seam is `ui/plant_creation.py`: gallery and
Plant Lists drops and guild stamps share species snapshots, size/date and semantic
layer selection. Creation commands own `_auto_parent_plant`; guild links never
change Qt parenting, bed IDs, child IDs or stack ranks.

Trait controls use `ui/plant_traits.py` and `ChangePropertyCommand` with copied
snapshots. `core/guild_commands.py` owns insertion/membership; deleting a centre
composes survivor-link cleanup into `DeleteItemsCommand`. `ui/guild_copy.py` and
`models/guild.py::remap_copied_guilds` provide the one copy rule for paste,
duplicate, arrays and mirrors: complete copies get independent IDs/snapshots,
partial copies lose membership.

`ui/guild_coordinator.py` computes runtime status once, debounced and idempotent.
Badge children never enter serialization or resize/pivot geometry. The panel and
API share Qt-free `services/diagnostics.py` conversion of cached flags; MCP reads
must not recompute. Grouped-centre warnings navigate to the top-level group while
retaining the physical centre ID in structured details. Document clearing drops
guild caches at `CanvasScene.clear()`. Curated traits are read-only API fields;
there are no new trait/guild write tools or authentication changes.
