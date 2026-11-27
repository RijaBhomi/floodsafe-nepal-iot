"""Generate best-effort ThingsBoard reference templates.

This script is deliberately offline and credential-free. It writes:

* ``dashboard_template_floodsafe.json`` — a reference dashboard template.
* ``rule_chain_operational_state_template.json`` — a reference chain template.

The committed ``dashboard_floodsafe.json`` and
``rule_chain_operational_state.json`` are sanitised real exports from a verified
ThingsBoard 4.4.1 tenant. The generator uses separate ``*_template.json`` names
so running it cannot overwrite those exports. The templates are only a starting
point for another tenant: import them, check every widget, then export the real
configuration. See ``README.md`` in this folder.

No real access tokens are read, written or required.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def uid(label: str) -> str:
    """Stable UUID so regenerating the file does not create random diffs."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "floodsafe-thingsboard/" + label))


FLEET_ALIAS = uid("alias/fleet-nodes")
STATE_ALIAS = uid("alias/state-node")

# Widget type FQNs are the bundle-prefixed names used in dashboard exports.
# The /api/widgetTypes response omits the "system." bundle alias, but an export
# from ThingsBoard 4.4.1 writes "system.<fqn>" for every stock widget.
MAP_FQN = "system.maps_v2.openstreetmap"
GAUGE_FQN = "system.analogue_gauges.radial_gauge_canvas_gauges"
CHART_FQN = "system.time_series_chart"
TABLE_FQN = "system.cards.entities_table"
VALUE_CARD_FQN = "system.cards.value_card"
ALARM_FQN = "system.alarm_widgets.alarms_table"

STATE_COLOURS = """
if (value == 'Intervention') return '#d32f2f';
if (value == 'Investigate') return '#f57c00';
if (value == 'Watch') return '#fbc02d';
return '#2e7d32';
""".strip()

# Alarms table cell function signature: f(value, alarm, ctx).  ThingsBoard
# exposes startTs/endTs/cleared on the alarm row, so the "startTime" alarm field
# can be rendered as a live duration for active alarms and a fixed one for
# cleared alarms.  This avoids inventing a duration telemetry field.
ALARM_DURATION_FN = """
var start = alarm.startTs || value;
var end = alarm.cleared && alarm.endTs ? alarm.endTs : Date.now();
var seconds = Math.max(0, Math.floor((end - start) / 1000));
var hours = Math.floor(seconds / 3600);
var minutes = Math.floor((seconds % 3600) / 60);
var secs = seconds % 60;
return (hours ? hours + 'h ' : '') + (minutes ? minutes + 'm ' : '') + secs + 's';
""".strip()

GRID_SETTINGS: dict[str, Any] = {
    "backgroundColor": "#f5f7fa",
    "color": "rgba(0,0,0,0.87)",
    "columns": 24,
    "backgroundSizeMode": "100%",
    "autoFillHeight": True,
    "mobileAutoFillHeight": False,
    "mobileRowHeight": 70,
    "margin": 10,
    "outerMargin": True,
    "layoutType": "default",
}


