# Adding a New Language to Open Garden Planner

This guide explains how to add a new translation language to the application.

## Overview

Open Garden Planner uses Qt's i18n system:
- **`.ts` files** — XML source files containing translatable strings (edited by translators)
- **`.qm` files** — compiled binary files loaded at runtime by `QTranslator`
- **`pylupdate6`** — extracts marked strings from Python source into `.ts` files
- **`scripts/compile_translations.py`** — compiles `.ts` to `.qm` (pure-Python replacement for `lrelease`)

Translation files live in `src/open_garden_planner/resources/translations/`.

## Step-by-Step: Adding a Language

### 1. Register the language

Edit `src/open_garden_planner/core/i18n.py` and add your language to `SUPPORTED_LANGUAGES`:

```python
SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "de": "Deutsch",
    "fr": "Fran\u00e7ais",  # <-- new
}
```

Use the **native name** (how speakers of that language write it) as the value.

### 2. Extract strings into a new `.ts` file

Run `pylupdate6` from the project root:

```bash
venv/Scripts/pylupdate6 \
    --ts src/open_garden_planner/resources/translations/open_garden_planner_fr.ts \
    src/open_garden_planner/
```

This creates a `.ts` XML file with all `self.tr()` and `QCoreApplication.translate()` strings.

### 3. Add manually-maintained strings

`pylupdate6` cannot extract strings from:
- **`QT_TR_NOOP()`** calls at module level without a class context (e.g., `object_types.py`)
- **Helper functions** that wrap `QCoreApplication.translate()` (e.g., gallery panel `_tr()`)

These strings are maintained in `scripts/fill_translations.py` under the `"ObjectType"` and expanded `"GalleryPanel"` contexts. After running `pylupdate6`, run the fill script or manually add these contexts to your `.ts` file.

### 4. Translate the strings

Open the `.ts` file in a text editor or Qt Linguist and fill in all `<translation>` elements. Each entry looks like:

```xml
<message>
    <source>Save the current project</source>
    <translation type="unfinished" />
</message>
```

Replace the empty translation tag:

```xml
<message>
    <source>Save the current project</source>
    <translation>Enregistrer le projet actuel</translation>
</message>
```

Remove `type="unfinished"` once the translation is complete.

**Guidelines:**
- Keep `{placeholder}` variables unchanged (e.g., `{count}`, `{path}`)
- Preserve `&` accelerator keys in menu items (e.g., `&File` -> `&Fichier`), avoiding conflicts within the same menu
- HTML tags (`<b>`, `<br>`, `<p>`) should be preserved
- Plant scientific names (Latin) are **not translated**
- Keyboard shortcuts (Ctrl+S, F11, etc.) are **not translated**

### 5. Compile to `.qm`

```bash
venv/Scripts/python scripts/compile_translations.py
```

This compiles all `.ts` files in the translations directory to `.qm` binary files.

### 6. Test

```bash
# Run the app with your language
venv/Scripts/python -m open_garden_planner

# In the app: View > Language > select your language
# Restart the app to see the translation
```

Run the test suite to verify nothing is broken:

```bash
venv/Scripts/python -m pytest tests/ -v
```

### 7. Update tests

Add your language code to the assertions in `tests/unit/test_i18n.py` if desired (the existing tests dynamically check all entries in `SUPPORTED_LANGUAGES`).

## File Reference

| File | Purpose |
|------|---------|
| `src/open_garden_planner/core/i18n.py` | Language registry, translator loading |
| `src/open_garden_planner/app/settings.py` | Persists language preference |
| `src/open_garden_planner/app/application.py` | Language submenu in View menu |
| `src/open_garden_planner/resources/translations/*.ts` | Translation source files |
| `src/open_garden_planner/resources/translations/*.qm` | Compiled translation binaries |
| `scripts/compile_translations.py` | `.ts` to `.qm` compiler |
| `scripts/fill_translations.py` | Translation mapping + fill helper |

## String Wrapping Patterns

When adding new UI strings to the codebase:

| Context | Pattern |
|---------|---------|
| Inside a `QObject` subclass method | `self.tr("text")` |
| Module-level constant | `QT_TR_NOOP("text")` + translate at display time |
| Non-QObject function | `QCoreApplication.translate("ContextName", "text")` |
| f-string with variables | `self.tr("text {var}").format(var=value)` |

After adding new strings, re-run `pylupdate6` to update the `.ts` files, then recompile.
