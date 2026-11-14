"""Plant Details panel — missing enum traits must render as a neutral "—", not
the first concrete dropdown option (#231).

Regression: the characteristic combos (cycle / flower type / pollination / sun /
water) were built with the ``UNKNOWN`` member excluded, and the populate code
fell back to ``setCurrentIndex(0)`` when a value was unknown — so a species with
no data for a trait was silently shown as the first option (e.g. a tree's
lifecycle read "Annual"). Worse, saving then wrote that wrong concrete value back.
"""

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.plant_data import PlantCycle, PlantSpeciesData
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.panels.plant_database_panel import PlantDatabasePanel


def _plant(species: PlantSpeciesData) -> CircleItem:
    item = CircleItem(
        center_x=0, center_y=0, radius=20, object_type=ObjectType.TREE, name="Tree"
    )
    item.metadata["plant_species"] = species.to_dict()
    return item


class TestUnknownEnumRendersDash:
    def test_sparse_species_shows_dash_not_first_option(self, qtbot) -> None:
        panel = PlantDatabasePanel()
        qtbot.addWidget(panel)

        # A sparse species (e.g. from online Search) — every trait defaults UNKNOWN.
        panel.set_selected_items([_plant(PlantSpeciesData(scientific_name="Prunus domestica", common_name="Plum"))])

        # Regression guard: cycle was "annual" (index 0 of the UNKNOWN-excluded combo).
        assert panel.cycle_combo.currentData() == PlantCycle.UNKNOWN.value
        assert panel.cycle_combo.currentText() == "—"
        # The sibling characteristic combos were equally bogus index-0 fallbacks.
        for combo in (
            panel.flower_type_combo,
            panel.pollination_combo,
            panel.sun_combo,
            panel.water_combo,
        ):
            assert combo.currentData() == "unknown"
            assert combo.currentText() == "—"

    def test_known_cycle_still_displayed(self, qtbot) -> None:
        panel = PlantDatabasePanel()
        qtbot.addWidget(panel)

        species = PlantSpeciesData(
            scientific_name="Prunus domestica", common_name="Plum", cycle=PlantCycle.PERENNIAL
        )
        panel.set_selected_items([_plant(species)])

        assert panel.cycle_combo.currentData() == PlantCycle.PERENNIAL.value
        assert panel.cycle_combo.currentText() != "—"


class TestPlantProfilePicture:
    """#857: the profile picture is the plant's drawing, large in its tile."""

    def test_the_drawn_picture_fills_the_96_px_tile(self, qtbot) -> None:
        from open_garden_planner.core.project import ProjectManager
        from open_garden_planner.services import pdf_report_service as svc
        from open_garden_planner.services.example_library import BUNDLED_EXAMPLES
        from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

        scene = CanvasScene()
        ProjectManager().load(
            scene, BUNDLED_EXAMPLES / "family-garden.ogp", as_template=True
        )
        plant = svc._plant_items(scene)[0]
        panel = PlantDatabasePanel()
        qtbot.addWidget(panel)
        panel.show()
        panel.set_selected_items([plant])
        panel._show_drawn_thumbnail()
        pixmap = panel._profile_thumbnail.pixmap()
        assert pixmap is not None and not pixmap.isNull()
        image = pixmap.toImage()
        xs: list[int] = []
        ys: list[int] = []
        for y in range(image.height()):
            for x in range(image.width()):
                if image.pixelColor(x, y).alpha() > 0:
                    xs.append(x)
                    ys.append(y)
        assert xs and ys
        drawn_w = max(xs) - min(xs) + 1
        drawn_h = max(ys) - min(ys) + 1
        # The tile is 96 logical px; the old bug drew a tiny sprite in it.
        assert drawn_w >= 72 and drawn_h >= 72


class TestPlantAge:
    def test_the_age_label_follows_the_plan_day(self, qtbot) -> None:
        """#859: a plan standing in 2031 must not show a planted tree as future."""
        from datetime import date

        from open_garden_planner.core.sim_clock import SimClock
        from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

        scene = CanvasScene(width_cm=1000, height_cm=800)
        clock = SimClock()
        clock.set_date(date(2031, 3, 1))
        scene.bind_plan_clock(clock)
        plant = _plant(
            PlantSpeciesData(scientific_name="Solanum lycopersicum", common_name="Tomato")
        )
        plant.metadata["plant_instance"] = {"planting_date": "2031-01-01"}
        scene.addItem(plant)

        panel = PlantDatabasePanel()
        qtbot.addWidget(panel)
        panel.set_selected_items([plant])
        assert "(1 mo)" in panel.age_label.text()


