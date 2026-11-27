"""Virtual sensor logic for FloodSafe Nepal.

This module turns a small JSON configuration into realistic-looking
water-quality readings. It deliberately contains no database, MQTT, cloud or
dashboard code — only the sensor models and the shared telemetry schema.
The "response" scenario emits a deterministic Intervention → containment →
verification → recovery sequence for the operational-response demo.

Only Python's standard library is used.
"""

from __future__ import annotations

import json
import math
import random
import time
from pathlib import Path
from typing import Any

# The only scenario names accepted by the command line and the simulator.
SCENARIOS = ("normal", "flood", "response")

# Deterministic intervention-response demonstration sequence. Each node receives one step
# per round-robin pass, so "--scenario response --count 18" gives every node all
# six steps. Values are chosen to match the documented alarm clear thresholds
# and the operational_state transform; they are scenario data, not a mid-demo
# script edit. Water temperature still comes from the normal baseline model.
RESPONSE_STEPS = (
    {"ph": 6.2, "turbidity_ntu": 260, "tds_ppm": 600, "flow_lpm": 12},
    {"ph": 6.2, "turbidity_ntu": 260, "tds_ppm": 600, "flow_lpm": 12},
    {"ph": 6.2, "turbidity_ntu": 260, "tds_ppm": 600, "flow_lpm": 0},
    {"ph": 7.1, "turbidity_ntu": 4, "tds_ppm": 180, "flow_lpm": 0},
    {"ph": 7.1, "turbidity_ntu": 4, "tds_ppm": 180, "flow_lpm": 12},
    {"ph": 7.1, "turbidity_ntu": 4, "tds_ppm": 180, "flow_lpm": 12},
)

# The exact key set of one telemetry reading. Keeping this in one place makes
# it easy to check that every code path produces the same schema.
REQUIRED_FIELDS = (
    "ts",
    "node_id",
    "water_point",
    "latitude",
    "longitude",
    "ph",
    "turbidity_ntu",
    "tds_ppm",
    "water_temp_c",
    "flow_lpm",
    "scenario",
)


class SimulationError(Exception):
    """Raised when the configuration or simulation inputs are invalid."""


def load_config(path: str | Path) -> dict[str, Any]:
    """Read config/nodes.json and check the parts the simulator relies on."""
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            config = json.load(handle)
    except FileNotFoundError as exc:
        raise SimulationError(f"Config file not found: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise SimulationError(
            f"Config file is not valid JSON: {config_path} ({exc})"
        ) from exc
    except OSError as exc:
        raise SimulationError(f"Could not read config file {config_path}: {exc}") from exc

    if not isinstance(config, dict):
        raise SimulationError("Config root must be a JSON object.")

    nodes = config.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise SimulationError("Config must contain a non-empty 'nodes' list.")

    # Node IDs must be unique, and so must the demonstration coordinates.
    seen_ids: set[str] = set()
    seen_locations: set[tuple[float, float]] = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise SimulationError(f"Node at index {index} must be a JSON object.")
        for field in ("node_id", "water_point", "latitude", "longitude"):
            if field not in node:
                raise SimulationError(f"Node at index {index} is missing '{field}'.")

        node_id = str(node["node_id"])
        if node_id in seen_ids:
            raise SimulationError(f"Duplicate node_id: {node_id}")
        seen_ids.add(node_id)

        try:
            location = (float(node["latitude"]), float(node["longitude"]))
        except (TypeError, ValueError) as exc:
            raise SimulationError(f"Node {node_id} has invalid coordinates.") from exc
        if location in seen_locations:
            raise SimulationError(f"Duplicate coordinates for node {node_id}.")
        seen_locations.add(location)

    simulation = config.get("simulation")
    if not isinstance(simulation, dict):
        raise SimulationError("Config must contain a 'simulation' object.")
    for section in ("baseline", "flood", "flood_event"):
        if not isinstance(simulation.get(section), dict):
            raise SimulationError(f"Config must contain a 'simulation.{section}' object.")

    return config


