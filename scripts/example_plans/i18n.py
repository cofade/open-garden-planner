"""The example plans' words: one table of authored translations, applied by field.

Botanical keys and renderer species strings stay canonical; only what a person reads is
translated, and only at the fields named in ``TRANSLATED``.
"""

from __future__ import annotations

import re

# Explicit authored translations: botanical keys and renderer species strings stay canonical.
TRANSLATIONS = {}


def text(en, de, es):
    """Register one English string's translations. One string has ONE translation per
    language: every plan is localized from this single table, so a second, different
    entry would silently win for whichever plan is authored later (it turned the
    showcase's "Compostador" into "Compost" whenever all four plans were regenerated)."""
    entry = {"de": de, "es": es}
    assert TRANSLATIONS.setdefault(en, entry) == entry, (en, TRANSLATIONS[en], entry)
    return en


SPECIES_NAMES = {
    "Carrot": ("Möhre", "Zanahoria"), "Radish": ("Radieschen", "Rábano"),
    "Lettuce": ("Salat", "Lechuga"), "Garlic": ("Knoblauch", "Ajo"),
    "Chives": ("Schnittlauch", "Cebollino"), "Parsley": ("Petersilie", "Perejil"),
    "Basil": ("Basilikum", "Albahaca"), "Thyme": ("Thymian", "Tomillo"),
    "Strawberry": ("Erdbeere", "Fresa"), "Runner Bean": ("Feuerbohne", "Judía escarlata"),
    "Borage": ("Borretsch", "Borraja"), "Pot Marigold": ("Ringelblume", "Caléndula"),
    "Apple Tree": ("Apfelbaum", "Manzano"), "Peach Tree": ("Pfirsichbaum", "Melocotonero"),
    "Currant": ("Johannisbeere", "Grosellero"), "Bean (Bush)": ("Buschbohne", "Judía de mata baja"),
}
#: Every other bundled species, named as the plant gallery names it (the app's own
#: ``GalleryData`` translations), so that a plant in an example reads like the same plant
#: dragged from the gallery. ``tests/unit/test_example_specs.py`` holds the two together.
SPECIES_NAMES |= {
    "Artichoke": ("Artischocke", "Alcachofa"), "Asparagus": ("Spargel", "Espárrago"),
    "Barberry": ("Berberitze", "Berberis"), "Blackberry": ("Brombeere", "Zarzamora"),
    "Broad Bean": ("Ackerbohne", "Haba"), "Broccoli": ("Brokkoli", "Brócoli"),
    "Brussels Sprouts": ("Rosenkohl", "Coles de Bruselas"), "Camellia": ("Kamelie", "Camelia"),
    "Cauliflower": ("Blumenkohl", "Coliflor"), "Celery": ("Sellerie", "Apio"),
    "Chamomile": ("Kamille", "Manzanilla"), "Chicory": ("Chicorée", "Achicoria"),
    "Chili Pepper": ("Chili", "Chile/Guindilla"), "Chinese Cabbage": ("Chinakohl", "Col china"),
    "Clematis": ("Waldrebe", "Clemátide"), "Coriander": ("Koriander", "Cilantro"),
    "Crocus": ("Krokus", "Croco"), "Daffodil": ("Narzisse", "Narciso"), "Dill": ("Dill", "Eneldo"),
    "Eggplant": ("Aubergine", "Berenjena"), "Elderberry": ("Holunder", "Saúco"),
    "Endive": ("Endivie", "Escarola"), "Fennel": ("Fenchel", "Hinojo"),
    "Fig Tree": ("Feigenbaum", "Higuera"), "Flax": ("Lein", "Lino"),
    "Garden Pea": ("Gartenerbse", "Guisante"), "Hibiscus": ("Hibiskus", "Hibisco"),
    "Holly": ("Stechpalme", "Acebo"), "Hyssop": ("Ysop", "Hisopo"), "Jasmine": ("Jasmin", "Jazmín"),
    "Juniper": ("Wacholder", "Enebro"), "Kohlrabi": ("Kohlrabi", "Colinabo"),
    "Lemon Balm": ("Zitronenmelisse", "Melisa"), "Lemon Tree": ("Zitronenbaum", "Limonero"),
    "Maple": ("Ahorn", "Arce"), "Melon": ("Melone", "Melón"),
    "Nasturtium": ("Kapuzinerkresse", "Capuchina"), "Oak": ("Eiche", "Roble"),
    "Olive Tree": ("Olivenbaum", "Olivo"), "Orange Tree": ("Orangenbaum", "Naranjo"),
    "Parsnip": ("Pastinake", "Chirivía"), "Petunia": ("Petunie", "Petunia"),
    "Pine": ("Kiefer", "Pino"), "Plum Tree": ("Pflaumenbaum", "Ciruelo"),
    "Potato": ("Kartoffel", "Patata"), "Privet": ("Liguster", "Aligustre"),
    "Rhubarb": ("Rhabarber", "Ruibarbo"), "Rocket (Arugula)": ("Rucola", "Rúcula"),
    "Spearmint": ("Grüne Minze", "Hierbabuena"), "Spirea": ("Spierstrauch", "Espirea"),
    "Sweet Corn": ("Zuckermais", "Maíz dulce"), "Sweet Pea": ("Duftwicke", "Guisante de olor"),
    "Sweet Potato": ("Süßkartoffel", "Boniato"), "Valerian": ("Baldrian", "Valeriana"),
    "Viburnum": ("Schneeball", "Viburno"), "Walnut Tree": ("Walnussbaum", "Nogal"),
    "Watermelon": ("Wassermelone", "Sandía"), "Willow": ("Weide", "Sauce"),
    "Winter Squash": ("Winterkürbis", "Calabaza de invierno"), "Wisteria": ("Glyzinie", "Glicinia"),
    # the five species added with the example plans (#940)
    "Japanese Maple": ("Fächerahorn", "Arce japonés"), "Bamboo": ("Bambus", "Bambú"),
    "Miscanthus": ("Chinaschilf", "Eulalia"), "Windmill Palm": ("Hanfpalme", "Palmera de Fortune"),
    "Grape Vine": ("Weinrebe", "Vid"),
}
for _en, (_de, _es) in SPECIES_NAMES.items():
    text(_en, _de, _es)


