"""Pasting supported map links fills the location without saving the dialog."""

import pytest
from PyQt6.QtCore import QUrl

from open_garden_planner.ui.dialogs.location_dialog import LocationDialog

_PLACE = "https://www.google.com/maps/place/Sample+Garden/@10.3652534,20.0515546,750m/data=!8m2!3d10.3652497!4d20.0541297!16s"
_SHORT = "https://maps.app.goo.gl/SyntheticGoogleId"


@pytest.mark.parametrize(("url", "expected"), [
    (_PLACE, (10.365250, 20.054130)),
    ("https://www.google.com/maps/@?api=1&map_action=map&center=10.25%2C20.5", (10.25, 20.5)),
    ("https://www.openstreetmap.org/?mlat=10.25&mlon=20.5#map=19/10.2/20.4", (10.25, 20.5)),
    ("10.365049818651066, 20.053885428310425", (10.365050, 20.053885)),
    ("https://maps.apple.com/search?center=10.365175%2C20.054624&span=0.001686%2C0.003259",
     (10.365175, 20.054624)),
    ("https://maps.apple.com/place?coordinate=10.36525767354156%2C20.054108964095207",
     (10.365258, 20.054109)),
    ("https://maps.apple.com/directions?destination=10.365175%2C20.054624",
     (10.365175, 20.054624)),
    ("https://www.openstreetmap.org/way/12345#map=19/10.365136/20.054225", (10.365136, 20.054225)),
    ("https://www.openstreetmap.org/search?query=sample&minlat=46#map=19/10.365025/20.054499",
     (10.365025, 20.054499)),
    ("https://earth.google.com/web/search/sample/@10.3652497,20.0541297,410a,561d", (10.365250, 20.054130)),
])
def test_map_link_paste_fills_location(qtbot, url, expected):
    dialog = LocationDialog()
    qtbot.addWidget(dialog)
    dialog._map_link_edit.setText(url)
    assert (dialog._lat_spin.value(), dialog._lon_spin.value()) == pytest.approx(expected, abs=1e-6)
    dialog._map_link_edit.setText("https://www.google.com/maps/@100,15,10z")
    assert (dialog._lat_spin.value(), dialog._lon_spin.value()) == pytest.approx(expected, abs=1e-6)


@pytest.mark.parametrize(("short", "target", "expected"), [
    (_SHORT, _PLACE, (10.365250, 20.054130)),
    ("https://maps.apple/p/SyntheticAppleId",
     "https://maps.apple.com/place?coordinate=10.36525767354156%2C20.054108964095207",
     (10.365258, 20.054109)),
])
def test_short_link_resolves_without_following_redirect(qtbot, monkeypatch, short, target, expected):
    class Reply:
        def attribute(self, _attribute):
            return QUrl(target)

        def deleteLater(self):
            pass

    dialog = LocationDialog()
    qtbot.addWidget(dialog)
    dialog._map_link_edit.setText(short)
    assert dialog._map_link_timer.isActive()
    assert not dialog._ok_button.isEnabled()
    assert not dialog._lookup_btn.isEnabled()
    dialog._map_link_timer.stop()
    reply = Reply()
    monkeypatch.setattr(dialog, "_map_link_reply", reply)
    dialog._map_link_finished(reply)
    assert dialog._ok_button.isEnabled()
    assert dialog._lookup_btn.isEnabled()
    assert dialog._lat_spin.value() == pytest.approx(expected[0], abs=1e-6)
    assert dialog._lon_spin.value() == pytest.approx(expected[1], abs=1e-6)



def test_reject_cancels_pending_short_link(qtbot):
    dialog = LocationDialog()
    qtbot.addWidget(dialog)
    dialog._map_link_edit.setText(_SHORT)
    dialog.reject()
    assert not dialog._map_link_timer.isActive()
    assert dialog._ok_button.isEnabled()



def test_pending_short_link_ignores_frost_result_for_previous_location(qtbot):
    from open_garden_planner.services.climate_service import FrostData

    dialog = LocationDialog()
    qtbot.addWidget(dialog)
    dialog._lookup_coordinates = (0.0, 0.0)
    dialog._map_link_edit.setText(_SHORT)
    dialog._on_lookup_success(FrostData(
        last_spring_frost="04-15", first_fall_frost="10-20", hardiness_zone="7b",
        data_source="open-meteo", latitude=0.0, longitude=0.0,
    ))
    assert not dialog._spring_frost_edit.text()
    assert not dialog._fall_frost_edit.text()
    assert not dialog._zone_edit.text()
    dialog.reject()
