# Four operational states — decision support, not alarm severities

The states come from **Assessment 1, Table 4** and are confirmed in the
Assessment 2 report. They are **Normal, Watch, Investigate, Intervention**.
Never replace them with ThingsBoard's Warning / Major / Critical severities:
those belong to the six alarms in `alarm_rules.md`.

## What the assignment actually defines

| State | Meaning (exact wording from Assessment 1, Table 4) | Example action |
| --- | --- | --- |
| Normal | Readings are within the expected range. | Continue monitoring |
| Watch | One unusual reading or minor change is detected. | Increase monitoring or sampling |
| Investigate | Multiple abnormal readings or a clear trend is detected. | Send a field team and collect samples |
| Intervention | Serious abnormality continues over time. | Issue a water use advisory and begin response |

The same source says: *"These states now indicate abnormal conditions, not
water-safety levels. Rules are location-specific and require persistent
readings before escalation."*

**The documents do not give numeric transition thresholds, a persistence count,
or an escalation timing.** These are clarification items for your group, not
values I have silently invented.

## Proposed mapping — requires group approval before submission

This candidate mapping is derived only from documented values: NDWQS screening
numbers in Assessment 1 (pH 6.5–8.5, turbidity 5 NTU, TDS 1000 mg/L) and the
exact alarm severities in Task 3.

| Telemetry condition (single reading) | Proposed state | Basis — and limitation |
| --- | --- | --- |
| No unusual value and no active alarm | Normal | "Readings are within the expected range." |
| One unusual screening value, or High Turbidity (Warning) alarm active | Watch | "One unusual reading or minor change"; Warning is the least severe alarm. |
| Two or more unusual values in the same reading, or Supply Interruption (Major) alarm active | Investigate | "Multiple abnormal readings"; Major is the middle severity. **Proxy only** — it does not count readings over time. |
| Gross Contamination, pH Out of Range, High TDS or Node Inactive (Critical) alarm active | Intervention | "Serious abnormality continues over time"; Critical is the highest severity. **Proxy only** — duration is not enforced. |

Because the rule node is stateless, "continues over time" and "clear trend"
cannot be evaluated exactly in the supplied TBEL script. Two compatible options:

1. **Simplest (supplied):** use the table above and state the simplification in
   your manuscript limitations section.
2. **Exact:** add a stateful step — read the device's previous state and an
   `unusual_count` attribute with a `TbGetAttributesNode`, update the count in a
   transform node, and write it back with `TbMsgAttributesNode`. Decide the
   count and timeout with your group first. This needs no change to the Python
   simulator or telemetry schema.

## Implementation supplied

| File | Purpose |
| --- | --- |
| `operational_state.tbel.js` | TBEL transform script. Every proposed constant is commented as PROPOSED. |
| `rule_chain_operational_state.json` | Sanitised real export containing the transform node and a Save Timeseries node, verified in ThingsBoard 4.4.1. |

`msg['operational_state']` is written as a **new telemetry key**. The original
11 telemetry fields are untouched. The dashboard's state table, map labels and
state card bind to this key. The TBEL script returns the full
`{msg, metadata, msgType}` envelope required by ThingsBoard's Script
Transformation node.

## Intervention response loop (scenario-visible)

The built-in `response` scenario demonstrates what an operator does after
Intervention without editing values during the demo:

```powershell
.\.venv\Scripts\python.exe -m src.main --scenario response --count 18 --save-db --sync
```

`--count 18` gives each of the three round-robin nodes six readings. The values
are checked against the committed `alarm_rules.json` thresholds and the TBEL
decision tree by `tests/test_response_scenario.py`.