def data_key(
    name: str,
    label: str,
    colour: str,
    *,
    key_type: str = "timeseries",
    units: str | None = None,
    decimals: int | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    key: dict[str, Any] = {
        "name": name,
        "type": key_type,
        "label": label,
        "color": colour,
        "settings": settings or {},
    }
    if units is not None:
        key["units"] = units
    if decimals is not None:
        key["decimals"] = decimals
    return key


def table_cell(colour_function: str = "", width: str = "0px") -> dict[str, Any]:
    return {
        "columnWidth": width,
        "useCellStyleFunction": bool(colour_function),
        "cellStyleFunction": colour_function,
        "useCellContentFunction": False,
        "cellContentFunction": "",
    }


def base_config(title: str, *, settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "showTitle": True,
        "backgroundColor": "rgb(255, 255, 255)",
        "color": "rgba(0, 0, 0, 0.87)",
        "padding": "8px",
        "settings": settings,
        "title": title,
        "dropShadow": True,
        "enableFullscreen": True,
        "titleStyle": {"fontSize": "16px", "fontWeight": 500},
        "widgetStyle": {},
        "widgetCss": "",
        "actions": {},
    }


def widget(
    label: str,
    title: str,
    fqn: str,
    widget_type: str,
    config: dict[str, Any],
    size_x: int,
    size_y: int,
    row: int,
    col: int,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    widget_id = uid("widget/" + label)
    full = {
        "id": widget_id,
        "type": widget_type,
        "typeFullFqn": fqn,
        "sizeX": size_x,
        "sizeY": size_y,
        "row": row,
        "col": col,
        "config": config,
    }
    placement = {
        "sizeX": size_x,
        "sizeY": size_y,
        "row": row,
        "col": col,
        "mobileOrder": row * 100 + col,
        "mobileHeight": size_y,
    }
    return widget_id, full, placement


def datasource(alias_id: str, keys: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "entity", "name": None, "entityAliasId": alias_id, "dataKeys": keys}


def map_widget() -> tuple[str, dict[str, Any], dict[str, Any]]:
    keys = [
        data_key("latitude", "Latitude", "#2196f3", decimals=6),
        data_key("longitude", "Longitude", "#4caf50", decimals=6),
        data_key("operational_state", "State", "#8bc34a"),
        data_key("turbidity_ntu", "Turbidity", "#ffc107", decimals=1),
        data_key("node_id", "Node", "#607d8b"),
        data_key("water_point", "Water point", "#9c27b0"),
    ]
    settings = {
        "provider": "openstreet-map",
        "mapProvider": "OpenStreetMap.Mapnik",
        "useCustomProvider": False,
        "latKeyName": "latitude",
        "lngKeyName": "longitude",
        "defaultCenterPosition": "27.709,85.352",
        "fitMapBounds": True,
        "useDefaultCenterPosition": False,
        "disableScrollZooming": False,
        "disableZoomControl": False,
        "showLabel": True,
        "label": "${entityName}",
        "showTooltip": True,
        "tooltipPattern": (
            "<b>${entityName}</b><br/>State: ${operational_state}<br/>"
            "Water point: ${water_point}<br/>Turbidity: ${turbidity_ntu} NTU"
        ),
        "useColorFunction": True,
        "colorFunction": (
            "var state = dsData[dsIndex]['operational_state'];\n"
            + STATE_COLOURS.replace("value", "state")
        ),
        "useMarkerImageFunction": False,
        "markerImageSize": 34,
    }
    cfg = base_config("FloodSafe water points — click a marker for detail", settings=settings)
    cfg["datasources"] = [datasource(FLEET_ALIAS, keys)]
    return widget("map", "Water-point map (OpenStreetMap)", MAP_FQN, "latest", cfg, 24, 8, 0, 0)


def state_table_widget() -> tuple[str, dict[str, Any], dict[str, Any]]:
    keys = [
        data_key(
            "operational_state",
            "State",
            "#2e7d32",
            settings=table_cell(STATE_COLOURS, "110px"),
        ),
        data_key("turbidity_ntu", "Turbidity (NTU)", "#ffc107", decimals=1),
        data_key("ph", "pH", "#2196f3", decimals=2),
        data_key("tds_ppm", "TDS (ppm)", "#9c27b0", decimals=0),
        data_key("ts", "Last activity", "#607d8b"),
    ]
    settings = {
        "entitiesTitle": "Water points",
        "enableSearch": False,
        "enableSelectColumnDisplay": True,
        "enableStickyHeader": True,
        "displayEntityName": True,
        "displayEntityType": False,
        "displayPagination": False,
        "defaultPageSize": 10,
        "defaultSortOrder": "displayName",
    }
    cfg = base_config("Operational state — at a glance", settings=settings)
    cfg["datasources"] = [datasource(FLEET_ALIAS, keys)]
    cfg["actions"] = {
        "rowClick": [
            {
                "name": "Open node detail",
                "type": "openDashboardState",
                "targetDashboardStateId": "node_detail",
                "setEntityId": True,
            }
        ]
    }
    return widget("state_table", "Operational state summary", TABLE_FQN, "latest", cfg, 12, 6, 8, 0)


def alarms_widget(label: str, title: str, alias_id: str, size_x: int, row: int, col: int) -> tuple[str, dict[str, Any], dict[str, Any]]:
    settings = {
        "enableSelection": True,
        "enableSearch": True,
        "displayDetails": True,
        "displayActivity": True,
        "allowAcknowledgment": True,
        "allowClear": True,
        "allowAssign": True,
        "displayPagination": True,
        "defaultPageSize": 10,
        "defaultSortOrder": "-createdTime",
        "enableFilter": True,
        "enableSelectColumnDisplay": True,
        "alarmsTitle": "Active and cleared alarms",
    }
    cfg = base_config(title, settings=settings)
    cfg["timewindow"] = {
        "realtime": {"interval": 1000, "timewindowMs": 86400000},
        "aggregation": {"type": "NONE", "limit": 200},
    }
    cfg["useDashboardTimewindow"] = False
    cfg["displayTimewindow"] = True
    cfg["alarmSource"] = {
        "type": "entity",
        "name": "alarms",
        "entityAliasId": alias_id,
        "filterId": None,
        "dataKeys": [
            data_key("createdTime", "Created", "#2196f3", key_type="alarm"),
            data_key("originator", "Device", "#4caf50", key_type="alarm"),
            data_key("type", "Alarm", "#f44336", key_type="alarm"),
            data_key("severity", "Severity", "#ffc107", key_type="alarm"),
            data_key("status", "Status", "#607d8b", key_type="alarm"),
            data_key(
                "startTime",
                "Duration",
                "#9c27b0",
                key_type="alarm",
                settings={
                    "columnWidth": "90px",
                    "useCellStyleFunction": False,
                    "cellStyleFunction": "",
                    "useCellContentFunction": True,
                    "cellContentFunction": ALARM_DURATION_FN,
                },
            ),
        ],
    }
    cfg["alarmFilterConfig"] = {
        "statusList": [],  # empty = active AND cleared
        "severityList": [],
        "typeList": [],
        "searchPropagatedAlarms": True,
    }
    cfg["alarmsPollingInterval"] = 5
    return widget(label, title, ALARM_FQN, "alarm", cfg, size_x, 6, row, col)


def health_widget() -> tuple[str, dict[str, Any], dict[str, Any]]:
    keys = [
        data_key("node_id", "Node ID", "#2196f3"),
        data_key("water_point", "Water point", "#4caf50"),
        data_key("ts", "Last activity (epoch ms)", "#607d8b"),
        data_key("flow_lpm", "Flow (L/min)", "#ffc107", decimals=1),
        data_key("scenario", "Scenario", "#9c27b0"),
    ]
    settings = {
        "entitiesTitle": "Node health",
        "enableSearch": False,
        "displayEntityName": True,
        "displayEntityType": False,
        "displayPagination": False,
        "defaultSortOrder": "displayName",
    }
    cfg = base_config("Node health — last activity", settings=settings)
    cfg["datasources"] = [datasource(FLEET_ALIAS, keys)]
    return widget("node_health", "Node health", TABLE_FQN, "latest", cfg, 24, 4, 14, 0)


def gauge_widget(
    label: str,
    title: str,
    key_name: str,
    units: str,
    minimum: float,
    maximum: float,
    decimals: int,
    highlights: list[dict[str, Any]],
    col: int,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    settings = {
        "minValue": minimum,
        "maxValue": maximum,
        "startAngle": 45,
        "ticksAngle": 270,
        "showBorder": True,
        "defaultColor": "#2e7d32",
        "highlights": highlights,
        "highlightsWidth": 15,
        "minorTicks": 10,
        "valueInt": decimals,
        "valueBox": True,
        "animation": True,
        "animationDuration": 500,
        "animationRule": "cycle",
        "showUnitTitle": True,
        "unitsFont": {"family": "Roboto", "size": 18, "style": "normal", "weight": "500"},
    }
    cfg = base_config(title, settings=settings)
    cfg["datasources"] = [
        datasource(
            STATE_ALIAS,
            [data_key(key_name, title, "#2e7d32", units=units, decimals=decimals)],
        )
    ]
    return widget(label, title, GAUGE_FQN, "latest", cfg, 4, 4, 0, col)


def chart_widget(
    label: str,
    title: str,
    keys: list[tuple[str, str, str, int]],
    row: int,
    col: int,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    data_keys = [
        data_key(name, title_label, colour, decimals=decimals)  # noqa: B023
        for name, title_label, colour, decimals in keys
    ]
    settings = {
        "showLegend": True,
        "legendConfig": {
            "direction": "column",
            "position": "top",
            "showAvg": True,
            "showMin": False,
            "showMax": True,
        },
        "thresholds": [],
        "dataZoom": True,
        "yAxis": {"show": True, "label": "Value", "position": "left"},
        "xAxis": {"show": True, "label": "Time"},
        "showTooltip": True,
    }
    cfg = base_config(title, settings=settings)
    cfg["datasources"] = [datasource(STATE_ALIAS, data_keys)]
    cfg["useDashboardTimewindow"] = True
    return widget(label, title, CHART_FQN, "timeseries", cfg, 12, 6, row, col)


def state_card_widget() -> tuple[str, dict[str, Any], dict[str, Any]]:
    settings = {
        "labelPosition": "top",
        "showLabel": True,
        "showIcon": False,
        "showDate": True,
        "dateFormat": {"format": None, "lastUpdateAgo": True, "custom": False},
        "valueColor": {"type": "function", "colorFunction": STATE_COLOURS},
        "valueFont": {"family": "Roboto", "size": 32, "style": "normal", "weight": "500"},
    }
    cfg = base_config("Current operational state", settings=settings)
    cfg["datasources"] = [
        datasource(STATE_ALIAS, [data_key("operational_state", "State", "#2e7d32")])
    ]
    cfg["units"] = ""
    cfg["decimals"] = 0
    return widget("state_card", "Current operational state", VALUE_CARD_FQN, "latest", cfg, 6, 3, 10, 0)


def build_dashboard() -> dict[str, Any]:
    fleet_alias = {
        "id": FLEET_ALIAS,
        "alias": "FloodSafe Nodes",
        "filter": {
            "type": "deviceType",
            "resolveMultiple": True,
            "deviceNameFilter": "",
            "deviceTypes": ["FloodSafe Node"],
        },
    }
    state_alias = {
        "id": STATE_ALIAS,
        "alias": "Selected FloodSafe Node",
        "filter": {
            "type": "stateEntity",
            "resolveMultiple": False,
            "stateEntityParamName": None,
            "defaultStateEntity": None,
        },
    }

    root_items = [
        map_widget(),
        state_table_widget(),
        alarms_widget("fleet_alarms", "Active and cleared alarms", FLEET_ALIAS, 12, 8, 12),
        health_widget(),
    ]
    detail_items = [
        gauge_widget(
            "gauge_ph", "pH", "ph", "pH", 5.5, 9.5, 2,
            [
                {"from": 5.5, "to": 6.5, "color": "#d32f2f"},
                {"from": 6.5, "to": 8.5, "color": "#2e7d32"},
                {"from": 8.5, "to": 9.5, "color": "#d32f2f"},
            ],
            0,
        ),
        gauge_widget(
            "gauge_turbidity", "Turbidity", "turbidity_ntu", "NTU", 0, 800, 1,
            [
                {"from": 0, "to": 5, "color": "#2e7d32"},
                {"from": 5, "to": 50, "color": "#fbc02d"},
                {"from": 50, "to": 200, "color": "#f57c00"},
                {"from": 200, "to": 800, "color": "#d32f2f"},
            ],
            4,
        ),
        gauge_widget(
            "gauge_tds", "TDS", "tds_ppm", "ppm", 0, 1200, 0,
            [
                {"from": 0, "to": 500, "color": "#2e7d32"},
                {"from": 500, "to": 1000, "color": "#f57c00"},
                {"from": 1000, "to": 1200, "color": "#d32f2f"},
            ],
            8,
        ),
        gauge_widget("gauge_temp", "Water temperature", "water_temp_c", "°C", 10, 30, 1, [], 12),
        gauge_widget(
            "gauge_flow", "Flow", "flow_lpm", "L/min", 0, 25, 1,
            [
                {"from": 0, "to": 0.1, "color": "#d32f2f"},
                {"from": 0.1, "to": 25, "color": "#2e7d32"},
            ],
            16,
        ),
        chart_widget(
            "chart_quality",
            "Turbidity / pH / TDS trend",
            [
                ("turbidity_ntu", "Turbidity (NTU)", "#ffc107", 1),
                ("ph", "pH", "#2196f3", 2),
                ("tds_ppm", "TDS (ppm)", "#9c27b0", 0),
            ],
            4,
            0,
        ),
        chart_widget(
            "chart_supply",
            "Temperature and flow trend",
            [
                ("water_temp_c", "Water temp (°C)", "#00bcd4", 1),
                ("flow_lpm", "Flow (L/min)", "#4caf50", 1),
            ],
            4,
            12,
        ),
        state_card_widget(),
        alarms_widget("detail_alarms", "Alarms for this node", STATE_ALIAS, 18, 10, 6),
    ]

    widgets: dict[str, Any] = {}
    root_layout: dict[str, Any] = {}
    detail_layout: dict[str, Any] = {}
    for wid, full, placement in root_items:
        widgets[wid] = full
        root_layout[wid] = placement
    for wid, full, placement in detail_items:
        widgets[wid] = full
        detail_layout[wid] = placement

    return {
        "title": "FloodSafe Nepal — Municipal Operations",
        "image": None,
        "mobileHide": False,
        "mobileOrder": None,
        "name": "FloodSafe Nepal — Municipal Operations",
        "resources": [],
        "configuration": {
            "description": (
                "Operational overview for three virtual water points. "
                "Generated template — verify in your ThingsBoard version."
            ),
            "widgets": widgets,
            "states": {
                "default": {
                    "name": "Fleet overview",
                    "root": True,
                    "layouts": {"main": {"widgets": root_layout, "gridSettings": GRID_SETTINGS}},
                },
                "node_detail": {
                    "name": "Node detail: ${entityName}",
                    "root": False,
                    "layouts": {"main": {"widgets": detail_layout, "gridSettings": GRID_SETTINGS}},
                },
            },
            "entityAliases": {FLEET_ALIAS: fleet_alias, STATE_ALIAS: state_alias},
            "filters": {},
            "timewindow": {
                "selectedTab": 0,
                "realtime": {"realtimeType": 0, "timewindowMs": 900000},
                "aggregation": {"type": "NONE", "limit": 50000},
            },
            "settings": {
                "stateControllerId": "entity",
                "showTitle": True,
                "showDashboardsSelect": True,
                "showEntitiesSelect": True,
                "showDashboardTimewindow": True,
                "showDashboardExport": True,
                "toolbarAlwaysOpen": True,
                "title": "FloodSafe Nepal — Municipal Operations",
            },
        },
    }


def build_rule_chain() -> dict[str, Any]:
    script = (HERE / "operational_state.tbel.js").read_text(encoding="utf-8")
    transform = {
        "additionalInfo": {"layoutX": 320, "layoutY": 200},
        "type": "org.thingsboard.rule.engine.transform.TbTransformMsgNode",
        "name": "Compute operational_state (PROPOSED)",
        "configurationVersion": 0,
        "debugFailures": False,
        "debugAll": False,
        "configuration": {
            "scriptLang": "TBEL",
            "jsScript": script,
            "tbelScript": script,
        },
    }
    save = {
        "additionalInfo": {"layoutX": 700, "layoutY": 200},
        "type": "org.thingsboard.rule.engine.telemetry.TbMsgTimeseriesNode",
        "name": "Save operational_state",
        "configurationVersion": 1,
        "debugFailures": False,
        "debugAll": False,
        "configuration": {
            "defaultTTL": 0,
            "useServerTs": False,
            "processingSettings": {"type": "ON_EVERY_MESSAGE"},
        },
    }
    return {
        "ruleChain": {
            "additionalInfo": {
                "description": (
                    "Template only. Link from Root Rule Chain via a Rule Chain node after Save Timeseries. "
                    "State thresholds are PROPOSED and require group approval."
                )
            },
            "name": "FloodSafe Operational State",
            "firstRuleNodeId": None,
            "root": False,
            "debugMode": False,
            "configuration": None,
        },
        "metadata": {
            "firstNodeIndex": 0,
            "nodes": [transform, save],
            "connections": [{"fromIndex": 0, "toIndex": 1, "type": "Success"}],
            "ruleChainConnections": None,
        },
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    write_json(HERE / "dashboard_template_floodsafe.json", build_dashboard())
    write_json(HERE / "rule_chain_operational_state_template.json", build_rule_chain())
    print(
        "Wrote dashboard_template_floodsafe.json and "
        "rule_chain_operational_state_template.json"
    )


if __name__ == "__main__":
    main()
