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

## 11.4 Community and Governance

**Feature Requests**: Open to community input, pivots, and voting. The goal is to avoid a dead project — community engagement is welcome.

**Contribution Model**:
- GitHub Issues for bug reports and feature requests
- Pull requests welcome with review process
- Clear CONTRIBUTING.md with code style, testing requirements
- All PRs must pass CI (tests, linting, type checking)
