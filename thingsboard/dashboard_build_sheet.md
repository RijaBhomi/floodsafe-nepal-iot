# Dashboard build sheet (import reference and fallback)

`dashboard_floodsafe.json` was rebased from the user-supplied earlier ThingsBoard
4.4.1 export, then polished locally into a light operations view. Import it
first. If another tenant rejects the import or a widget shows no data, use this
sheet to rebuild the same view manually, then export that tenant's real JSON.

## Before any widget: prerequisites

- The three devices exist and are assigned to device profile `FloodSafe Node`.
- Telemetry has arrived at least once, so the keys exist.
- The operational-state rule chain is linked (see `operational_states.md`).
- Use the same aliases and filters as the export:
  - `State=Normal`, `State=Watch`, `State=Investigate`, `State=Intervention`:
    each filters timeseries key `operational_state` with STRING EQUAL.
  - `NeedsAttention`: timeseries `operational_state` EQUAL `Intervention`
    **OR** EQUAL `Investigate` (`keyFiltersOperation: OR`).
- The summary cards are read-only. Do not add element/card click actions to the
  four state cards or the three alarm-count cards.

## Entity aliases (edit mode → Entity aliases)

| Alias | Type / filter | Why |
| --- | --- | --- |
| `FloodSafe Nodes` | **Device type** = `FloodSafe Node`, "resolve multiple" ON | Points at exactly the three virtual nodes. |
| `Selected FloodSafe Node` | **State entity**, resolve multiple OFF | Used by the detail state after a map/table drill-down. |

Dashboard theme: light `#f8fafc` grid background, white `#ffffff` cards,
`#1e293b` text and `#e2e8f0` borders, 24 columns, 8 px margin. The top section
is two equal 12-column halves. State-card fills are `#15803d` (Normal, white
text), `#fef08a` (Watch, `#713f12` text), `#ffedd5` (Investigate, `#7c2d12`
text) and `#dc2626` (Intervention, white text). Map/table state badges remain
green `#2e7d32`, amber `#fbc02d`, orange `#f57c00` and red `#d32f2f`.

## State 1 — `default`

| Row | Widget | Library item | Size | Binding and settings |
| --- | --- | --- | --- | --- |
| 0, 3 | NORMAL / WATCH / INVESTIGATE / INTERVENTION | **HTML value card** (`system.cards.html_value_card`) ×4 | `6 × 3` at cols 0 and 6 | Left 2 × 2 grid. Each uses an **Entity count** datasource on alias `FloodSafe Nodes` with its matching state filter. Counts water points, never alarms. `cardHtml` uses `${<state>Count:0}` and `cardCss` uses `background: var(--accent)` with `--fg` contrast. **No actions.** |
| 0, 2, 4 | Critical / Major / Warning active | **Alarm count** (`system.alarm_count`) ×3 | `12 × 2` at col 12 | Right-hand stack spanning the same six rows as the state grid. Alias `FloodSafe Nodes`; status `ACTIVE`; severity `CRITICAL`, `MAJOR` or `WARNING`. Labels are exactly **Critical active**, **Major active**, **Warning active**. Horizontal layout with coloured icon backgrounds. **No actions.** |
| 6 | Water-point map | **Map** (`system.map`) | `12 × 8` at col 0 | Alias `FloodSafe Nodes`; X/Y keys `latitude` / `longitude` as `timeseries`; short label `${node_id}`; additional keys `operational_state`, `turbidity_ntu`, `ph`, `tds_ppm`, `flow_lpm`, `water_point`, `node_id`, `ts`, `lastActivityTime`; state-based marker colours; light tooltip function; click → `node_detail` with `setEntityId: true`. |
| 6 | Needs attention | **Entities table** (`system.cards.entities_table`) | `12 × 8` at col 12 | Alias `FloodSafe Nodes`; one datasource using filter `NeedsAttention`; columns State, NTU, pH, TDS, Flow; row click → `node_detail`. Do not replace it with four state datasources; that was the superseded redesign. |
| 14 | District & source context | **Markdown card** (`system.cards.markdown_card`) | `24 × 2` | Static scope note: All Districts; no invented shared-source links; per-district filters are a documented future enhancement. |
| 16 | Node health | **Entities table** | `12 × 7` at col 0 | Alias `FloodSafe Nodes`; platform `active` attribute, `water_point`, readable `lastActivityTime` attribute, `ts` telemetry key labelled **Telemetry time**, `flow_lpm`, `scenario`. |
| 16 | Alarm table | **Alarms table** (`system.alarm_widgets.alarms_table`) | `12 × 7` at col 12 | Alias `FloodSafe Nodes`; Created, Device, Alarm, Severity, Status and computed Duration; `statusList` explicitly contains `ACTIVE` and `CLEARED`; widget time window **last 24h**; title states that scope. |
| 23 | Operational state by water point | **Entities table** | `24 × 7` | Alias `FloodSafe Nodes`; State, NTU, pH, TDS, formatted **Telemetry time**; row click → `node_detail`. |