class TestMissingDimensionsShowDash:
    """Missing dimension/pH/hardiness traits render as "—", not "0 cm"/"0"/"0.0" (#231).

    Sibling of the enum-combo regression above: the spin-boxes used
    ``setSpecialValueText("")`` — an *empty* string, which Qt treats as *disabling*
    the special-value feature, so a missing (0 = "unset" sentinel) value printed as a
    real "0 cm" instead of blank. A non-empty "—" engages the placeholder.
    """

    # Every dimension/pH/hardiness box (species traits + instance current size).
    _SPINS = (
        "max_height_spin",
        "max_spread_spin",
        "current_height_spin",
        "current_spread_spin",
        "hardiness_min_spin",
        "hardiness_max_spin",
        "ph_min_spin",
        "ph_max_spin",
    )

    def test_special_value_text_is_non_empty_dash(self, qtbot) -> None:
        panel = PlantDatabasePanel()
        qtbot.addWidget(panel)
        for name in self._SPINS:
            assert getattr(panel, name).specialValueText() == "—", name

    def test_sparse_species_shows_dash_not_zero(self, qtbot) -> None:
        panel = PlantDatabasePanel()
        qtbot.addWidget(panel)
        # A sparse online-search result — every dimension field defaults to None.
        panel.set_selected_items(
            [_plant(PlantSpeciesData(scientific_name="Juglans regia", common_name="Walnut"))]
        )
        for name in self._SPINS:
            spin = getattr(panel, name)
            assert spin.value() == 0, name  # the "unset" sentinel
            assert spin.text() == "—", name  # regression guard: was "0 cm"/"0"/"0.0"

    def test_known_dimensions_show_numbers(self, qtbot) -> None:
        panel = PlantDatabasePanel()
        qtbot.addWidget(panel)
        species = PlantSpeciesData(
            scientific_name="Juglans regia",
            common_name="Walnut",
            max_height_cm=800,
            max_spread_cm=600,
            ph_min=6.0,
            hardiness_zone_min=4,
        )
        panel.set_selected_items([_plant(species)])
        assert panel.max_height_spin.value() == 800
        assert panel.max_height_spin.text() != "—"
        assert panel.max_spread_spin.value() == 600
        assert panel.ph_min_spin.value() == 6.0
        assert panel.ph_min_spin.text() != "—"
        assert panel.hardiness_min_spin.value() == 4

    def test_sparse_species_saves_back_as_none(self, qtbot) -> None:
        # The dash-at-0 display must not corrupt a missing value into a concrete 0
        # on save (mirrors the enum combos' UNKNOWN→concrete corruption guard).
        panel = PlantDatabasePanel()
        qtbot.addWidget(panel)
        panel.set_selected_items(
            [_plant(PlantSpeciesData(scientific_name="Juglans regia", common_name="Walnut"))]
        )
        panel._on_field_changed()
        assert panel._current_plant_data.max_height_cm is None
        assert panel._current_plant_data.max_spread_cm is None
        assert panel._current_plant_data.ph_min is None
        assert panel._current_plant_data.hardiness_zone_min is None


class TestPlantThumbnailDownload:
    def test_uncached_thumbnail_starts_fetch_and_updates_on_ready(self, qtbot, monkeypatch, tmp_path) -> None:
        from PyQt6.QtGui import QImage

        img_path = tmp_path / "test_thumb.png"
        img = QImage(64, 64, QImage.Format.Format_ARGB32)
        img.fill(0xFF00FF00)
        img.save(str(img_path))

        monkeypatch.setattr(
            "open_garden_planner.services.plant_api.thumbnail_loader.fetch_thumbnail",
            lambda url: img_path if url == "https://example.com/plant.png" else None,
        )
        monkeypatch.setattr(
            "open_garden_planner.services.plant_api.thumbnail_loader.get_cached_thumbnail",
            lambda _url: None,
        )

        panel = PlantDatabasePanel()
        qtbot.addWidget(panel)

        species = PlantSpeciesData(
            common_name="Rose",
            scientific_name="Rosa",
            thumbnail_url="https://example.com/plant.png",
        )
        panel.set_selected_items([_plant(species)])

        qtbot.waitUntil(
            lambda: (
                panel._profile_thumbnail.pixmap() is not None
                and not panel._profile_thumbnail.pixmap().isNull()
            ),
            timeout=3000,
        )

    def test_thumbnail_worker_shutdown_cancels_and_disconnects(self, qtbot) -> None:
        """Issue #765: _ThumbnailWorker shutdown cancels execution and disconnects signals."""
        from open_garden_planner.ui.panels.plant_database_panel import _ThumbnailWorker

        worker = _ThumbnailWorker("https://example.com/test.png")
        received = []
        worker.thumbnail_ready.connect(lambda u, p: received.append((u, p)))

        worker.shutdown(timeout_ms=50)
        assert worker._is_cancelled is True

    def test_panel_shutdown_cleans_up_worker(self, qtbot) -> None:
        """Issue #765: PlantDatabasePanel.shutdown cleans up active thumbnail worker."""
        panel = PlantDatabasePanel()
        qtbot.addWidget(panel)
        panel._start_thumbnail_fetch("https://example.com/dummy.png")
        assert panel._thumb_worker is not None

        panel.shutdown()
        assert panel._thumb_worker is None


class TestProfileHeaderHeight:
    """#905: the profile header must not eat the space the details need."""

    def test_the_details_scroll_gets_the_surplus_sidebar_height(self, qtbot) -> None:
        from PyQt6.QtWidgets import QApplication

        panel = PlantDatabasePanel()
        qtbot.addWidget(panel)
        panel.resize(450, 1198)
        panel.show()
        panel.set_selected_items([
            _plant(
                PlantSpeciesData(
                    common_name="Apple tree",
                    scientific_name="Malus domestica",
                    description="A garden apple tree.",
                )
            )
        ])
        QApplication.processEvents()

        assert panel._profile_header.isVisibleTo(panel)
        # The header keeps the height its own content asks for...
        natural = panel._profile_header.sizeHint().height()
        assert panel._profile_header.height() <= natural + 2
        # ...and the details viewport receives the rest of the sidebar.
        assert panel.details_scroll.height() > 400
