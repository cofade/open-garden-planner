# 6. Runtime View

## 6.1 Drawing Workflow

```
User selects tool (e.g., Rectangle Tool)
    │
    ├── ToolManager activates RectangleTool
    ├── Canvas cursor changes to crosshair
    │
    v
User clicks first point on canvas
    │
    ├── Tool captures start coordinate (scene coords)
    ├── Preview rectangle drawn (rubber band)
    │
    v
User clicks second point (or drags)
    │
    ├── Tool calculates final geometry
    ├── Creates AddObjectCommand with Rectangle data
    ├── Command pushed to UndoStack
    ├── Command.execute() creates RectangleItem in scene
    ├── Scene emits objectAdded signal
    └── Properties panel updates if auto-select enabled
```

## 6.2 Save/Load Flow

### Save
```
User triggers Save (Ctrl+S)
    │
    ├── ProjectManager.save()
    ├── Serialize all scene objects → JSON
    ├── Include: layers, objects, metadata, background images (base64)
    ├── Write to .ogp file (atomic write via temp file)
    └── Status bar shows "Saved"
```

### Load
```
User opens .ogp file
    │
    ├── ProjectManager.load()
    ├── Parse JSON, validate version
    ├── Clear current scene
    ├── Reconstruct layers
    ├── Reconstruct objects → create QGraphicsItems
    ├── Reconstruct background images
    ├── Fit view to content
    └── UndoStack cleared (fresh session)
```

## 6.3 Plant API Integration Flow

```
User searches for plant species
    │
    ├── Check local SQLite cache first
    │   ├── Cache hit → return cached data
    │   └── Cache miss → continue
    │
    ├── Try Trefle.io API (primary)
    │   ├── Success → cache result, return data
    │   └── Failure → try fallback
    │
    ├── Try Permapeople API (secondary)
    │   ├── Success → cache result, return data
    │   └── Failure → try fallback
    │
    ├── Check bundled plant database
    │   ├── Found → return data
    │   └── Not found → continue
    │
    └── Allow manual entry (user creates custom species)
```

## 6.4 Export Flow

```
User triggers Export (File → Export as PNG/SVG)
    │
    ├── Export dialog shown (format, DPI, options)
    ├── User configures and confirms
    │
    ├── [PNG] QGraphicsScene.render() → QImage → save as PNG
    │   └── Options: DPI (72/150/300), include/exclude grid
    │
    ├── [SVG] QSvgGenerator renders scene
    │   └── Options: include/exclude annotations
    │
    └── [CSV] Iterate plant objects → extract metadata → write CSV
```

## 6.5 Undo/Redo Flow

```
User performs action (e.g., move object)
    │
    ├── Tool creates MoveObjectCommand(obj, old_pos, new_pos)
    ├── UndoStack.push(command)
    │   ├── command.execute() applies the change
    │   └── Redo stack cleared (new branch)
    │
    v
User presses Ctrl+Z (Undo)
    │
    ├── UndoStack.undo()
    │   ├── command.undo() reverses the change
    │   └── Command moved to redo stack
    │
    v
User presses Ctrl+Y (Redo)
    │
    ├── UndoStack.redo()
    │   ├── command.execute() re-applies the change
    │   └── Command moved back to undo stack
```

## 6.6 Auto-Save Flow

```
Timer fires every N seconds (configurable)
    │
    ├── Check if document has unsaved changes
    │   └── No changes → skip
    │
    ├── Serialize current state to temp file
    │   └── Path: ~/.open-garden-planner/autosave/<project-hash>.ogp
    │
    └── On next successful manual save, remove auto-save file

On startup:
    │
    ├── Check for auto-save files
    │   └── Found → prompt user: "Recover unsaved changes?"
    │       ├── Yes → load auto-save
    │       └── No → delete auto-save, proceed normally
```
