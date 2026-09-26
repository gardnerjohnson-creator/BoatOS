# US / Bahamas data feasibility spike

Findings from a read-only spike (2026-09-26) that checked whether the US data
sources needed for a US/Bahamas port are reachable and whether they fit the
existing BoatOS pipeline (`backend/app/ienc.py`, `weather_alerts.py`,
`pegelonline.py`, OSRM build from `docs/osrm.md`). No production code was
changed. All probes were run from an x86_64 Ubuntu 22.04 box with GDAL 3.4.1
(Pi ships GDAL 3.10 — both lack the separate `_iw` catalog, so `_open_s57()`
takes the "no S57_PROFILE" branch on both).

## Summary

| Source | Accessible | Format compatible | Gaps | Adaptation estimate |
|---|---|---|---|---|
| NOAA ENC (charts.noaa.gov) | yes — free, no auth, XML catalog + per-cell ZIPs | **yes** — `.000` S-57 cells open with `_open_s57()`, `extract_geojson()` / `build_mbtiles()` / `check_route()` / `depth_at_point()` all run unchanged | `IENC_CLASSES` misses ~20 coastal object classes (see below); catalog scraper is ELWIS-specific; vertical datum is MLLW, not GlW/MNW | small: new catalog/download functions (~1 session incl. UI wiring); class extension is a config edit; datum handling is a design decision |
| Geofabrik US extracts | yes — `us-northeast` 1.8 GB, `us-south` 4.1 GB, `north-america` 19.4 GB, per-state e.g. `us/maryland` 214 MB, `us/florida` 657 MB; `central-america/bahamas` 14 MB | **yes** — `osrm-extract` with `waterway_balanced_v2.lua` accepted `maryland-latest.osm.pbf` unchanged; partition/customize/routed OK | profile routes only `waterway=*` ways → **no routes across open bays/coastal water** (Chesapeake Bay Annapolis→Baltimore = `NoRoute`); `extract_regions.sh` hard-codes `europe/germany/` | download script: trivial; open-water routing is a real feature gap (grid/visibility graph or `seamark`/`route=ferry` based) — out of scope for a config port |
| NWS api.weather.gov | yes — free, no key, needs `User-Agent` | **mostly** — alerts are CAP/GeoJSON with the same field names Bright Sky/DWD deliver (`event, headline, description, instruction, severity, urgency, onset, effective, expires, category`) | 2-step lookup (`/points` → gridpoint); imperial units in `/forecast`, mixed in `/gridpoints`; marine alerts (Small Craft Advisory) only appear when querying a marine zone / offshore point; no `location.name` (use `areaDesc`/`senderName`) | alerts: ~50 lines (new `fetch_nws_alerts()` + `alertSource="nws"`); forecast optional — OpenWeather already works in the US |
| NOAA CO-OPS (tidesandcurrents) | yes — free, no key | **yes** — JSON, 6-min observations + harmonic predictions; metric units on request | different station model (metadata API + per-station data calls vs. PEGELONLINE's single `stations.json` with current values); values are metres above MLLW (not cm); no `MNW`/`charValue`; **no flow velocity** at water-level stations (86 separate current stations, none returned for FL) | ~1 session: `NoaaCoops` class mirroring `PegelOnline.get_tide()` / `nearest_station()`; can improve on the MVP by using real hi/lo predictions |
| Bahamas OSM / OpenSeaMap | yes — Geofabrik `bahamas` extract, OpenSeaMap tiles serve | partial | OSM: 502 seamark objects for the whole country (14 lateral buoys, 14 lateral beacons, 22 lights), 8 161 coastline ways, 494 `natural=reef`; OpenSeaMap tiles are near-empty (1–3 kB PNGs at z12 vs. 12 kB Hamburg). **NOAA ENCs do not cover Bahamas waters** except the Bimini/Cat Cay approach cell `US4FL2AL` and small-scale overview cells (`US2ATLMB` 1:700k, `US1GLBCF` 1:3.5M) | none in code — the existing generic MBTiles / KAP upload is the fallback; CO-OPS does provide **tide predictions for 26 Bahamas/Cuba stations** (e.g. `TEC4617` North Bimini, `TEC4623` Nassau, `9710441` Settlement Point) |

Verdict: every source is reachable and no format blocks the port. NOAA ENC
import is **config + a new catalog/download adapter**, not a mapping rewrite;
the `IENC_CLASSES` extension is optional but recommended (coastline, seabed,
unsurveyed/anchoring-restricted areas). The largest genuinely new work is not
data access but **open-water routing**, which the current OSRM waterway profile
cannot do.

---

## 1. NOAA ENC (critical gate) — PASS

### Catalog

Two machine-readable catalogs exist, both refreshed nightly, no auth:

| URL | Size | Content |
|---|---|---|
| `https://charts.noaa.gov/ENCs/ENCProdCat.xml` | 10.6 MB | `<cell>` per ENC: `name, lname, cscale, status, zipfile_location, zipfile_size, zipfile_datetime_iso8601, edtn, updn, isdt, coast_guard_districts, states, regions, cov/panel/vertex(lat,long)` |
| `https://charts.noaa.gov/ENCs/ENCProdCat_19115.xml` | 52.6 MB | ISO 19115 version of the same 7 345 cells (`gml:pos` = `lat lon`) |

Both parse with stdlib `xml.etree` (7 345 cells, all `status=Active`/`completed`;
US1 24, US2 110, US3 365, US4 2 312, US5 4 470, US6 64). The small catalog is
the right one: it carries state/CG-district grouping and human names
(`lname`), which map onto the ELWIS "one entry per waterway" UI directly.

Bundle downloads also exist and mirror the ELWIS one-ZIP-per-waterway model:
`https://charts.noaa.gov/ENCs/05CGD_ENCs.zip` (Chesapeake/Mid-Atlantic, 100 MB),
`07CGD_ENCs.zip` (Florida/SE, 97 MB), `All_ENCs.zip` (837 MB). Per-state ZIPs
follow the same pattern (`<STATE>_ENCs.zip`).

Point-in-coverage lookups against the catalog polygons work
(Annapolis → `US5MD1MC` 1:12k, `US4MD1DD`, `US3MD1AA`, `US2ATLPC`;
Miami → `US5MIACB` 1:12k, `US4FL2AI`, `US3FL1CG`, `US2ATLMB`, `US1GLBCF`).

Differences to `scrape_catalog()` / `download_waterway()`:

- ELWIS is HTML scraped with BeautifulSoup + a 12 h anti-ban cooldown. NOAA is
  a plain XML file; a 24 h cache is still sensible (10 MB) but no cooldown logic
  is needed.
- ZIP layout differs: `ENC_ROOT/<CELL>/<CELL>.000` plus `.001…` update files
  and `.TXT` notes. `download_waterway()` uses `rglob("*.000")`, so it already
  finds the cells. Updates are picked up because `_open_s57()` sets
  `UPDATES=APPLY` — `US5MD1MC` reported `DSID_UPDN=6` after opening the `.000`
  with its `.001…` siblings present.
- `chart_id` must be derived from the cell name or bundle, not from a German
  waterway name (`safe_id()` works on either).

### Cells tested

| Cell | Area | Scale | ZIP | Features extracted | `extract_geojson()` time |
|---|---|---|---|---|---|
| `US5MD1MC` | Annapolis / Severn River (Chesapeake) | 1:12 000 | 451 kB | 4 210 in 32 classes | 2.3 s |
| `US5MIACB` | Miami River – Miami Harbor – Biscayne Bay | 1:12 000 | 188 kB | 2 229 in 27 classes | 1.0 s |
| `US4FL2AL` | Bimini Islands approach (Bahamas, NOAA-produced) | 1:90 000 | 45 kB | 242 in 17 classes | 0.1 s |

`extract_geojson()` was called via `asyncio.to_thread` exactly like
`main.py` does. Downstream steps were also exercised on the output:
`build_mbtiles()` → 455 tiles / 6 681 features / 0.98 MB in 3.4 s,
`check_route()` on a Biscayne Bay leg with draft 2.0 m produced two
`depare` depth warnings (DRVAL1 1.8 m < required 2.3 m), `read_tiles_meta()` OK.

### Object classes vs. `IENC_CLASSES`

Present in NOAA cells **and** already in `IENC_CLASSES` (extracted without
change): `DEPARE DRGARE DEPCNT SOUNDG FAIRWY NAVLNE RECTRC BRIDGE CBLOHD PIPOHD
SLCONS PONTON HULKES OBSTRN WRECKS UWTROC CTNARE RESARE BOYLAT BOYSPP BCNLAT
BCNSPP DAYMAR LIGHTS HRBFAC BERTHS MORFAC ACHARE ACHBRT SMCFAC LNDARE RIVERS
LAKARE LNDMRK BUAARE` plus one `dismar` (used in the Miami River for
distance marks — the inland class survives in US ENCs).

Present in NOAA cells but **not** in `IENC_CLASSES` (silently dropped today):

| Class | Meaning | Count (MD1MC / MIACB / FL2AL) | Relevance |
|---|---|---|---|
| `COALNE` | Coastline | 185 / 84 / 33 | high — base geometry, needed for a usable coastal render (`LNDARE` alone is fine inland; at sea the coastline linework is what you read) |
| `SBDARE` | Seabed area (nature of bottom) | 55 / 28 / – | medium — anchoring |
| `SEAARE` | Named sea area | 38 / 10 / 3 | low — labels |
| `UNSARE` | Unsurveyed area | – / 5 / – | **high** — hazard, must not look like surveyed water |
| `CBLARE` / `PIPARE` | Cable / pipeline area (no anchoring) | 9+4 / 12+3 / – | medium — anchoring restriction |
| `DMPGRD` | Dumping ground | – / 4 / – | medium |
| `MIPARE` | Military practice area | 3 / – / – | medium |
| `OFSPLF` | Offshore platform | 4 / – / – | high — hazard |
| `PILPNT` | Pile / post | 334 / 77 / – | medium — small-craft hazard, very numerous |
| `BUISGL` | Single building | 214 / 37 / – | low — landmark context |
| `LNDRGN` / `LNDELV` / `VEGATN` / `SILTNK` / `SLOTOP` / `FNCLNE` / `AIRARE` / `ADMARE` | Land detail | small | low |
| `MAGVAR` | Magnetic variation | 2 / 3 / 2 | low — could feed COG/heading display |
| `CURENT` | Current (non-gravitational) | – / – / 1 | low |
| `RETRFL`, `SPLARE`, `OSPARE`, `MARCUL`, `WEDKLP` | Retro-reflector, sea-plane landing, offshore production, marine farm, kelp | few | low |
| `M_COVR`, `M_QUAL`, `M_NPUB`, `M_NSYS`, `C_AGGR`, `C_ASSO`, `DSID` | Meta / collection objects | – | `M_QUAL` (CATZOC) would be useful for a data-quality overlay; `M_NSYS` says IALA-B (`MARSYS=2`) |

Inland-only classes in `IENC_CLASSES` that never appear in NOAA data (harmless,
they just produce no output): `notmrk wtwaxs wtwgag lokbsn bunsta refdmp termnl
vehtrf`, `BOYCAR BOYISD BOYSAW BCNCAR BCNISD BCNSAW TOPMAR SISTAT SISTAW FERYRT
DAMCON GATCON FLODOC CHKPNT CANALS` (not in these three cells; `BOYCAR/BOYSAW`
will appear in other US cells).

**Conclusion on mapping:** NOAA import works with the current `IENC_CLASSES`
as-is (depth, hazards, marks, structures, harbour all populate). Recommended
extension is a config-only edit, e.g.

```python
"base":    [..., "COALNE", "SEAARE", "SBDARE", "BUISGL"],
"hazards": [..., "UNSARE", "OFSPLF", "PILPNT", "DMPGRD", "MIPARE", "CBLARE", "PIPARE"],
```

plus matching style rules in `frontend/js/ienc.js` (a line layer for `coalne`,
hatched fills for `unsare`/`cblare`/`pipare`). No attribute-level surprises
were found: the attributes the code depends on are present with the same
names and types as in the German cells — `DRVAL1/DRVAL2` on `DEPARE`,
`DEPTH` (and Z coordinate) on `SOUNDG`, `VERCLR/HORCLR/CATBRG` on `BRIDGE`
(`VERCLR` present on 6/9 and 10/72 bridges; `VERCCL` sometimes instead — the
frontend only reads `VERCLR`), `COLOUR/CATLAM/BOYSHP` on buoys, `SCAMIN` on
most point/line objects (list-typed attributes such as `CATBRG` arrive as
Python lists, exactly as from GDAL for ELWIS cells).

### Things that are different and need a decision

1. **Vertical datum.** NOAA cells declare `DSPM_VDAT=16` (MLLW) and
   `DSPM_HUNI=1` (metres). German cells reference GlW/equivalent low water and
   the code corrects depths with `PEGELONLINE (W − MNW)`. For US cells the
   correction is simpler: CO-OPS `water_level` with `datum=MLLW` **is** the
   offset in metres (see §4), so `apply_level_offsets()` needs a per-chart
   "datum source" rather than a new formula. Cells without a nearby CO-OPS
   station should use chart depth directly (as canal gauges do today).
2. **Buoyage.** IALA region B (`M_NSYS.MARSYS=2`): red-right-returning.
   `frontend/js/buoy3d.js` colours from `COLOUR` so geometry is right, but
   any CEVNI/`notmrk` assumptions and German labels in `ienc.js` need an
   i18n pass.
3. **Scale bands.** NOAA publishes overlapping US1–US6 cells for the same
   water. `build_mbtiles()` merges everything, so a harbour would be drawn
   from 1:12k and 1:700k data simultaneously. Either import only US4/US5/US6
   per region (recommended for a first cut) or add a `DSPM_CSCL`-based
   SCAMIN default for cells whose objects lack `SCAMIN` (`DEPARE`, `LNDARE`).
4. **Volume.** A CG-district bundle is ~100 MB zipped and several hundred
   cells; `extract_geojson()` at ~1–2 s per US5 cell on x86 → expect
   10–20 min per district on a Pi, and `build_mbtiles()` holds all features
   in RAM. Fine for a state, not for `All_ENCs.zip`.

---

## 2. Geofabrik US extracts — PASS (routing profile gap)

`HEAD` on `download.geofabrik.de` (302 → dated file, all 200):

| Extract | Size |
|---|---|
| `north-america/us-northeast-latest.osm.pbf` | 1.80 GB |
| `north-america/us-south-latest.osm.pbf` | 4.13 GB |
| `north-america-latest.osm.pbf` | 19.4 GB (served from a mirror) |
| `north-america/us/maryland-latest.osm.pbf` | 214 MB |
| `north-america/us/florida-latest.osm.pbf` | 657 MB |
| `central-america/bahamas-latest.osm.pbf` | 14 MB |

`maryland-latest.osm.pbf` was run through the exact `install.sh` sequence
(`osrm-extract -p waterway_balanced_v2.lua` → `osrm-partition` →
`osrm-customize` → `osrm-routed --algorithm=MLD`) using the upstream
`ghcr.io/project-osrm/osrm-backend` image. Extract took 8.6 s / 568 MB peak
RAM, produced 132 630 nodes and 4 677 edges, no profile errors.

Routing results:

| Query | Result |
|---|---|
| Washington → Alexandria (Potomac, `waterway=river`) | `Ok`, 5.7 km |
| Chesapeake City → Delaware City (C&D Canal, `waterway=canal`) | `Ok` |
| Annapolis → Baltimore (open Chesapeake Bay) | **`NoRoute`** |

The profile only accepts `waterway ∈ {river, canal, fairway, tidal_channel}`
and `route=ferry`. Maryland OSM contains 1 555 `river`, 247 `canal`, 26
`tidal_channel` ways and essentially no `fairway`; the bay itself is a
`natural=water`/coastline polygon with no routable linework. The same holds
for Biscayne Bay, the Florida Keys and all Bahamas banks (Bahamas: 195
`tidal_channel`, 66 `river`, 46 `canal` — mostly creeks). The ICW is partly
tagged as `waterway=canal`/`river`, so ICW legs may route, but open-water
coastal routing will fall back to the straight line. This is a routing
feature gap, not a data gap.

Script changes: `scripts/extract_regions.sh` hard-codes
`https://download.geofabrik.de/europe/germany/${REGION}-latest.osm.pbf` and a
German state menu; `docs/osrm.md` likewise. A region table keyed by Geofabrik
path is a small change. Memory: `us-south` (4.1 GB) will not extract on a Pi
without a large swap; per-state files are the realistic unit.

---

## 3. NWS api.weather.gov — PASS (shape differs, fields map)

All requests `200`, no key. A `User-Agent` header is documented as required
(the probe without one also succeeded, but do not rely on it).

Forecast is two-step: `GET /points/25.76,-80.19` returns
`properties.forecast`, `forecastHourly`, `forecastGridData`, `forecastZone`,
`county`, `radarStation`, `timeZone` (Miami → `gridpoints/MFL/110,50`). Then:

- `/gridpoints/MFL/110,50/forecast` — 14 half-day `periods` with
  `temperature` (°F), `windSpeed` as text `"7 to 13 mph"`, `windDirection`
  `"N"`, `probabilityOfPrecipitation.value`, `shortForecast`,
  `detailedForecast`, `icon` URL.
- `/forecast/hourly` — 156 hourly periods, same shape plus `dewpoint`
  (°C), `relativeHumidity`.
- `/gridpoints/MFL/110,50` — raw grid, 60+ variables as
  `{uom, values:[{validTime: ISO/duration, value}]}` in SI units
  (`windSpeed` km/h, `temperature` °C) including marine fields
  `waveHeight, wavePeriod, primarySwellHeight/Direction, windWaveHeight,
  windGust, visibility, pressure`.

`/api/weather` in `main.py` and `frontend/js/weather.js` are written against
OpenWeather (`main.temp`, `wind.speed` m/s → kn, 3-hourly `list`). OpenWeather
already works for US coordinates, so NWS forecast is **optional**. If added,
the gridpoint endpoint is the one to use (SI, structured), and it would need
a ~80-line adapter that resamples `validTime` ranges to the 3-hourly rows the
frontend renders. `/forecast` (imperial, free text wind) is not a good fit.

Alerts: `GET /alerts/active?point=lat,lon` returns a GeoJSON
`FeatureCollection`; each `feature.properties` has

```
id, event, headline, description, instruction, severity (Minor|Moderate|Severe|Extreme|Unknown),
urgency, certainty, category ("Met"), onset, effective, expires, ends, sent,
messageType, status, areaDesc, affectedZones[], senderName, response, parameters{...}
```

This is the same CAP vocabulary Bright Sky returns for DWD, so
`format_alert_for_ui()`, `get_alert_severity_level()` and the frontend
badge/colour code work unchanged once `data["alerts"]` is built from
`features[*].properties`. Differences to handle:

- No `location.name`; use `areaDesc` (e.g. `"Coastal Miami Dade County"`) or
  `senderName` (`"NWS Miami FL"`) for `alertsPlace`.
- `severity` may be `"Unknown"` → maps to level 1 today; acceptable.
- **Marine warnings are zone-based.** `point=25.76,-80.19` (Miami, on land)
  returned 2 alerts (Coastal Flood Statement) but *not* the active Small Craft
  Advisory; `point=25.80,-80.05` (offshore) or `zone=AMZ651` did. For a boat
  the position is normally on water so `point=` is fine, but when moored the
  backend should also query the nearest marine zone
  (`GET /zones?type=marine&point=…` → `AMZ651`).
- Alerts carry `geometry` (polygon) or `null` with `affectedZones`; not needed
  by the UI.

Estimated work: `fetch_nws_alerts(lat, lon)` alongside `fetch_owm_alerts()`
plus `alertSource="nws"` in settings, ~50 lines; label `DWD` → source-dependent
in `weather.js`.

---

## 4. NOAA CO-OPS — PASS (different station model)

Base `https://api.tidesandcurrents.noaa.gov/api/prod/datagetter`, no key,
`application=BoatOS` parameter recommended. Tested station `8723214`
Virginia Key (Miami):

| Request | Response |
|---|---|
| `product=water_level&date=latest&datum=MLLW&units=metric` | `{"metadata":{id,name,lat,lon},"data":[{"t":"2026-09-26 13:30","v":"1.27","s":"0.008","f":"0,0,0,0","q":"p"}]}` |
| `product=water_level&range=30` | 299 six-minute samples (same record shape) |
| `product=predictions&range=48&interval=hilo` | `{"predictions":[{"t","v","type":"H"|"L"}]}` — 8 turning points |
| `product=predictions&range=48&interval=h` | 49 hourly predicted heights |
| `product=currents&station=mia1101` | `400` — currents are only at the 86 dedicated current stations (none in FL from the metadata query) |

Metadata API `https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/`:
`stations.json?type=waterlevels` → 302 stations (`id, name, lat, lng, state,
tidal, greatlakes, timezone, affiliations`); `type=tidepredictions` → 3 499
(1 256 reference `R`, 2 243 subordinate `S`); `stations/<id>/datums.json` →
`MLLW, MLW, MSL, MHW, MHHW, NAVD88, …` (in feet unless `units=metric`).

Mapping onto `pegelonline.py`:

| PEGELONLINE (current code) | CO-OPS equivalent | Note |
|---|---|---|
| one `stations.json?includeCurrentMeasurement=true` gives *all* stations with latest `W` | `mdapi stations.json` (index only) + one `datagetter …date=latest` per station | `fetch_gauges(bbox)` must fan out per station (or cache per-station latest for ~6 min); 40 WL stations in FL+MD+VA, so a bbox call is a handful of requests |
| `value` in **cm**, `unit` | `v` as **string, metres** (`units=metric`) | parse + ×100 for `water_level_cm` |
| `timestamp` ISO with offset | `t` = `"YYYY-MM-DD HH:MM"` in `time_zone=gmt` (or `lst_ldt`) | must append tz explicitly |
| `characteristicValues` `MNW` → `delta_m = (W−MNW)/100` | not needed: `datum=MLLW` water level **is** the height above chart datum | `get_reference_levels()` becomes `delta_m = v` for US charts |
| `VA` flow velocity timeseries | none at WL stations; `product=currents` at separate current stations | drop `flow_velocity_*` for US gauges |
| `stateMnwMhw` trend | not provided; compute from series (as `get_tide()` already does) | — |
| `measurements.json?start=P2D` → `fetch_tide_curve()` | `water_level&range=30` | same shape after mapping `t/v` → `t/cm` |
| `get_tide()` derives last high/low from measured extrema (MVP) | `predictions&interval=hilo` gives actual **next** H/L times | strict improvement; also works where no gauge exists (subordinate stations, incl. Bahamas) |

Bahamas: `predictions` for `TEC4617` North Bimini returned valid hi/lo data;
`9710441` Settlement Point has predictions but `water_level` → "No data".
26 subordinate stations cover the Bahamas + N Cuba coast.

Estimated work: ~1 session for a `NoaaCoops` provider with the same public
methods (`fetch_gauges`, `get_reference_levels`, `nearest_station`,
`get_tide`) selected by position/region in `main.py`.

---

## 5. Bahamas coverage — fallback path confirmed

- **NOAA ENC:** catalog polygon lookup for Nassau (25.08, −77.35), West End
  (26.69, −78.98) hits only `US2ATLMB` (1:700k) and `US1GLBCF` (1:3.5M).
  Bimini (25.72, −79.28) additionally hits `US4FL2AL` (1:90k), whose `M_COVR`
  is −79.5…−79.2 / 25.5…25.8 and which contains named `LNDARE` for North/South
  Bimini, Gun Cay, Cat Cays and 56 soundings — a genuine NOAA approach chart
  for the Bahamas gateway. Everything east of that is not covered at
  navigational scale.
- **OSM (Geofabrik `bahamas`, 2.1 M nodes / 206 k ways):** 8 161
  `natural=coastline` ways (coastline and land are fine), 494 `natural=reef`,
  85 `leisure=marina`, but only **502 objects with `seamark:*` tags**
  (harbour 98, rock 52, mooring 44, sea_area 42, berth 41, dredged_area 27,
  wreck 16, light_minor 15, beacon_lateral 14, buoy_lateral 4,
  light_major 7). No depth data. The Overpass-based buoy/harbour import in
  `main.py` will return these few objects; it will not error.
- **OpenSeaMap raster (`tiles.openseamap.org/seamark`):** z12 tiles for
  Nassau 1.2 kB, Marsh Harbour 1.9 kB, Bimini 3.4 kB vs. Hamburg 12.1 kB —
  effectively empty.
- **What exists instead:** CO-OPS tide predictions (§4); Explorer Charts /
  Navionics / commercial BSB-KAP sets. The existing generic **MBTiles upload**
  (`POST /api/map/regions/upload`) and **KAP → tiles** conversion
  (`POST /api/charts/upload`) in `main.py` are the
  right fallback and need no change; the UI should simply say "no official
  ENC coverage" for positions outside the catalog polygons.

---

## Recommended sequencing

1. `ienc.py`: add `scrape_noaa_catalog()` (ENCProdCat.xml, grouped by
   state/CG district) and `download_noaa(zip_url, chart_dir)`; reuse
   `extract_geojson()`/`build_mbtiles()` as-is. Extend `IENC_CLASSES` with
   `COALNE, SBDARE, SEAARE, UNSARE, OFSPLF, PILPNT, CBLARE, PIPARE, DMPGRD,
   MIPARE` and add the matching styles. Mark chart datum per chart.
2. `pegelonline.py` → provider interface + `noaa_coops.py`; wire
   `delta_m = water_level(MLLW)` into the depth correction for NOAA charts.
3. `weather_alerts.py`: `fetch_nws_alerts()`; keep OpenWeather for forecast.
4. `extract_regions.sh` / `docs/osrm.md`: region table with Geofabrik paths
   for US states + Bahamas.
5. Separate track: open-water routing (visibility graph over `LNDARE`/`DEPARE`
   or a coarse grid), since OSRM+`waterway=*` cannot route across bays.

## Reproduction

```bash
sudo apt install python3-gdal gdal-bin osmium-tool
curl -o ENCProdCat.xml https://charts.noaa.gov/ENCs/ENCProdCat.xml
for c in US5MD1MC US5MIACB US4FL2AL; do curl -o $c.zip https://www.charts.noaa.gov/ENCs/$c.zip; unzip -q $c.zip -d $c; done
python3 -c "
import asyncio, sys; from pathlib import Path
sys.path.insert(0, 'backend/app'); import ienc
print(asyncio.run(asyncio.to_thread(ienc.extract_geojson, Path('US5MIACB')))['classes'])"

curl -O https://download.geofabrik.de/north-america/us/maryland-latest.osm.pbf
docker run --rm -v $PWD:/data ghcr.io/project-osrm/osrm-backend \
  osrm-extract -p /data/backend/app/waterway_balanced_v2.lua /data/maryland-latest.osm.pbf

curl -H 'User-Agent: BoatOS' 'https://api.weather.gov/alerts/active?point=25.80,-80.05'
curl 'https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?product=predictions&station=8723214&range=48&datum=MLLW&units=metric&time_zone=gmt&format=json&interval=hilo'
```
