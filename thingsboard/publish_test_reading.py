"""Publish ONE controlled reading for ThingsBoard alarm testing.

This is a test helper, not part of the normal simulator. It never touches the
SQLite database and never changes the telemetry schema. It uses the same TLS
MQTT client and token routing as ``python -m src.main --sync``.

Example (PowerShell, after setting the three FSN_XX_TOKEN variables):

    python thingsboard/publish_test_reading.py --node FSN-01 --turbidity 60

No token is printed. The token is read only from the environment or .env.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import mqtt_client  # noqa: E402
from src.simulator import SCENARIOS, REQUIRED_FIELDS, load_config  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", required=True, choices=list(mqtt_client.NODE_TOKEN_VARS))
    parser.add_argument("--ph", type=float, default=7.1)
    parser.add_argument("--turbidity", type=float, default=4.0)
    parser.add_argument("--tds", type=int, default=180)
    parser.add_argument("--temp", type=float, default=21.0)
    parser.add_argument("--flow", type=float, default=12.0)
    parser.add_argument("--scenario", choices=SCENARIOS, default="normal")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    mqtt_client.load_local_env()

    host = os.environ.get("THINGSBOARD_HOST", "").strip()
    env_name = mqtt_client.NODE_TOKEN_VARS[args.node]
    token = os.environ.get(env_name, "").strip()
    if not host:
        print("THINGSBOARD_HOST is not set."); return 2
    if not mqtt_client._is_usable_token(token):
        print(f"{env_name} is not set (or is still a placeholder)."); return 2

    config = load_config(Path(__file__).resolve().parents[1] / "config" / "nodes.json")
    node = next(n for n in config["nodes"] if n["node_id"] == args.node)

    reading = {
        "ts": time.time_ns() // 1_000_000,
        "node_id": args.node,
        "water_point": node["water_point"],
        "latitude": float(node["latitude"]),
        "longitude": float(node["longitude"]),
        "ph": round(args.ph, 2),
        "turbidity_ntu": round(args.turbidity, 1),
        "tds_ppm": int(args.tds),
        "water_temp_c": round(args.temp, 1),
        "flow_lpm": round(args.flow, 1),
        "scenario": args.scenario,
    }
    if tuple(reading) != REQUIRED_FIELDS:  # safety net
        raise SystemExit("Test reading does not match the telemetry schema.")

    client_id = f"{mqtt_client.CLIENT_ID}-{args.node.lower()}-test"
    client = mqtt_client.build_client(token, client_id=client_id)
    try:
        mqtt_client.connect(client, host)
        delivered = mqtt_client.publish_reading(client, reading)
    except mqtt_client.MQTTError as exc:
        print(f"MQTT error for {args.node}: {exc}")
        return 1
    finally:
        mqtt_client.disconnect(client)

    if not delivered:
        print(f"Delivery not confirmed for {args.node}; nothing was marked sent.")
        return 1
    print(
        f"Delivered test reading for {args.node}: "
        f"turbidity={reading['turbidity_ntu']} NTU, ph={reading['ph']}, "
        f"tds={reading['tds_ppm']} ppm, flow={reading['flow_lpm']} L/min."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
