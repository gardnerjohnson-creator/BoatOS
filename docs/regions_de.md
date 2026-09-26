# Regionen, Profile & Locale

Die gesamte Geographie in BoatOS wird über eine Registry gesteuert:
`backend/data/regions.json`. Sie definiert **Profile** (Fahrtgebiete mit
Locale-Standards) und **Regionen** (Geofabrik-OSM-Extrakte, aus denen
Basiskarten-MBTiles bzw. OSRM-Graphen entstehen).

Das Backend enthält kein festverdrahtetes `germany` mehr — Standard-Basiskarte,
Kartenmitte, Einheiten, Sprache und Datenanbieter kommen aus dem aktiven Profil.

## Profile

| Profil | Sprache | Einheiten | Basiskarte | Pegel/Tide | Wetter / Warnungen | Karten |
|---|---|---|---|---|---|---|
| `de` (Standard) | de | metrisch | `germany` | `pegelonline` | `openweather` / `dwd` | `elwis` (IENC) |
| `us-east` | en | imperial | `us-south` | `noaa-coops` | `nws` / `nws` | `noaa-enc` |
| `bahamas` | en | imperial | `bahamas` | `noaa-coops` | `nws` / `nws` | `osm` (keine ENCs) |

Profilfelder:

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

`tideProvider` / `weatherProvider` / `alertProvider` / `chartSource` sind Kennungen,
die spätere Provider-Module auslesen. Eine frische Installation ohne
`settings.json` verhält sich exakt wie der bisherige Deutschland-Build.

## Regionen (Geofabrik-Extrakte)

```json
{ "id": "florida", "name": "Florida", "geofabrik": "north-america/us/florida", "profile": "us-east" }
```

* `id` — Dateiname der `.mbtiles` (`data/florida.mbtiles`), Name des OSRM-Graphen
  (`data/osrm/florida-latest.osrm`) und Name der Vektor-Tile-Quelle.
* `geofabrik` — Pfad unter `https://download.geofabrik.de/` (ohne `-latest.osm.pbf`).
* `profile` — Profil, in dem die Region zuerst gelistet wird (optional).

Beliebige Geofabrik-Extrakte funktionieren: Eintrag hinzufügen, und die Region
erscheint unter **Einstellungen → Karte → Offline-Karten**, sobald eine passende
`.mbtiles` existiert. Dateien ohne Registry-Eintrag werden mit dem Dateinamen gelistet.

### Lokale Ergänzungen ohne Git

`backend/data/regions.local.json` mit gleicher Struktur anlegen; sie wird über
`regions.json` gemischt (Profile und Regionen werden per Schlüssel/ID ergänzt oder überschrieben).

## Profil wählen

* **UI:** Einstellungen → Karte → *Region & Fahrtgebiet*.
* **API:**

```bash
curl http://localhost:8000/api/regions            # Registry (Profile + Regionen)
curl http://localhost:8000/api/region             # wirksame Konfiguration
curl -X POST http://localhost:8000/api/region -H 'content-type: application/json' \
     -d '{"profile":"us-east"}'                    # Profil wechseln
curl -X POST http://localhost:8000/api/region -H 'content-type: application/json' \
     -d '{"units":"metric"}'                       # einzelnes Feld überschreiben
```

Überschreibungen liegen unter `region` in `backend/data/settings.json` und haben
Vorrang vor den Profil-Standards. Das Frontend lädt `/api/region` beim Start
(`core.loadRegionConfig()` → `REGION_CONFIG`, auch `window.BOATOS_REGION`) und nutzt
es für Kartenmitte/Zoom und den Namen der Basiskarten-Quelle.

## Skripte

| Skript | Regionsbehandlung |
|---|---|
| `scripts/extract_regions.sh [id|geofabrik-pfad|all]` | OSRM-Graphen; Liste aus `regions.json`, Filter über `BOATOS_REGION_PROFILE=us-east` |
| `process_germany.sh [region]` | alter Einzel-Extrakt-Build, Standard `germany` |
| `tools/mbtiles-creator/` | Windows-MBTiles-Tool mit eigener Extraktliste inkl. USA |
| `deploy/tileserver-config.json`, `deploy/basic-style.json` | tileserver-gl-Beispiele mit `germany.mbtiles`; durch eigene Region-ID ersetzen |
| `frontend/test_tiles.html?region=<id>` | Tile-Schnelltest für beliebige Regionen |

Zum Erzeugen der MBTiles siehe [tileserver_de.md](tileserver_de.md).
