# PennyPressMap – public map data

Pressed-coin (elongated coin / „préselt érme”) and souvenir-medal machines from **OpenStreetMap**, split into one JSON file per country, for the PennyPressMap Android app.

- Index: `https://github.com/meszarosatilla-hue/pennypressmappublic/releases/download/data/index.json`
- Country: `https://github.com/meszarosatilla-hue/pennypressmappublic/releases/download/data/<CC>.json` (ISO 3166-1 alpha-2, e.g. `HU.json`)
- Updated every Monday by GitHub Actions (`.github/workflows/data.yml`, `tools/build.py`); can also be started by hand (Actions → Run workflow).

## What is included
One worldwide Overpass query; the country comes from the Natural Earth 1:10m borders (public domain). Every OpenStreetMap object whose `vending` tag mentions an elongated/pressed coin (`vending=elongated_coin`, the documented tag) or a souvenir medal. `kind` is `pressed` or `medal`. All tags are kept except source/import/fixme bookkeeping. `edited` is the date of the last edit in OpenStreetMap.

## Missing or wrong machine?
Fix it in OpenStreetMap (e.g. with StreetComplete, Every Door, OsmAnd, or the openstreetmap.org editor): `amenity=vending_machine` + `vending=elongated_coin`, optionally `coin:design_count`, `coin:type`, `charge`, `opening_hours`, `operator`, `level`, `description`. The next weekly update brings it into the app.

## License
Data © OpenStreetMap contributors, available under the [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/). See https://www.openstreetmap.org/copyright. The build script is MIT.
