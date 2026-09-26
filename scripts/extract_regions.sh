#!/bin/bash
# Extract Geofabrik regions for OSRM waterway routing.
# Regions come from backend/data/regions.json (id + geofabrik path); any other
# Geofabrik path (e.g. north-america/us/florida) can be passed directly.
set -e

echo "🚢 OSRM Waterway Region Extractor"
echo "=================================="
echo ""

OSRM_BACKEND="$HOME/osrm-backend"
OSRM_REGIONS="$HOME/osrm_regions"
BOATOS_DATA="$HOME/BoatOS/data/osrm"

# Check if OSRM is installed
if ! command -v osrm-extract &> /dev/null; then
    echo "❌ OSRM not found. Please run install.sh first."
    exit 1
fi

# Check if waterway profile exists
if [ ! -f "$OSRM_BACKEND/profiles/waterway.lua" ]; then
    echo "❌ Waterway profile not found at $OSRM_BACKEND/profiles/waterway.lua"
    exit 1
fi

# Regions from the registry (id<TAB>geofabrik-path), profile filter optional
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGISTRY="${BOATOS_REGIONS_JSON:-$SCRIPT_DIR/../backend/data/regions.json}"
REGION_PROFILE="${BOATOS_REGION_PROFILE:-}"
REGIONS=()
declare -A GEOFABRIK
while IFS=$'\t' read -r rid rpath; do
    REGIONS+=("$rid"); GEOFABRIK["$rid"]="$rpath"
done < <(python3 - "$REGISTRY" "$REGION_PROFILE" <<'PY'
import json, sys
reg = json.load(open(sys.argv[1]))
prof = sys.argv[2]
for r in reg["regions"]:
    if prof and r.get("profile") != prof:
        continue
    print(f"{r['id']}\t{r['geofabrik']}")
PY
)

# Resolve a region id (or raw Geofabrik path) to its download URL
geofabrik_url() {
    local path="${GEOFABRIK[$1]:-$1}"
    echo "https://download.geofabrik.de/${path}-latest.osm.pbf"
}

# Show menu if no argument provided
if [ $# -eq 0 ]; then
    echo "Verfügbare Regionen:"
    echo ""
    for i in "${!REGIONS[@]}"; do
        printf "  %2d) %s\n" $((i+1)) "${REGIONS[$i]}"
    done
    echo ""
    echo "  all) alle Regionen extrahieren (Filter: BOATOS_REGION_PROFILE=de|us-east|bahamas)"
    echo ""
    read -p "Region auswählen (Nummer, ID, Geofabrik-Pfad oder 'all'): " selection

    if [ "$selection" = "all" ]; then
        SELECTED_REGIONS=("${REGIONS[@]}")
    elif [[ "$selection" =~ ^[0-9]+$ ]] && [ $selection -ge 1 ] && [ $selection -le ${#REGIONS[@]} ]; then
        SELECTED_REGIONS=("${REGIONS[$((selection-1))]}")
    else
        SELECTED_REGIONS=("$selection")
    fi
else
    if [ "$1" = "all" ]; then
        SELECTED_REGIONS=("${REGIONS[@]}")
    else
        SELECTED_REGIONS=("$@")
    fi
fi

# Create regions directory
mkdir -p "$OSRM_REGIONS"
cd "$OSRM_REGIONS"

echo ""
echo "Extracting ${#SELECTED_REGIONS[@]} region(s)..."
echo ""

for SEL in "${SELECTED_REGIONS[@]}"; do
    REGION="$(basename "$SEL")"
    echo "=== Processing: $REGION ($(geofabrik_url "$SEL")) ==="

    # Download if not exists
    if [ ! -f "${REGION}-latest.osm.pbf" ]; then
        echo "  [1/4] Downloading OSM data..."
        wget -q --show-progress -O "${REGION}-latest.osm.pbf" "$(geofabrik_url "$SEL")"
    else
        echo "  [1/4] OSM data already downloaded"
    fi

    # Extract
    echo "  [2/4] Extracting with waterway profile..."
    osrm-extract -p "$OSRM_BACKEND/profiles/waterway.lua" "${REGION}-latest.osm.pbf"

    # Partition
    echo "  [3/4] Partitioning..."
    osrm-partition "${REGION}-latest.osrm"

    # Customize
    echo "  [4/4] Customizing..."
    osrm-customize "${REGION}-latest.osrm"

    echo "  ✅ $REGION complete!"
    echo ""
done

# Copy all to BoatOS data directory
echo "Copying OSRM data to $BOATOS_DATA..."
cp *.osrm* "$BOATOS_DATA/" 2>/dev/null || true

echo ""
echo "✅ Extraction complete!"
echo ""
echo "Total OSRM files: $(ls $BOATOS_DATA/*.osrm 2>/dev/null | wc -l)"
echo ""
echo "To switch regions, update the OSRM service:"
echo "  sudo systemctl stop osrm"
echo "  sudo nano /etc/systemd/system/osrm.service  # Change .osrm file"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl start osrm"
