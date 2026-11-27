# ThingsBoard setup — FloodSafe Nepal (Stage 4)

This folder contains **verified ThingsBoard configuration and instructions**.
`rule_chain_operational_state.json` is a sanitised real export from a ThingsBoard
4.4.1 tenant. `dashboard_floodsafe.json` keeps those verified device/telemetry
bindings but uses a light operations layout built from stock widgets.
It must be imported and visually re-verified. In a different account you must
still provision devices, set tokens, import/link the configuration and verify it
there.

## Committed exports vs manual steps

| File | What it is | Do you need to do anything? |
| --- | --- | --- |
| `dashboard_floodsafe.json` | Light municipal operations dashboard (23 stock widgets, `default` and `node_detail` states) based on the verified export. | Import into your tenant and visually re-verify. If the import fails or a widget opens empty, follow `dashboard_build_sheet.md`. |
| `rule_chain_operational_state.json` | Sanitised real export of the verified transform + Save Timeseries chain. | **Rule chains → + → Import**, then link it from Root Rule Chain after "Save Timeseries". Review the **PROPOSED** thresholds before submission. |
| `operational_state.tbel.js` | Copy-paste TBEL script used by the transform node. | Contains PROPOSED thresholds. Your group must approve them. |
| `alarm_rules.json` | Machine-readable copy of the six exact Task 3 alarm rules. | Reference only; configure the rules in Device Profile → Alarm Rules. |
| `alarm_rules.md` | Exact alarm table + click-by-click configuration. | Manual web-interface work required. |
| `operational_states.md` | Four documented state meanings, proposed mapping, limitations. | Manual rule-chain work + group approval required. |
| `dashboard_build_sheet.md` | Manual widget/alias/colour layout. | Use if JSON import fails. |
| `verification_checklist.md` | Screenshot checklist for the assignment report. | Perform and capture evidence. |
| `publish_test_reading.py` | Test-only publisher for deterministic alarm tests. | Run with your tokens already set; never writes to SQLite. |
| `email_notification_setup.md` | Gmail/ThingsBoard rule-engine steps for emailing water-quality Critical alarms. | Verified in the demo tenant. In another tenant, configure the rule nodes; the SMTP password stays in the `Send Email` node only. |
| `generate_config.py` | Offline generator for best-effort reference templates. | It now writes `*_template.json` files so it cannot overwrite the committed real exports. Needs no credentials. |

`src/`, the SQLite database and the 11-field telemetry schema are unchanged.
No real token or credential is stored in this folder.

## Step 1 — Check the cloud region and devices

1. Your `THINGSBOARD_HOST` must match the region of your login.
   - Logged in at `thingsboard.cloud` → `mqtt.thingsboard.cloud`
   - Logged in at `eu.thingsboard.cloud` → `mqtt.eu.thingsboard.cloud`
   - Self-hosted → that server's IP/domain
   - `demo.thingsboard.io` is a **web demo**, not the Cloud MQTT broker.
2. In ThingsBoard open **Devices** and confirm the three devices exist:
   `FSN-01`, `FSN-02`, `FSN-03`.
3. Copy each device's access token privately into `.env` (never into Git):

```powershell
cd D:\floodsafe_iot
Copy-Item .env.example .env
notepad .env
```

Set `THINGSBOARD_HOST` and the three `FSN_XX_TOKEN` values. Values still
starting with `replace-with-` are treated as missing.

4. Confirm telemetry arrives (this does not modify your database):

```powershell
.\.venv\Scripts\python.exe thingsboard\publish_test_reading.py --node FSN-01 --turbidity 4
```

Check **FSN-01 → Latest telemetry** in the web UI.

## Step 2 — Create the device profile

1. **Device profiles → + Add device profile** → name it exactly `FloodSafe Node`.
   The dashboard alias depends on this exact name.
2. Assign `FSN-01`, `FSN-02`, `FSN-03` to it.
3. Configure the **inactivity timeout**. Task 3 requires it but gives no value —
   agree one with your group and record it in the report.
4. Add the six alarm rules exactly as in `alarm_rules.md`.

## Step 3 — Add the operational-state rule chain

Full instructions are in `operational_states.md`. Short version:

1. **Rule engine → Rule chains → + → Import** →
   `rule_chain_operational_state.json`.
2. In Root Rule Chain, add a **Rule Chain** node that points to
   `FloodSafe Operational State`, then connect **Save Timeseries → Rule Chain
   node** with relation type **Success**.
