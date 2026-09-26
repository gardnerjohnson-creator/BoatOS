#!/usr/bin/env python3
"""
Publish simulated sensor values to the MQTT topics BoatOS groups in
backend/app/main.py (_SENSOR_GROUP_RULES): ESP32 engine/battery/tank/
attitude/flow sensors, a bilge sensor and a boat/gps/* GPS module.

    tools/fake_sensors.py [--host localhost] [--port 1883] [--interval 2]
                          [--no-gps] [--lat 53.55 --lon 9.99]

Use --no-gps when tools/fake_gps_track.py provides the position instead
(the external GPS override takes priority in the backend anyway).
"""
import argparse
import math
import random
import time

import paho.mqtt.client as mqtt


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--interval", type=float, default=2.0, help="seconds between publishes")
    ap.add_argument("--no-gps", action="store_true", help="do not publish boat/gps/* topics")
    ap.add_argument("--lat", type=float, default=53.5511, help="start latitude (default Hamburg)")
    ap.add_argument("--lon", type=float, default=9.9937)
    args = ap.parse_args()

    client = mqtt.Client(client_id="boatos_fake_sensors")
    client.connect(args.host, args.port, 60)
    client.loop_start()
    print(f"📡 publishing fake sensors to mqtt://{args.host}:{args.port} every {args.interval}s (Ctrl+C to stop)")

    t0 = time.time()
    lat, lon = args.lat, args.lon
    fuel = 78.0
    water = 55.0
    try:
        while True:
            t = time.time() - t0
            rpm = 1800 + 400 * math.sin(t / 20) + random.uniform(-30, 30)
            pub = client.publish

            # ESP32 engine
            pub("boot/sensoren/motor/drehzahl", f"{rpm:.0f}")
            pub("boot/sensoren/motor/temperatur", f"{78 + 4 * math.sin(t / 60):.1f}")
            pub("boot/sensoren/motor/oeldruck", f"{3.2 + 0.3 * math.sin(t / 15):.2f}")
            pub("boot/sensoren/motor/kuehlwasser", f"{82 + 3 * math.sin(t / 45):.1f}")

            # Battery
            pub("boot/sensoren/batterie/spannung", f"{12.6 + 0.2 * math.sin(t / 90):.2f}")
            pub("boot/sensoren/batterie/strom", f"{-4.5 + 2 * math.sin(t / 30):.2f}")
            pub("boot/sensoren/batterie/ladung", f"{85 + 5 * math.sin(t / 300):.0f}")

            # Tanks
            fuel = max(5.0, fuel - 0.002)
            pub("boot/sensoren/tank/diesel/fuellstand", f"{fuel:.1f}")
            pub("boot/sensoren/tank/diesel/liter", f"{fuel * 2.0:.0f}")
            water = max(0.0, water - 0.001)
            pub("boot/sensoren/tank/wasser/fuellstand", f"{water:.1f}")
            pub("boot/sensoren/tank/abwasser/fuellstand", f"{100 - water:.1f}")

            # Attitude
            pub("boot/sensoren/lage/roll", f"{3 * math.sin(t / 4):.1f}")
            pub("boot/sensoren/lage/pitch", f"{1.5 * math.sin(t / 7):.1f}")
            pub("boot/sensoren/lage/heading", f"{(45 + 10 * math.sin(t / 50)) % 360:.0f}")

            # Fuel flow
            pub("boot/sensoren/durchfluss/liter_pro_stunde", f"{rpm / 400:.2f}")
            pub("boot/sensoren/durchfluss/gesamt", f"{t * 0.001:.3f}")

            # Bilge sensor
            pub("boatos/bilge/temperature", f"{18 + 1.5 * math.sin(t / 120):.1f}")
            pub("boatos/bilge/humidity", f"{65 + 5 * math.sin(t / 200):.0f}")

            # Status topics (ignored by sensor grouping, shown in topic browser)
            pub("boot/status/online", "1")
            pub("boot/status/uptime", f"{t:.0f}")

            if not args.no_gps:
                speed_kn = 5.5 + math.sin(t / 30)
                course = (45 + 10 * math.sin(t / 50)) % 360
                d = speed_kn * 1852 / 3600 * args.interval  # metres this tick
                lat += (d * math.cos(math.radians(course))) / 111_320
                lon += (d * math.sin(math.radians(course))) / (111_320 * math.cos(math.radians(lat)))
                pub("boat/gps/latitude", f"{lat:.6f}")
                pub("boat/gps/longitude", f"{lon:.6f}")
                pub("boat/gps/speed", f"{speed_kn:.1f}")
                pub("boat/gps/course", f"{course:.0f}")
                pub("boat/gps/satellites", str(random.randint(8, 12)))
                pub("boat/gps/altitude", f"{2 + random.uniform(-0.5, 0.5):.1f}")

            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
