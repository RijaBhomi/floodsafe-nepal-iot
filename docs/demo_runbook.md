# FloodSafe Nepal — live demonstration runbook

Use this runbook for the seven demonstration points. Run all commands from the
project root. Tokens stay private in `.env`; never paste them into a terminal
recording, screenshot or Git.

## 0. One-time setup

```powershell
Copy-Item .env.example .env
notepad .env
```

Fill in `THINGSBOARD_HOST` plus `FSN_01_TOKEN`, `FSN_02_TOKEN` and
`FSN_03_TOKEN`. Use `mqtt.thingsboard.cloud` for `thingsboard.cloud` or
`mqtt.eu.thingsboard.cloud` for `eu.thingsboard.cloud`.

Confirm the broker is reachable:

```powershell
Test-NetConnection mqtt.thingsboard.cloud -Port 8883
```

Confirm in ThingsBoard that:

- `FSN-01`, `FSN-02` and `FSN-03` are assigned to device profile `FloodSafe Node`.
- The six exact Task 3 alarm rules are configured on that profile.
- The `FloodSafe Operational State` rule chain is linked after **Save Timeseries**.
- An earlier dashboard export was imported as a new dashboard in the verified
  tenant. The current `thingsboard/dashboard_floodsafe.json` is a later local
  polish; import it as a new dashboard before treating it as live. Do not
  overwrite an existing dashboard without explicit approval.

## 1. Baseline telemetry

```powershell
.\.venv\Scripts\python.exe -m src.main --scenario normal --count 9 --save-db --sync
```

Expected:

- JSON lines on stdout.
- `Saved ... readings ... pending (unsent): 0` on stderr.
- `[SYNC] Marked id=... (FSN-01) as sent.` lines.

Clearer terminal view:

```powershell
.\.venv\Scripts\python.exe -m src.main --scenario normal --count 9 --save-db --sync | ConvertFrom-Json | Format-Table ts,node_id,scenario,turbidity_ntu,ph,tds_ppm,flow_lpm
```

Database count:

```powershell
.\.venv\Scripts\python.exe -c "from src.database import initialize_database,count_readings,count_pending_readings; c=initialize_database(); print('stored:',count_readings(c),'pending:',count_pending_readings(c)); c.close()"
```

## 2. Live dashboard update

After the sync:

1. Open each device in ThingsBoard and confirm **Latest telemetry** contains
   fresh `turbidity_ntu`, `ph`, `tds_ppm`, `flow_lpm`, etc.
2. Open the dashboard and click a **map marker** to enter `node_detail`.
   The detail charts use `Selected FloodSafe Node`; opening the state directly
   with no selected entity leaves them empty.
3. The gauges and charts should show the new points within seconds.

For a visible live stream, send small batches with a pause:

```powershell
1..5 | ForEach-Object {
  .\.venv\Scripts\python.exe -m src.main --scenario normal --count 3 --save-db --sync
  Start-Sleep -Seconds 2
}
```

## 3. Contamination event (scenario-driven, not hardcoded)

```powershell
.\.venv\Scripts\python.exe -m src.main --scenario flood --count 30 --save-db --sync
```

`config/nodes.json` drives one shared severity for all nodes:

- Turbidity rises into roughly `100–800 NTU`.
- pH drops toward the `5.8` floor.
- TDS rises by about `260 ppm × severity`.
- Flow is reduced and may hit zero.

Do not edit the script or inject a high value mid-demo. The `flood` scenario is
the built-in trigger.

## 4. Alarms and marker colour

With the alarm rules configured:

- `turbidity_ntu > 50` → High Turbidity / Warning.
- `turbidity_ntu > 200` → Gross Contamination / Critical.
- `ph < 6.5` or `tds_ppm > 500` → additional Critical alarms.

Verify that the `Critical active`, `Major active` and `Warning active` cards
change, the alarm table shows ACTIVE rows with severity and Duration, and the
map marker changes colour with `operational_state`.

For a guaranteed screenshot only, not the graded trigger:

```powershell
.\.venv\Scripts\python.exe thingsboard\publish_test_reading.py --node FSN-01 --turbidity 260 --ph 6.2 --tds 600 --flow 12
```

## 4b. Intervention response scenario

Use the built-in response scenario to show what happens **after** Intervention.
It does not edit values mid-demo and it does not change the rule chain:

```powershell
.\.venv\Scripts\python.exe -m src.main --scenario response --count 18 --save-db --sync
```