#: The fields of a plan that carry words a person reads, as paths of keys (``*`` stands for
#: an id used as a key; a list has no step of its own). Every string there has to be in
#: ``TRANSLATIONS``; a string anywhere else is never touched, so that a registered word
#: cannot rewrite an enum value or a key that happens to read the same.
TRANSLATED = frozenset({
    ("objects", "name"), ("objects", "content"),
    ("objects", "metadata", "plant_species", "common_name"),
    ("objects", "metadata", "guild", "name"),
    ("objects", "metadata", "guild", "template", "name"),
    ("objects", "metadata", "guild", "template", "description"),
    ("objects", "metadata", "guild", "template", "attribution"),
    ("layers", "name"),
    ("harvest_logs", "*", "species_name"),
    ("harvest_logs", "*", "records", "notes"), ("harvest_logs", "*", "records", "quality"),
    ("soil_tests", "*", "records", "notes"),
    ("succession_plans", "*", "entries", "common_name"),
    ("camera_tours", "name"),
})
_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class MissingTranslation(KeyError):
    """A word a person reads has no authored translation."""


def localized_plan(plan, language, slug=""):
    """``plan`` in ``language``. A word at a translated field that is not in the table stops
    the generation: it used to fall back to English silently, and the translated plan
    shipped with an English name in it."""
    def localize(value, path):
        if isinstance(value, dict):
            return {k: localize(v, (*path, "*" if _ID.match(k) else k)) for k, v in value.items()}
        if isinstance(value, list):
            return [localize(v, path) for v in value]
        if isinstance(value, str) and value and path in TRANSLATED:
            if value not in TRANSLATIONS:
                raise MissingTranslation(f"{slug}: {'/'.join(path)}: {value!r} has no translation")
            return TRANSLATIONS[value][language]
        return value
    return localize(plan, ())
