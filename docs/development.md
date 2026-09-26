# Local Development (no Raspberry Pi required)

BoatOS normally runs on a Raspberry Pi with SignalK, Mosquitto, systemd
services, GPIO and a Wayland kiosk. **Dev mode** lets you run the backend and
the web frontend on any Linux/macOS/WSL machine so changes can be verified
without hardware.

## Quick start

```bash
git clone https://github.com/gardnerjohnson-creator/BoatOS.git
cd BoatOS
tools/dev_run.sh --all
```

This will:

| Step | What happens |
|------|--------------|
| venv | creates `backend/venv` and installs `backend/requirements.txt` (minus `evdev`, which is Pi-only) |
| `.env` | copies `.env.example` to `.env` if none exists |
| Mosquitto | starts a broker on `:1883` (skipped with a warning if `mosquitto` is not installed) |
| Backend | `uvicorn app.main:app --reload` on `:8000` with `BOATOS_DEV_MODE=1` |
| Frontend | in dev mode the backend mounts `frontend/` at `/`, so the UI is on `:8000` too (relative `/api` + `/ws` URLs work without a proxy) |
| `--sensors` | runs `tools/fake_sensors.py` (MQTT engine/battery/tank/attitude/flow/bilge/GPS) |
| `--gps` | runs `tools/fake_gps_track.py` (moving position via `POST /api/gps/external`) |

Open http://localhost:8000 (UI) and http://localhost:8000/docs (API).
Everything binds to `127.0.0.1`; set `BOATOS_DEV_BIND=0.0.0.0` to reach it from
another device on your network (the dev stack has no authentication).
`Ctrl+C` stops everything.

Install Mosquitto with `sudo apt install mosquitto` (Debian/Ubuntu) or
`brew install mosquitto` (macOS).

## Environment variables

All variables live in `.env` (see `.env.example`) or the process environment.

| Variable | Default | Meaning |
|----------|---------|---------|
| `BOATOS_DEV_MODE` | unset | `1`/`true`/`yes`/`on` enables dev mode. **Unset = production behaviour, unchanged.** |
| `BOATOS_SIGNALK_URL` | `http://localhost:3000` | SignalK server. Set to an **empty string** to disable SignalK polling entirely (GPS then comes from MQTT `boat/gps/*` or `POST /api/gps/external`). `tools/dev_run.sh` disables it unless you export a URL. |
| `BOATOS_MQTT_HOST` | `localhost` | MQTT broker host used by the backend. |
| `BOATOS_MQTT_PORT` | `1883` | MQTT broker port. |
| `BOATOS_DEV_BIND` | `127.0.0.1` | Bind address used by `tools/dev_run.sh` for Mosquitto and uvicorn. |

## What dev mode changes

Everything is centralised in `backend/app/devmode.py`:

```python
devmode.is_dev_mode()              # bool
devmode.signalk_url()              # str | None (None = disabled)
devmode.mqtt_host() / mqtt_port()
devmode.run_system(cmd, **kw)      # subprocess.run       → no-op, returncode 0 in dev mode
devmode.check_output_system(cmd)   # subprocess.check_output → b""
devmode.popen_system(cmd)          # subprocess.Popen     → None
await devmode.run_system_async(*cmd)  # asyncio.create_subprocess_exec → fake process
```

When `BOATOS_DEV_MODE` is **unset** every wrapper passes straight through to
`subprocess`, so a Pi installation behaves exactly as before.

When dev mode is **on**:

- Pi/systemd-only commands (`systemctl`, `sudo`, `nmcli`, `pinctrl`, `pkill`,
  tileserver/OSRM/Helm restarts, shutdown/reboot, `update.sh`) are logged as
  `🧪 [dev-mode] skipped system command: …` and the API returns `ok`.
- `/api/gps/config` returns `{"status": "ok", "dev_mode": true}` instead of
  writing SignalK settings and restarting `signalk.service`.
- `backend/virtual_input.py` does not import `evdev`/uinput; the remote-control
  server logs touches instead of injecting them and skips `grim` screenshots.
- `display_power.py` GPIO calls become no-ops.
- Missing SignalK is not an error: `gps_service.read_gps_from_signalk()` exits
  immediately when the URL is empty, and logs/backs off when it is unreachable.

Use the wrappers for any **new** hardware/OS call so it stays testable:

```python
import devmode
devmode.run_system(["sudo", "systemctl", "restart", "foo.service"], check=True)
```

## Fake data tools

```bash
# MQTT sensors — topics match _SENSOR_GROUP_RULES in backend/app/main.py
tools/fake_sensors.py --host localhost --port 1883 --interval 2
tools/fake_sensors.py --no-gps            # keep boat/gps/* quiet (e.g. when using fake_gps_track)

# Moving GPS via POST /api/gps/external
tools/fake_gps_track.py --track hamburg   # also: us-east, bahamas
tools/fake_gps_track.py --gpx my_trip.gpx --speed 8 --loop
```

Published MQTT topics: `boot/sensoren/motor/*`, `boot/sensoren/batterie/*`,
`boot/sensoren/tank/*`, `boot/sensoren/lage/*`, `boot/sensoren/durchfluss/*`,
`boatos/bilge/*`, `boat/gps/{latitude,longitude,speed,course,altitude,satellites}`.

## Running the backend manually

```bash
cd backend
source venv/bin/activate
BOATOS_DEV_MODE=1 BOATOS_SIGNALK_URL= uvicorn app.main:app --reload --port 8000
```

## Verifying

```bash
curl -s localhost:8000/api/gps
curl -s localhost:8000/api/sensors | jq keys
curl -s -X POST localhost:8000/api/gps/config -H 'content-type: application/json' \
     -d '{"device":"/dev/ttyUSB0","baud":9600}'   # → {"status":"ok",...,"dev_mode":true}
```