3. Publish one reading and check that `operational_state` appears in Latest
   telemetry.
4. **Do not change the four state names to alarm severities.**

## Step 4 — Add the dashboard

1. **Dashboards → + → Import dashboard** → `dashboard_floodsafe.json`.
2. Open it and check the entity aliases:
   - `FloodSafe Nodes` → device type `FloodSafe Node`, resolve multiple ON.
   - `Selected FloodSafe Node` → state entity.
3. If widgets are blank, work through `dashboard_build_sheet.md` manually.
4. Check the map has three distinct markers and the state table shows one row
   per water point.
5. If you rebuild the dashboard in another tenant, export it and replace this
   file there. This file was rebased from the user-supplied earlier export from
   the verified tenant; the current polish pass is described in Step 4b and is
   not live yet.

   That earlier export was imported as a **new** dashboard alongside
   the original one; both share the title
   `FloodSafe Nepal — Municipal Operations`. Distinguish them by creation time or
   dashboard ID. The original dashboard `9f26ac00-e6ef-11f1-b738-a5db76a1a080`
   was not modified. The imported dashboard ID is
   `e0c83200-e712-11f1-9e1c-c93dd85f5a1f`.

## Step 4b — What the local polish pass changed

These edits are **local only**. They have not been imported into ThingsBoard;
ask before replacing any live dashboard. This version was **rebased from the
previously supplied export**, so the earlier large banner, clickable summary
cards and four-datasource **Priority water points** table are gone. The later
`floodsafe_nepal_—_municipal_operations (3).json` layout export, supplied
outside this repository, was then used for its user-tuned widget sizes and
positions; four widgets wider than the 24-column grid were clamped to the grid.
Aliases, filters, datasource bindings and telemetry keys were not changed by
that layout merge.

- The whole dashboard is a **light theme**: `#f8fafc` grid background,
  `#ffffff` cards, `#1e293b` text and `#e2e8f0` borders. Maps, tables, gauges,
  charts, cards and both layout states use the same palette.
- The top of `default` is split into two equal 12-column halves. The left half
  is a 2 × 2 grid of operational-state cards (NORMAL, WATCH, INVESTIGATE,
  INTERVENTION); the right half is three stacked alarm bars (Critical active,
  Major active, Warning active) covering the same six grid rows.
- State cards use full `var(--accent)` fills: Normal `#15803d` with white text,
  Watch `#fef08a` with `#713f12`, Investigate `#ffedd5` with `#7c2d12`, and
  Intervention `#dc2626` with white text. Counts come from `entityCount` filters
  on `operational_state`; they are not hardcoded examples.
- **State and alarm summary cards are not clickable.** Their `actions` are
  empty. Map markers and the exported **Needs attention** table retain their
  row/marker click-through to `node_detail` with `setEntityId: true`.
- The exported `NeedsAttention` filter (`Intervention` OR `Investigate`) and the
  `Needs attention — highest priority first` table are preserved unchanged.
- Dashboard default time window remains **24 hours** so buffered readings from
  an earlier `--sync` run are visible in the trends.
- The map still draws the same three entities at the same coordinates, with
  short `FSN-01` / `FSN-02` / `FSN-03` labels, a light rich popup and click
  through to `node_detail` with the selected entity.
- In `node_detail`, the attached user-tuned layout is authoritative:
  **Current operational state** is a compact 9 × 5 colour-coded badge at top-left,
  not the earlier large banner. Green Normal, amber Watch, orange Investigate and
  red Intervention use dark text on the two lighter colours. During
  Intervention only, the same badge shows a small **RESPONSE REQUIRED** strip:
  stop supply, acknowledge the Critical alarm, resample/verify, then resume after
  safe readings. No widget or layout size changed. Charts remain bound to the
  selected node.
- The redundant **Selected water point — live state** card was replaced by
  **Node Metadata & Location**. Its data-key labels match the names its markdown
  function reads, so values actually render. It uses only `node_id`,
  `water_point`, telemetry `latitude` / `longitude` / `ts`, server `active` and
  `lastActivityTime`. The District row now resolves from the selected `node_id`
  using the three demo districts in `config/nodes.json`: FSN-01 and FSN-02 are
  **Kathmandu**, FSN-03 is **Lalitpur**. These values were derived by
  reverse-geocoding the demonstration coordinates with OpenStreetMap/Nominatim
  on 2026-11-27; they are not a new telemetry field or a claim of verified
  deployment. No fake ONLINE state or shared-source claim was added.
