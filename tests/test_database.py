"""Basic tests for the SQLite local buffer.

Run from the project root:
    python -m unittest discover -s tests -v

Every test uses a temporary database file, so the real data/floodsafe.db is
never touched.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.database import (
    count_pending_readings,
    count_readings,
    get_pending_readings,
    initialize_database,
    insert_reading,
    insert_readings,
    mark_as_sent,
)
from src.simulator import REQUIRED_FIELDS


def sample_reading(ts: int = 1790000000000, node_id: str = "FSN-01") -> dict:
    """Build one valid telemetry reading for the tests."""
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


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = Path(self.temp_dir.name) / "test_floodsafe.db"
        self.connection = initialize_database(self.db_path)
        self.addCleanup(self.connection.close)  # closes before temp dir cleanup

    def test_database_and_table_are_created(self) -> None:
        self.assertTrue(self.db_path.exists())
        names = {
            row[0]
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'index')"
            )
        }
        self.assertIn("sensor_readings", names)
        self.assertIn("idx_sensor_readings_sent_ts", names)
        # Calling initialize again must be harmless.
        again = initialize_database(self.db_path)
        again.close()

    def test_one_reading_can_be_inserted(self) -> None:
        self.assertEqual(insert_reading(self.connection, sample_reading()), 1)
        self.assertEqual(count_readings(self.connection), 1)

    def test_all_eleven_telemetry_fields_are_stored(self) -> None:
        reading = sample_reading()
        insert_reading(self.connection, reading)
        row = self.connection.execute("SELECT * FROM sensor_readings").fetchone()
        self.assertEqual(len(REQUIRED_FIELDS), 11)
        for field in REQUIRED_FIELDS:
            self.assertEqual(row[field], reading[field], field)

    def test_new_reading_is_unsent(self) -> None:
        insert_reading(self.connection, sample_reading())
        row = self.connection.execute("SELECT * FROM sensor_readings").fetchone()
        self.assertEqual(row["sent"], 0)
        self.assertIsNone(row["sent_at"])

    def test_pending_readings_can_be_retrieved(self) -> None:
        insert_readings(
            self.connection,
            [sample_reading(ts=1000), sample_reading(ts=2000, node_id="FSN-02")],
        )
        pending = get_pending_readings(self.connection)
        self.assertEqual([row["ts"] for row in pending], [1000, 2000])
        self.assertEqual(get_pending_readings(self.connection, limit=1)[0]["ts"], 1000)

    def test_reading_can_be_marked_as_sent(self) -> None:
        insert_reading(self.connection, sample_reading())
        row_id = self.connection.execute("SELECT id FROM sensor_readings").fetchone()[0]
        self.assertEqual(mark_as_sent(self.connection, row_id, sent_at=123456), 1)
        row = self.connection.execute("SELECT * FROM sensor_readings").fetchone()
        self.assertEqual(row["sent"], 1)
        self.assertEqual(row["sent_at"], 123456)
        # Marking the same row twice changes nothing.
        self.assertEqual(mark_as_sent(self.connection, row_id, sent_at=999999), 0)

    def test_marked_reading_is_not_in_pending_queue(self) -> None:
        insert_reading(self.connection, sample_reading())
        row_id = self.connection.execute("SELECT id FROM sensor_readings").fetchone()[0]
        mark_as_sent(self.connection, row_id)
        self.assertEqual(get_pending_readings(self.connection), [])
        self.assertEqual(count_pending_readings(self.connection), 0)
        self.assertEqual(count_readings(self.connection), 1)

    def test_multiple_readings_can_be_inserted(self) -> None:
        readings = [
            sample_reading(ts=1000 + index, node_id=f"FSN-0{(index % 3) + 1}")
            for index in range(3)
        ]
        self.assertEqual(insert_readings(self.connection, readings), 3)
        self.assertEqual(count_readings(self.connection), 3)
        self.assertEqual(count_pending_readings(self.connection), 3)

    def test_duplicate_reading_is_ignored(self) -> None:
        reading = sample_reading()
        self.assertEqual(insert_reading(self.connection, reading), 1)
        self.assertEqual(insert_reading(self.connection, reading), 0)
        self.assertEqual(insert_reading(self.connection, dict(reading)), 0)
        self.assertEqual(count_readings(self.connection), 1)

    def test_duplicates_in_a_batch_are_skipped(self) -> None:
        first = sample_reading(ts=1000)
        second = sample_reading(ts=2000, node_id="FSN-02")
        third = sample_reading(ts=3000, node_id="FSN-03")
        self.assertEqual(insert_readings(self.connection, [first, second]), 2)
        self.assertEqual(insert_readings(self.connection, [first, second, third]), 1)
        self.assertEqual(count_readings(self.connection), 3)

    def test_database_only_fields_cannot_enter_telemetry(self) -> None:
        reading = sample_reading()
        reading["sent"] = 1
        with self.assertRaises(ValueError):
            insert_reading(self.connection, reading)


if __name__ == "__main__":
    unittest.main()
