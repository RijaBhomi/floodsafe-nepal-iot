# Verification and evidence checklist

The ThingsBoard work in this workspace was verified against **ThingsBoard Cloud
v4.4.1** with real MQTT telemetry. The rule-chain JSON is a sanitised real export
from that tenant. The dashboard file was **rebased from the user-supplied earlier
export** and then polished locally; it is not invented, but the current polish is
offline-validated only.

Existing screenshots in `screenshots/` show the earlier verified layout:

- `01_overview_kpi_and_alarms_summary.png` — state and alarm summary cards.
- `02_overview_map_and_priority_nodes.png` — three map markers, state table and
  priority water points after normal readings.
- `03_overview_node_health_and_alarm_log.png` — node health and alarm log with
  Duration.
- `05_node_detail_fsn01_gauges_and_metadata.png`,
  `06_node_detail_fsn01_timeseries_trends.png` and
  `07_node_detail_fsn01_alarm_history.png` — FSN-01 gauges, metadata, trends,
  current state and node-specific alarms after marker click-through.

Those screenshots are **pre-rebase evidence**; re-capture them after importing
the current layout. If you use a different ThingsBoard account, repeat the
relevant steps and do not describe the configuration as live there until you
have verified it.

## A. Local checks

```powershell
cd D:\floodsafe_iot
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

- [x] All project tests pass after the rebase, layout merge and timestamp pass.
- [x] JSON files parse as valid JSON:
      `python -c "import json,pathlib; [json.loads(p.read_text(encoding='utf-8')) for p in pathlib.Path('thingsboard').glob('*.json')]; print('ok')"`
- [x] No credential-like token was found in the repository files.

## B. Devices and profile

- [x] Three devices named `FSN-01`, `FSN-02`, `FSN-03` exist.
- [x] All three are assigned to device profile `FloodSafe Node`.
- [x] Latest telemetry contains the 11-field payload; `latitude` and
      `longitude` are telemetry keys, not attributes.
- [x] Device profile has the six Task 3 alarm rules with exact severities and
      create/clear expressions.
- [ ] Device inactivity timeout: **not configured**. The assignment gives no
      value; get a group-agreed number and record it in the report.

## C. Normal scenario and fleet overview

```powershell
python -m src.main --scenario normal --count 3 --save-db
python -m src.main --sync
```

- [x] `[SYNC]` lines showed per-node routing with QoS 1 confirmations.
- [x] Map shows three distinct markers with state labels, state-based colours,
      tooltips and click-through to `node_detail`
      (`screenshots/02_overview_map_and_priority_nodes.png`).
- [x] Gauges were checked in the Task 3 bands after normal readings
      (`screenshots/05_node_detail_fsn01_gauges_and_metadata.png`).
- [x] State table showed **Normal** for all three devices
      (`screenshots/01_overview_kpi_and_alarms_summary.png` and
      `screenshots/03_overview_node_health_and_alarm_log.png`).
- [x] Alarm table shows active and cleared alarms plus computed Duration;
      previous test alarms remained visible, so it was not empty.
- [x] Node health table showed recent last-activity timestamps.

## D. Flood / contamination event

```powershell
python -m src.main --scenario flood --count 30 --save-db --sync
```

- [x] Flood run completed with `--save-db --sync`; the overview subsequently
      showed Intervention states for the three nodes.
- [x] Parameter coupling was verified from the generated readings and the
      deterministic alarm tests (turbidity spike, pH dip, TDS rise, flow zero).
- [x] High Turbidity (Warning above 50 NTU) and Gross Contamination (Critical
      above 200 NTU) were verified with deterministic readings.
- [x] Clearing below 40 / 150 NTU was verified from the alarm table.
- [ ] Add a dedicated flood-event screenshot and time-series chart screenshot
      if the report needs visual evidence of the curve shape.

## E. Controlled alarm tests

`publish_test_reading.py` publishes one reading through the same TLS/MQTT path
as `--sync`; it does **not** write to SQLite.

- [x] High Turbidity: Warning active above 50 NTU; cleared below 40.
- [x] Gross Contamination: Critical active above 200 NTU; cleared below 150.
- [x] pH Out of Range: Critical active below 6.5 / above 8.5; cleared in 6.7–8.3.
- [x] High TDS: Critical active above 500 ppm; cleared below 450.
- [x] Supply Interruption: Major active at `flow_lpm == 0`; cleared above 0.
      No sustained-duration value was invented.
- [x] Node Inactive: Critical appeared after inactivity and cleared when
      telemetry resumed; no explicit timeout value was configured.
- [x] Final normal reading returned the node to Normal with zero active alarms.
- [ ] Alarm activation delay was not measured as a manuscript metric.

## F. Four operational states

The deterministic publisher produced, in order:

- [x] Normal (`--turbidity 4 --ph 7.1 --tds 180 --flow 12`).
- [x] Watch (`--turbidity 60 --ph 7.1 --tds 180 --flow 12`).
- [x] Investigate (`--turbidity 4 --ph 7.1 --tds 180 --flow 0`).
- [x] Intervention (`--turbidity 260 --ph 6.2 --tds 600 --flow 12`).
- [x] Final recovery to Normal.
- [x] A reading with Critical values (`--ph 6.2 --tds 1200`) correctly produced
      Intervention, not Investigate.

The four state names remain Normal, Watch, Investigate and Intervention; they
were not replaced by ThingsBoard alarm severities. The numeric state mapping is
still **PROPOSED** and requires group approval. Persistence over time is
simplified in the stateless transform script; document that limitation.

## G. Earlier live dashboard (historical)

An earlier export was imported into ThingsBoard Cloud as a **second, new
dashboard**; the original dashboard was left untouched. Both share the title
`FloodSafe Nepal — Municipal Operations`.

- Original dashboard ID: `9f26ac00-e6ef-11f1-b738-a5db76a1a080` (unchanged).
- Previously imported dashboard ID: `e0c83200-e712-11f1-9e1c-c93dd85f5a1f`.
- The live import initially showed `Failed to parse the payload` in Needs
  attention; the fix was two OR-ed key filters and one `operational_state`
  column. The rebased file keeps that working filter shape.
- Those screenshots and live observations are **not evidence for the current
  local file**. Do not overwrite either dashboard without explicit approval.

## H. Resilience evidence

- [ ] Console screenshot showing readings buffering while the broker is
      unavailable.
- [x] Database count after the interrupted 30-reading sync run: 222 stored,
       205 sent and 17 pending. The `KeyboardInterrupt` happened while waiting
       for QoS 1 confirmation, so those 17 rows remain safely queued for the
       next `--sync` run.
- [ ] Replayed-reading chart screenshot showing the gap backfilled at the
      original client timestamps.
- [x] MQTT publishes ThingsBoard's timestamp envelope, so replayed rows keep
      their acquisition `ts` instead of being stamped at sync time. The 11
      logical telemetry fields are unchanged; `ts` is also kept in `values`.

## I. Final repository hygiene

- [x] `dashboard_floodsafe.json` was replaced with the user-supplied earlier
      export as the baseline, then polished locally per the new request.
- [x] The user's later `(1)` export was merged for its widget geometry; four
      widgets wider than the 24-column grid were clamped and the layouts were
      checked for overlaps. Aliases, filters and datasource bindings stayed put.
- [x] The superseded large-banner/clickable-card redesign is no longer in the
      committed dashboard.
- [x] Real rule-chain export remains
      `thingsboard/rule_chain_operational_state.json`.
- [x] `.env` is ignored and no real token is in the source, docs or logs.
- [x] Tests were run one final time after the rebase/polish pass.
- [ ] Update Appendix A truthfully for the member who did the cloud work.

## J. Pending live re-verification after the rebase/local polish

This pass is **local only**. Do **not** import or overwrite a live dashboard
without explicit approval. When approved, import as a **new** dashboard and tick
these items:

- [ ] Light theme renders correctly: `#f8fafc` grid, `#ffffff` cards, `#1e293b`
      text and `#e2e8f0` borders in both dashboard states.
