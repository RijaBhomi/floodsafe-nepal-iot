"""Offline checks for the deterministic Intervention response scenario.

The scenario is checked against the committed alarm rules and the operational
state transform so a future edit cannot silently break the demonstration. No
network, ThingsBoard tenant or real database is needed.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from src.simulator import REQUIRED_FIELDS, RESPONSE_STEPS, generate_readings, load_config

ROOT = Path(__file__).resolve().parents[1]
TB = ROOT / "thingsboard"


def numbers(expression: str) -> list[float]:
    """Read the numeric thresholds from a documented rule expression."""
    return [float(value) for value in re.findall(r"\d+(?:\.\d+)?", expression)]


def tbel_constants() -> dict[str, float]:
    source = (TB / "operational_state.tbel.js").read_text(encoding="utf-8")
    constants = dict(re.findall(r"var\s+(\w+)\s*=\s*([0-9.]+);", source))
    required = (
        "WATCH_TURBIDITY_NTU",
        "WATCH_TDS_PPM",
        "PH_LOW",
        "PH_HIGH",
        "HIGH_TURBIDITY_WARNING",
        "GROSS_CONTAMINATION",
        "HIGH_TDS_CRITICAL",
    )
    return {name: float(constants[name]) for name in required}


def operational_state(reading: dict, constants: dict[str, float]) -> str:
    """Mirror the committed stateless TBEL decision tree for one reading."""
    turbidity = reading["turbidity_ntu"]
    ph = reading["ph"]
    tds = reading["tds_ppm"]
    flow = reading["flow_lpm"]

    unusual_count = sum(
        (
            turbidity > constants["WATCH_TURBIDITY_NTU"],
            ph < constants["PH_LOW"] or ph > constants["PH_HIGH"],
            tds > constants["WATCH_TDS_PPM"],
        )
    )
    critical = (
        turbidity > constants["GROSS_CONTAMINATION"]
        or ph < constants["PH_LOW"]
        or ph > constants["PH_HIGH"]
        or tds > constants["HIGH_TDS_CRITICAL"]
    )
    major = flow == 0
    warning = turbidity > constants["HIGH_TURBIDITY_WARNING"]

    if critical:
        return "Intervention"
    if major or unusual_count >= 2:
        return "Investigate"
    if warning or unusual_count >= 1:
        return "Watch"
    return "Normal"


class ResponseScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config(ROOT / "config" / "nodes.json")
        cls.rules = {
            alarm["name"]: alarm
            for alarm in json.loads(
                (TB / "alarm_rules.json").read_text(encoding="utf-8")
            )["alarms"]
        }
        cls.constants = tbel_constants()
        cls.readings = generate_readings(cls.config, "response", 18)

    def alarm_conditions(self, name: str, reading: dict) -> tuple[bool, bool]:
        """Return (create, clear) for a reading using the documented rules."""
        rule = self.rules[name]
        turbidity = reading["turbidity_ntu"]
        ph = reading["ph"]
        tds = reading["tds_ppm"]
        flow = reading["flow_lpm"]

        if name in ("High Turbidity", "Gross Contamination"):
            threshold = numbers(rule["create"])[0]
            clear = numbers(rule["clear"])[0]
            return turbidity > threshold, turbidity < clear
        if name == "pH Out of Range":
            low, high = numbers(rule["create"])
            clear_low, clear_high = numbers(rule["clear"])
            return ph < low or ph > high, clear_low <= ph <= clear_high
        if name == "High TDS":
            threshold = numbers(rule["create"])[0]
            clear = numbers(rule["clear"])[0]
            return tds > threshold, tds < clear
        if name == "Supply Interruption":
            self.assertIn("flow_lpm == 0", rule["create"])
            self.assertEqual(rule["clear"], "flow_lpm > 0")
            return flow == 0, flow > 0
        raise AssertionError(f"Unexpected alarm: {name}")

    def apply_alarms(self, active: set[str], reading: dict) -> None:
        names = (
            "High Turbidity",
            "Gross Contamination",
            "pH Out of Range",
            "High TDS",
            "Supply Interruption",
        )
        for name in names:
            create, clear = self.alarm_conditions(name, reading)
            if create:
                active.add(name)
            elif clear:
                active.discard(name)

    def readings_for(self, node_id: str) -> list[dict]:
        return [reading for reading in self.readings if reading["node_id"] == node_id]

    def test_response_scenario_is_registered_and_keeps_the_schema(self) -> None:
        from src.simulator import SCENARIOS

        self.assertIn("response", SCENARIOS)
        self.assertEqual(len(self.readings), 18)
        for reading in self.readings:
            self.assertEqual(tuple(reading), REQUIRED_FIELDS)
            self.assertEqual(reading["scenario"], "response")
            self.assertIsInstance(reading["water_temp_c"], (int, float))

    def test_every_node_receives_the_six_deterministic_steps(self) -> None:
        for node in self.config["nodes"]:
            readings = self.readings_for(node["node_id"])
            self.assertEqual(len(readings), 6)
            actual = [
                (
                    reading["ph"],
                    reading["turbidity_ntu"],
                    reading["tds_ppm"],
                    reading["flow_lpm"],
                )
                for reading in readings
            ]
            expected = [
                (
                    step["ph"],
                    step["turbidity_ntu"],
                    step["tds_ppm"],
                    float(step["flow_lpm"]),
                )
                for step in RESPONSE_STEPS
            ]
            self.assertEqual(actual, expected, node["node_id"])
            self.assertEqual(actual[0], actual[1])  # visible two-reading confirmation

    def test_sequence_matches_states_and_alarm_thresholds(self) -> None:
        expected_states = (
            "Intervention",
            "Intervention",
            "Intervention",
            "Investigate",
            "Normal",
            "Normal",
        )
        active: set[str] = set()
        for step, (reading, expected_state) in enumerate(
            zip(self.readings_for("FSN-01"), expected_states), start=1
        ):
            with self.subTest(step=step):
                self.apply_alarms(active, reading)
                self.assertEqual(
                    operational_state(reading, self.constants), expected_state
                )
                if step == 1:
                    self.assertEqual(
                        {
                            "Gross Contamination",
                            "pH Out of Range",
                            "High TDS",
                        },
                        {
                            name
                            for name in active
                            if self.rules[name]["severity"] == "Critical"
                        }
                        - {"Node Inactive"},
                    )
                    self.assertIn("High Turbidity", active)
                if step == 3:
                    self.assertIn("Supply Interruption", active)
                if step == 4:
                    self.assertIn("Supply Interruption", active)
                    self.assertNotIn("Gross Contamination", active)
                    self.assertNotIn("pH Out of Range", active)
                    self.assertNotIn("High TDS", active)
                    self.assertNotIn("High Turbidity", active)
                if step >= 5:
                    self.assertEqual(active, set())

    def test_safe_steps_are_inside_every_clear_band(self) -> None:
        for reading in self.readings_for("FSN-01")[3:]:
            for name in (
                "High Turbidity",
                "Gross Contamination",
                "pH Out of Range",
                "High TDS",
            ):
                with self.subTest(step=reading["ts"], alarm=name):
                    create, clear = self.alarm_conditions(name, reading)
                    self.assertFalse(create)
                    self.assertTrue(clear)


if __name__ == "__main__":
    unittest.main()
