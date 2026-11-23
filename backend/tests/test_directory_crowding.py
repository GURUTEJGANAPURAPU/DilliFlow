from contextlib import contextmanager
import sqlite3

from app.services import transit


def directory_crowding_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
      CREATE TABLE routes (route_id TEXT PRIMARY KEY, route_short_name TEXT, route_long_name TEXT);
      CREATE TABLE stops (stop_id TEXT PRIMARY KEY, stop_code TEXT, stop_name TEXT, stop_lat REAL, stop_lon REAL);
      CREATE TABLE route_stop_order (route_id TEXT, stop_sequence INTEGER, stop_id TEXT);
      CREATE TABLE ticket_route_hourly (
        route_id TEXT, service_date TEXT, hour INTEGER, day_type TEXT,
        passenger_journeys REAL, ticket_count INTEGER, vehicle_known_count INTEGER
      );
      CREATE TABLE ticket_segment_hourly (
        route_id TEXT, service_date TEXT, hour INTEGER, day_type TEXT,
        from_stop_id TEXT, to_stop_id TEXT, passenger_journeys REAL,
        ticket_count INTEGER, vehicle_known_count INTEGER
      );
    """)
    conn.execute("INSERT INTO routes VALUES ('R1','19UP','Test route')")
    conn.executemany("INSERT INTO stops VALUES (?,?,?,?,?)", [
        ('A', 'A1', 'Origin Stop', 28.60, 77.20),
        ('B', 'B1', 'Middle Stop', 28.61, 77.21),
        ('C', 'C1', 'Destination Stop', 28.62, 77.22),
    ])
    conn.executemany("INSERT INTO route_stop_order VALUES (?,?,?)", [
        ('R1', 1, 'A'), ('R1', 2, 'B'), ('R1', 3, 'C'),
    ])
    conn.commit()
    return conn


def patch_database(monkeypatch, conn):
    @contextmanager
    def fake_database():
        yield conn
    monkeypatch.setattr(transit, "database", fake_database)


def test_crowding_segments_follow_gtfs_stop_order_and_include_insufficient_pairs(monkeypatch):
    conn = directory_crowding_db()
    try:
        patch_database(monkeypatch, conn)
        result = transit.crowding_segments("R1", hour=8, day_type="weekday")
        assert [(x["from_stop_id"], x["to_stop_id"]) for x in result["items"]] == [
            ("A", "B"), ("B", "C")
        ]
        assert all(x["crowding"]["seat_capacity"] == 35 for x in result["items"])
        assert all(x["crowding"]["standing_capacity"] == 25 for x in result["items"])
        assert all(x["crowding"]["availability_basis"] == "capacity_only_fallback" for x in result["items"])
        assert all(x["crowding"]["confidence"] == "low" for x in result["items"])
    finally:
        conn.close()


def test_stop_crowding_details_returns_served_routes_and_adjacent_segments(monkeypatch):
    conn = directory_crowding_db()
    try:
        patch_database(monkeypatch, conn)
        result = transit.stop_crowding_details("B")
        assert result is not None
        assert result["stop"]["stop_name"] == "Middle Stop"
        assert result["routes_count"] == 1
        route = result["routes"][0]
        assert route["route_id"] == "R1"
        assert route["previous_segment"]["from_stop_id"] == "A"
        assert route["previous_segment"]["to_stop_id"] == "B"
        assert route["next_segment"]["from_stop_id"] == "B"
        assert route["next_segment"]["to_stop_id"] == "C"
    finally:
        conn.close()


def test_stop_crowding_details_returns_none_for_unknown_stop(monkeypatch):
    conn = directory_crowding_db()
    try:
        patch_database(monkeypatch, conn)
        assert transit.stop_crowding_details("UNKNOWN") is None
    finally:
        conn.close()


def test_route_crowding_does_not_calculate_per_bus_from_all_hours_fallback(monkeypatch):
    conn = directory_crowding_db()
    try:
        conn.executemany("INSERT INTO ticket_route_hourly VALUES (?,?,?,?,?,?,?)", [
            ('R1', '2026-10-05', 7, 'weekday', 30, 10, 5),
            ('R1', '2026-10-05', 8, 'weekday', 45, 15, 7),
        ])
        monkeypatch.setattr(transit, 'scheduled_departures_for_hour', lambda *args, **kwargs: 3)
        result = transit.crowding_for_route(conn, 'R1', 22, 'weekend')
        assert result['used_fallback'] == 'all_available_route_hours'
        assert result['estimated_ticketed_passengers_per_bus'] is None
        assert result['scheduled_departures_in_hour'] == 0
        assert result['availability_basis'] == 'capacity_only_fallback'
        assert result['total_capacity'] == 60
    finally:
        conn.close()


def test_segment_crowding_does_not_calculate_per_bus_from_all_hours_fallback(monkeypatch):
    conn = directory_crowding_db()
    try:
        conn.executemany("INSERT INTO ticket_segment_hourly VALUES (?,?,?,?,?,?,?,?,?)", [
            ('R1', '2026-10-05', 7, 'weekday', 'A', 'B', 20, 8, 4),
            ('R1', '2026-10-05', 8, 'weekday', 'A', 'B', 35, 12, 6),
        ])
        monkeypatch.setattr(transit, 'scheduled_departures_for_hour', lambda *args, **kwargs: 3)
        result = transit.crowding_for_segment(conn, 'R1', 'A', 'B', 22, 'weekend')
        assert result['used_fallback'] == 'all_available_segment_hours'
        assert result['estimated_ticketed_passengers_per_bus'] is None
        assert result['scheduled_departures_in_hour'] == 0
        assert result['availability_basis'] == 'capacity_only_fallback'
        assert result['total_capacity'] == 60
    finally:
        conn.close()
