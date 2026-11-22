"""Tests for the MQTT client and synchronization manager.

Everything here uses fakes/mocks: no real ThingsBoard broker or token is
needed, and the real data/floodsafe.db is never touched.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import MagicMock, patch

import paho.mqtt as paho
import paho.mqtt.client as mqtt

from src import main as app
from src import mqtt_client, sync_manager
from src.database import (
    count_pending_readings,
    count_readings,
    get_pending_readings,
    initialize_database,
    insert_readings,
    mark_as_sent,
)
from src.simulator import REQUIRED_FIELDS


def sample_reading(ts: int = 1790000000000, node_id: str = "FSN-01") -> dict:
    """One valid 11-field telemetry reading, ready for SQLite."""
    return {
        "ts": ts,
        "node_id": node_id,
        "water_point": "Reservoir Outlet",
        "latitude": 27.745,
        "longitude": 85.4167,
        "ph": 7.12,
        "turbidity_ntu": 4.8,
        "tds_ppm": 185,
        "water_temp_c": 21.4,
        "flow_lpm": 12.6,
        "scenario": "normal",
    }


def reading_with_db_fields() -> dict:
    """A row as SQLite returns it, with extra fields that must never be sent."""
    return dict(sample_reading(), id=1, sent=0, sent_at=None)


class FakePublishInfo:
    """Minimal stand-in for Paho's MQTTMessageInfo."""

    def __init__(self, rc: int = mqtt.MQTT_ERR_SUCCESS, published: bool = True) -> None:
        self.rc = rc
        self.published = published
        self.wait_timeout: int | None = None

    def wait_for_publish(self, timeout: int | None = None) -> None:
        self.wait_timeout = timeout

    def is_published(self) -> bool:
        return self.published


class FakeClient:
    """Minimal stand-in for a connected Paho client."""

    def __init__(self, info: FakePublishInfo) -> None:
        self.info = info
        self.calls: list[tuple[str, str, int]] = []

    def publish(self, topic: str, payload: str, qos: int = 0) -> FakePublishInfo:
        self.calls.append((topic, payload, qos))
        return self.info


class FailingConnectClient:
    """Paho-like client whose connect() raises a chosen error."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def connect(self, host: str, port: int, keepalive: int) -> None:
        raise self.error


class FailingPublishClient:
    """Paho-like client whose publish() raises a chosen error."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def publish(self, topic: str, payload: str, qos: int = 0) -> None:
        raise self.error


