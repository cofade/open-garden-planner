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
