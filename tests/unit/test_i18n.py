"""Tests for internationalization (i18n) infrastructure."""

from open_garden_planner.core.i18n import _TRANSLATIONS_DIR, SUPPORTED_LANGUAGES, load_translator
from open_garden_planner.core.object_types import ObjectType, get_translated_display_name


class TestSupportedLanguages:
    """Tests for the supported languages configuration."""

    def test_contains_english(self, qtbot) -> None:  # noqa: ARG002
        assert "en" in SUPPORTED_LANGUAGES

    def test_contains_german(self, qtbot) -> None:  # noqa: ARG002
        assert "de" in SUPPORTED_LANGUAGES

    def test_english_native_name(self, qtbot) -> None:  # noqa: ARG002
        assert SUPPORTED_LANGUAGES["en"] == "English"

    def test_german_native_name(self, qtbot) -> None:  # noqa: ARG002
        assert SUPPORTED_LANGUAGES["de"] == "Deutsch"

    def test_at_least_two_languages(self, qtbot) -> None:  # noqa: ARG002
        assert len(SUPPORTED_LANGUAGES) >= 2


class TestTranslationFiles:
    """Tests for the existence of translation files."""

    def test_translations_directory_exists(self, qtbot) -> None:  # noqa: ARG002
        assert _TRANSLATIONS_DIR.is_dir()

    def test_german_ts_file_exists(self, qtbot) -> None:  # noqa: ARG002
        ts_file = _TRANSLATIONS_DIR / "open_garden_planner_de.ts"
        assert ts_file.exists(), f"German .ts file not found at {ts_file}"

    def test_english_ts_file_exists(self, qtbot) -> None:  # noqa: ARG002
        ts_file = _TRANSLATIONS_DIR / "open_garden_planner_en.ts"
        assert ts_file.exists(), f"English .ts file not found at {ts_file}"

    def test_german_qm_file_exists(self, qtbot) -> None:  # noqa: ARG002
        qm_file = _TRANSLATIONS_DIR / "open_garden_planner_de.qm"
        assert qm_file.exists(), f"German .qm file not found at {qm_file}"

    def test_english_qm_file_exists(self, qtbot) -> None:  # noqa: ARG002
        qm_file = _TRANSLATIONS_DIR / "open_garden_planner_en.qm"
        assert qm_file.exists(), f"English .qm file not found at {qm_file}"

    def test_german_ts_has_no_unfinished(self, qtbot) -> None:  # noqa: ARG002
        """All translations in the German .ts file should be complete."""
        ts_file = _TRANSLATIONS_DIR / "open_garden_planner_de.ts"
        content = ts_file.read_text(encoding="utf-8")
        assert 'type="unfinished"' not in content, (
            "German .ts file contains unfinished translations"
        )


class TestLoadTranslator:
    """Tests for the load_translator function."""

    def test_english_returns_true(self, qtbot) -> None:  # noqa: ARG002
        """English is the source language — no translator needed, should return True."""
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        result = load_translator(app, "en")
        assert result is True

    def test_german_returns_true(self, qtbot) -> None:  # noqa: ARG002
        """German .qm file exists — should load successfully and return True."""
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        result = load_translator(app, "de")
        assert result is True
        # Clean up: restore to English
        load_translator(app, "en")

    def test_unknown_language_returns_false(self, qtbot) -> None:  # noqa: ARG002
        """An unsupported language with no .qm file should return False."""
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        result = load_translator(app, "xx")
        assert result is False
        # Clean up: restore to English
        load_translator(app, "en")


class TestSettingsLanguage:
    """Tests for the language setting in AppSettings."""

    def test_default_language_is_english(self, qtbot) -> None:  # noqa: ARG002
        from open_garden_planner.app.settings import AppSettings

        settings = AppSettings()
        # Default should be English
        assert settings.DEFAULT_LANGUAGE == "en"

    def test_language_property_getter(self, qtbot) -> None:  # noqa: ARG002
        from open_garden_planner.app.settings import AppSettings

        settings = AppSettings()
        lang = settings.language
        assert isinstance(lang, str)
        assert len(lang) >= 2

    def test_language_property_setter(self, qtbot) -> None:  # noqa: ARG002
        from open_garden_planner.app.settings import AppSettings

        settings = AppSettings()
        original = settings.language
        try:
            settings.language = "de"
            assert settings.language == "de"
            settings.language = "en"
            assert settings.language == "en"
        finally:
            # Restore original
            settings.language = original


