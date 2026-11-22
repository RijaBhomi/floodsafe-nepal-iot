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
        # Strip database-only fields before handing the reading to MQTT.
        payload = mqtt_client.telemetry_payload(row)
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
