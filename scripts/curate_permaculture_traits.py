"""Reproduce the reviewed F1 food-forest niche and function annotations.

Classification and evidence: docs/08-crosscutting-concepts/README.md, section 8.26.
This is an explicit curation table, never inference from gallery categories.
"""

import json
from pathlib import Path

LAYERS = {
    "canopy": "Juglans regia|Quercus robur|Acer platanoides|Betula pendula|Salix alba|Pinus sylvestris|Picea abies",
    "sub_canopy": "Malus domestica|Prunus avium|Pyrus communis|Prunus domestica|Prunus persica|Ficus carica|Olea europaea|Citrus limon|Citrus sinensis|Magnolia x soulangeana",
    "shrub": "Rosmarinus officinalis|Salvia officinalis|Lavandula angustifolia|Buxus sempervirens|Rhododendron ponticum|Vaccinium corymbosum|Rubus idaeus|Rubus fruticosus|Ribes uva-crispa|Ribes rubrum|Ilex aquifolium|Juniperus communis|Forsythia x intermedia|Syringa vulgaris|Sambucus nigra|Ligustrum vulgare|Viburnum opulus|Berberis vulgaris|Camellia japonica|Spiraea japonica|Rosa rugosa|Hydrangea macrophylla|Hibiscus syriacus",
    "ground_cover": "Fragaria ananassa|Thymus vulgaris|Chamaemelum nobile|Tropaeolum majus|Viola x wittrockiana",
    "root": "Daucus carota|Beta vulgaris|Raphanus sativus|Allium cepa|Allium sativum|Solanum tuberosum|Ipomoea batatas|Pastinaca sativa",
    "vine": "Cucumis sativus|Cucurbita maxima|Pisum sativum|Cucumis melo|Citrullus lanatus|Phaseolus coccineus|Lathyrus odoratus|Clematis vitalba|Wisteria sinensis|Jasminum officinale",
    "herbaceous": "Solanum lycopersicum|Capsicum annuum|Capsicum chinense|Solanum melongena|Cucurbita pepo|Phaseolus vulgaris|Spinacia oleracea|Lactuca sativa|Brassica oleracea var. capitata|Brassica oleracea var. botrytis|Brassica oleracea var. italica|Brassica oleracea var. gemmifera|Brassica rapa subsp. pekinensis|Allium porrum|Allium schoenoprasum|Petroselinum crispum|Ocimum basilicum|Coriandrum sativum|Anethum graveolens|Foeniculum vulgare|Mentha spicata|Origanum vulgare|Valeriana officinalis|Echinacea purpurea|Apium graveolens|Asparagus officinalis|Rheum rhabarbarum|Zea mays|Cichorium intybus|Cichorium endivia|Eruca vesicaria|Brassica napus|Cynara scolymus|Vicia faba|Helianthus annuus|Tagetes erecta|Borago officinalis|Melissa officinalis|Hyssopus officinalis|Linum usitatissimum|Calendula officinalis|Brassica oleracea var. acephala|Tulipa gesneriana|Narcissus pseudonarcissus|Dahlia pinnata|Paeonia lactiflora|Iris germanica|Lilium candidum|Zinnia elegans|Cosmos bipinnatus|Symphyotrichum novi-belgii|Chrysanthemum x morifolium|Pelargonium x hortorum|Petunia x atkinsiana|Crocus vernus",
}
FUNCTIONS = {
    "nitrogen_fixer": "Phaseolus vulgaris|Phaseolus coccineus|Pisum sativum|Vicia faba",
    "pollinator_attractor": "Borago officinalis|Symphyotrichum novi-belgii|Fragaria ananassa",
    "ground_cover": "Fragaria ananassa|Cucurbita maxima",
}


def main() -> None:
    path = Path(__file__).resolve().parents[1] / "src/open_garden_planner/resources/data/plant_species.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    niches = {name: layer for layer, names in LAYERS.items() for name in names.split("|")}
    assert set(niches) == {r["scientific_name"] for r in data["plants"]}
    for record in data["plants"]:
        name = record["scientific_name"]
        record["permaculture_layer"] = niches[name]
        record["functions"] = [f for f, names in FUNCTIONS.items() if name in names.split("|")]
    data["sources"] += [
        "University of Minnesota legume/rhizobia guidance (bean, pea, broad bean fixation): https://blog-fruit-vegetable-ipm.extension.umn.edu/2022/01/rhizobia-inoculation-for-organic.html",
        "RHS Plants for Pollinators (borage, aster, strawberry): https://www.rhs.org.uk/science/research/plants-for-pollinators",
        "Cornell Three Sisters (bean fixation, squash ground cover): https://warren.cce.cornell.edu/gardening-landscape/warren-county-master-gardener-articles/creating-a-three-sisters-garden",
        "Penn State walnut tolerance (observational): https://extension.psu.edu/landscaping-and-gardening-around-walnuts-and-other-juglone-producing-plants",
    ]
    data["sources"] = list(dict.fromkeys(data["sources"]))
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