class TestTranslatedDisplayNames:
    """Tests for translated display names of ObjectTypes."""

    def test_all_object_types_have_display_name(self, qtbot) -> None:  # noqa: ARG002
        """Every ObjectType should return a non-empty translated display name."""
        for obj_type in ObjectType:
            name = get_translated_display_name(obj_type)
            assert isinstance(name, str), f"{obj_type} returned non-string"
            assert len(name) > 0, f"{obj_type} returned empty display name"

    def test_display_names_are_unique(self, qtbot) -> None:  # noqa: ARG002
        """Each ObjectType should have a unique display name."""
        names = [get_translated_display_name(t) for t in ObjectType]
        assert len(names) == len(set(names)), "Duplicate display names found"

    def test_house_display_name(self, qtbot) -> None:  # noqa: ARG002
        """Spot-check: House should return 'House' in English (no translator loaded)."""
        name = get_translated_display_name(ObjectType.HOUSE)
        assert name == "House"


class TestNoHardcodedEnglish:
    """Catch user-visible English strings that bypass tr() / QT_TR_NOOP.

    The existing ``test_german_ts_has_no_unfinished`` only sees strings already
    in the ``.ts`` file. Strings hardcoded in f-strings or dict literals that
    never reach pylupdate6 stay English in every locale and slip past that
    check. This test greps the source tree for a curated list of phrases that
    were observed shipping un-translated; the list grows whenever a new
    leakage is found in user testing.

    Each entry MUST appear inside a ``tr()``, ``QT_TR_NOOP()``,
    ``QCoreApplication.translate(...)``, or ``self.tr(...)`` call. Hits
    elsewhere fail the test and force the developer to wrap the string.
    """

    # Curated list of phrases known to leak past tr() in this codebase.
    # Add new entries here every time a user-visible English string is
    # discovered in a non-English locale.
    SUSPICIOUS_PHRASES = [
        " overlaps ",                 # succession overlap warning (US-12.8)
        ": antagonist",               # succession overlap warning (US-12.8)
        '"Early Spring"',             # _SEGMENT_LABELS (US-12.8)
        '"Late Spring"',
        '"Plan Anbaufolge',           # German hardcoded source — must be English (US-12.8)
        "Plan Anbaufolge",
    ]

    # File-level allowlist is intentionally minimal — broad allowlisting
    # neuters the test in the very file the strings live in. Per-line
    # exemption via a trailing ``# i18n-source`` comment is preferred for
    # source-of-truth dict literals that are translated at lookup time.
    ALLOWED_FILES = (
        "fill_translations.py",      # translation registry — defines the strings
        "test_i18n.py",              # this test file
    )

    def test_no_hardcoded_english_in_src(self, qtbot) -> None:  # noqa: ARG002
        from pathlib import Path

        root = Path(__file__).resolve().parents[2] / "src"
        offenders: list[str] = []
        for path in root.rglob("*.py"):
            if path.name in self.ALLOWED_FILES:
                continue
            for lineno, raw_line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                # Skip pure comment lines (false positives like "# Check overlaps").
                stripped = raw_line.lstrip()
                if stripped.startswith("#"):
                    continue
                # Per-line escape for source-of-truth literals translated
                # elsewhere (e.g. _SEGMENT_LABELS dict consumed by
                # _segment_label() which calls QCoreApplication.translate).
                if "i18n-source" in raw_line:
                    continue
                for phrase in self.SUSPICIOUS_PHRASES:
                    if phrase not in raw_line:
                        continue
                    # Require the match to be inside a string literal — guards
                    # against in-line comments and variable names that happen
                    # to share a substring.
                    if not _phrase_is_in_string_literal(raw_line, phrase):
                        continue
                    # Also accept if the line itself routes through tr() etc.
                    if any(t in raw_line for t in ("tr(", "QT_TR_NOOP", "translate(")):
                        continue
                    offenders.append(
                        f"{path.relative_to(root)}:{lineno}: {phrase!r} → {raw_line.strip()}"
                    )
        assert not offenders, (
            "Suspicious un-translated phrases found in source. Wrap with "
            "tr() / QT_TR_NOOP / QCoreApplication.translate(), add an "
            "``# i18n-source`` per-line escape if it is a source-of-truth "
            "literal translated elsewhere, or add the file to ALLOWED_FILES "
            "if it is a registry:\n  "
            + "\n  ".join(offenders)
        )


def _phrase_is_in_string_literal(line: str, phrase: str) -> bool:
    """Return True if ``phrase`` appears inside a quoted string on ``line``.

    Cheap heuristic: locate the phrase and require an unescaped quote
    character (``"`` or ``'``) to appear both before and after it on the
    same line. Good enough for the curated phrase list — pathological cases
    (multi-line strings, escapes) can be added to ALLOWED_FILES.
    """
    idx = line.find(phrase)
    if idx == -1:
        return False
    before = line[:idx]
    after = line[idx + len(phrase):]
    has_quote_before = any(q in before for q in ('"', "'"))
    has_quote_after = any(q in after for q in ('"', "'"))
    return has_quote_before and has_quote_after
