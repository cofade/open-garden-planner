"""Welcome's supported small size leaves a complete thumbnail card visible."""

import pytest
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QTabWidget

from open_garden_planner.app.settings import get_settings
from open_garden_planner.core.i18n import load_translator
from open_garden_planner.ui.dialogs.welcome_dialog import WelcomeDialog


@pytest.mark.parametrize("language", ["en", "de", "es"])
@pytest.mark.parametrize("point_size", [9, 12])
def test_minimum_welcome_size_shows_a_complete_selected_thumbnail(qtbot, qapp, language, point_size):
    original = QFont(qapp.font())
    font = QFont(original)
    font.setPointSize(point_size)
    qapp.setFont(font)
    get_settings().language = language
    load_translator(qapp, language)
    try:
        dialog = WelcomeDialog()
        qtbot.addWidget(dialog)
        dialog.resize(600, 500)
        dialog.findChild(QTabWidget).setCurrentIndex(1)
        dialog.show()
        gallery = dialog._gallery
        for index in range(3):
            gallery.list.setCurrentRow(index)
            gallery.list.scrollToItem(gallery.list.currentItem())
            qapp.processEvents()
            card = gallery.list.visualItemRect(gallery.list.currentItem())
            viewport = gallery.list.viewport().rect()
            assert viewport.height() >= card.height()
            assert viewport.contains(card)
        assert gallery.open_button.isVisible()
    finally:
        load_translator(qapp, "en")
        qapp.setFont(original)
