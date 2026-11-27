# FloodSafe Nepal — Shared Telemetry Specification

This document is the contract for one telemetry reading. The same spelling,
units and meaning must be used by every later stage of the project (local
buffer, MQTT payload and cloud widgets). Today only the simulator produces
these readings.

## Field list

| Field | Type | Unit | Meaning |
| --- | --- | --- | --- |
| `ts` | integer | Unix epoch milliseconds | Simulated acquisition time of the reading (not the time it is printed). |
| `node_id` | string | — | Stable unique node ID: `FSN-01`, `FSN-02` or `FSN-03`. |
| `water_point` | string | — | Human-readable site name for that node. |
| `latitude` | float | degrees | Fixed demonstration latitude for the node. |
| `longitude` | float | degrees | Fixed demonstration longitude for the node. |
| `ph` | float, 2 dp | pH units | Acidity/alkalinity of the water. |
| `turbidity_ntu` | float, 1 dp | NTU | Cloudiness caused by suspended silt. |
| `tds_ppm` | integer | ppm | Total dissolved solids (dissolved load). |
| `water_temp_c` | float, 1 dp | °C | Water temperature with a gentle daily cycle. |
| `flow_lpm` | float, 1 dp | L/min | Water flow; `0.0` means supply interruption. |
| `scenario` | string | — | `normal` or `flood` — which model produced the reading. |

Field names are exact. Do not rename, add aliases, or change units.

## Example reading

```json
{"ts": 1790000000000, "node_id": "FSN-01", "water_point": "Reservoir Outlet", "latitude": 27.745, "longitude": 85.4167, "ph": 7.12, "turbidity_ntu": 4.8, "tds_ppm": 185, "water_temp_c": 21.4, "flow_lpm": 12.6, "scenario": "normal"}
```

## Scenario values and ranges

| Parameter | `normal` baseline | `flood` behaviour |
| --- | --- | --- |
| `ph` | about 6.8–7.6 | decreases with contamination severity, with a floor of 5.8 |
| `turbidity_ntu` | about 2–8 NTU | configurable 100–800 NTU, driven by severity |
| `tds_ppm` | about 120–250 ppm | rises with the same severity (dissolved ingress load) |
| `water_temp_c` | about 16–24 °C | stays in the same plausible band; no extreme values |
| `flow_lpm` | about 8–18 L/min | reduced by severity and sometimes `0.0` at a supply interruption |

All ranges live in `config/nodes.json` so they can be tuned without editing
Python code.

## Coupled flood event

Flood mode does not draw five independent random numbers. One shared
`severity` value (0.15 → 1.0 → about 0.19) is computed for every sample step
and used by all three nodes:

1. **Fast rise** — severity climbs from its minimum to 1.0.
2. **Peak** — severity holds at 1.0; turbidity and TDS are highest and pH is
   most depressed.
3. **Slow washout** — severity decays exponentially towards the minimum.

This produces the rainfall-triggered silt/sewage intrusion shape needed later
for the demonstration: a sharp turbidity rise, a peak, and a gradual recovery.
Because severity is shared across nodes at the same step, the three water
points experience the same event.

## Timestamps

`ts` is generated from the system clock in milliseconds. Samples in a single
run are spaced by `sample_interval_ms` from the configuration. The simulator
does not sleep between samples, so a run completes immediately while the
timestamps still represent a regular sampling timeline.

## MQTT wire format

The simulator, JSON Lines output and SQLite rows stay flat as shown above. The
MQTT publisher wraps the same 11 fields in ThingsBoard's timestamp envelope:

```json
{"ts": 1790000000000, "values": {"ts": 1790000000000, "node_id": "FSN-01", "water_point": "Reservoir Outlet", "latitude": 27.745, "longitude": 85.4167, "ph": 7.12, "turbidity_ntu": 4.8, "tds_ppm": 185, "water_temp_c": 21.4, "flow_lpm": 12.6, "scenario": "normal"}}
```

The outer `ts` becomes the ThingsBoard record timestamp, so buffered readings
replay with their original client timestamps rather than the sync time. `ts` is
also kept inside `values` so dashboard widgets that read the `ts` telemetry key
continue to work. Database-only columns (`id`, `sent`, `sent_at`) are never sent.

## Node locations

The three coordinates are distinct points in Kathmandu Valley chosen for the
prototype. They are **demonstration coordinates only**: they are not verified
deployment locations and are not a claim that equipment is installed there.

## Limitations

These are surrogate indicator values from a software model. They have no
laboratory calibration, no sensor error model, and must not be used to decide
whether water is safe to drink.