- Both time-series charts keep the `Selected FloodSafe Node` alias and the
  original keys (`turbidity_ntu`, `ph`, `tds_ppm`, `water_temp_c`, `flow_lpm`).
  The rebased export uses its shared axis; the earlier custom `ph` right axis
  was deliberately not reintroduced.
- Node health still shows the platform `active` attribute, `lastActivityTime`
  as a readable local date/time, and the simulator's `ts` telemetry key
  separately as **Telemetry time**. MQTT publishes that same `ts` in the
  ThingsBoard timestamp envelope so replayed rows keep their original time.
- Alarm counts are labelled exactly **Critical active**, **Major active** and
  **Warning active** and filter `statusList` to `ACTIVE` only. Both alarm tables
  state **last 24h** and explicitly include `ACTIVE` and `CLEARED`. Active alarm
  counts and cleared-history tables are different scopes and must not be compared
  as if they were the same query.

## Optional: ThingsBoard email notifications (verified in the demo tenant)

The verified tenant uses a **rule-engine email path**, not a repository change.
The working sequence is:

1. `Alarm Created` emits a new alarm event.
2. `FloodSafe Critical Water Quality` admits only `Gross Contamination`,
   `pH Out of Range` and `High TDS`.
3. `To Email` prepares the message for the operator group.
4. `Send Email` delivers it through custom Gmail SMTP (`smtp.gmail.com`,
   STARTTLS on port 587). The Gmail app password is entered only in that rule
   node's SMTP password field.

Only a newly created alarm sends mail. Acknowledgement, severity changes,
updates and clears do not, and `Node Inactive` is excluded because it reports
an offline device rather than contaminated water.

Follow [`email_notification_setup.md`](email_notification_setup.md) to reproduce
the path in another tenant and to test it. No credential is stored in this
repository; do not export a rule chain containing the configured SMTP password,
photograph the form, or paste the value into Git. Web, Slack, Teams and SMS
remain available but were not configured for this demo.

## Why devices can be OFFLINE while charts still show data

ThingsBoard's Device State service sets `active=false` after the device
inactivity timeout (default 10 minutes). Telemetry that was already accepted is
still stored as time series, so gauges and trends can display recent stored
values and Node Inactive can remain a legitimate Critical alarm. In this
workspace the last synced readings were from 2026-11-23 around 15:33 local; a
later check on 2026-11-24 was about 15 hours afterwards. The `active` attribute
was therefore false even though historical readings remained visible. The
correct response is to send fresh telemetry and let ThingsBoard update
`active` / `lastActivityTime`, not to hide the alarm or fake ONLINE.

The interrupted `--sync` command raised `KeyboardInterrupt` inside
`wait_for_publish()` because Ctrl+C was pressed while the client waited for a
QoS 1 acknowledgement. Rows were only marked `sent` after confirmation, so the
17 unacknowledged rows stayed pending and can be retried with `--sync`; no data
was silently lost.

## Step 5 — Verify

Follow `verification_checklist.md`. In short:

```powershell
python -m src.main --scenario normal --count 3 --save-db
python -m src.main --sync
python -m src.main --scenario flood --count 30 --save-db --sync
python -m src.main --scenario response --count 18 --save-db --sync
```

The `response` run is the six-step Intervention → contain → verify → resume
sequence described in `operational_states.md`; it does not change the rule chain.
Then use the deterministic test publisher to see each state and its alarms.
The simulator generates readings; the **rule chain** derives the state, so use
these exact readings after setting your three `FSN_XX_TOKEN` values in `.env`:

```powershell
# Normal — no unusual value, no alarm
python thingsboard/publish_test_reading.py --node FSN-01 --turbidity 4 --ph 7.1 --tds 180 --flow 12
# Watch — High Turbidity (Warning) active
python thingsboard/publish_test_reading.py --node FSN-01 --turbidity 60 --ph 7.1 --tds 180 --flow 12
# Investigate — Supply Interruption (Major) active
python thingsboard/publish_test_reading.py --node FSN-01 --turbidity 4 --ph 7.1 --tds 180 --flow 0
# Intervention — Gross Contamination + pH Out of Range + High TDS (Critical) active
python thingsboard/publish_test_reading.py --node FSN-01 --turbidity 260 --ph 6.2 --tds 600 --flow 12
# Clear back to Normal and let the critical alarms clear through hysteresis
python thingsboard/publish_test_reading.py --node FSN-01 --turbidity 4 --ph 7.1 --tds 180 --flow 12
```

