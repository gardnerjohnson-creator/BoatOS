# Regions, profiles & locale

All geography in BoatOS is driven by one registry: `backend/data/regions.json`.
It defines **profiles** (cruising areas with locale defaults) and **regions**
(Geofabrik OSM extracts that can be turned into basemap MBTiles / OSRM graphs).

The backend never hardcodes `germany` any more — the default basemap, map centre,
units, language and data providers come from the active profile.

## Profiles

| Profile | Language | Units | Basemap | Tides | Weather / alerts | Charts |
|---|---|---|---|---|---|---|
| `de` (default) | de | metric | `germany` | `pegelonline` | `openweather` / `dwd` | `elwis` (IENC) |
| `us-east` | en | imperial | `us-south` | `noaa-coops` | `nws` / `nws` | `noaa-enc` |
| `bahamas` | en | imperial | `bahamas` | `noaa-coops` | `nws` / `nws` | `osm` (no ENCs) |

Profile fields:

```json
"us-east": {
  "name": "US East Coast",
  "language": "en",
  "units": "imperial",
  "defaultBasemap": "us-south",
  "defaultCenter": { "lat": 26.12, "lon": -80.10 },
  "defaultZoom": 12,
  "tideProvider": "noaa-coops",
  "weatherProvider": "nws",
  "alertProvider": "nws",
  "chartSource": "noaa-enc"
}
```

`tideProvider` / `weatherProvider` / `alertProvider` / `chartSource` are
identifiers that later provider modules read; a fresh install with no
`settings.json` behaves exactly like the previous German-only build.

## Regions (Geofabrik extracts)

```json
{ "id": "florida", "name": "Florida", "geofabrik": "north-america/us/florida", "profile": "us-east" }
```

* `id` — used as the `.mbtiles` filename (`data/florida.mbtiles`), the OSRM
  graph name (`data/osrm/florida-latest.osrm`) and the vector-tile source name.
* `geofabrik` — path under `https://download.geofabrik.de/` (without `-latest.osm.pbf`).
* `profile` — which profile lists this region first in the UI (optional).

Any Geofabrik extract works: add an entry and it appears in
**Settings → Map → Offline Maps** as soon as a matching `.mbtiles` exists.
Files without a registry entry are still listed, using the filename as label.

### Local additions without touching git

Create `backend/data/regions.local.json` with the same structure; it is merged
over `regions.json` (profiles and regions are added/overridden by key/id).

## Selecting the profile

* **UI:** Settings → Map → *Region & Cruising Area*.
* **API:**

```bash
curl http://localhost:8000/api/regions            # registry (profiles + regions)
curl http://localhost:8000/api/region             # effective config
curl -X POST http://localhost:8000/api/region -H 'content-type: application/json' \
     -d '{"profile":"us-east"}'                    # switch profile
curl -X POST http://localhost:8000/api/region -H 'content-type: application/json' \
     -d '{"units":"metric"}'                       # override one field
```

Overrides are stored under `region` in `backend/data/settings.json` and take
precedence over profile defaults. The frontend loads `/api/region` at start-up
(`core.loadRegionConfig()` → `REGION_CONFIG`, also `window.BOATOS_REGION`) and
uses it for the map centre/zoom and the basemap source name.

## Scripts

| Script | Region handling |
|---|---|
| `scripts/extract_regions.sh [id|geofabrik-path|all]` | OSRM graphs; region list from `regions.json`, filter with `BOATOS_REGION_PROFILE=us-east` |
| `process_germany.sh [region]` | legacy single-extract OSRM build, defaults to `germany` |
| `tools/mbtiles-creator/` | Windows MBTiles tool, has its own extract list incl. USA |
| `deploy/tileserver-config.json`, `deploy/basic-style.json` | tileserver-gl examples using `germany.mbtiles`; replace with your region id |
| `frontend/test_tiles.html?region=<id>` | tile smoke test for any region |

See [tileserver.md](tileserver.md) for building the MBTiles themselves.