| Step per node | Reading | Proposed state | Alarm behaviour |
| --- | --- | --- | --- |
| 1 Trigger | turbidity 260, pH 6.2, TDS 600, flow 12 | Intervention | Gross Contamination, pH Out of Range, High TDS and High Turbidity satisfy their create conditions. |
| 2 Confirm | identical to step 1 | Intervention | Visually shows the proposed "two consecutive abnormal readings" idea. It is **not** a rule-chain counter. |
| 3 Contain | same Critical water quality, flow 0 | Intervention | Adds the Supply Interruption create condition (`flow_lpm == 0`). |
| 4 Verify | turbidity 4, pH 7.1, TDS 180, flow 0 | Investigate | Water-quality alarms satisfy their clear bands, but Supply Interruption remains because flow is still 0. |
| 5 Resume | turbidity 4, pH 7.1, TDS 180, flow 12 | Normal | Supply Interruption clears (`flow_lpm > 0`); no water-quality alarm recreates. |
| 6 Stable | identical to step 5 | Normal | Confirms stable recovery. |

This matches the documented hysteresis: Gross Contamination clears below 150
NTU, pH clears within 6.7–8.3, High TDS clears below 450 ppm, High Turbidity
clears below 40 NTU, and Supply Interruption clears above 0 L/min. The
assignment says Supply Interruption must be "sustained" but gives no duration;
the scenario demonstrates the create **condition**, not a group-approved
duration.

Honest limitation: the supplied rule chain remains stateless. The two trigger
steps are scenario evidence for a proposed persistence rule, not proof that
ThingsBoard is counting readings. If your group approves true persistence, use
the attribute-counter option described above instead.

For the live follow-up workflow, the state badge shows a compact
**RESPONSE REQUIRED** strip during Intervention: stop supply, acknowledge the
Critical alarm, resample/verify, then resume only after safe readings persist.
Optional Gmail/ThingsBoard email setup for the three water-quality Critical
alarms is documented in [`email_notification_setup.md`](email_notification_setup.md).

## Import and link the rule chain

1. In ThingsBoard go to **Rule engine → Rule chains → + → Import**.
2. Choose `rule_chain_operational_state.json` and import it.
3. Open the imported chain and check the two nodes:
   **Compute operational_state (PROPOSED)** → **Save operational_state**.
4. Open **Root Rule Chain**. Add a **Rule Chain** node, select the imported
   `FloodSafe Operational State` chain in that node, then connect
   **Save Timeseries → Rule Chain node** with relation type **Success**.
   (Importing a chain does not link it automatically.)
5. Save, then send a reading and check the device's **Latest telemetry** for
   `operational_state`.
6. The committed `rule_chain_operational_state.json` is already the real export
   from the verified tenant. If you rebuild the chain in another tenant, export
   it there and replace this file.

## Verify all four states safely

Use the test publisher (it does **not** write to SQLite) with your real tokens
already set in PowerShell:

```powershell
# Normal
python thingsboard/publish_test_reading.py --node FSN-01 --turbidity 4 --ph 7.1 --tds 180 --flow 12
# Watch (High Turbidity Warning)
python thingsboard/publish_test_reading.py --node FSN-01 --turbidity 60 --ph 7.1 --tds 180 --flow 12
# Investigate (Supply Interruption Major; wait for the group-agreed sustained duration)
python thingsboard/publish_test_reading.py --node FSN-01 --turbidity 4 --ph 7.1 --tds 180 --flow 0
# Intervention (Gross Contamination / pH Out of Range / High TDS Critical)
python thingsboard/publish_test_reading.py --node FSN-01 --turbidity 260 --ph 6.2 --tds 600 --flow 12
# Back to Normal (all critical alarms clear through hysteresis)
python thingsboard/publish_test_reading.py --node FSN-01 --turbidity 4 --ph 7.1 --tds 180 --flow 12
```

Expected proposed states: **Normal**, **Watch**, **Investigate**, **Intervention**,
**Normal**. Take a screenshot of the `operational_state` key in Latest telemetry
after each command, and of the dashboard state card/table colour changing.

`Investigate` is driven by `flow_lpm == 0` (Major) because the stateless script
cannot count abnormal values over time. A reading such as `--ph 6.2 --tds 1200`
contains Critical values, so it correctly yields **Intervention**, not
**Investigate**.

## Known limitation

Node Inactive produces no telemetry, so the transform cannot run while a node
is offline. Its Critical alarm still appears in the alarm table and can colour
the map marker; the stored `operational_state` remains the last known value.
Document this rather than claiming the state updates while offline.
