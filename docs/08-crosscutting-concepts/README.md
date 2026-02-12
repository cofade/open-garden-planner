# 8. Crosscutting Concepts

## 8.1 Coordinate System

**Origin**: Bottom-left corner of canvas (CAD convention)
**Y-axis**: Increases upward (mathematical/CAD convention, not screen coordinates)
**Units**: Centimeters internally, displayed as cm or m based on context

```python
@dataclass
class Point:
    x: float  # centimeters, positive = East/Right
    y: float  # centimeters, positive = North/Up (CAD convention)
    z: float = 0.0  # centimeters, elevation (unused in 2D, ready for 3D)
```

Qt's QGraphicsView uses Y-down screen coordinates. The canvas view applies a transform to flip the Y-axis for display while maintaining the CAD convention in the data model.

## 8.2 Command Pattern (Undo/Redo)

All modifications to the document are wrapped in command objects:

```python
class Command(ABC):
    def execute(self) -> None: ...
    def undo(self) -> None: ...

class MoveObjectCommand(Command):
    def __init__(self, obj: GardenObject, old_pos: Point, new_pos: Point): ...
```

- Every user action that modifies state creates a Command
- Commands are pushed onto an UndoStack (QUndoStack)
- Undo history clears on project close (standard behavior)
- Each vertex operation, property change, etc. is a separate undoable command
- The `CommandManager` is owned by `CanvasView` and shared with `CanvasScene` via `scene.get_command_manager()` so that `QGraphicsItem` subclasses can push commands directly when handling resize, rotation, or vertex-editing interactions
- Operations that change both geometry and position (e.g. scaling from a left handle) must be captured in a single command to avoid requiring multiple undos

## 8.3 Internationalization (i18n)

Uses Qt Linguist translation system:

1. All user-facing strings wrapped in `self.tr()` or `QCoreApplication.translate()`
2. Source strings extracted with `pylupdate6` into `.ts` XML files
3. Translators edit `.ts` files (Qt Linguist tool or text editor)
4. `.ts` files compiled to `.qm` binary with `lrelease`
5. `QTranslator` loaded at app startup based on saved language preference

**Shipped languages**: English (default), German
**Extensible**: Community can add languages by creating new `.ts` files

**Translation files location**: `translations/en.ts`, `translations/de.ts`

**Not translated**: Plant scientific names (Latin), file format identifiers

## 8.4 Theme System

Branded green color palette with light and dark variants:

| Color Role | Light Theme | Dark Theme |
|------------|-------------|------------|
| Primary | Garden green | Softer green |
| Surface | White/cream | Dark gray/slate |
| Text | Dark gray | Light gray |
| Accent | Complementary | Complementary |

Applied via QSS stylesheets. Theme preference stored in QSettings.

## 8.5 Graphics Asset Pipeline

### Plant SVGs
- AI-generated illustrations in consistent top-down garden style
- ~15-20 category-based shapes (deciduous, conifer, shrub, flower, etc.)
- ~10 unique popular species (rose, lavender, apple, cherry, etc.)
- Stored in `resources/plants/{category}/{name}.svg`
- Color-tinted at render time based on species data

### Textures
- Tileable PNG textures (256x256 or 512x512)
- Materials: grass, gravel, concrete, wood, stone, water, soil, mulch, sand
- Multiple LOD versions for different zoom ranges
- Loaded as QPixmap, applied via QBrush TexturePattern mode

### Object SVGs
- Furniture and infrastructure illustrations (top-down view)
- Stored in `resources/objects/{category}/{name}.svg`
- Rendered via QSvgRenderer into QGraphicsItem paint method

## 8.6 Development Workflow

### Feature Development Process

1. **Create feature branch**: `feature/US-X.X-short-description`
2. **Read user story** from roadmap
3. **Implement** with type hints
4. **Write tests**, run lint (`pytest tests/ -v && ruff check src/`)
5. **Manual testing** by user
6. **Commit** after approval: `feat(US-X.X): Description`
7. **Push and create PR** via GitHub CLI
8. **Merge with admin flag** (squash merge)
9. **Switch back to master**: `git checkout master && git pull`

### Code Quality Standards

- **Type hints**: All functions must have type annotations
- **Linting**: Code must pass ruff checks
- **Test coverage**: New code must maintain >80% coverage
- **Line length**: 110 characters (Black/ruff config)

### Git Workflow

- **master branch**: Always deployable, protected
- **Feature branches**: `feature/US-X.X-short-description`
- **Commits**: Small, atomic, conventional commit format
- **PRs**: Required for all changes, must pass CI

## 8.7 Error Handling

- Graceful degradation when APIs are unavailable
- Corrupted project files: partial load with warning
- Auto-save recovery on crash
- No silent failures: all errors logged and shown to user where appropriate

## 8.8 Settings Storage

User preferences stored via QSettings (platform-native):
- Window size, position, panel collapse states
- Recent files list
- Theme preference (light/dark)
- Language preference
- Auto-save interval
- Grid and snap settings
- Last used export options
