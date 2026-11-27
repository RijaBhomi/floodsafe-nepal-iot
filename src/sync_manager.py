"""Sync pending SQLite readings to ThingsBoard through the MQTT client.

This is the "forward" half of store-and-forward. It reads only rows with
sent = 0, publishes them, and marks a row sent ONLY after MQTT confirms
delivery. Failed rows are left untouched so the next run can retry them.
"""

from __future__ import annotations

import sqlite3
import sys
from typing import Callable, Mapping

try:
    from . import mqtt_client
    from .database import count_pending_readings, get_pending_readings, mark_as_sent
except ImportError:  # pragma: no cover - only used when run as a plain script
    import mqtt_client
    from database import count_pending_readings, get_pending_readings, mark_as_sent


def _log(message: str) -> None:
    """Print a sync status message on stderr."""
    print(f"[SYNC] {message}", file=sys.stderr)


def sync_pending_readings(
    connection: sqlite3.Connection,
    client: object,
    *,
    publish_fn: Callable[[object, Mapping[str, object]], bool] | None = None,
    limit: int | None = None,
) -> dict[str, int]:
    """Publish pending rows in timestamp order and mark confirmed ones sent.

    ``publish_fn`` can be replaced in tests with a fake, so no real broker is
    needed. With a failed publish we stop this run and leave the row (and all
    later rows) pending for the next attempt.
    """
    if publish_fn is None:
        publish_fn = mqtt_client.publish_reading

    pending = get_pending_readings(connection, limit=limit)
    sent_count = 0
    failed_count = 0

    if not pending:
        _log("No pending readings to send.")
    else:
        _log(f"Found {len(pending)} pending reading(s).")

    for row in pending:
        # Hand the publisher a flat 11-field reading; publish_reading() applies
        # the timestamp envelope once, so replay keeps the original client ts.
        payload = mqtt_client.telemetry_values(row)
        try:
            delivered = publish_fn(client, payload)
        except Exception as exc:  # network errors vary by library and OS
            # Never include the token here: exceptions from Paho do not carry it.
            _log(f"Publish error for ts={row['ts']}: {exc}")
            delivered = False

        if delivered:
            # This is the ONLY place a row becomes sent = 1.
            mark_as_sent(connection, row["id"])
            sent_count += 1
            _log(f"Marked id={row['id']} ts={row['ts']} as sent.")
        else:
            failed_count += 1
            _log(f"Failed to send id={row['id']} ts={row['ts']}; left pending.")
            break  # do not hammer an unavailable broker

    _log(f"Finished: sent={sent_count}, failed={failed_count}, pending={count_pending_readings(connection)}")
    return {"pending": len(pending), "sent": sent_count, "failed": failed_count}


def sync_from_environment(
    connection: sqlite3.Connection,
    *,
    publish_fn: Callable[[object, Mapping[str, object]], bool] | None = None,
    limit: int | None = None,
) -> dict[str, int]:
    """Read settings, connect with TLS, sync once, then disconnect.

    If configuration or connection fails, the exception is passed to the CLI.
    No database row is changed in that case, so queued readings are safe.
    """
    host, token = mqtt_client.read_settings()
    client = mqtt_client.build_client(token)
    try:
        mqtt_client.connect(client, host)
        return sync_pending_readings(connection, client, publish_fn=publish_fn, limit=limit)
    finally:
        # Runs after success AND after a connection failure.
        mqtt_client.disconnect(client)


def sync_pending_readings_by_node(
    connection: sqlite3.Connection,
    clients: Mapping[str, object],
    *,
    publish_fn: Callable[[object, Mapping[str, object]], bool] | None = None,
    limit: int | None = None,
) -> dict[str, int]:
    """Publish pending rows using the MQTT client belonging to each node.

    ``clients`` maps ``node_id`` to an already-connected MQTT client. Rows for
    nodes without a token are skipped and stay pending; other nodes can still
    be sent. A real publish failure stops this run so the broker is not
    hammered. No row is ever deleted.
    """
    if publish_fn is None:
        publish_fn = mqtt_client.publish_reading

    pending = get_pending_readings(connection, limit=limit)
    sent_count = 0
    failed_count = 0
    missing_reported: set[str] = set()

    if not pending:
        _log("No pending readings to send.")
    else:
        _log(f"Found {len(pending)} pending reading(s) for per-node sync.")

    for row in pending:
        node_id = row["node_id"]
        client = clients.get(node_id)

        if client is None:
            if node_id not in missing_reported:
                env_name = mqtt_client.NODE_TOKEN_VARS.get(node_id, "a matching token")
                _log(f"No token configured for {node_id} ({env_name}); left pending.")
                missing_reported.add(node_id)
            failed_count += 1
            continue  # keep going so configured nodes still get their data

        # Hand the publisher a flat 11-field reading; publish_reading() applies
        # the timestamp envelope once, so replay keeps the original client ts.
        payload = mqtt_client.telemetry_values(row)
        try:
            delivered = publish_fn(client, payload)
        except Exception as exc:  # network errors vary by library and OS
            # Never include the token here: exceptions from Paho do not carry it.
            _log(f"Publish error for {node_id} ts={row['ts']}: {exc}")
            delivered = False

        if delivered:
            # This is the ONLY place a row becomes sent = 1.
            mark_as_sent(connection, row["id"])
            sent_count += 1
            _log(f"Marked id={row['id']} ts={row['ts']} ({node_id}) as sent.")
        else:
            failed_count += 1
            _log(
                f"Failed to send id={row['id']} ts={row['ts']} ({node_id}); "
                "left pending."
            )
            break  # do not hammer an unavailable broker

    _log(
        f"Finished: sent={sent_count}, failed={failed_count}, "
        f"pending={count_pending_readings(connection)}"
    )
    return {"pending": len(pending), "sent": sent_count, "failed": failed_count}


def sync_from_environment_by_node(
    connection: sqlite3.Connection,
    *,
    publish_fn: Callable[[object, Mapping[str, object]], bool] | None = None,
    limit: int | None = None,
) -> dict[str, int]:
    """Connect one TLS client per configured node, sync once, disconnect all.

    Each device gets its own MQTT client ID so the broker does not disconnect
    an earlier node when a new one connects. Already-sent rows are never read
    or changed because the database query only returns ``sent = 0``.
    """
    host, tokens = mqtt_client.read_node_settings()
    clients: dict[str, object] = {}
    try:
        for node_id, token in tokens.items():
            client_id = f"{mqtt_client.CLIENT_ID}-{node_id.lower()}"
            client = mqtt_client.build_client(token, client_id=client_id)
            try:
                mqtt_client.connect(client, host)
            except mqtt_client.MQTTError as exc:
                # The node ID is safe to log; the token is never included.
                raise mqtt_client.MQTTError(f"{node_id}: {exc}") from exc
            clients[node_id] = client

        return sync_pending_readings_by_node(
            connection, clients, publish_fn=publish_fn, limit=limit
        )
    finally:
        for client in clients.values():
            mqtt_client.disconnect(client)