## State 2 — `node_detail`

Add this state in **Manage dashboard states**. The map and table row-click
actions above must target ID `node_detail`.

| Row | Widget | Library item | Size | Binding and settings |
| --- | --- | --- | --- | --- |
| 0 | Current operational state | **Markdown card** (`system.cards.markdown_card`) | `9 × 5` at col 0 | Compact colour-coded badge, not the earlier large banner. Green Normal, amber Watch, orange Investigate, red Intervention; dark text on amber/orange. Conditional **RESPONSE REQUIRED** strip only for Intervention: stop supply, acknowledge Critical alarm, resample/verify, resume after safe readings. Alias `Selected FloodSafe Node`, key `operational_state`. No size or layout change. |
| 0 | Node Metadata & Location | **Markdown card** (`system.cards.markdown_card`) | `15 × 5` at col 9 | Data-key **labels** match the names the markdown function reads (`node_id`, `water_point`, `latitude`, `longitude`, `active`, `lastActivityTime`, `ts`). District is resolved from `node_id` using the verified demo-coordinate mapping (`FSN-01`/`FSN-02` Kathmandu, `FSN-03` Lalitpur); no district data key or fake connectivity is added. |
| 5 | Gauges | **Radial gauge** (`system.analogue_gauges.radial_gauge_canvas_gauges`) ×5 | `5 × 5` at cols 0/5/10/15, `4 × 5` at col 20 | Alias `Selected FloodSafe Node`. pH 2 dp, min 5.5, max 9.5 with red/green/red bands; turbidity 1 dp, min 0, max 800 with 0–5/5–50/50–200/200–800 bands; TDS 0 dp, min 0, max 1200 with 0–500/500–1000/1000–1200 bands; flow 1 dp, L/min, 0–25 with red at 0; temperature 1 dp, °C, 10–30. |
| 10 | Quality trend | **Time series chart** (`system.time_series_chart`) | `12 × 9` at col 0 | Alias `Selected FloodSafe Node`; keys `turbidity_ntu`, `ph`, `tds_ppm`; shared axis from the rebased export. Use dashboard time window (default **24h**). Do not add the earlier custom `ph` right axis. |
| 10 | Supply trend | **Time series chart** | `12 × 9` at col 12 | Alias `Selected FloodSafe Node`; keys `water_temp_c`, `flow_lpm`; light legend/axis styling; same time window. |
| 19 | Node alarms | **Alarms table** (`system.alarm_widgets.alarms_table`) | `24 × 10` | Alias `Selected FloodSafe Node`; `statusList` explicitly contains `ACTIVE` and `CLEARED`; widget time window **last 24h**; title states that scope. |

## Operational checks after building

- Map shows **three distinct markers** in Kathmandu Valley at the coordinates
  in `config/nodes.json`: FSN-01 `27.745, 85.4167`, FSN-02 `27.712, 85.322`,
  FSN-03 `27.671, 85.318`.
- Colour bands match Task 3 exactly for pH, turbidity and TDS.
- Charts show the flood event (turbidity spike, pH dip, TDS rise) and any
  historical readings inside the chosen 24 h window.
- State counts come from real `entityCount` filters; alarm counts come from real
  active-alarm severity queries. No number is hardcoded.
- Alarm tables include cleared alarms, not only active ones.
- Clicking a map marker or a table row opens the correct node's detail state.
  **State and alarm summary cards must not navigate anywhere.**
- The node state badge, gauges, charts, metadata and per-node alarm table all
  follow the selected device. If charts are empty, return to the overview and
  click a marker or a table row first.
- District/source limitation: district display is derived from the demo
  coordinates in `config/nodes.json`, but no district or shared-source ID is in
  the 11-field telemetry schema. The overview therefore shows **All Districts**
  and independent water points only. Do not claim district-wide filtering, or
  one shared source affecting multiple districts, until source IDs are confirmed
  and added as device attributes.

These coordinates are demonstration points only, not verified deployment
locations or a claim that equipment is installed there.
