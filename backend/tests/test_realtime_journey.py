import sqlite3

from app.services.realtime_journey import _project_to_line
from app.services.transit import crowding_for_route, crowding_for_segment


def test_projects_vehicle_position_onto_route_shape():
    line = [(28.0, 77.0), (28.01, 77.0)]
    along, cross = _project_to_line((28.005, 77.0001), line)
    assert 500 <= along <= 610
    assert cross < 15


def _crowding_db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('''CREATE TABLE ticket_route_hourly (
        route_id TEXT, service_date TEXT, hour INTEGER, day_type TEXT,
        passenger_journeys REAL, ticket_count INTEGER, vehicle_known_count INTEGER
    )''')
    conn.execute('''CREATE TABLE ticket_segment_hourly (
        route_id TEXT, service_date TEXT, hour INTEGER, day_type TEXT,
        from_stop_id TEXT, to_stop_id TEXT, passenger_journeys REAL,
        ticket_count INTEGER, vehicle_known_count INTEGER
    )''')
    for day, demand in [(1, 10), (2, 15), (3, 80), (4, 90)]:
        conn.execute(
            'INSERT INTO ticket_route_hourly VALUES (?,?,?,?,?,?,?)',
            ('R1', f'2026-10-{day:02d}', 8, 'weekday', demand, 20, 10),
        )
        conn.execute(
            'INSERT INTO ticket_segment_hourly VALUES (?,?,?,?,?,?,?,?,?)',
            ('R1', f'2026-10-{day:02d}', 8, 'weekday', 'A', 'B', demand, 20, 10),
        )
    conn.commit()
    return conn


def test_route_crowding_uses_nearest_available_hour_with_low_confidence():
    conn = _crowding_db()
    try:
        result = crowding_for_route(conn, 'R1', 9, 'weekday')
        assert result['level'] in {'low', 'moderate', 'high'}
        assert result['used_fallback'] == 'nearest_available_hour'
        assert result['confidence'] == 'low'
        assert 'historical' in result['label'].lower()
    finally:
        conn.close()


def test_segment_crowding_uses_nearest_available_hour_with_low_confidence():
    conn = _crowding_db()
    try:
        result = crowding_for_segment(conn, 'R1', 'A', 'B', 9, 'weekday')
        assert result['level'] in {'low', 'moderate', 'high'}
        assert result['used_fallback'] == 'nearest_available_hour'
        assert result['confidence'] == 'low'
    finally:
        conn.close()


def test_route_progress_is_oriented_by_selected_stop_order():
    from app.services.realtime_journey import _orient_progress

    # Shape is stored north-to-south, but this trip runs from south to north.
    total = 1000.0
    origin_raw = 900.0
    destination_raw = 100.0
    vehicle_raw = 990.0  # just south of the origin in the stored shape direction

    vehicle_progress, origin_progress, destination_progress, forward = _orient_progress(
        vehicle_raw, total, origin_raw, destination_raw
    )

    assert forward is False
    assert origin_progress < destination_progress
    assert vehicle_progress < origin_progress
    assert origin_progress - vehicle_progress == 90.0


def test_live_eta_never_rounds_a_nearby_bus_to_zero_without_stop_confirmation():
    from app.services.realtime_journey import _eta_minutes

    assert _eta_minutes(20.0, 8.0, at_stop=False) is None
    assert _eta_minutes(80.0, 10.0, at_stop=False) == 1
    assert _eta_minutes(0.0, None, at_stop=True) == 0
    assert _eta_minutes(0.0, 8.0, at_stop=False) is None


def test_live_eta_requires_a_real_live_speed_not_a_scheduled_average():
    from app.services.realtime_journey import _live_speed

    speed, source = _live_speed({"speed_mps": None, "speed_estimate_mps": None})
    assert speed is None
    assert source == "unavailable"

    speed, source = _live_speed({"speed_estimate_mps": 7.5, "speed_source": "derived_from_recent_positions"})
    assert speed == 7.5
    assert source == "derived_from_recent_positions"


def test_route_progress_context_identifies_last_and_next_stop():
    from app.services.realtime_journey import _route_progress_context

    stops = [
        ({"stop_id": "A", "stop_name": "Origin", "stop_sequence": 1}, 0.0, 0.0),
        ({"stop_id": "B", "stop_name": "Middle", "stop_sequence": 2}, 100.0, 0.0),
        ({"stop_id": "C", "stop_name": "Destination", "stop_sequence": 3}, 200.0, 0.0),
    ]
    result = _route_progress_context(stops, 60.0, 0.0, 200.0)

    assert result["progress_percent"] == 30.0
    assert result["last_passed_stop_id"] == "A"
    assert result["next_stop_id"] == "B"
    assert result["distance_to_next_stop_m"] == 40
    assert result["progress_source"] == "gps_shape_projection"


def test_route_progress_context_prefers_feed_stop_id_for_current_stop():
    from app.services.realtime_journey import _route_progress_context

    stops = [
        ({"stop_id": "A", "stop_name": "Origin", "stop_sequence": 1}, 0.0, 0.0),
        ({"stop_id": "B", "stop_name": "Middle", "stop_sequence": 2}, 100.0, 0.0),
        ({"stop_id": "C", "stop_name": "Destination", "stop_sequence": 3}, 200.0, 0.0),
    ]
    result = _route_progress_context(stops, 95.0, 0.0, 200.0, current_stop_id="B")

    assert result["current_stop_id"] == "B"
    assert result["current_stop_name"] == "Middle"
    assert result["next_stop_id"] == "C"
    assert result["progress_source"] == "gtfs_stop_id"
