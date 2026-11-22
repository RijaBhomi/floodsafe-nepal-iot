"""SQLite local buffer for FloodSafe Nepal telemetry.

This is the "store" part of store-and-forward. Every reading is saved with
``sent = 0`` and stays in the database until a later stage successfully
transmits it and calls :func:`mark_as_sent`. There is no networking in this
module — MQTT and ThingsBoard come later.

Only Python's built-in ``sqlite3`` library is used.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

# Reuse the exact telemetry field list from the simulator so the database and
# the JSON output can never drift apart.
try:
    from .simulator import REQUIRED_FIELDS
except ImportError:  # pragma: no cover - only used when run as a plain script
    from simulator import REQUIRED_FIELDS

# Resolve paths from the project root so commands work from any folder.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "floodsafe.db"

# The table stores the 11 telemetry fields, then three management fields.
# UNIQUE (ts, node_id) means one node cannot produce two rows with the same
# acquisition timestamp, which prevents accidental duplicate inserts.
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS sensor_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    node_id TEXT NOT NULL,
    water_point TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    ph REAL NOT NULL,
    turbidity_ntu REAL NOT NULL,
    tds_ppm INTEGER NOT NULL,
    water_temp_c REAL NOT NULL,
    flow_lpm REAL NOT NULL,
    scenario TEXT NOT NULL,
    sent INTEGER NOT NULL DEFAULT 0,
    sent_at INTEGER,
    UNIQUE (ts, node_id)
)
"""

# This index makes "find all rows where sent = 0" fast, even with many rows.
# ts is included because pending rows are returned in timestamp order.
CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_sensor_readings_sent_ts
ON sensor_readings (sent, ts)
"""

INSERT_SQL = """
INSERT OR IGNORE INTO sensor_readings
    (ts, node_id, water_point, latitude, longitude,
     ph, turbidity_ntu, tds_ppm, water_temp_c, flow_lpm, scenario)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def initialize_database(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Create the data folder, database file, table and index; return a connection.

    The caller owns the connection and should close it when finished, for
    example with ``connection.close()``.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path)
    # sqlite3.Row lets us read columns by name (row["ts"]), like a dictionary.
    connection.row_factory = sqlite3.Row

    with connection:  # commits the CREATE statements, or rolls back on error
        connection.execute(CREATE_TABLE_SQL)
        connection.execute(CREATE_INDEX_SQL)
    return connection


def _values_from(reading: Mapping[str, Any]) -> tuple[Any, ...]:
    """Return the 11 telemetry values in the table's column order.

    The strict check is deliberate: database-only fields such as ``sent`` must
    never leak into the simulator's telemetry output.
    """
    missing = set(REQUIRED_FIELDS) - set(reading)
    extra = set(reading) - set(REQUIRED_FIELDS)
    if missing or extra:
        raise ValueError(
            "Reading must contain exactly the 11 telemetry fields. "
            f"Missing: {sorted(missing)}; unexpected: {sorted(extra)}"
        )
    return tuple(reading[name] for name in REQUIRED_FIELDS)


def insert_reading(connection: sqlite3.Connection, reading: Mapping[str, Any]) -> int:
    """Insert one reading. Return 1 if inserted, or 0 if it was a duplicate."""
    with connection:
        cursor = connection.execute(INSERT_SQL, _values_from(reading))
    return cursor.rowcount


def insert_readings(
    connection: sqlite3.Connection, readings: Iterable[Mapping[str, Any]]
) -> int:
    """Insert many readings in one transaction. Return the number inserted.

    ``executemany`` is much faster than calling ``insert_reading`` in a loop.
    Duplicates are skipped silently because of INSERT OR IGNORE.
    """
    values = [_values_from(reading) for reading in readings]
    if not values:
        return 0
    with connection:
        cursor = connection.executemany(INSERT_SQL, values)
    return cursor.rowcount


def get_pending_readings(
    connection: sqlite3.Connection, limit: int | None = None
) -> list[sqlite3.Row]:
    """Return readings with sent = 0, oldest first.

    ``limit`` is optional and exists so a future replay stage can send rows in
    batches. With no limit, every pending row is returned.
    """
    sql = "SELECT * FROM sensor_readings WHERE sent = 0 ORDER BY ts ASC"
    parameters: tuple[Any, ...] = ()
    if limit is not None:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("limit must be a positive whole number")
        sql += " LIMIT ?"
        parameters = (limit,)
    return connection.execute(sql, parameters).fetchall()


def mark_as_sent(
    connection: sqlite3.Connection, reading_id: int, sent_at: int | None = None
) -> int:
    """Mark one row sent = 1 and record when. Return 1 if changed, else 0.

    Call this ONLY after a successful transmission. On failure, simply do not
    call it — the row stays in the pending queue with sent = 0.
    """
    if sent_at is None:
        sent_at = time.time_ns() // 1_000_000  # Unix milliseconds, like ts
    with connection:
        cursor = connection.execute(
            "UPDATE sensor_readings SET sent = 1, sent_at = ? "
            "WHERE id = ? AND sent = 0",
            (sent_at, reading_id),
        )
    return cursor.rowcount


def count_readings(connection: sqlite3.Connection) -> int:
    """Return the total number of stored rows (sent and unsent)."""
    return connection.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0]


def count_pending_readings(connection: sqlite3.Connection) -> int:
    """Return the number of rows still waiting to be sent."""
    return connection.execute(
        "SELECT COUNT(*) FROM sensor_readings WHERE sent = 0"
    ).fetchone()[0]
