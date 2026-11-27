"""Tests for the ThingsBoard configuration committed to this repository.

These are offline tests: no ThingsBoard account, token or network is needed,
and the real database is never touched. The rule-chain file is a sanitised
export from the verified ThingsBoard 4.4.1 tenant. The dashboard JSON was
rebased from the user-supplied earlier export and then polished locally for a
light theme, compact state badge, Intervention response strip and non-clickable
summary cards; the generator remains a design-time reference only.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from thingsboard import generate_config

ROOT = Path(__file__).resolve().parents[1]
TB = ROOT / "thingsboard"


def load_json(name: str) -> dict:
    return json.loads((TB / name).read_text(encoding="utf-8"))


class ThingsBoardConfigTests(unittest.TestCase):
    def test_all_generated_json_files_are_valid(self) -> None:
        names = (
            "dashboard_floodsafe.json",
            "rule_chain_operational_state.json",
            "alarm_rules.json",
        )
        for name in names:
            with self.subTest(name=name):
                self.assertIsInstance(load_json(name), dict)

    def test_no_credential_like_strings_are_present(self) -> None:
        # UUIDs contain dashes, so this only catches long random tokens.
        pattern = re.compile(r"\b[A-Za-z0-9]{32,}\b")
        for path in TB.iterdir():
            if path.is_file() and path.suffix in {".json", ".js", ".py", ".md"}:
                with self.subTest(file=path.name):
                    self.assertIsNone(pattern.search(path.read_text(encoding="utf-8")))

    def test_dashboard_has_all_required_widget_types(self) -> None:
        dashboard = load_json("dashboard_floodsafe.json")
        fqns = {w["typeFullFqn"] for w in dashboard["configuration"]["widgets"].values()}
        self.assertTrue(
            {
                "system.map",
                "system.analogue_gauges.radial_gauge_canvas_gauges",
                "system.time_series_chart",
                "system.cards.entities_table",
                "system.cards.markdown_card",
                "system.alarm_widgets.alarms_table",
            }.issubset(fqns)
        )
        self.assertEqual(set(dashboard["configuration"]["states"]), {"default", "node_detail"})

    def test_dashboard_matches_thingsboard_export_shape(self) -> None:
        dashboard = load_json("dashboard_floodsafe.json")
        self.assertIsInstance(dashboard["resources"], list)
        settings = dashboard["configuration"]["settings"]
        self.assertEqual(settings["stateControllerId"], "entity")
        self.assertNotIn("stateController", settings)
        for widget in dashboard["configuration"]["widgets"].values():
            for key in ("sizeX", "sizeY", "row", "col"):
                self.assertIn(key, widget)

    def test_dashboard_aliases_target_the_device_profile(self) -> None:
        dashboard = load_json("dashboard_floodsafe.json")
        aliases = list(dashboard["configuration"]["entityAliases"].values())
        fleet = next(a for a in aliases if a["alias"] == "FloodSafe Nodes")
        self.assertEqual(fleet["filter"]["type"], "deviceType")
        self.assertEqual(fleet["filter"]["deviceTypes"], ["FloodSafe Node"])
        self.assertTrue(fleet["filter"]["resolveMultiple"])
        state = next(a for a in aliases if a["alias"] == "Selected FloodSafe Node")
        self.assertEqual(state["filter"]["type"], "stateEntity")

    def test_map_colour_function_uses_the_state_variable(self) -> None:
        dashboard = load_json("dashboard_floodsafe.json")
        map_widget = next(
            w
            for w in dashboard["configuration"]["widgets"].values()
            if w["typeFullFqn"] == "system.map"
        )
        marker = map_widget["config"]["settings"]["markers"][0]
        colour_function = marker["markerShape"]["color"]["colorFunction"]
        self.assertIn("var state = data.operational_state;", colour_function)
        self.assertIn("if (state == 'Intervention')", colour_function)
        self.assertIn("if (state == 'Watch')", colour_function)
        self.assertIn("return '#9e9e9e';", colour_function)
        self.assertNotIn("dsData[dsIndex]", colour_function)

    def test_committed_map_uses_timeseries_coordinates_and_drilldown(self) -> None:
        dashboard = load_json("dashboard_floodsafe.json")
        map_widget = next(
            w
            for w in dashboard["configuration"]["widgets"].values()
            if w["typeFullFqn"] == "system.map"
        )
        marker = map_widget["config"]["settings"]["markers"][0]
        self.assertEqual(marker["xKey"]["type"], "timeseries")
        self.assertEqual(marker["yKey"]["type"], "timeseries")
        self.assertEqual(marker["click"]["targetDashboardStateId"], "node_detail")
        self.assertTrue(marker["click"]["setEntityId"])

    def test_gauge_bands_match_task_three(self) -> None:
        dashboard = load_json("dashboard_floodsafe.json")
        widgets = dashboard["configuration"]["widgets"]
        ph = next(w for w in widgets.values() if w["config"]["title"] == "pH")
        highlights = ph["config"]["settings"]["highlights"]
        self.assertEqual([(h["from"], h["to"]) for h in highlights], [(5.5, 6.5), (6.5, 8.5), (8.5, 9.5)])

        turbidity = next(w for w in widgets.values() if w["config"]["title"] == "Turbidity")
        highlights = turbidity["config"]["settings"]["highlights"]
        self.assertEqual([h["from"] for h in highlights], [0, 5, 50, 200])
        self.assertEqual([h["to"] for h in highlights], [5, 50, 200, 800])

        tds = next(w for w in widgets.values() if w["config"]["title"] == "TDS")
        highlights = tds["config"]["settings"]["highlights"]
        self.assertEqual([h["from"] for h in highlights], [0, 500, 1000])

    def test_alarm_rules_match_task_three_exactly(self) -> None:
        data = load_json("alarm_rules.json")
        self.assertEqual(data["device_profile"], "FloodSafe Node")
        expected = {
            "High Turbidity": ("Warning", "turbidity_ntu > 50", "turbidity_ntu < 40"),
            "Gross Contamination": ("Critical", "turbidity_ntu > 200", "turbidity_ntu < 150"),
            "pH Out of Range": ("Critical", "ph < 6.5 OR ph > 8.5", "6.7 <= ph <= 8.3"),
            "High TDS": ("Critical", "tds_ppm > 500", "tds_ppm < 450"),
            "Supply Interruption": ("Major", "flow_lpm == 0 sustained", "flow_lpm > 0"),
            "Node Inactive": ("Critical", "Device inactivity timeout exceeded", "Telemetry resumes"),
        }
        actual = {
            a["name"]: (a["severity"], a["create"], a["clear"]) for a in data["alarms"]
        }
        self.assertEqual(actual, expected)

    def test_rule_chain_contains_transform_and_save_nodes(self) -> None:
        chain = load_json("rule_chain_operational_state.json")
        nodes = chain["metadata"]["nodes"]
        self.assertEqual(
            [n["type"] for n in nodes],
            [
                "org.thingsboard.rule.engine.transform.TbTransformMsgNode",
                "org.thingsboard.rule.engine.telemetry.TbMsgTimeseriesNode",
            ],
        )
        self.assertEqual(chain["metadata"]["connections"], [{"fromIndex": 0, "toIndex": 1, "type": "Success"}])
        live_script = nodes[0]["configuration"]["tbelScript"]
        js_script = nodes[0]["configuration"]["jsScript"]
        self.assertIn("return {msg: msg, metadata: metadata, msgType: msgType};", js_script)
        for state in ("Normal", "Watch", "Investigate", "Intervention"):
            self.assertIn("'" + state + "'", live_script)
        self.assertIn("var turbidity = msg['turbidity_ntu'];", live_script)
        self.assertIn("msg['operational_state'] = state;", live_script)
        self.assertIn("return {msg: msg, metadata: metadata, msgType: msgType};", live_script)

    def test_tbel_script_marks_proposed_thresholds(self) -> None:
        script = (TB / "operational_state.tbel.js").read_text(encoding="utf-8")
        self.assertIn("PROPOSED", script)
        self.assertIn("return {msg: msg, metadata: metadata, msgType: msgType};", script)
        for state in ("Normal", "Watch", "Investigate", "Intervention"):
            self.assertIn(state, script)
        for threshold in ("50", "200", "6.5", "8.5", "500", "1000"):
            self.assertIn(threshold, script)
        self.assertNotIn("Warning'", script)  # states are not alarm severities

    def test_docs_flag_unspecified_values_and_limitations(self) -> None:
        alarm_doc = (TB / "alarm_rules.md").read_text(encoding="utf-8")
        self.assertIn("Not specified in the assignment", alarm_doc)
        self.assertIn("inactivity timeout", alarm_doc)
        state_doc = (TB / "operational_states.md").read_text(encoding="utf-8")
        self.assertIn("PROPOSED", state_doc)
        self.assertIn("require persistent", state_doc)
        self.assertIn("before escalation", state_doc)
        readme = (TB / "README.md").read_text(encoding="utf-8")
        self.assertIn("timestamp envelope", readme)
        self.assertNotIn("payload is flat", readme)

    def test_test_publisher_does_not_touch_the_database(self) -> None:
        source = (TB / "publish_test_reading.py").read_text(encoding="utf-8")
        self.assertNotIn("src.database", source)
        self.assertNotIn("insert_reading", source)

    def test_generator_still_produces_a_valid_reference_template(self) -> None:
        # The committed dashboard is a redesigned export; the generator remains
        # a deterministic design-time reference for rebuilding a new template.
        generated = json.loads(json.dumps(generate_config.build_dashboard()))
        self.assertIn("configuration", generated)
        self.assertIn("widgets", generated["configuration"])
        self.assertEqual(set(generated["configuration"]["states"]), {"default", "node_detail"})

    def test_state_kpis_count_water_points_and_are_not_clickable(self) -> None:
        dashboard = load_json("dashboard_floodsafe.json")
        widgets = dashboard["configuration"]["widgets"]
        filters = dashboard["configuration"]["filters"]
        ids = [
            "d490b168-9871-5d9f-a3a2-c1b17edadfa0",
            "b32ef427-fb55-5316-af0b-23bcc32bc585",
            "b92f891c-3192-5713-a9ad-12b34d02d2f4",
            "12165aa1-4582-5913-a51b-c6f83596282f",
        ]
        expected_colours = ["#15803d", "#fef08a", "#ffedd5", "#dc2626"]
        for widget_id, colour in zip(ids, expected_colours):
            kpi = widgets[widget_id]
            self.assertEqual(kpi["typeFullFqn"], "system.cards.html_value_card")
            datasource = kpi["config"]["datasources"][0]
            self.assertEqual(datasource["type"], "entityCount")
            self.assertEqual(datasource["entityAliasId"], "4362b944-40bc-5596-be72-bc3fa7b4a344")
            key_filter = filters[datasource["filterId"]]["keyFilters"][0]
            self.assertEqual(key_filter["key"]["key"], "operational_state")
            html = kpi["config"]["settings"]["cardHtml"]
            self.assertIn("${" + datasource["dataKeys"][0]["label"] + ":0}", html)
            self.assertIn("water points", html)
            self.assertIn("--accent:" + colour, html)
            self.assertEqual(kpi["config"]["actions"], {})
            css = kpi["config"]["settings"]["cardCss"]
            self.assertIn("background: var(--accent)", css)
            self.assertIn("color: var(--fg)", css)

    def test_alarm_summary_uses_severity_counts_and_is_not_clickable(self) -> None:
        dashboard = load_json("dashboard_floodsafe.json")
        widgets = dashboard["configuration"]["widgets"]
        ids = [
            "f20b5576-6233-564c-8d0c-2326f3d57cd7",
            "6d1c28c7-9d6b-50a0-a9fa-984608221709",
            "02e07beb-f0d7-5359-8401-37bf179f1770",
        ]
        expected = [
            ("CRITICAL", "Critical active"),
            ("MAJOR", "Major active"),
            ("WARNING", "Warning active"),
        ]
        for widget_id, (severity, label) in zip(ids, expected):
            widget = widgets[widget_id]
            self.assertEqual(widget["typeFullFqn"], "system.alarm_count")
            alarm_filter = widget["config"]["datasources"][0]["alarmFilterConfig"]
            self.assertEqual(alarm_filter["severityList"], [severity])
            self.assertEqual(alarm_filter["statusList"], ["ACTIVE"])
            self.assertEqual(widget["config"]["settings"]["label"], label)
            self.assertEqual(widget["config"]["settings"]["layout"], "row")
            self.assertEqual(widget["config"]["actions"], {})
            self.assertNotIn("Click target", [ds.get("name") for ds in widget["config"]["datasources"]])

    def test_attention_table_keeps_the_exported_needs_attention_filter(self) -> None:
        dashboard = load_json("dashboard_floodsafe.json")
        widgets = dashboard["configuration"]["widgets"]
        filters = dashboard["configuration"]["filters"]
        attention = next(
            w
            for w in widgets.values()
            if w["config"].get("title") == "Needs attention — highest priority first"
        )
        datasource = attention["config"]["datasources"][0]
        self.assertEqual(datasource["entityAliasId"], "4362b944-40bc-5596-be72-bc3fa7b4a344")
        self.assertEqual(datasource["filterId"], "3b95d544-636f-528d-960a-d6b3b0b52d7c")
        self.assertEqual(attention["config"]["settings"]["entitiesTitle"], "Needs attention")
        values = [
            key_filter["predicates"][0]["keyFilterPredicate"]["value"]["defaultValue"]
            for key_filter in filters[datasource["filterId"]]["keyFilters"]
        ]
        self.assertEqual(values, ["Intervention", "Investigate"])
        labels = [key["label"] for key in datasource["dataKeys"]]
        self.assertEqual(labels.count("State"), 1)
        self.assertNotIn("Reason", labels)
        state_key = next(
            key for key in datasource["dataKeys"] if key["name"] == "operational_state"
        )
        content_function = state_key["settings"]["cellContentFunction"]
        self.assertIn("Intervention", content_function)
        self.assertIn("#f57c00", content_function)  # Investigate fallback colour
        row_action = attention["config"]["actions"]["rowClick"][0]
        self.assertEqual(row_action["targetDashboardStateId"], "node_detail")
        self.assertTrue(row_action["setEntityId"])

    def test_priority_table_keeps_district_limitation_note(self) -> None:
        dashboard = load_json("dashboard_floodsafe.json")
        context = next(
            w
            for w in dashboard["configuration"]["widgets"].values()
            if "DISTRICT & SHARED-SOURCE CONTEXT"
            in w["config"]["settings"].get("markdownTextPattern", "")
        )
        self.assertIn(
            "future enhancement", context["config"]["settings"]["markdownTextPattern"]
        )

    def test_demo_timewindow_is_long_enough_for_offline_sync(self) -> None:
        dashboard = load_json("dashboard_floodsafe.json")
        realtime = dashboard["configuration"]["timewindow"]["realtime"]
        self.assertEqual(realtime["timewindowMs"], 86_400_000)

    def test_map_uses_short_labels_and_rich_click_tooltip(self) -> None:
        dashboard = load_json("dashboard_floodsafe.json")
        map_widget = next(
            w
            for w in dashboard["configuration"]["widgets"].values()
            if w["typeFullFqn"] == "system.map"
        )
        marker = map_widget["config"]["settings"]["markers"][0]
        self.assertIn("${node_id}", marker["label"]["pattern"])
        self.assertNotIn("${entityName}", marker["label"]["pattern"])
        self.assertEqual(marker["tooltip"]["type"], "function")
        tooltip = marker["tooltip"]["patternFunction"]
        for field in (
            "operational_state",
            "water_point",
            "turbidity_ntu",
            "ph",
            "tds_ppm",
            "flow_lpm",
            "ts",
            "lastActivityTime",
        ):
            self.assertIn(field, tooltip)
        self.assertEqual(marker["click"]["targetDashboardStateId"], "node_detail")
        self.assertTrue(marker["click"]["setEntityId"])

    def test_metadata_card_uses_only_existing_fields(self) -> None:
        dashboard = load_json("dashboard_floodsafe.json")
        cards = [
            w
            for w in dashboard["configuration"]["widgets"].values()
            if w["config"].get("title") == "Node Metadata & Location"
        ]
        self.assertEqual(len(cards), 1)
        card = cards[0]
        self.assertEqual(card["typeFullFqn"], "system.cards.markdown_card")
        settings = card["config"]["settings"]
        self.assertTrue(settings["useMarkdownTextFunction"])
        function = settings["markdownTextFunction"]
        self.assertNotIn("Not configured (unverified)", function)
        self.assertIn("districts", function)
        self.assertIn("'FSN-01': 'Kathmandu'", function)
        self.assertIn("'FSN-02': 'Kathmandu'", function)
        self.assertIn("'FSN-03': 'Lalitpur'", function)
        self.assertIn("district ? esc(district) : 'Unavailable'", function)
        self.assertIn("active", function)
        self.assertIn("lastActivityTime", function)
        self.assertIn("latitude", function)
        self.assertIn("longitude", function)
        self.assertIn("Telemetry time", function)
        self.assertIn("if (v == null || v === '') return 'Unavailable';", function)
        self.assertNotIn("ONLINE", function)
        data_keys = card["config"]["datasources"][0]["dataKeys"]
        names = {key["name"] for key in data_keys}
        labels = {key["label"] for key in data_keys}
        self.assertEqual(
            names,
            {
                "node_id",
                "water_point",
                "latitude",
                "longitude",
                "active",
                "lastActivityTime",
                "ts",
            },
        )
        # ThingsBoard passes data-key labels into markdown functions, so the
        # labels must match the names the function reads.
        self.assertEqual(labels, names)
        self.assertNotIn("district", names)

    def test_node_config_provides_districts_for_all_three_demo_nodes(self) -> None:
        config = json.loads((ROOT / "config" / "nodes.json").read_text(encoding="utf-8"))
        districts = {node["node_id"]: node["district"] for node in config["nodes"]}
        self.assertEqual(
            districts,
            {"FSN-01": "Kathmandu", "FSN-02": "Kathmandu", "FSN-03": "Lalitpur"},
        )
        self.assertIn("OpenStreetMap/Nominatim", config["coordinate_notice"])

    def test_current_operational_state_is_a_compact_colour_coded_badge(self) -> None:
        dashboard = load_json("dashboard_floodsafe.json")
        card = next(
            w
            for w in dashboard["configuration"]["widgets"].values()
            if w["config"].get("title") == "Current operational state"
        )
        self.assertEqual(card["typeFullFqn"], "system.cards.markdown_card")
        # The attached user-tuned layout is authoritative; it widened the badge.
        self.assertEqual(card["sizeX"], 9)
        self.assertEqual(card["sizeY"], 5)
        settings = card["config"]["settings"]
        function = settings["markdownTextFunction"]
        for state, colour in (
            ("normal", "#2e7d32"),
            ("watch", "#fbc02d"),
            ("investigate", "#f57c00"),
            ("intervention", "#d32f2f"),
        ):
            self.assertIn(state + ": '" + colour + "'", function)
        self.assertNotIn("font-size:34px", settings["markdownCss"])
        self.assertIn("clamp(20px,3vh,30px)", settings["markdownCss"])
        # The response strip is conditional and stays inside the existing 9x5 badge.
        self.assertIn("state === 'intervention'", function)
        self.assertIn("RESPONSE REQUIRED", function)
        self.assertIn("Acknowledge Critical alarm", function)
        self.assertIn("node-state-response", settings["markdownCss"])
        datasource = card["config"]["datasources"][0]
        self.assertEqual(
            datasource["entityAliasId"], "809504e0-7de1-5bd9-9322-b11f413c0428"
        )
        self.assertEqual(datasource["dataKeys"][0]["label"], "operational_state")

    def test_charts_keep_existing_alias_and_telemetry_keys(self) -> None:
        dashboard = load_json("dashboard_floodsafe.json")
        charts = [
            w
            for w in dashboard["configuration"]["widgets"].values()
            if w["typeFullFqn"] == "system.time_series_chart"
        ]
        self.assertEqual(len(charts), 2)
        for chart in charts:
            config = chart["config"]
            self.assertTrue(config["useDashboardTimewindow"])
            self.assertEqual(config["titleColor"], "#1e293b")
            self.assertIn("tb-legend-label", config["widgetCss"])
            datasource = config["datasources"][0]
            self.assertEqual(
                datasource["entityAliasId"], "809504e0-7de1-5bd9-9322-b11f413c0428"
            )
            self.assertTrue(all(key["type"] == "timeseries" for key in datasource["dataKeys"]))
        first_keys = {
            key["name"] for key in charts[0]["config"]["datasources"][0]["dataKeys"]
        }
        second_keys = {
            key["name"] for key in charts[1]["config"]["datasources"][0]["dataKeys"]
        }
        self.assertEqual(first_keys, {"turbidity_ntu", "ph", "tds_ppm"})
        self.assertEqual(second_keys, {"water_temp_c", "flow_lpm"})
        # The rebased export uses the chart's shared axis. Keep the standard
        # axis contract rather than reintroducing the earlier custom yAxes.
        for chart in charts:
            settings = chart["config"]["settings"]
            self.assertNotIn("showSeparateAxis", settings)
            self.assertNotIn("yAxes", settings)
            self.assertIn("#1e293b", chart["config"]["widgetCss"])

    def test_node_health_formats_timestamps(self) -> None:
        dashboard = load_json("dashboard_floodsafe.json")
        table = next(
            w
            for w in dashboard["configuration"]["widgets"].values()
            if w["config"].get("title") == "Node health — device state / last activity"
        )
        keys = {key["name"]: key for key in table["config"]["datasources"][0]["dataKeys"]}
        self.assertEqual(keys["lastActivityTime"]["type"], "attribute")
        self.assertEqual(keys["ts"]["label"], "Telemetry time")
        for name in ("lastActivityTime", "ts"):
            settings = keys[name]["settings"]
            self.assertTrue(settings["useCellContentFunction"])
            self.assertIn("toLocaleString", settings["cellContentFunction"])

    def test_alarm_scopes_are_explicit(self) -> None:
        dashboard = load_json("dashboard_floodsafe.json")
        widgets = dashboard["configuration"]["widgets"]
        counts = [
            w["config"]["settings"]["label"]
            for w in widgets.values()
            if w["typeFullFqn"] == "system.alarm_count"
        ]
        self.assertEqual(counts, ["Critical active", "Major active", "Warning active"])
        tables = [
            w for w in widgets.values() if w["typeFullFqn"] == "system.alarm_widgets.alarms_table"
        ]
        self.assertTrue(all("last 24h" in w["config"]["title"] for w in tables))
        for table in tables:
            self.assertEqual(
                table["config"]["alarmFilterConfig"]["statusList"], ["ACTIVE", "CLEARED"]
            )
            self.assertTrue(table["config"]["alarmSource"]["entityAliasId"])

    def test_dashboard_uses_light_theme(self) -> None:
        raw = (TB / "dashboard_floodsafe.json").read_text(encoding="utf-8")
        dashboard = load_json("dashboard_floodsafe.json")
        self.assertTrue(dashboard["configuration"]["description"].startswith("Light"))
        self.assertNotIn("#0a1120", raw)
        self.assertNotIn("#e6edf3", raw)
        for state in dashboard["configuration"]["states"].values():
            grid = state["layouts"]["main"]["gridSettings"]
            self.assertEqual(grid["backgroundColor"], "#f8fafc")
            self.assertEqual(grid["color"], "#1e293b")
        for widget in dashboard["configuration"]["widgets"].values():
            config = widget["config"]
            self.assertEqual(config["backgroundColor"], "#ffffff")
            self.assertEqual(config["color"], "#1e293b")
            if "titleColor" in config:
                self.assertEqual(config["titleColor"], "#1e293b")

    def test_default_state_uses_two_equal_columns(self) -> None:
        dashboard = load_json("dashboard_floodsafe.json")
        layout = dashboard["configuration"]["states"]["default"]["layouts"]["main"]["widgets"]
        state_ids = [
            "d490b168-9871-5d9f-a3a2-c1b17edadfa0",
            "b32ef427-fb55-5316-af0b-23bcc32bc585",
            "b92f891c-3192-5713-a9ad-12b34d02d2f4",
            "12165aa1-4582-5913-a51b-c6f83596282f",
        ]
        alarm_ids = [
            "f20b5576-6233-564c-8d0c-2326f3d57cd7",
            "6d1c28c7-9d6b-50a0-a9fa-984608221709",
            "02e07beb-f0d7-5359-8401-37bf179f1770",
        ]
        self.assertEqual(
            [(layout[i]["row"], layout[i]["col"], layout[i]["sizeX"], layout[i]["sizeY"])
             for i in state_ids],
            [(0, 0, 6, 3), (0, 6, 6, 3), (3, 0, 6, 3), (3, 6, 6, 3)],
        )
        self.assertEqual(
            [(layout[i]["row"], layout[i]["col"], layout[i]["sizeX"], layout[i]["sizeY"])
             for i in alarm_ids],
            [(0, 12, 12, 2), (2, 12, 12, 2), (4, 12, 12, 2)],
        )
        # Both columns occupy the same six rows.
        self.assertEqual(max(layout[i]["row"] + layout[i]["sizeY"] for i in state_ids), 6)
        self.assertEqual(max(layout[i]["row"] + layout[i]["sizeY"] for i in alarm_ids), 6)
        for widget_id in state_ids + alarm_ids:
            item = layout[widget_id]
            widget = dashboard["configuration"]["widgets"][widget_id]
            self.assertEqual(widget["sizeX"], item["sizeX"])
            self.assertEqual(widget["sizeY"], item["sizeY"])
            self.assertEqual(widget["row"], item["row"])
            self.assertEqual(widget["col"], item["col"])

    def test_node_detail_uses_the_attached_tuned_layout(self) -> None:
        dashboard = load_json("dashboard_floodsafe.json")
        layout = dashboard["configuration"]["states"]["node_detail"]["layouts"]["main"]["widgets"]
        state_item = layout["ae67ac18-a79d-5b51-85e4-ee382e54c4a0"]
        self.assertEqual(
            (state_item["row"], state_item["col"], state_item["sizeX"], state_item["sizeY"]),
            (0, 0, 9, 5),
        )
        meta_item = layout["fcecdc79-2560-586a-abdf-fdce9490c0ad"]
        self.assertEqual(
            (meta_item["row"], meta_item["col"], meta_item["sizeX"], meta_item["sizeY"]),
            (0, 9, 15, 5),
        )
        gauge_rows = {
            layout[i]["row"] for i in (
                "3d9d454f-77e7-5124-a932-dea99f10ff86",
                "6e7486f3-5ce5-51a7-82ff-221464fcc47b",
                "428d13b2-a2cf-5cc5-b157-9b3c75f5ebd1",
                "528aac5a-03c8-50b5-a9bf-2f10dccf6409",
                "5db1b96b-4c61-5ed1-a2d6-c02b599e554c",
            )
        }
        self.assertEqual(gauge_rows, {5})
        for chart_id in ("17955f27-5736-5b34-bb50-7531be0fb564", "870e5076-7858-51ca-b16d-67975257dc81"):
            self.assertEqual(layout[chart_id]["row"], 10)
        self.assertEqual(layout["5f2f753e-40e4-5e26-b73e-2f779ad151db"]["row"], 19)

    def test_layouts_fit_the_24_column_grid_without_overlap(self) -> None:
        dashboard = load_json("dashboard_floodsafe.json")
        for state_name, state in dashboard["configuration"]["states"].items():
            grid = state["layouts"]["main"]["gridSettings"]
            columns = grid["columns"]
            self.assertEqual(columns, 24)
            items = list(state["layouts"]["main"]["widgets"].values())
            for left_index, left in enumerate(items):
                self.assertGreaterEqual(left["col"], 0)
                self.assertGreaterEqual(left["sizeX"], 1)
                self.assertLessEqual(left["col"] + left["sizeX"], columns)
                for right in items[left_index + 1:]:
                    row_overlap = (
                        left["row"] < right["row"] + right["sizeY"]
                        and right["row"] < left["row"] + left["sizeY"]
                    )
                    col_overlap = (
                        left["col"] < right["col"] + right["sizeX"]
                        and right["col"] < left["col"] + left["sizeX"]
                    )
                    self.assertFalse(
                        row_overlap and col_overlap,
                        f"{state_name}: overlapping widgets at rows "
                        f"{left['row']}/{right['row']}",
                    )

    def test_docs_describe_the_light_local_polish(self) -> None:
        readme = (TB / "README.md").read_text(encoding="utf-8")
        build_sheet = (TB / "dashboard_build_sheet.md").read_text(encoding="utf-8")
        checklist = (TB / "verification_checklist.md").read_text(encoding="utf-8")
        runbook = (ROOT / "docs" / "demo_runbook.md").read_text(encoding="utf-8")
        self.assertIn("scenario flood", runbook)
        self.assertIn("scenario response", runbook)
        self.assertIn("timestamp envelope", runbook)
        self.assertIn("email_notification_setup.md", readme)
        self.assertIn("smtp.gmail.com", readme)
        self.assertIn("RESPONSE REQUIRED", readme)
        self.assertIn("Intervention response loop", (TB / "operational_states.md").read_text(encoding="utf-8"))
        email_doc = (TB / "email_notification_setup.md").read_text(encoding="utf-8")
        self.assertIn("smtp.gmail.com", email_doc)
        self.assertIn("Gross Contamination", email_doc)
        self.assertIn("pH Out of Range", email_doc)
        self.assertIn("High TDS", email_doc)
        self.assertIn("app password", email_doc)
        self.assertNotIn("GMAIL_APP_PASSWORD=", email_doc)
        self.assertIn("light", readme.lower())
        self.assertIn("rebased from the", readme.lower())
        self.assertIn("not clickable", readme.lower())
        self.assertIn("Needs attention", build_sheet)
        self.assertNotIn("Priority water points", build_sheet)
        self.assertNotIn(
            "Priority water points",
            (TB / "dashboard_floodsafe.json").read_text(encoding="utf-8"),
        )
        self.assertIn("Node Metadata & Location", build_sheet)
        self.assertIn("local", checklist.lower())
        self.assertIn("light theme", checklist.lower())
        self.assertIn("compact", checklist.lower())


if __name__ == "__main__":
    unittest.main()
