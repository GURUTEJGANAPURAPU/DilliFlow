import sqlite3

from app.services import transit


def _network_db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE calendar (
            service_id TEXT, monday INTEGER, tuesday INTEGER, wednesday INTEGER,
            thursday INTEGER, friday INTEGER, saturday INTEGER, sunday INTEGER,
            start_date TEXT, end_date TEXT
        );
        CREATE TABLE trips (route_id TEXT, trip_id TEXT, service_id TEXT);
        CREATE TABLE stop_times (trip_id TEXT, stop_sequence INTEGER, departure_time TEXT);
        CREATE TABLE ticket_route_hourly (
            route_id TEXT, service_date TEXT, hour INTEGER, day_type TEXT,
            passenger_journeys REAL, ticket_count INTEGER, vehicle_known_count INTEGER
        );
    ''')
    conn.execute(
        "INSERT INTO calendar VALUES ('S1',1,1,1,1,1,1,1,'20261001','20261031')"
    )
    for route, trip in [('A','A1'),('A','A2'),('B','B1')]:
        conn.execute('INSERT INTO trips VALUES (?,?,?)', (route, trip, 'S1'))
        conn.execute('INSERT INTO stop_times VALUES (?,?,?)', (trip, 1, '08:10:00'))
    for route, values in [('A',[10,20]),('B',[40,50])]:
        for index, value in enumerate(values):
            conn.execute(
                'INSERT INTO ticket_route_hourly VALUES (?,?,?,?,?,?,?)',
                (route, f'2026-10-{5+index:02d}', 8, 'weekday', value, 10, 5),
            )
    conn.commit()
    return conn


def test_planning_baseline_is_explicit_and_available_places_are_calculated():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    baseline = transit._capacity_for_route(conn, 'route-without-profile')
    assert baseline['seat_capacity'] == 35
    assert baseline['standing_capacity'] == 25
    assert baseline['capacity_configured'] is False
    assert baseline['capacity_source'] == 'dilliflow_planning_baseline'

    snapshot = transit._capacity_availability_fields(12.2, baseline, 'route_ticket_history')
    assert snapshot['estimated_occupied_seats'] == 13
    assert snapshot['estimated_available_seats'] == 22
    assert snapshot['estimated_occupied_standing_spaces'] == 0
    assert snapshot['estimated_available_standing_spaces'] == 25
    assert snapshot['availability_is_estimate'] is True


def test_capacity_only_fallback_does_not_claim_observed_vacancy():
    capacity = {
        'seat_capacity': 35,
        'standing_capacity': 25,
        'capacity_configured': False,
        'capacity_source': 'dilliflow_planning_baseline',
    }
    snapshot = transit._capacity_availability_fields(None, capacity, 'capacity_only_fallback')
    assert snapshot['estimated_available_seats'] == 35
    assert snapshot['estimated_available_standing_spaces'] == 25
    assert snapshot['availability_basis'] == 'capacity_only_fallback'
    assert snapshot['estimated_occupied_seats'] is None


def test_network_fallback_uses_ticketed_journeys_per_scheduled_departure():
    conn = _network_db()
    transit._NETWORK_REFERENCE_CACHE.clear()
    estimate = transit._network_reference_per_bus(conn, 8, 'weekday')
    assert estimate['routes_in_reference'] == 2
    assert estimate['reference_hour'] == 8
    # Route A: median 15 / 2 departures = 7.5; route B: median 45 / 1 = 45.
    assert estimate['passengers_per_bus'] == 26.2
    conn.close()