`--count 18` gives each node six readings. In `node_detail`, the badge should
show the compact **RESPONSE REQUIRED** strip during the first three steps.

| Step per node | Reading | Expected state | Expected alarms |
| --- | --- | --- | --- |
| 1 Trigger | turbidity 260, pH 6.2, TDS 600, flow 12 | Intervention | Gross Contamination, pH Out of Range, High TDS, High Turbidity active |
| 2 Confirm | identical to step 1 | Intervention | Same alarms; visually demonstrates the proposed two-reading persistence idea |
| 3 Contain | same Critical values, flow 0 | Intervention | Supply Interruption create condition added |
| 4 Verify | turbidity 4, pH 7.1, TDS 180, flow 0 | Investigate | Water-quality alarms clear; Supply Interruption remains |
| 5 Resume | turbidity 4, pH 7.1, TDS 180, flow 12 | Normal | Supply Interruption clears |
| 6 Stable | identical to step 5 | Normal | No active alarms |

This sequence was checked against `thingsboard/alarm_rules.json` and
`thingsboard/operational_state.tbel.js`; `tests/test_response_scenario.py`
re-checks those thresholds offline. The two trigger steps are **scenario
evidence only** — the supplied rule chain is stateless, so it does not truly
count readings over time. Supply Interruption's assignment duration is
UNDEFINED; the scenario shows the create condition, not an agreed duration.

In the verified demo tenant, one email arrives per newly created water-quality
Critical alarm when step 1 fires; updates and clears do not send another. To
reproduce that behaviour in another tenant, follow
`thingsboard/email_notification_setup.md`; no credential belongs in this repo.

## 5. Network outage / SQLite buffering

Force a failed broker name:

```powershell
$env:THINGSBOARD_HOST = "invalid.invalid"
.\.venv\Scripts\python.exe -m src.main --scenario normal --count 9 --save-db
.\.venv\Scripts\python.exe -m src.main --sync
```

Expected: the simulator keeps logging JSON, rows stay in SQLite with
`sent = 0`, sync logs publish failures, and nothing crashes. Show the queue:

```powershell
.\.venv\Scripts\python.exe -c "from src.database import initialize_database,count_readings,count_pending_readings; c=initialize_database(); print('stored:',count_readings(c),'pending:',count_pending_readings(c)); c.close()"
```

## 6. Restore and replay with original timestamps

Remove the override so `.env` supplies the real host, then retry:

```powershell
Remove-Item Env:THINGSBOARD_HOST
.\.venv\Scripts\python.exe -m src.main --sync
```

Expected: pending rows are published oldest-first and marked sent only after
QoS 1 confirmation. The MQTT payload uses ThingsBoard's timestamp envelope:

```json
{"ts": 1790000000000, "values": {"ts": 1790000000000, "node_id": "FSN-01", "...": "..."}}
```

The outer `ts` is the acquisition time from the original reading, so replayed
rows backfill the gap at their correct historical timestamps. `ts` is also
kept inside `values` so existing dashboard widgets continue to work.

## 7. Explanation prompts

- **Simulator:** generates 11-field readings from normal/flood/response models;
  `response` is the deterministic Intervention workflow; no direct I/O.
- **SQLite:** rows stay `sent = 0` until MQTT confirms delivery.
- **MQTT:** TLS on 8883, QoS 1, one token/device, one client ID/node.
- **Rule chain:** derives `operational_state` as a new telemetry key.
- **Alarms:** six exact Task 3 rules; the dashboard only displays them.
- **Dashboard:** aliases bind to the device profile and the selected state entity.

## Dashboard layout checks

The attached layout was merged and normalised to the 24-column grid:

- Node detail state badge: `9 × 5` at row 0, col 0.
- Metadata: `15 × 5` at row 0, col 9.
- Gauges: row 5 across cols 0, 5, 10, 15 and 20 (last one narrowed to 4 columns).
- Trends: row 10, `12 × 9` each.
- Node alarms: `24 × 10` at row 19.

No widget extends past column 24 or overlaps another widget. The metadata card
shows District from the demo-node mapping: FSN-01/FSN-02 **Kathmandu**, FSN-03
**Lalitpur**. This is derived from the demonstration coordinates in
`config/nodes.json`, not from a new telemetry field. If you resize in
the ThingsBoard UI, export the dashboard back into
`thingsboard/dashboard_floodsafe.json` so the repository matches what is live.