def _range(settings: dict[str, Any], key: str) -> tuple[float, float]:
    """Return a configured [low, high] pair as two floats."""
    value = settings.get(key)
    if not isinstance(value, list) or len(value) != 2:
        raise SimulationError(f"Expected '{key}' to be a two-number list.")
    try:
        low, high = float(value[0]), float(value[1])
    except (TypeError, ValueError) as exc:
        raise SimulationError(f"'{key}' must contain two numbers.") from exc
    if low > high:
        raise SimulationError(f"'{key}' has a lower bound above its upper bound.")
    return low, high


def _number(settings: dict[str, Any], key: str) -> float:
    """Return one configured numeric setting as a float."""
    if key not in settings:
        raise SimulationError(f"Missing simulation setting: '{key}'")
    try:
        return float(settings[key])
    except (TypeError, ValueError) as exc:
        raise SimulationError(f"Setting '{key}' must be a number.") from exc


def event_severity(
    step: int, total_steps: int, event_settings: dict[str, Any]
) -> float:
    """Return the shared contamination severity for one sample step.

    The curve has three parts: a fast rise to 1.0, a short peak, then a slow
    exponential washout back towards ``minimum_severity``. Every node at the
    same step gets the same value, which models one shared event.
    """
    minimum = _number(event_settings, "minimum_severity")
    rise = _number(event_settings, "rise_fraction")
    peak = _number(event_settings, "peak_fraction")
    decay = _number(event_settings, "washout_rate")

    if not 0 <= minimum < 1:
        raise SimulationError("'minimum_severity' must be at least 0 and below 1.")
    if rise <= 0 or peak <= 0 or rise + peak >= 1:
        raise SimulationError("'rise_fraction' + 'peak_fraction' must be between 0 and 1.")
    if decay <= 0:
        raise SimulationError("'washout_rate' must be greater than 0.")

    # With a single step there is no timeline to draw, so use the peak.
    if total_steps <= 1:
        return 1.0

    progress = step / (total_steps - 1)  # 0.0 (first step) to 1.0 (last step)
    if progress < rise:
        # Fast rise: scale from the minimum up to full severity.
        return minimum + (1.0 - minimum) * (progress / rise)

    peak_end = rise + peak
    if progress < peak_end:
        return 1.0

    # Slow washout: exponential decay leaves a long tail after the peak.
    washout_progress = (progress - peak_end) / (1.0 - peak_end)
    return minimum + (1.0 - minimum) * math.exp(-decay * washout_progress)


def _water_temperature(rng: random.Random, baseline: dict[str, Any]) -> float:
    """Baseline temperature plus a simple daily (diurnal) cycle and noise."""
    low, high = _range(baseline, "water_temp_c")
    middle = (low + high) / 2
    amplitude = (high - low) / 2

    now = time.localtime()
    hour = now.tm_hour + now.tm_min / 60
    # Coolest around 06:00, warmest around 18:00.
    daily_cycle = math.sin(2 * math.pi * (hour - 6) / 24)

    value = middle + 0.8 * amplitude * daily_cycle + rng.uniform(-0.6, 0.6)
    # Clamp so temperature stays plausible and never becomes extreme.
    return round(max(low, min(high, value)), 1)