- [ ] The top area is split 50/50: four full-colour state cards in a 2 × 2 left
      grid, three alarm bars stacked to the same total height on the right.
      Watch/Investigate remain readable with dark text; Normal/Intervention use
      white text. Titles and `water points` counts are unchanged.
- [ ] State counts read **2 / 1 / 0 / 0** (or the current live values) and come
      from `entityCount` filters, not hardcoded numbers. Alarm counts read
      **Critical active / Major active / Warning active** from ACTIVE alarm
      queries.
- [ ] **Clicking any state or alarm card does nothing.** No URL change, no
      hidden datasource and no `node_detail` navigation from those cards.
- [ ] Needs attention still shows Intervention / Investigate water points with
      State and current NTU / pH / TDS / Flow readings; no payload error appears.
      This is the exported single-filter table, not the superseded four-datasource
      priority table.
- [ ] Dashboard default time window reads **Last 24 hours** and both time-series
      charts show stored readings for the selected device. The quality trend uses
      the rebased shared axis, not the earlier custom pH right axis.
- [ ] The existing telemetry keys remain bound: `turbidity_ntu`, `ph`,
      `tds_ppm`, `water_temp_c`, `flow_lpm`; no chart shows hardcoded data.
- [ ] Map labels are only `FSN-01`, `FSN-02`, `FSN-03`; markers do not overlap
      in a confusing way at the default zoom.