class MqttClientTests(unittest.TestCase):
    def test_payload_contains_only_the_11_telemetry_fields(self) -> None:
        payload = mqtt_client.telemetry_payload(reading_with_db_fields())
        self.assertEqual(set(payload), set(REQUIRED_FIELDS))
        for name in ("id", "sent", "sent_at"):
            self.assertNotIn(name, payload)

    def test_publish_uses_exact_topic_qos1_and_json(self) -> None:
        info = FakePublishInfo(published=True)
        client = FakeClient(info)
        self.assertTrue(mqtt_client.publish_reading(client, reading_with_db_fields()))

        topic, payload, qos = client.calls[0]
        self.assertEqual(topic, "v1/devices/me/telemetry")
        self.assertEqual(qos, 1)
        self.assertEqual(info.wait_timeout, mqtt_client.PUBLISH_TIMEOUT_SECONDS)
        parsed = json.loads(payload)
        self.assertEqual(set(parsed), set(REQUIRED_FIELDS))
        self.assertEqual(parsed["ts"], 1790000000000)

    def test_publish_returns_false_without_delivery_confirmation(self) -> None:
        client = FakeClient(FakePublishInfo(published=False))
        self.assertFalse(mqtt_client.publish_reading(client, sample_reading()))

    def test_publish_returns_false_when_broker_rejects_it(self) -> None:
        client = FakeClient(FakePublishInfo(rc=1, published=False))
        self.assertFalse(mqtt_client.publish_reading(client, sample_reading()))

    def test_settings_are_read_from_environment(self) -> None:
        with patch.object(mqtt_client, "load_local_env"), patch.dict(
            os.environ,
            {"THINGSBOARD_HOST": "demo.example.com", "THINGSBOARD_TOKEN": "tkn"},
            clear=True,
        ):
            self.assertEqual(
                mqtt_client.read_settings(), ("demo.example.com", "tkn")
            )

    def test_missing_settings_raise_a_clear_error_without_the_token(self) -> None:
        with patch.object(mqtt_client, "load_local_env"), patch.dict(
            os.environ, {}, clear=True
        ):
            with self.assertRaises(mqtt_client.MQTTConfigError):
                mqtt_client.read_settings()

    def test_node_settings_are_read_from_environment(self) -> None:
        env = {
            "THINGSBOARD_HOST": "demo.example.com",
            "FSN_01_TOKEN": "token-one",
            "FSN_02_TOKEN": "token-two",
            "FSN_03_TOKEN": "token-three",
        }
        with patch.object(mqtt_client, "load_local_env"), patch.dict(
            os.environ, env, clear=True
        ):
            host, tokens = mqtt_client.read_node_settings()
        self.assertEqual(host, "demo.example.com")
        self.assertEqual(
            tokens,
            {
                "FSN-01": "token-one",
                "FSN-02": "token-two",
                "FSN-03": "token-three",
            },
        )

    def test_missing_node_tokens_raise_a_clear_error(self) -> None:
        with patch.object(mqtt_client, "load_local_env"), patch.dict(
            os.environ, {"THINGSBOARD_HOST": "demo.example.com"}, clear=True
        ):
            with self.assertRaises(mqtt_client.MQTTConfigError) as caught:
                mqtt_client.read_node_settings()
        message = str(caught.exception)
        for name in ("FSN_01_TOKEN", "FSN_02_TOKEN", "FSN_03_TOKEN"):
            self.assertIn(name, message)

    def test_has_node_tokens_detects_configuration(self) -> None:
        with patch.object(mqtt_client, "load_local_env"), patch.dict(
            os.environ, {"FSN_02_TOKEN": "token-two"}, clear=True
        ):
            self.assertTrue(mqtt_client.has_node_tokens())
        with patch.object(mqtt_client, "load_local_env"), patch.dict(
            os.environ, {}, clear=True
        ):
            self.assertFalse(mqtt_client.has_node_tokens())

    def test_placeholder_tokens_are_treated_as_missing(self) -> None:
        env = {
            "THINGSBOARD_HOST": "demo.example.com",
            "FSN_01_TOKEN": "replace-with-fsn-01-reservoir-outlet-token",
        }
        with patch.object(mqtt_client, "load_local_env"), patch.dict(
            os.environ, env, clear=True
        ):
            self.assertFalse(mqtt_client.has_node_tokens())
            with self.assertRaises(mqtt_client.MQTTConfigError):
                mqtt_client.read_node_settings()

    def test_connect_timeout_becomes_friendly_error(self) -> None:
        # Regression: Paho 2.x puts MQTTException in paho.mqtt. An old handler
        # looked in paho.mqtt.client and crashed while handling this timeout.
        client = FailingConnectClient(TimeoutError("timed out"))
        with self.assertRaises(mqtt_client.MQTTError) as caught:
            mqtt_client.connect(client, "broker.example")
        self.assertIn("timed out", str(caught.exception))

    def test_connect_paho_exception_becomes_friendly_error(self) -> None:
        client = FailingConnectClient(paho.MQTTException("bad handshake"))
        with self.assertRaises(mqtt_client.MQTTError) as caught:
            mqtt_client.connect(client, "broker.example")
        self.assertIn("bad handshake", str(caught.exception))

    def test_publish_paho_exception_is_handled(self) -> None:
        client = FailingPublishClient(paho.MQTTException("connection lost"))
        self.assertFalse(mqtt_client.publish_reading(client, sample_reading()))


class SyncManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.connection = initialize_database(Path(self.temp_dir.name) / "sync_test.db")
        self.addCleanup(self.connection.close)

    def test_successful_publish_marks_reading_sent(self) -> None:
        insert_readings(self.connection, [sample_reading()])
        publisher = MagicMock(return_value=True)

        stats = sync_manager.sync_pending_readings(
            self.connection, client=object(), publish_fn=publisher
        )

        self.assertEqual(stats["sent"], 1)
        row = self.connection.execute("SELECT * FROM sensor_readings").fetchone()
        self.assertEqual(row["sent"], 1)
        self.assertIsNotNone(row["sent_at"])
        self.assertEqual(count_pending_readings(self.connection), 0)
        # The publisher received a reading without database-only fields.
        published = publisher.call_args.args[1]
        self.assertEqual(set(published.keys()), set(REQUIRED_FIELDS))

    def test_failed_publish_leaves_reading_pending(self) -> None:
        insert_readings(self.connection, [sample_reading()])
        publisher = MagicMock(return_value=False)

        stats = sync_manager.sync_pending_readings(
            self.connection, client=object(), publish_fn=publisher
        )

        self.assertEqual(stats["failed"], 1)
        self.assertEqual(stats["sent"], 0)
        row = self.connection.execute("SELECT * FROM sensor_readings").fetchone()
        self.assertEqual(row["sent"], 0)
        self.assertIsNone(row["sent_at"])
        self.assertEqual(count_pending_readings(self.connection), 1)

    def test_connection_failure_does_not_lose_queued_readings(self) -> None:
        insert_readings(
            self.connection,
            [sample_reading(ts=1000), sample_reading(ts=2000, node_id="FSN-02")],
        )
        with patch.object(
            mqtt_client, "read_settings", return_value=("broker.example", "fake-token")
        ), patch.object(mqtt_client, "build_client", return_value=object()), patch.object(
            mqtt_client, "connect", side_effect=mqtt_client.MQTTError("broker offline")
        ), patch.object(mqtt_client, "disconnect") as fake_disconnect:
            with self.assertRaises(mqtt_client.MQTTError):
                sync_manager.sync_from_environment(self.connection)

        fake_disconnect.assert_called_once()
        self.assertEqual(count_readings(self.connection), 2)
        self.assertEqual(count_pending_readings(self.connection), 2)

    def test_failed_reading_is_retried_on_a_later_run(self) -> None:
        insert_readings(self.connection, [sample_reading()])
        sync_manager.sync_pending_readings(
            self.connection, client=object(), publish_fn=MagicMock(return_value=False)
        )
        self.assertEqual(count_pending_readings(self.connection), 1)

        stats = sync_manager.sync_pending_readings(
            self.connection, client=object(), publish_fn=MagicMock(return_value=True)
        )
        self.assertEqual(stats["sent"], 1)
        self.assertEqual(count_pending_readings(self.connection), 0)

    def test_sync_stops_after_a_failure_and_keeps_later_rows(self) -> None:
        insert_readings(
            self.connection,
            [
                sample_reading(ts=1000),
                sample_reading(ts=2000, node_id="FSN-02"),
                sample_reading(ts=3000, node_id="FSN-03"),
            ],
        )
        publisher = MagicMock(side_effect=[False, True, True])
        stats = sync_manager.sync_pending_readings(
            self.connection, client=object(), publish_fn=publisher
        )
        self.assertEqual(stats["sent"], 0)
        self.assertEqual(publisher.call_count, 1)
        self.assertEqual(count_pending_readings(self.connection), 3)

    def test_pending_readings_are_published_in_timestamp_order(self) -> None:
        insert_readings(
            self.connection,
            [
                sample_reading(ts=3000, node_id="FSN-03"),
                sample_reading(ts=1000, node_id="FSN-01"),
                sample_reading(ts=2000, node_id="FSN-02"),
            ],
        )
        publisher = MagicMock(return_value=True)
        sync_manager.sync_pending_readings(
            self.connection, client=object(), publish_fn=publisher
        )
        self.assertEqual(
            [call.args[1]["ts"] for call in publisher.call_args_list],
            [1000, 2000, 3000],
        )
        self.assertEqual(len(get_pending_readings(self.connection)), 0)