def make_reading(
    node: dict[str, Any],
    scenario: str,
    step: int,
    total_steps: int,
    simulation: dict[str, Any],
    rng: random.Random,
    ts_ms: int,
) -> dict[str, Any]:
    """Build one telemetry reading for one node."""
    baseline = simulation["baseline"]

    ph_low, ph_high = _range(baseline, "ph")
    turbidity_low, turbidity_high = _range(baseline, "turbidity_ntu")
    tds_low, tds_high = _range(baseline, "tds_ppm")
    flow_low, flow_high = _range(baseline, "flow_lpm")

    if scenario == "normal":
        # Normal mode: each parameter gently varies inside its baseline range.
        ph = rng.uniform(ph_low, ph_high)
        turbidity = rng.uniform(turbidity_low, turbidity_high)
        tds = rng.uniform(tds_low, tds_high)
        flow = rng.uniform(flow_low, flow_high)

    elif scenario == "response":
        # Intervention response: fixed, documented steps. This is scenario data,
        # so the demo never depends on editing values by hand mid-run.
        values = RESPONSE_STEPS[step % len(RESPONSE_STEPS)]
        ph = values["ph"]
        turbidity = values["turbidity_ntu"]
        tds = values["tds_ppm"]
        flow = float(values["flow_lpm"])

    else:  # scenario == "flood"
        # Flood mode: ONE severity value drives all four affected parameters.
        severity = event_severity(step, total_steps, simulation["flood_event"])
        flood = simulation["flood"]

        # Turbidity carries the clearest signature of a silt intrusion.
        flood_turbidity_low, flood_turbidity_high = _range(flood, "turbidity_ntu")
        turbidity = (
            flood_turbidity_low
            + severity * (flood_turbidity_high - flood_turbidity_low)
        )

        # pH drops with severity. The exponent makes the drop non-linear, and
        # the floor keeps the value physically sensible.
        ph_drop = _number(flood, "ph_drop_per_severity")
        ph_floor = _number(flood, "ph_floor")
        ph = max(ph_floor, rng.uniform(ph_low, ph_high) - ph_drop * severity ** 1.5)

        # Dissolved solids enter with the same ingress, so TDS rises too.
        tds_rise = _number(flood, "tds_rise_ppm_per_severity")
        tds = rng.uniform(tds_low, tds_high) + tds_rise * severity

        # Pressure at the breach perturbs flow; sometimes supply stops entirely.
        flow_reduction = _number(flood, "flow_reduction_per_severity")
        interruption_chance = _number(flood, "flow_interruption_probability")
        if rng.random() < interruption_chance:
            flow = 0.0
        else:
            flow = max(0.0, rng.uniform(flow_low, flow_high) * (1 - flow_reduction * severity))

    # Temperature uses the same plausible daily model in both scenarios.
    water_temp = _water_temperature(rng, baseline)

    reading = {
        "ts": int(ts_ms),
        "node_id": str(node["node_id"]),
        "water_point": str(node["water_point"]),
        "latitude": float(node["latitude"]),
        "longitude": float(node["longitude"]),
        "ph": round(ph, 2),
        "turbidity_ntu": round(turbidity, 1),
        "tds_ppm": int(round(tds)),
        "water_temp_c": water_temp,
        "flow_lpm": round(flow, 1),
        "scenario": scenario,
    }
    if tuple(reading) != REQUIRED_FIELDS:  # safety net during development
        raise SimulationError("Generated reading does not match the telemetry schema.")
    return reading


def generate_readings(
    config: dict[str, Any], scenario: str, count: int
) -> list[dict[str, Any]]:
    """Generate ``count`` readings, shared across the configured nodes."""
    if scenario not in SCENARIOS:
        raise SimulationError(
            f"Invalid scenario '{scenario}'. Choose one of: {', '.join(SCENARIOS)}."
        )
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise SimulationError("'count' must be a whole number of at least 1.")

    nodes = config["nodes"]
    simulation = config["simulation"]
    interval_ms = int(_number(simulation, "sample_interval_ms"))

    # Round-robin: index 0 -> node 0, index 1 -> node 1, index 2 -> node 2,
    # index 3 -> node 0 again. Nodes with the same step share the event phase.
    steps_needed = math.ceil(count / len(nodes))
    rng = random.Random()  # one generator keeps the run self-contained
    start_ms = time.time_ns() // 1_000_000  # Unix time in milliseconds
    readings: list[dict[str, Any]] = []

    for index in range(count):
        node = nodes[index % len(nodes)]
        step = index // len(nodes)
        ts_ms = start_ms + index * interval_ms
        readings.append(
            make_reading(node, scenario, step, steps_needed, simulation, rng, ts_ms)
        )

    return readings
