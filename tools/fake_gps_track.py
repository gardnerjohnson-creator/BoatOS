#!/usr/bin/env python3
"""
Drive a simulated vessel along a track by POSTing positions to
POST /api/gps/external (the same endpoint the phone/tablet GPS uses).

    tools/fake_gps_track.py [--api http://localhost:8000] [--interval 1]
                            [--speed 6] [--track hamburg|us-east|bahamas]
                            [--gpx file.gpx] [--loop]

The backend treats external GPS as an override that expires 10 s after the
last update, so stopping this script hands GPS back to SignalK/MQTT.
"""
import argparse
import math
import time
import xml.etree.ElementTree as ET

import requests

TRACKS = {
    # Elbe, Hamburg harbour → downstream
    "hamburg": [
        (53.5447, 9.9660), (53.5432, 9.9520), (53.5405, 9.9380),
        (53.5390, 9.9200), (53.5375, 9.9000), (53.5395, 9.8800),
        (53.5440, 9.8600), (53.5480, 9.8400),
    ],
    # Intracoastal Waterway near Fort Lauderdale → Port Everglades → Atlantic
    "us-east": [
        (26.1224, -80.1210), (26.1180, -80.1195), (26.1120, -80.1180),
        (26.1000, -80.1160), (26.0935, -80.1150), (26.0930, -80.1050),
        (26.0925, -80.0900), (26.0920, -80.0700),
    ],
    # Nassau harbour → Paradise Island
    "bahamas": [
        (25.0800, -77.3500), (25.0810, -77.3400), (25.0830, -77.3300),
        (25.0850, -77.3200), (25.0870, -77.3100), (25.0900, -77.3000),
    ],
}


def load_gpx(path):
    ns = {"g": "http://www.topografix.com/GPX/1/1"}
    root = ET.parse(path).getroot()
    pts = root.findall(".//g:trkpt", ns) or root.findall(".//trkpt")
    return [(float(p.get("lat")), float(p.get("lon"))) for p in pts]


def bearing(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    x = math.sin(lon2 - lon1) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def distance_m(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def interpolate(track, step_m):
    for a, b in zip(track, track[1:]):
        d = distance_m(a, b)
        n = max(1, int(d // step_m))
        brg = bearing(a, b)
        for i in range(n):
            f = i / n
            yield (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, brg)
    yield (*track[-1], bearing(track[-2], track[-1]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--speed", type=float, default=6.0, help="knots")
    ap.add_argument("--track", choices=sorted(TRACKS), default="hamburg")
    ap.add_argument("--gpx", help="GPX file to follow instead of a built-in track")
    ap.add_argument("--loop", action="store_true", help="restart at the beginning when finished")
    args = ap.parse_args()

    track = load_gpx(args.gpx) if args.gpx else TRACKS[args.track]
    step_m = args.speed * 1852 / 3600 * args.interval
    url = f"{args.api.rstrip('/')}/api/gps/external"
    print(f"🛥  {len(track)} waypoints, {args.speed} kn, POST {url} every {args.interval}s (Ctrl+C to stop)")

    offline = False
    while True:
        for lat, lon, brg in interpolate(track, step_m):
            try:
                r = requests.post(url, json={"lat": lat, "lon": lon, "speed": args.speed,
                                             "heading": brg, "accuracy": 5}, timeout=3)
                r.raise_for_status()
                if offline:
                    print("\n✅ backend reachable again")
                    offline = False
                print(f"\r📍 {lat:.5f}, {lon:.5f}  COG {brg:5.1f}°  SOG {args.speed} kn   ", end="", flush=True)
            except requests.RequestException as e:
                if not offline:
                    print(f"\n⚠ backend not reachable ({e.__class__.__name__}) — retrying every {args.interval}s")
                    offline = True
            time.sleep(args.interval)
        print("\n🏁 end of track")
        if not args.loop:
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nstopped; backend falls back to SignalK/MQTT GPS in ~10 s")
