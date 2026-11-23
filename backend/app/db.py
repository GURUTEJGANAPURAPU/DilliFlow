from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import settings

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS routes (
    route_id TEXT PRIMARY KEY,
    agency_id TEXT,
    route_long_name TEXT,
    route_short_name TEXT,
    route_desc TEXT,
    route_type TEXT
);
CREATE TABLE IF NOT EXISTS stops (
    stop_id TEXT PRIMARY KEY,
    stop_code TEXT,
    stop_name TEXT NOT NULL,
    stop_lat REAL,
    stop_lon REAL
);
CREATE TABLE IF NOT EXISTS trips (
    trip_id TEXT PRIMARY KEY,
    route_id TEXT NOT NULL,
    service_id TEXT,
    trip_headsign TEXT,
    trip_short_name TEXT,
    direction_id TEXT,
    block_id TEXT,
    shape_id TEXT,
    wheelchair_accessible TEXT,
    bikes_allowed TEXT
);
CREATE TABLE IF NOT EXISTS stop_times (
    trip_id TEXT NOT NULL,
    arrival_time TEXT,
    departure_time TEXT,
    stop_id TEXT NOT NULL,
    stop_sequence INTEGER NOT NULL,
    fare_stage TEXT,
    stop_dist REAL,
    PRIMARY KEY (trip_id, stop_sequence)
);
CREATE TABLE IF NOT EXISTS shapes (
    shape_id TEXT NOT NULL,
    shape_pt_lat REAL NOT NULL,
    shape_pt_lon REAL NOT NULL,
    shape_pt_sequence INTEGER NOT NULL,
    shape_dist_traveled REAL,
    PRIMARY KEY (shape_id, shape_pt_sequence)
);
CREATE TABLE IF NOT EXISTS calendar (
    service_id TEXT PRIMARY KEY,
    monday INTEGER, tuesday INTEGER, wednesday INTEGER, thursday INTEGER,
    friday INTEGER, saturday INTEGER, sunday INTEGER,
    start_date TEXT, end_date TEXT
);
CREATE TABLE IF NOT EXISTS route_stop_order (
    route_id TEXT NOT NULL,
    stop_sequence INTEGER NOT NULL,
    stop_id TEXT NOT NULL,
    PRIMARY KEY(route_id, stop_sequence)
);
CREATE TABLE IF NOT EXISTS ticket_route_hourly (
    route_id TEXT NOT NULL,
    service_date TEXT NOT NULL,
    hour INTEGER NOT NULL,
    day_type TEXT NOT NULL,
    passenger_journeys REAL NOT NULL DEFAULT 0,
    ticket_count INTEGER NOT NULL DEFAULT 0,
    vehicle_known_count INTEGER NOT NULL DEFAULT 0,
    ac_ticket_count INTEGER NOT NULL DEFAULT 0,
    fare_total REAL NOT NULL DEFAULT 0,
    PRIMARY KEY(route_id, service_date, hour)
);
CREATE TABLE IF NOT EXISTS ticket_od_hourly (
    route_id TEXT NOT NULL, service_date TEXT NOT NULL, hour INTEGER NOT NULL,
    day_type TEXT NOT NULL, start_stop_id TEXT NOT NULL, end_stop_id TEXT NOT NULL,
    passenger_journeys REAL NOT NULL DEFAULT 0, ticket_count INTEGER NOT NULL DEFAULT 0,
    vehicle_known_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(route_id, service_date, hour, start_stop_id, end_stop_id)
);
CREATE TABLE IF NOT EXISTS ticket_segment_hourly (
    route_id TEXT NOT NULL,
    service_date TEXT NOT NULL,
    hour INTEGER NOT NULL,
    day_type TEXT NOT NULL,
    from_stop_id TEXT NOT NULL,
    to_stop_id TEXT NOT NULL,
    passenger_journeys REAL NOT NULL DEFAULT 0,
    ticket_count INTEGER NOT NULL DEFAULT 0,
    vehicle_known_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(route_id, service_date, hour, from_stop_id, to_stop_id)
);
CREATE TABLE IF NOT EXISTS ingestion_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS operator_route_capacity (
    route_id TEXT PRIMARY KEY,
    seat_capacity INTEGER NOT NULL CHECK(seat_capacity > 0),
    standing_capacity INTEGER NOT NULL CHECK(standing_capacity >= 0),
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL DEFAULT 'operator'
);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or settings.database_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=60000")
    return conn


@contextmanager
def database(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


def initialize_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def ensure_runtime_schema() -> None:
    """Create application-owned tables without rebuilding the GTFS/ticket database."""
    with database() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS operator_route_capacity (
                route_id TEXT PRIMARY KEY,
                seat_capacity INTEGER NOT NULL CHECK(seat_capacity > 0),
                standing_capacity INTEGER NOT NULL CHECK(standing_capacity >= 0),
                updated_at TEXT NOT NULL,
                updated_by TEXT NOT NULL DEFAULT 'operator'
            )"""
        )
        conn.commit()
