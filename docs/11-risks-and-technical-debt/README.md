# 11. Risks and Technical Debt

## 11.1 Open Questions

| Question | Impact | Resolution Path |
|----------|--------|-----------------|
| Trefle.io rate limits and reliability? | Plant search UX | Test API, implement robust caching, Permapeople as fallback, bundled DB as last resort |
| Texture licensing for fill patterns? | Legal | Use AI-generated or CC0/public domain textures, document sources |
| DXF export complexity for future versions? | Interoperability | Evaluate ezdxf library, may need simplification |
| Qt6 3D capabilities vs dedicated engine? | Future 3D feature | Prototype with Qt3D, evaluate PyVista as alternative |
| Bundled plant database source? | Offline functionality | Evaluate USDA Plants Database, consider one-time Trefle.io bulk export |
| AI-generated SVG quality consistency? | Visual appeal | Test with multiple prompts, establish style guide, manual cleanup if needed |
| NSIS installer signing? | Trust/distribution | Unsigned initially, document for users; investigate free code signing options |

## 11.2 Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| PyQt6 licensing complexity (GPL/Commercial) | Medium | High | Use GPLv3, document clearly, ensure compliance |
| Performance with very large images | Medium | Medium | Implement image tiling/downsampling at zoom levels |
| Scope creep delaying v1.0 | High | High | Strict phase adherence, defer nice-to-haves to Phase 7 |
| Limited development time | High | Medium | Focus on quality over speed, attract contributors |
| Project not attracting contributors | Medium | High | Excellent documentation, clean code, contributor guide, CI/CD |
| External API deprecation | Low | Medium | Fallback chain: Trefle -> Permapeople -> Bundled DB |
| AI-generated SVGs inconsistent quality | Medium | Medium | Establish style reference set, manual review/cleanup |
| Windows installer blocked by SmartScreen | Medium | Low | Document workaround, investigate signing options |
| Large bundle size from PyInstaller | Medium | Low | Optimize includes, strip unused Qt modules |

## 11.3 Technical Debt

| Item | Area | Description | Priority |
|------|------|-------------|----------|
| TD-001 | Plant rendering | Plants currently rendered as flat colored circles | High (Phase 6 addresses) |
| TD-002 | Textures | Procedural patterns are too subtle, barely visible | High (Phase 6 addresses) |
| TD-003 | Plant cache | SQLite cache for plant API data not yet implemented | Medium |
| TD-004 | Object model | Some object types share code that could be better abstracted | Low |
| TD-005 | Test coverage | Some UI components lack automated tests | Medium |
| TD-006 | Error messages | Some error messages are technical, not user-friendly | Low |

## 11.4 Known Development Pitfalls

Hard-won lessons from implementation. Read these before modifying the related subsystems.

- **Release workflow race condition with chore commits**: After merging a feature PR, two chore commits are pushed (sync version + mark progress). These land ~37s after the PR merge but the Release workflow building the new tag takes ~2m50s. The chore-commit Release runs start while the tag doesn't exist yet, compute a stale version (e.g., `v1.8.4` instead of `v1.9.2`), and fail with "release with the same tag name already exists". Fixed by adding `if: "!startsWith(github.event.head_commit.message, 'chore:')"` to the release job, which skips the workflow for chore commits.

- **Anchor index on same-type anchors**: When multiple anchors share the same `AnchorType` (e.g. rectangle corners are all `CORNER`, polygon vertices are all `CORNER`, polyline vertices are all `ENDPOINT`), each must have a unique `anchor_index` in `get_anchor_points()`. Without it, `DimensionLineManager._resolve_anchor_position()` falls back to type-only matching and picks the first anchor. Always pass `anchor_index=i` when creating `AnchorPoint` for same-type anchors.

- **Dimension line updates after undo/redo**: `CommandManager.command_executed` only fires on `execute()`, NOT on `undo()`/`redo()`. Dimension line updates must also be connected to `can_undo_changed`/`can_redo_changed` signals.

- **3-anchor constraints not solved on add**: `_compute_constraint_solve_moves()` in `canvas_view.py` collects `constrained_ids` from `anchor_a` and `anchor_b` only. Any constraint with a third anchor (`anchor_c`, e.g. ANGLE) must also add `anchor_c.item_id` here, otherwise the third item is absent from `item_positions` and the solver cannot move it — showing as red/violated until the user manually drags an object.

- **Canvas Y-axis flip**: The view applies `scale(zoom, -zoom)` so **positive scene Y is visually upward** on canvas (CAD-style, origin bottom-left). When computing directional offsets from user-facing angles (e.g. linear array), negate `dy`: `dy = -spacing * sin(angle_rad)` so that 0°=right, 90°=down, 180°=left, 270°=up matches screen-space intuition. The canvas rect in scene coords is `QRectF(0, 0, width_cm, height_cm)` accessed via `self._canvas_scene.canvas_rect`.

## 11.5 Community and Governance

**Feature Requests**: Open to community input, pivots, and voting. The goal is to avoid a dead project — community engagement is welcome.

**Contribution Model**:
- GitHub Issues for bug reports and feature requests
- Pull requests welcome with review process
- Clear CONTRIBUTING.md with code style, testing requirements
- All PRs must pass CI (tests, linting, type checking)
