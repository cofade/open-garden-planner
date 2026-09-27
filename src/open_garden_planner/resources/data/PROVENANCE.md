# Data Provenance & Licences

Every JSON data file in this directory MUST carry a `license` and
`attribution` object before it merges — same rule as the asset sets
(`ogp-asset-forge`: no provenance, no merge). A unit test
(`tests/unit/test_data_file_licenses.py`) enforces this gate.

## Licence

All bundled data files are licensed under **CC BY-SA 4.0** (Creative Commons
Attribution-ShareAlike 4.0 International), consistent with the upstream
Permapeople data (the primary online source) and the share-alike principle.

Each file carries:

```json
{
  "license": {
    "spdx": "CC-BY-SA-4.0",
    "name": "Creative Commons Attribution-ShareAlike 4.0 International",
    "url": "https://creativecommons.org/licenses/by-sa/4.0/"
  },
  "attribution": {
    "sources": ["..."],
    "note": "Curated from public horticultural references. Derived data, not verbatim copies."
  }
}
```

## Files

| file | sources |
| ---- | ------- |
| `plant_species.json` | RHS, Cornell, Kew, USDA/GRIN, UMN, OSU |
| `companion_planting.json` | RHS, Riotte, Rodale |
| `seed_viability.json` | OSU, Johnny's Selected Seeds, Mother Earth News, RHS |
| `amendments.json` | Rodale, RHS, USDA Extension |

## Online data sources

When plant data is fetched at runtime from online APIs, the attribution is
shown in-app (Plant Details panel + About dialog):

| provider | licence | attribution required |
| -------- | ------- | -------------------- |
| Permapeople | CC BY-SA 4.0 | Yes — link-back to permapeople.org |
| Trefle | Per their API terms | Yes — attribution wording per Trefle docs |
| Perenual | Free personal/commercial | Link-back recommended |

## Rule

**No data source without licence + in-app credit.** New data files or new
online providers must land with both a `license`/`attribution` block in the
JSON and an entry in the About dialog's "Data sources & licenses" section.
