# 10. Quality Requirements

## 10.1 Quality Tree

```
Quality
├── Usability
│   ├── Intuitive UI (first-time user can draw in < 5 minutes)
│   ├── Keyboard shortcuts for all actions
│   └── Multilingual (EN + DE)
├── Performance
│   ├── Smooth canvas (60fps pan/zoom with 500 objects)
│   ├── Fast save/load (< 2 seconds typical)
│   └── Responsive UI (no blocking operations)
├── Reliability
│   ├── No data loss (auto-save recovery)
│   ├── Graceful degradation (offline mode)
│   └── Robust file handling (corrupted file recovery)
├── Maintainability
│   ├── Clean architecture (layered, typed)
│   ├── Comprehensive tests (>80% coverage)
│   └── Contributor-friendly code
└── Portability
    ├── Windows 10/11 (primary)
    └── Future: macOS, Linux
```

## 10.2 Performance Requirements

| ID | Requirement | Target |
|----|------------|--------|
| NFR-PERF-01 | Smooth canvas interaction (pan/zoom) | 60fps with up to 500 objects |
| NFR-PERF-02 | File save/load time | < 2 seconds for typical projects |
| NFR-PERF-03 | PNG export time | < 5 seconds for high-resolution output |
| NFR-PERF-04 | Memory usage | < 500MB for typical projects; an idle plan (no input) must reach a **quiescent state** — 0 `scene.changed` emissions and 0 minimap renders per 2 s after a 1.5 s settle (issue #305, `tests/integration/test_idle_scene_quiescence.py`) |
| NFR-PERF-05 | Startup time | < 3 seconds on modern hardware |

## 10.3 Reliability Requirements

| ID | Requirement | Target |
|----|------------|--------|
| NFR-REL-01 | Crash recovery | No data loss via auto-save |
| NFR-REL-02 | Corrupted files | Partial load with user warning |
| NFR-REL-03 | Offline functionality | Core features work without internet |

## 10.4 Maintainability Requirements

| ID | Requirement | Target |
|----|------------|--------|
| NFR-MAINT-01 | Architecture | Modular, layered separation |
| NFR-MAINT-02 | Test coverage | >80% on non-UI code |
| NFR-MAINT-03 | Documentation | Docstrings + arc42 architecture docs |
| NFR-MAINT-04 | Type safety | Type hints throughout, mypy strict |

Measured baseline (2026-10-03, `84ead2e`): non-UI coverage 80.2 % lines / 66.4 % branches (every package except `ui`); `mypy --strict` 2 104 errors in 134 of 248 files. Neither number is enforced in CI today. Scorecard and method: [audit-2026-10.md](../11-risks-and-technical-debt/audit-2026-10.md) §3; numbers: `audit-2026-10-metrics.json` beside it, re-run with `scripts/audit_metrics.py`.

## 10.5 Extensibility Requirements

| ID | Requirement | Target |
|----|------------|--------|
| NFR-EXT-01 | Plugin architecture | Post-v1.0 enhancement |
| NFR-EXT-02 | New object types | Supported without schema changes |
| NFR-EXT-03 | Custom renderers | Rendering pipeline supports extensions |

## 10.6 Testing Strategy

### Unit Tests (pytest)
- **Geometry module**: Point operations, polygon area, distance calculations, transformations, snapping
- **Command system**: Execute/undo/redo for all command types, edge cases
- **Object model**: Creation, modification, serialization of all object types
- **File I/O**: Serialization round-trips, backward compatibility, corrupted file handling
- **Export**: Output validation for PNG, SVG, CSV
- **Plant data**: API response parsing, caching, fallback logic

### Integration Tests
- **Plant API**: Mock server responses, timeout handling, cache invalidation
- **Document operations**: Full workflow tests (create, modify, save, load, export)
- **Multi-object operations**: Selection, grouping, layer operations

### UI Tests (pytest-qt)
- **Canvas interactions**: Pan, zoom, click, drag operations
- **Tool behavior**: Each drawing tool's complete workflow
- **Panel updates**: Properties panel reflects selection, layer panel syncs
- **Keyboard shortcuts**: All shortcuts function correctly

### Manual Testing Checklist
Each feature requires hands-on testing before completion:
- [ ] Feature works as specified
- [ ] Undo/redo functions correctly for all operations
- [ ] Edge cases handled gracefully
- [ ] UI updates correctly in all scenarios
- [ ] No performance regression

### CI/CD Quality Gates
- **On every push and PR** (`ci.yml`, as of 2026-10-03): agent-context parity, ruff over `src/`, the full
  pytest suite (Linux, Qt offscreen), Bandit at HIGH severity, and the committed-secrets scan. The frozen-exe
  gate runs on Windows only, locally before merge and in `release.yml` after it (change-control §2.8).
- **Not enforced in CI**: mypy and coverage are configured in `pyproject.toml` but no CI step runs them
  (tracked in #401 and #402; register rows TD-020, TD-021).
- **Coverage target**: >80 % on non-UI code (NFR-MAINT-02) is a target the §11.3 register tracks, not a gate;
  "non-UI" means every package except `ui` until #402 defines it.
