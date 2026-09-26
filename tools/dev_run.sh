#!/usr/bin/env bash
# BoatOS local development runner (no Raspberry Pi required).
#
#   tools/dev_run.sh            # backend + UI on :8000 (+ mosquitto :1883 if installed)
#   tools/dev_run.sh --sensors  # additionally start tools/fake_sensors.py
#   tools/dev_run.sh --gps      # additionally start tools/fake_gps_track.py
#   tools/dev_run.sh --all      # both
#
# Environment overrides: BOATOS_DEV_PORT (8000), BOATOS_MQTT_PORT (1883),
# BOATOS_DEV_BIND (127.0.0.1; set 0.0.0.0 to test from another device),
# BOATOS_SIGNALK_URL (default: disabled in dev).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
VENV="$BACKEND/venv"
API_PORT="${BOATOS_DEV_PORT:-8000}"
BIND="${BOATOS_DEV_BIND:-127.0.0.1}"
MQTT_PORT="${BOATOS_MQTT_PORT:-1883}"

WITH_SENSORS=0
WITH_GPS=0
for arg in "$@"; do
  case "$arg" in
    --sensors) WITH_SENSORS=1 ;;
    --gps) WITH_GPS=1 ;;
    --all) WITH_SENSORS=1; WITH_GPS=1 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

export BOATOS_DEV_MODE=1
export BOATOS_MQTT_HOST="${BOATOS_MQTT_HOST:-localhost}"
export BOATOS_MQTT_PORT="$MQTT_PORT"
# SignalK is normally not running on a dev box: disable polling unless the
# developer explicitly points at one.
export BOATOS_SIGNALK_URL="${BOATOS_SIGNALK_URL-}"

# --- venv + requirements --------------------------------------------------
if [ ! -x "$VENV/bin/python" ]; then
  echo "▶ creating venv at $VENV"
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q --upgrade pip
# evdev needs kernel headers and is only used by the Pi remote-control server.
grep -v -E '^evdev' "$BACKEND/requirements.txt" > "$BACKEND/.requirements-dev.txt"
"$VENV/bin/pip" install -q -r "$BACKEND/.requirements-dev.txt"
rm -f "$BACKEND/.requirements-dev.txt"

[ -f "$ROOT/.env" ] || cp "$ROOT/.env.example" "$ROOT/.env"
mkdir -p "$BACKEND/data" "$ROOT/data/charts" "$ROOT/data/routing"

PIDS=()
cleanup() {
  echo; echo "▶ stopping…"
  for p in "${PIDS[@]:-}"; do [ -n "$p" ] && kill "$p" 2>/dev/null || true; done
}
trap cleanup EXIT INT TERM

# --- Mosquitto -----------------------------------------------------------
if command -v mosquitto >/dev/null 2>&1; then
  if (echo > /dev/tcp/127.0.0.1/"$MQTT_PORT") 2>/dev/null; then
    echo "▶ MQTT broker already listening on :$MQTT_PORT"
  else
    echo "▶ starting mosquitto on :$MQTT_PORT"
    MQ_CONF="$(mktemp)"
    printf 'listener %s %s\nallow_anonymous true\n' "$MQTT_PORT" "$BIND" > "$MQ_CONF"
    mosquitto -c "$MQ_CONF" -v >"$BACKEND/data/mosquitto-dev.log" 2>&1 &
    PIDS+=($!)
  fi
else
  echo "⚠ mosquitto not installed — MQTT disabled (apt install mosquitto / brew install mosquitto)"
fi

# --- Backend -------------------------------------------------------------
echo "▶ starting backend on :$API_PORT (dev mode)"
( cd "$BACKEND" && exec "$VENV/bin/uvicorn" --app-dir app main:app --host "$BIND" --port "$API_PORT" --reload ) &
PIDS+=($!)

# Frontend: in dev mode the backend mounts frontend/ at "/" so that relative
# /api and /ws URLs hit the same origin (no separate static server needed).

sleep 2
if [ "$WITH_SENSORS" = 1 ]; then
  echo "▶ starting fake sensors"
  "$VENV/bin/python" "$ROOT/tools/fake_sensors.py" --host localhost --port "$MQTT_PORT" &
  PIDS+=($!)
fi
if [ "$WITH_GPS" = 1 ]; then
  echo "▶ starting fake GPS track"
  "$VENV/bin/python" "$ROOT/tools/fake_gps_track.py" --api "http://localhost:$API_PORT" &
  PIDS+=($!)
fi

echo
echo "  BoatOS dev:  UI http://localhost:$API_PORT   API http://localhost:$API_PORT/docs"
echo "  Ctrl+C stops everything."
wait