Watch the `default` cards and the alarm tables after each command. To see node
detail, click the map marker; the state badge, gauges, charts, metadata and
per-node alarm table all follow the selected device. `publish_test_reading.py`
publishes one reading through the same TLS/MQTT path as `--sync`, but does
**not** insert into SQLite and does **not** mark any database row sent. The
`--scenario normal` and `--scenario flood` simulator runs are for bulk historised
data. `--scenario response` is the only built-in deterministic response sequence;
even there, the rule chain still derives `operational_state` from each reading.

## What was verified in this workspace

- Device profile `FloodSafe Node`, MQTT topics, and all three assigned devices.
- Six Task 3 alarm rules with the exact create/clear expressions and severities.
- Root Rule Chain link: **Save Timeseries → FloodSafe Operational State**
  (`Success`) and the transform → Save Timeseries link inside that chain.
- Dashboard states `default` (`Fleet overview`) and `node_detail: ${entityName}`;
  three map markers with telemetry coordinates, state colours, labels, tooltip
  and click-through; gauges, trends, state card, node health and alarm tables
  including computed Duration.
- Deterministic readings produced Normal → Watch → Investigate → Intervention →
  Normal, with the expected active alarms and final cleared status.
- Earlier `normal --count 3 --save-db`, `--sync` and `flood --count 30 --save-db
  --sync` runs completed with 192 stored rows and 0 pending. A later interrupted
  30-reading `--sync` run left **222 stored, 205 sent and 17 pending**; the
  unacknowledged rows are still safely queued for a retry.
- Screenshots `01_overview_kpi_and_alarms_summary.png`,
  `02_overview_map_and_priority_nodes.png`,
  `03_overview_node_health_and_alarm_log.png`,
  `05_node_detail_fsn01_gauges_and_metadata.png`,
  `06_node_detail_fsn01_timeseries_trends.png` and
  `07_node_detail_fsn01_alarm_history.png` are in `screenshots/` and show the
  earlier verified layout.
- An earlier redesign was imported as a new dashboard and verified live, but it
  has been superseded. The file in this folder was rebased from the
  user-supplied previous export and the changes in Step 4b are
  **offline-validated only**. Import it as a new dashboard and re-capture the
  screenshots before treating this version as live; do not overwrite either
  existing dashboard without explicit approval.

## District and shared-source limitation

District **display** is now available for the three demo nodes from
`config/nodes.json` (FSN-01/FSN-02 Kathmandu, FSN-03 Lalitpur), derived from
their demonstration coordinates. It is not part of the 11-field telemetry
contract; the dashboard resolves it from the selected `node_id`. District
**filtering** across all districts, and separate source/branch status, remain
**not enabled**. The overview context still states "All Districts" and shows
each water point independently; an abnormal reading affects only that water
point. No shared-source contamination propagation is asserted. Add confirmed
source IDs as device attributes first, then add aliases/filters — do not invent
network connections.

**Recommendation for the demo map:** keep the three existing Kathmandu Valley
demonstration points. They match the configured devices, telemetry, screenshots
and the documented limitation. Do not move them to Bidur/Nuwakot or add nearby
"flood-affected" markers unless you have verified coordinates and real device
identities. If the assignment needs that geography, add it as a clearly labelled
reference/context note (or verified new devices with `district` and `source_id`
attributes), not as monitored nodes with invented data.

## Clarifications required (not invented here)

- Numeric thresholds, persistence counts and escalation timings for the four
  operational states.
- The "sustained" duration for `flow_lpm == 0`.
- The device inactivity timeout value.
- Named responder, acknowledgement deadline and escalation chain.
- Target ThingsBoard Cloud version for another tenant (these exports were
  verified on v4.4.1; other versions may differ).
- RSSI and buffer depth are suggested by Task 3's node-status widget but are
  not part of the 11-field telemetry contract; only last activity is shown.
- MQTT uses ThingsBoard's timestamp envelope `{"ts": ..., "values": {...}}`,
  so buffered replay keeps the original client acquisition time. The 11 logical
  telemetry fields are unchanged; `ts` is also kept inside `values` for the
  dashboard widgets. `id`, `sent` and `sent_at` are never published.

## Tests

From the project root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