- [ ] Clicking each marker opens a readable light popup with full water-point
      name, state badge, turbidity, pH, TDS, flow and both timestamp fields.
- [ ] The marker click opens `node_detail` for that device. The **Current
      operational state** badge is a compact 9 × 5 block at top-left and fills
      green for Normal, amber for Watch, orange for Investigate and red for
      Intervention (dark text on amber/orange). It no longer dominates the view.
      During Intervention only, the same badge shows a compact **RESPONSE
      REQUIRED** strip with stop supply, acknowledge, resample and resume steps;
      other states show the plain badge.
- [ ] The tuned node-detail layout renders as in the attached export: metadata
      15 × 5 at top-right, five gauges on row 5, two 12 × 9 charts on row 10 and
      the per-node alarm table 24 × 10 on row 19. No widget clips past column 24.
- [ ] **Node Metadata & Location** shows the selected node, water point,
      coordinates from real telemetry, Active/Inactive/Unavailable from `active`
      only, a readable `lastActivityTime` and telemetry `ts`. District resolves
      from `node_id`: FSN-01/FSN-02 **Kathmandu**, FSN-03 **Lalitpur**. The
      values come from the demo-coordinate mapping in `config/nodes.json`; no
      claim of verified deployment or shared-source propagation is made.
- [ ] Node health shows readable local date/time values rather than epoch ms,
      plus ONLINE/OFFLINE from the `active` server attribute.
- [ ] Alarm cards have no **all history** suffix; both alarm tables read
      **last 24h**, explicitly filter `ACTIVE` and `CLEARED`, and include rows
      when alarms exist in that window.
- [ ] The district/shared-source limitation card is still visible. District
      display is available for the three demo nodes; district-wide filtering,
      source IDs and propagation claims are still not enabled.
- [ ] `--scenario response --count 18 --save-db --sync` produces six steps per
      node: two identical Intervention triggers, a zero-flow containment step
      with Supply Interruption active, a safe-but-zero-flow Investigate step
      where water-quality alarms have cleared but Supply Interruption remains,
      then two Normal steps with all alarms cleared. This is scenario evidence;
      the rule chain still does not count readings over time.
- [x] In the demo tenant, the rule-engine email path sent one email per newly
      created water-quality Critical alarm; updates and clears sent no mail.
      The Gmail app password was configured only in the `Send Email` rule node.
- [ ] In another tenant, recreate
      `Alarm Created` → `FloodSafe Critical Water Quality` → `To Email` →
      `Send Email`, then verify one email per newly created water-quality
      Critical alarm and no mail on clear. Do not export or screenshot the
      configured `Send Email` node.
- [ ] Capture fresh overview and node-detail screenshots with the current local
      layout; the six existing screenshots are pre-rebase evidence only.
