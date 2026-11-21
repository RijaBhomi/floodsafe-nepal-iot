"""Command-line entry point for the FloodSafe Nepal telemetry simulator.

Example:
    python -m src.main --scenario flood --count 12 --output output/flood.jsonl

Each reading is printed as one JSON object on its own line. The optional
"--output" file receives the same lines (JSON Lines format).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Support both "python -m src.main" (relative import) and
# "python src/main.py" (plain import) without extra setup.
try:
    from .simulator import SCENARIOS, SimulationError, generate_readings, load_config
except ImportError:  # pragma: no cover - only used when run as a plain script
    from simulator import SCENARIOS, SimulationError, generate_readings, load_config

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
        required=True,
        choices=SCENARIOS,
        help="which sensor model to run",
    )
    parser.add_argument(
        "--count",
        required=True,
        type=positive_int,
        help="total number of readings to generate (spread across the 3 nodes)",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        help=(
            "optional JSON Lines file; relative paths start at the project root "
            "(e.g. output/flood.jsonl)"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        config = load_config(DEFAULT_CONFIG)
        readings = generate_readings(config, args.scenario, args.count)

        output_path: Path | None = None
        if args.output:
            output_path = Path(args.output)
            if not output_path.is_absolute():
                output_path = PROJECT_ROOT / output_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
    except SimulationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # Serialize once so stdout and the optional file are identical.
    lines = [json.dumps(reading) for reading in readings]

    if output_path is not None:
        try:
            with output_path.open("w", encoding="utf-8") as handle:
                for line in lines:
                    handle.write(line + "\n")
        except OSError as exc:
            print(f"Error: could not write {output_path}: {exc}", file=sys.stderr)
            return 1

    # Only JSON goes to stdout, so piping remains valid JSON Lines.
    for line in lines:
        print(line)

    if output_path is not None:
        print(f"Saved {len(lines)} readings to {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
