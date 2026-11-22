"""Command-line entry point for the FloodSafe Nepal telemetry simulator.

Example:
    python -m src.main --scenario flood --count 12 --output output/flood.jsonl
    python -m src.main --scenario normal --count 30 --save-db
    python -m src.main --sync

Each reading is printed as one JSON object on its own line. The optional
"--output" file receives the same lines (JSON Lines format). The optional
"--save-db" flag also stores the readings in the local SQLite buffer. The
optional "--sync" flag publishes pending rows to ThingsBoard once. When
per-node tokens (FSN_01_TOKEN, FSN_02_TOKEN, FSN_03_TOKEN) are set, each node
is routed to its own ThingsBoard device; otherwise the Stage 3 single
THINGSBOARD_TOKEN is used.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

# Support both "python -m src.main" (relative import) and
# "python src/main.py" (plain import) without extra setup.
try:
    from .database import (
        count_pending_readings,
        initialize_database,
        insert_readings,
    )
    from .mqtt_client import MQTTConfigError, MQTTError, has_node_tokens
    from .simulator import SCENARIOS, SimulationError, generate_readings, load_config
    from .sync_manager import sync_from_environment, sync_from_environment_by_node
except ImportError:  # pragma: no cover - only used when run as a plain script
    from database import count_pending_readings, initialize_database, insert_readings
    from mqtt_client import MQTTConfigError, MQTTError, has_node_tokens
    from simulator import SCENARIOS, SimulationError, generate_readings, load_config
    from sync_manager import sync_from_environment, sync_from_environment_by_node

# Resolve paths from the project root so the commands work from any folder.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "nodes.json"


def positive_int(value: str) -> int:
    """argparse type: accept only whole numbers of at least 1."""
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a whole number, e.g. 12") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate FloodSafe Nepal virtual water-quality telemetry."
    )
    parser.add_argument(
        "--scenario",
        choices=SCENARIOS,
        help="which sensor model to run (required unless --sync is used alone)",
    )
    parser.add_argument(
        "--count",
        type=positive_int,
        help="total readings to generate (spread across the 3 nodes)",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        help=(
            "optional JSON Lines file; relative paths start at the project root "
            "(e.g. output/flood.jsonl)"
        ),
    )
    parser.add_argument(
        "--save-db",
        action="store_true",
        help="also save the readings to the local SQLite buffer (data/floodsafe.db)",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="publish pending readings to ThingsBoard once, then exit (no retry loop)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Keep the old CLI behaviour, and allow "--sync" on its own.
    if not args.sync and (args.scenario is None or args.count is None):
        print("Error: --scenario and --count are required unless --sync is used.", file=sys.stderr)
        return 2
    if args.sync and args.scenario is not None and not args.save_db:
        print("Error: --sync with new readings also needs --save-db.", file=sys.stderr)
        return 2

    db_connection: sqlite3.Connection | None = None
    readings: list[dict] = []
    output_path: Path | None = None
    inserted = 0
    pending = 0
    stats: dict[str, int] | None = None

    try:
        if args.scenario is not None:
            config = load_config(DEFAULT_CONFIG)
            readings = generate_readings(config, args.scenario, args.count)

        if args.output:
            output_path = Path(args.output)
            if not output_path.is_absolute():
                output_path = PROJECT_ROOT / output_path
            output_path.parent.mkdir(parents=True, exist_ok=True)

        if args.save_db or args.sync:
            db_connection = initialize_database()

        # Serialize once so stdout and the optional file are identical.
        lines = [json.dumps(reading) for reading in readings]

        if output_path is not None:
            with output_path.open("w", encoding="utf-8") as handle:
                for line in lines:
                    handle.write(line + "\n")

        if db_connection is not None:
            inserted = insert_readings(db_connection, readings)
            pending = count_pending_readings(db_connection)

        if args.sync:
            # One controlled sync attempt; no endless retry loop in this stage.
            # Per-node tokens take priority; the Stage 3 single token still works.
            if has_node_tokens():
                stats = sync_from_environment_by_node(db_connection)
            else:
                stats = sync_from_environment(db_connection)
    except (
        SimulationError,
        OSError,
        sqlite3.Error,
        ValueError,
        MQTTConfigError,
        MQTTError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        if db_connection is not None:
            db_connection.close()

    # Only JSON goes to stdout, so piping remains valid JSON Lines.
    for line in lines:
        print(line)

    if output_path is not None:
        print(f"Saved {len(lines)} readings to {output_path}", file=sys.stderr)
    if args.save_db:
        print(
            f"Saved {inserted} readings to database; "
            f"skipped {len(readings) - inserted} duplicates; "
            f"pending (unsent): {pending}",
            file=sys.stderr,
        )
    if stats is not None:
        print(
            f"MQTT sync finished: sent={stats['sent']}, failed={stats['failed']}, "
            f"attempted={stats['pending']}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