class PerNodeSyncTests(unittest.TestCase):
    """Per-device routing tests. Still 100% mock-based, no real broker."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.connection = initialize_database(Path(self.temp_dir.name) / "per_node.db")
        self.addCleanup(self.connection.close)

    def test_each_node_uses_its_own_token_and_unique_client_id(self) -> None:
        insert_readings(
            self.connection,
            [
                sample_reading(ts=1000, node_id="FSN-01"),
                sample_reading(ts=2000, node_id="FSN-02"),
                sample_reading(ts=3000, node_id="FSN-03"),
            ],
        )
        tokens = {
            "FSN-01": "token-one",
            "FSN-02": "token-two",
            "FSN-03": "token-three",
        }
        built: dict[str, object] = {}
        client_ids: list[str] = []

        def fake_build(token: str, client_id: str = "") -> object:
            client = object()
            built[token] = client
            client_ids.append(client_id)
            return client

        publisher = MagicMock(return_value=True)
        with patch.object(
            mqtt_client, "read_node_settings", return_value=("broker.example", tokens)
        ), patch.object(mqtt_client, "build_client", side_effect=fake_build), patch.object(
            mqtt_client, "connect"
        ), patch.object(mqtt_client, "disconnect"):
            stats = sync_manager.sync_from_environment_by_node(
                self.connection, publish_fn=publisher
            )

        self.assertEqual(stats["sent"], 3)
        self.assertEqual(count_pending_readings(self.connection), 0)
        self.assertEqual(set(built), set(tokens.values()))
        self.assertEqual(
            sorted(client_ids),
            sorted(f"{mqtt_client.CLIENT_ID}-{node.lower()}" for node in tokens),
        )
        for call in publisher.call_args_list:
            client, payload = call.args
            self.assertIs(client, built[tokens[payload["node_id"]]])
            self.assertEqual(set(payload), set(REQUIRED_FIELDS))

    def test_missing_token_leaves_only_that_nodes_readings_pending(self) -> None:
        insert_readings(
            self.connection,
            [
                sample_reading(ts=1000, node_id="FSN-01"),
                sample_reading(ts=2000, node_id="FSN-02"),
            ],
        )
        tokens = {"FSN-02": "token-two"}
        publisher = MagicMock(return_value=True)
        stderr = io.StringIO()

        with patch.object(
            mqtt_client, "read_node_settings", return_value=("broker.example", tokens)
        ), patch.object(mqtt_client, "build_client", return_value=object()), patch.object(
            mqtt_client, "connect"
        ), patch.object(mqtt_client, "disconnect"), redirect_stderr(stderr):
            stats = sync_manager.sync_from_environment_by_node(
                self.connection, publish_fn=publisher
            )

        self.assertEqual(stats["sent"], 1)
        self.assertEqual(count_pending_readings(self.connection), 1)
        rows = {
            row["node_id"]: row
            for row in self.connection.execute("SELECT * FROM sensor_readings")
        }
        self.assertEqual(rows["FSN-01"]["sent"], 0)
        self.assertEqual(rows["FSN-02"]["sent"], 1)
        self.assertEqual(publisher.call_count, 1)
        self.assertEqual(publisher.call_args.args[1]["node_id"], "FSN-02")

        message = stderr.getvalue()
        self.assertIn("FSN-01", message)
        self.assertIn("FSN_01_TOKEN", message)
        self.assertNotIn("token-two", message)  # never reveal a token

    def test_successful_delivery_marks_only_the_confirmed_reading_sent(self) -> None:
        insert_readings(
            self.connection,
            [
                sample_reading(ts=1000, node_id="FSN-02"),
                sample_reading(ts=2000, node_id="FSN-01"),
                sample_reading(ts=3000, node_id="FSN-03"),
            ],
        )
        clients = {node: object() for node in ("FSN-01", "FSN-02", "FSN-03")}
        publisher = MagicMock(side_effect=[True, False])

        stats = sync_manager.sync_pending_readings_by_node(
            self.connection, clients, publish_fn=publisher
        )

        self.assertEqual(stats["sent"], 1)
        self.assertEqual(stats["failed"], 1)
        rows = {
            row["node_id"]: row
            for row in self.connection.execute("SELECT * FROM sensor_readings")
        }
        self.assertEqual(rows["FSN-02"]["sent"], 1)
        self.assertEqual(rows["FSN-01"]["sent"], 0)
        self.assertEqual(rows["FSN-03"]["sent"], 0)
        self.assertEqual(count_pending_readings(self.connection), 2)

    def test_failed_delivery_leaves_reading_pending(self) -> None:
        insert_readings(self.connection, [sample_reading(node_id="FSN-03")])
        clients = {"FSN-03": object()}

        stats = sync_manager.sync_pending_readings_by_node(
            self.connection, clients, publish_fn=MagicMock(return_value=False)
        )

        self.assertEqual(stats["failed"], 1)
        self.assertEqual(count_pending_readings(self.connection), 1)

    def test_already_sent_rows_are_not_touched(self) -> None:
        insert_readings(self.connection, [sample_reading(node_id="FSN-01")])
        row_id = self.connection.execute("SELECT id FROM sensor_readings").fetchone()["id"]
        mark_as_sent(self.connection, row_id)
        select = "SELECT * FROM sensor_readings WHERE id = ?"
        before = dict(self.connection.execute(select, (row_id,)).fetchone())

        publisher = MagicMock(return_value=True)
        stats = sync_manager.sync_pending_readings_by_node(
            self.connection, {"FSN-01": object()}, publish_fn=publisher
        )
        after = dict(self.connection.execute(select, (row_id,)).fetchone())

        self.assertEqual(stats["pending"], 0)
        self.assertEqual(publisher.call_count, 0)
        self.assertEqual(before, after)


class CliRoutingTests(unittest.TestCase):
    """The CLI chooses per-node sync only when node tokens are configured."""

    def test_sync_uses_per_node_path_when_node_tokens_are_set(self) -> None:
        connection = MagicMock()
        with patch.object(app, "initialize_database", return_value=connection), patch.object(
            app, "has_node_tokens", return_value=True
        ), patch.object(
            app,
            "sync_from_environment_by_node",
            return_value={"pending": 0, "sent": 0, "failed": 0},
        ) as per_node, patch.object(app, "sync_from_environment") as legacy:
            code = app.main(["--sync"])

        self.assertEqual(code, 0)
        per_node.assert_called_once_with(connection)
        legacy.assert_not_called()

    def test_sync_falls_back_to_single_token_when_no_node_tokens(self) -> None:
        connection = MagicMock()
        with patch.object(app, "initialize_database", return_value=connection), patch.object(
            app, "has_node_tokens", return_value=False
        ), patch.object(
            app,
            "sync_from_environment",
            return_value={"pending": 0, "sent": 0, "failed": 0},
        ) as legacy, patch.object(app, "sync_from_environment_by_node") as per_node:
            code = app.main(["--sync"])

        self.assertEqual(code, 0)
        legacy.assert_called_once_with(connection)
        per_node.assert_not_called()


if __name__ == "__main__":
    unittest.main()
