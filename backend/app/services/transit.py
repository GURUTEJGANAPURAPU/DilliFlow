from __future__ import annotations

import json
import math
import sqlite3
from datetime import date, datetime
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

from ..config import settings
from ..db import database


DAY_COLUMNS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def as_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def local_now() -> datetime:
    return datetime.now(ZoneInfo(settings.local_timezone))


def service_ids_for(conn: sqlite3.Connection, service_date: date) -> list[str]:
    day_col = DAY_COLUMNS[service_date.weekday()]
    date_text = service_date.strftime("%Y%m%d")
    rows = conn.execute(
        f"SELECT service_id FROM calendar WHERE {day_col}=1 AND start_date<=? AND end_date>=?",
        (date_text, date_text),
    ).fetchall()
    return [r[0] for r in rows]


def time_to_minutes(value: str | None) -> int | None:
    if not value:
        return None
    try:
        h, m, s = value.split(":")[:3]
        return int(h) * 60 + int(m) + int(s) / 60
    except Exception:
        return None


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * p
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    weight = index - low
    return ordered[low] * (1 - weight) + ordered[high] * weight



def scheduled_departures_for_hour(conn: sqlite3.Connection, route_id: str, hour: int, day_type: str, stop_id: str | None = None) -> int:
    """Count GTFS trips passing a route origin/segment start in the requested hour."""
    sample_date = date(2026, 10, 3) if day_type == "weekend" else date(2026, 10, 5)
    try:
        service_ids = service_ids_for(conn, sample_date)
    except sqlite3.OperationalError:
        service_ids = []
    if not service_ids:
        try:
            service_ids = [row[0] for row in conn.execute("SELECT DISTINCT service_id FROM trips WHERE service_id IS NOT NULL AND service_id<>''").fetchall()]
        except sqlite3.OperationalError:
            return 0
    if not service_ids:
        return 0
    placeholders = ",".join("?" for _ in service_ids)
    if stop_id:
        sql = f"""SELECT COUNT(DISTINCT t.trip_id) FROM trips t
            JOIN stop_times st ON st.trip_id=t.trip_id
            WHERE t.route_id=? AND t.service_id IN ({placeholders}) AND st.stop_id=?
            AND CAST(SUBSTR(st.departure_time,1,INSTR(st.departure_time,':')-1) AS INTEGER)=?"""
        params = [route_id, *service_ids, stop_id, hour]
    else:
        sql = f"""SELECT COUNT(DISTINCT t.trip_id) FROM trips t
            JOIN stop_times st ON st.trip_id=t.trip_id
            WHERE t.route_id=? AND t.service_id IN ({placeholders})
            AND st.stop_sequence=(SELECT MIN(st2.stop_sequence) FROM stop_times st2 WHERE st2.trip_id=t.trip_id)
            AND CAST(SUBSTR(st.departure_time,1,INSTR(st.departure_time,':')-1) AS INTEGER)=?"""
        params = [route_id, *service_ids, hour]
    return int(conn.execute(sql, params).fetchone()[0] or 0)


# DilliFlow's transparent fallback reference for routes without an operator-verified
# fleet profile. These are planning assumptions, NOT a claim about every Delhi bus model.
PLANNING_BASELINE_SEATS = 35
PLANNING_BASELINE_STANDING = 25
_NETWORK_REFERENCE_CACHE: dict[tuple[str, int, str], dict[str, Any]] = {}


def _capacity_for_route(conn: sqlite3.Connection, route_id: str) -> dict[str, Any]:
    try:
        row = conn.execute(
            "SELECT seat_capacity,standing_capacity FROM operator_route_capacity WHERE route_id=?",
            (route_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    if row:
        return {
            "seat_capacity": int(row[0]),
            "standing_capacity": int(row[1]),
            "capacity_configured": True,
            "capacity_source": "operator_verified",
        }
    return {
        "seat_capacity": PLANNING_BASELINE_SEATS,
        "standing_capacity": PLANNING_BASELINE_STANDING,
        "capacity_configured": False,
        "capacity_source": "dilliflow_planning_baseline",
    }


def _network_reference_per_bus(conn: sqlite3.Connection, hour: int, day_type: str) -> dict[str, Any]:
    """Median route-level ticketed demand per scheduled departure for a network fallback.

    This keeps every journey card populated without pretending an unmatched route had
    zero passengers. It is explicitly labelled as a network reference in the response.
    """
    try:
        database_file = str(conn.execute("PRAGMA database_list").fetchone()[2] or "")
    except sqlite3.Error:
        database_file = ""
    cache_key = (database_file, int(hour), str(day_type)) if database_file else None
    # In-memory SQLite connection IDs can be reused after a test closes a database;
    # do not cache those results because that could leak one fixture's demand into another.
    if cache_key is not None:
        cached = _NETWORK_REFERENCE_CACHE.get(cache_key)
        if cached is not None:
            return dict(cached)

    reference_hour = int(hour)
    ticket_rows = conn.execute(
        "SELECT route_id, passenger_journeys FROM ticket_route_hourly WHERE hour=? AND day_type=?",
        (reference_hour, day_type),
    ).fetchall()
    if not ticket_rows:
        nearest = conn.execute(
            "SELECT hour FROM ticket_route_hourly WHERE day_type=? GROUP BY hour ORDER BY ABS(hour-?) LIMIT 1",
            (day_type, reference_hour),
        ).fetchone()
        if nearest:
            reference_hour = int(nearest[0])
            ticket_rows = conn.execute(
                "SELECT route_id, passenger_journeys FROM ticket_route_hourly WHERE hour=? AND day_type=?",
                (reference_hour, day_type),
            ).fetchall()

    daily_by_route: dict[str, list[float]] = {}
    for row in ticket_rows:
        daily_by_route.setdefault(str(row["route_id"]), []).append(float(row["passenger_journeys"] or 0))

    sample_date = date(2026, 10, 3) if day_type == "weekend" else date(2026, 10, 5)
    try:
        service_ids = service_ids_for(conn, sample_date)
    except sqlite3.OperationalError:
        service_ids = []
    if not service_ids:
        try:
            service_ids = [str(r[0]) for r in conn.execute(
                "SELECT DISTINCT service_id FROM trips WHERE service_id IS NOT NULL AND service_id<>''"
            ).fetchall()]
        except sqlite3.OperationalError:
            service_ids = []

    departure_counts: dict[str, int] = {}
    if service_ids:
        placeholders = ",".join("?" for _ in service_ids)
        rows = conn.execute(
            f"""SELECT t.route_id,COUNT(DISTINCT t.trip_id) AS departures
                FROM trips t JOIN stop_times st ON st.trip_id=t.trip_id
                WHERE t.service_id IN ({placeholders})
                  AND st.stop_sequence=(SELECT MIN(st2.stop_sequence) FROM stop_times st2 WHERE st2.trip_id=t.trip_id)
                  AND CAST(SUBSTR(st.departure_time,1,INSTR(st.departure_time,':')-1) AS INTEGER)=?
                GROUP BY t.route_id""",
            (*service_ids, reference_hour),
        ).fetchall()
        departure_counts = {str(r["route_id"]): int(r["departures"] or 0) for r in rows}

    route_loads = []
    for route_id, daily_values in daily_by_route.items():
        departures = departure_counts.get(route_id, 0)
        if departures > 0 and daily_values:
            route_loads.append(median(daily_values) / departures)

    result = {
        "passengers_per_bus": round(median(route_loads), 1) if route_loads else None,
        "reference_hour": reference_hour,
        "routes_in_reference": len(route_loads),
        "basis": "network_median_ticketed_journeys_per_scheduled_departure",
    }
    if cache_key is not None:
        _NETWORK_REFERENCE_CACHE[cache_key] = dict(result)
    return result


def _capacity_availability_fields(load: float | None, capacity: dict[str, Any], basis: str) -> dict[str, Any]:
    seats = int(capacity["seat_capacity"])
    standing = int(capacity["standing_capacity"])
    if load is None:
        # Display the nominal capacity consistently, but explicitly tell the UI that
        # these are upper bounds rather than observed vacant places.
        available_seats = seats
        available_standing = standing
        occupied = None
        availability_basis = "capacity_only_fallback"
    else:
        occupied = max(0, math.ceil(float(load)))
        available_seats = max(0, seats - min(seats, occupied))
        standing_used = max(0, occupied - seats)
        available_standing = max(0, standing - min(standing, standing_used))
        availability_basis = basis
    return {
        "seat_capacity": seats,
        "standing_capacity": standing,
        "total_capacity": seats + standing,
        "capacity_configured": bool(capacity.get("capacity_configured")),
        "capacity_source": capacity.get("capacity_source", "dilliflow_planning_baseline"),
        "estimated_occupied_seats": min(seats, occupied) if occupied is not None else None,
        "estimated_available_seats": available_seats,
        "estimated_occupied_standing_spaces": max(0, occupied - seats) if occupied is not None else None,
        "estimated_available_standing_spaces": available_standing,
        "availability_basis": availability_basis,
        "availability_is_estimate": True,
    }


def _crowd_classification(relative_level: str, passengers_per_bus: float | None, capacity: dict[str, Any] | None) -> tuple[str, str, str | None]:
    # Seat/standing categorical claims are enabled only after an operator verifies
    # the route fleet profile. The default 35+25 planning baseline is a UI reference,
    # not evidence that a bus of that capacity is actually assigned to the route.
    if capacity and capacity.get("capacity_configured") and passengers_per_bus is not None:
        seats = capacity["seat_capacity"]
        total = seats + capacity["standing_capacity"]
        if passengers_per_bus <= seats:
            return "seats_available", "Seats likely available", "Ticket-demand proxy is within the displayed seating reference. This is not a live occupancy reading."
        if passengers_per_bus <= total:
            return "standing_room", "Standing room likely", "Ticket-demand proxy exceeds the seating reference but remains within total reference capacity."
        return "crowded", "Crowded (estimated)", "Ticket-demand proxy exceeds the displayed total capacity reference; validate before operational action."
    labels = {
        "low": "Less crowded (historical estimate)",
        "moderate": "Moderate crowd (historical estimate)",
        "high": "High crowd (historical estimate)",
    }
    return relative_level, labels.get(relative_level, "Typical network reference"), None


def crowding_for_route(conn: sqlite3.Connection, route_id: str, hour: int, day_type: str) -> dict[str, Any]:
    history = conn.execute(
        "SELECT service_date, hour, passenger_journeys, ticket_count, vehicle_known_count FROM ticket_route_hourly WHERE route_id=? AND hour=? AND day_type=? ORDER BY service_date",
        (route_id, hour, day_type),
    ).fetchall()
    fallback = None
    effective_hour = hour
    if not history:
        nearest = conn.execute(
            "SELECT hour FROM ticket_route_hourly WHERE route_id=? AND day_type=? GROUP BY hour ORDER BY ABS(hour-?) LIMIT 1",
            (route_id, day_type, hour),
        ).fetchone()
        if nearest:
            effective_hour = int(nearest[0])
            history = conn.execute(
                "SELECT service_date, hour, passenger_journeys, ticket_count, vehicle_known_count FROM ticket_route_hourly WHERE route_id=? AND day_type=? AND hour=? ORDER BY service_date",
                (route_id, day_type, effective_hour),
            ).fetchall()
            fallback = "nearest_available_hour"
        else:
            history = conn.execute(
                "SELECT service_date, hour, passenger_journeys, ticket_count, vehicle_known_count FROM ticket_route_hourly WHERE route_id=? ORDER BY service_date, hour",
                (route_id,),
            ).fetchall()
            fallback = "all_available_route_hours" if history else None
    all_route = conn.execute(
        "SELECT passenger_journeys FROM ticket_route_hourly WHERE route_id=?",
        (route_id,),
    ).fetchall()

    capacity = _capacity_for_route(conn, route_id)
    if not history or not all_route:
        network = _network_reference_per_bus(conn, hour, day_type)
        per_bus = network["passengers_per_bus"]
        classified, crowd_label, capacity_note = _crowd_classification("moderate", per_bus, capacity)
        fields = _capacity_availability_fields(per_bus, capacity, "network_reference" if per_bus is not None else "capacity_only_fallback")
        return {
            "level": classified, "relative_level": "moderate", "label": crowd_label,
            "passenger_journeys_median": None,
            "estimated_ticketed_passengers_per_bus": per_bus,
            "scheduled_departures_in_hour": 0,
            **fields,
            "sample_size": 0, "observed_days": 0, "confidence": "low", "coverage": 0,
            "vehicle_id_coverage_pct": 0.0, "period": "October 2026 ticket records",
            "hour": hour, "departure_count_hour": network["reference_hour"],
            "day_type": day_type, "used_fallback": "network_reference",
            "estimate_basis": network["basis"] if per_bus is not None else "capacity_only_reference",
            "note": "No route-specific ticket sample was matched for this route/time. Availability is estimated from the network median ticketed load per scheduled departure; the displayed capacity is an operator-verified profile or a DilliFlow planning baseline, not a vehicle-specific live count." if per_bus is not None else "No route-specific or network load could be calculated for this bucket. The displayed seats and standing places are nominal capacity upper bounds; they are not a claim that the bus is empty.",
        }

    values = [float(r[0]) for r in all_route]
    current_values = [float(r["passenger_journeys"]) for r in history]
    observed = median(current_values)
    p33 = _percentile(values, 1 / 3)
    p66 = _percentile(values, 2 / 3)
    relative_level = "low" if observed <= p33 else "moderate" if observed <= p66 else "high"
    samples = sum(int(r["ticket_count"]) for r in history)
    dates = len({str(r["service_date"]) for r in history})
    confidence = "high" if dates >= 12 and samples >= 100 else "medium" if dates >= 5 and samples >= 25 else "low"
    if fallback:
        confidence = "low"
    vehicle_count = sum(int(r["vehicle_known_count"]) for r in history)
    if fallback == "all_available_route_hours":
        departures = 0
        passengers_per_bus = None
    else:
        departures = scheduled_departures_for_hour(conn, route_id, effective_hour, day_type)
        passengers_per_bus = round(observed / departures, 1) if departures > 0 else None
    availability_basis = "route_ticket_history"
    if passengers_per_bus is None:
        network = _network_reference_per_bus(conn, hour, day_type)
        passengers_per_bus = network["passengers_per_bus"]
        availability_basis = "network_reference" if passengers_per_bus is not None else "capacity_only_fallback"
        if passengers_per_bus is not None:
            confidence = "low"
    classified_level, crowd_label, capacity_note = _crowd_classification(relative_level, passengers_per_bus, capacity)
    fields = _capacity_availability_fields(passengers_per_bus, capacity, availability_basis)
    note = capacity_note or "Estimated ticketed passengers per scheduled bus are based on historical ticket records. Displayed capacity uses an operator-verified route profile or a clearly identified planning baseline."
    if not capacity["capacity_configured"]:
        note += " Planning baseline: 35 seats + 25 standing places; replace with verified fleet values when available."
    note += " This is not a vehicle-specific live occupancy sensor."
    return {
        "level": classified_level, "relative_level": relative_level, "label": crowd_label,
        "passenger_journeys_median": round(observed, 1),
        "estimated_ticketed_passengers_per_bus": passengers_per_bus,
        "scheduled_departures_in_hour": departures,
        **fields,
        "sample_size": samples, "observed_days": dates, "confidence": confidence,
        "vehicle_id_coverage_pct": round(vehicle_count / samples * 100, 1) if samples else 0.0,
        "coverage": round(min(100.0, dates / 20 * 100), 1),
        "period": "October 2026 ticket records", "hour": hour,
        "departure_count_hour": effective_hour, "day_type": day_type,
        "used_fallback": fallback,
        "estimate_basis": "median_daily_route_hour_ticketed_journeys_divided_by_gtfs_departures" if availability_basis == "route_ticket_history" else "network_reference_or_capacity_fallback",
        "note": note,
    }


def crowding_for_segment(conn: sqlite3.Connection, route_id: str, from_stop_id: str, to_stop_id: str, hour: int, day_type: str) -> dict[str, Any]:
    base = (route_id, from_stop_id, to_stop_id)
    rows = conn.execute(
        "SELECT service_date, hour, passenger_journeys, ticket_count, vehicle_known_count FROM ticket_segment_hourly WHERE route_id=? AND from_stop_id=? AND to_stop_id=? AND hour=? AND day_type=? ORDER BY service_date",
        (*base, hour, day_type),
    ).fetchall()
    fallback = None
    effective_hour = hour
    if not rows:
        nearest = conn.execute(
            "SELECT hour FROM ticket_segment_hourly WHERE route_id=? AND from_stop_id=? AND to_stop_id=? AND day_type=? GROUP BY hour ORDER BY ABS(hour-?) LIMIT 1",
            (*base, day_type, hour),
        ).fetchone()
        if nearest:
            effective_hour = int(nearest[0])
            rows = conn.execute(
                "SELECT service_date, hour, passenger_journeys, ticket_count, vehicle_known_count FROM ticket_segment_hourly WHERE route_id=? AND from_stop_id=? AND to_stop_id=? AND day_type=? AND hour=? ORDER BY service_date",
                (*base, day_type, effective_hour),
            ).fetchall()
            fallback = "nearest_available_hour"
        else:
            rows = conn.execute(
                "SELECT service_date, hour, passenger_journeys, ticket_count, vehicle_known_count FROM ticket_segment_hourly WHERE route_id=? AND from_stop_id=? AND to_stop_id=? ORDER BY service_date, hour",
                base,
            ).fetchall()
            fallback = "all_available_segment_hours" if rows else None
    overall = conn.execute(
        "SELECT passenger_journeys FROM ticket_segment_hourly WHERE route_id=? AND from_stop_id=? AND to_stop_id=?",
        base,
    ).fetchall()
    if not rows or not overall:
        route_estimate = crowding_for_route(conn, route_id, hour, day_type)
        return {
            **route_estimate,
            "sample_size": 0,
            "confidence": "low",
            "estimate_basis": "route_level_fallback",
            "note": "No segment-specific ticket sample was matched. The displayed load and availability use the route-level historical/network reference and route capacity profile; this is not a measured segment or vehicle occupancy.",
        }

    vals = [float(r[0]) for r in overall]
    observed = median([float(r["passenger_journeys"]) for r in rows])
    p33, p66 = _percentile(vals, 1 / 3), _percentile(vals, 2 / 3)
    relative_level = "low" if observed <= p33 else "moderate" if observed <= p66 else "high"
    tickets = sum(int(r["ticket_count"]) for r in rows)
    days = len({str(r["service_date"]) for r in rows})
    known = sum(int(r["vehicle_known_count"]) for r in rows)
    confidence = "high" if days >= 12 and tickets >= 100 else "medium" if days >= 5 and tickets >= 25 else "low"
    if fallback:
        confidence = "low"
    if fallback == "all_available_segment_hours":
        departures = 0
        passengers_per_bus = None
    else:
        departures = scheduled_departures_for_hour(conn, route_id, effective_hour, day_type, from_stop_id)
        passengers_per_bus = round(observed / departures, 1) if departures > 0 else None
    capacity = _capacity_for_route(conn, route_id)
    availability_basis = "segment_ticket_history"
    if passengers_per_bus is None:
        route_estimate = crowding_for_route(conn, route_id, hour, day_type)
        passengers_per_bus = route_estimate.get("estimated_ticketed_passengers_per_bus")
        availability_basis = "route_level_fallback" if passengers_per_bus is not None else "capacity_only_fallback"
        if passengers_per_bus is not None:
            confidence = "low"
    classified_level, crowd_label, capacity_note = _crowd_classification(relative_level, passengers_per_bus, capacity)
    fields = _capacity_availability_fields(passengers_per_bus, capacity, availability_basis)
    note = capacity_note or "Estimated ticketed passengers per bus on this segment are derived from historical stop-pair ticket records."
    if not capacity["capacity_configured"]:
        note += " Planning baseline: 35 seats + 25 standing places; replace with verified fleet values when available."
    note += " This is not live onboard occupancy."
    return {
        "level": classified_level, "relative_level": relative_level, "label": crowd_label,
        "passenger_journeys_median": round(observed, 1),
        "estimated_ticketed_passengers_per_bus": passengers_per_bus,
        "scheduled_departures_in_hour": departures,
        **fields,
        "sample_size": tickets, "observed_days": days, "confidence": confidence,
        "vehicle_id_coverage_pct": round(known / tickets * 100, 1) if tickets else 0.0,
        "coverage": round(min(100.0, days / 20 * 100), 1),
        "period": "October 2026 ticket records", "departure_count_hour": effective_hour,
        "used_fallback": fallback,
        "estimate_basis": "median_daily_segment_hour_ticketed_journeys_divided_by_gtfs_departures_at_segment_origin" if availability_basis == "segment_ticket_history" else availability_basis,
        "note": note,
    }

def list_routes(q: str | None = None, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    with database() as conn:
        params: list[Any] = []
        where = ""
        if q:
            where = "WHERE route_id LIKE ? OR route_short_name LIKE ? OR route_long_name LIKE ?"
            token = f"%{q}%"
            params += [token, token, token]
        total = conn.execute(f"SELECT COUNT(*) FROM routes {where}", params).fetchone()[0]
        rows = conn.execute(f"SELECT route_id, agency_id, route_short_name, route_long_name, route_desc, route_type FROM routes {where} ORDER BY route_short_name LIMIT ? OFFSET ?", [*params, limit, offset]).fetchall()
        return {"items": [dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}


def list_stops(q: str | None = None, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    with database() as conn:
        params: list[Any] = []
        where = ""
        if q:
            where = "WHERE stop_id LIKE ? OR stop_code LIKE ? OR stop_name LIKE ?"
            token = f"%{q}%"
            params += [token, token, token]
        total = conn.execute(f"SELECT COUNT(*) FROM stops {where}", params).fetchone()[0]
        rows = conn.execute(f"SELECT stop_id, stop_code, stop_name, stop_lat, stop_lon FROM stops {where} ORDER BY stop_name LIMIT ? OFFSET ?", [*params, limit, offset]).fetchall()
        return {"items": [dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}


def get_route(route_id: str) -> dict[str, Any] | None:
    with database() as conn:
        route = conn.execute("SELECT * FROM routes WHERE route_id=?", (route_id,)).fetchone()
        if not route:
            return None
        stops = conn.execute(
            "SELECT rso.stop_sequence, s.stop_id, s.stop_code, s.stop_name, s.stop_lat, s.stop_lon FROM route_stop_order rso JOIN stops s ON s.stop_id=rso.stop_id WHERE rso.route_id=? ORDER BY rso.stop_sequence",
            (route_id,),
        ).fetchall()
        shape_row = conn.execute(
            "SELECT shape_id FROM trips WHERE route_id=? AND shape_id<>'' GROUP BY shape_id ORDER BY COUNT(*) DESC LIMIT 1",
            (route_id,),
        ).fetchone()
        shapes = conn.execute(
            "SELECT shape_pt_lat, shape_pt_lon FROM shapes WHERE shape_id=? ORDER BY shape_pt_sequence",
            (shape_row[0],),
        ).fetchall() if shape_row else []
        if len(shapes) > 800:
            stride = math.ceil(len(shapes) / 800)
            shapes = shapes[::stride]
        crowd = crowding_for_route(conn, route_id, local_now().hour, "weekend" if local_now().weekday() >= 5 else "weekday")
        return {"route": dict(route), "stops": [dict(r) for r in stops], "geometry": [[r["shape_pt_lat"], r["shape_pt_lon"]] for r in shapes], "crowding": crowd}


def crowding_overview() -> dict[str, Any]:
    now = local_now()
    day_type = "weekend" if now.weekday() >= 5 else "weekday"
    with database() as conn:
        summary_row = conn.execute("SELECT value FROM ingestion_meta WHERE key='ticket_summary'").fetchone()
        summary = json.loads(summary_row[0]) if summary_row else {}
        rows = conn.execute(
            "SELECT route_id, AVG(passenger_journeys) AS demand, SUM(ticket_count) AS tickets, COUNT(*) AS observed_buckets FROM ticket_route_hourly WHERE hour=? AND day_type=? GROUP BY route_id ORDER BY demand DESC LIMIT 8",
            (now.hour, day_type),
        ).fetchall()
        top = []
        for row in rows:
            route = conn.execute("SELECT route_short_name, route_long_name FROM routes WHERE route_id=?", (row["route_id"],)).fetchone()
            estimate = crowding_for_route(conn, row["route_id"], now.hour, day_type)
            top.append({"route_id": row["route_id"], "route_short_name": route[0] if route else row["route_id"], "route_long_name": route[1] if route else "", "average_ticket_demand": round(float(row["demand"] or 0), 1), "ticket_count": int(row["tickets"] or 0), "crowding": estimate})
        total_routes = conn.execute("SELECT COUNT(DISTINCT route_id) FROM ticket_route_hourly").fetchone()[0]
        days = conn.execute("SELECT COUNT(DISTINCT service_date) FROM ticket_route_hourly").fetchone()[0]
        ticket_count = conn.execute("SELECT SUM(ticket_count) FROM ticket_route_hourly").fetchone()[0] or 0
        return {
            "period": summary.get("date_range", {}),
            "ticket_records": int(summary.get("total_records", ticket_count)),
            "matched_ticket_records": int(ticket_count),
            "routes_with_ticket_data": int(total_routes),
            "observed_dates": int(days),
            "missing_vehicle_number_pct": summary.get("missing_vehicle_number_percentage"),
            "route_match_pct": summary.get("route_match_percentage"),
            "boarding_stop_match_pct": summary.get("boarding_stop_match_percentage"),
            "alighting_stop_match_pct": summary.get("alighting_stop_match_percentage"),
            "top_demand_routes": top,
            "methodology": "October 2026 ticket-based relative demand proxy. This is not live passenger occupancy.",
        }


def crowding_routes(hour: int | None = None, day_type: str | None = None, q: str | None = None, limit: int = 50) -> dict[str, Any]:
    now = local_now()
    hour = now.hour if hour is None else max(0, min(23, hour))
    day_type = day_type or ("weekend" if now.weekday() >= 5 else "weekday")
    with database() as conn:
        params: list[Any] = [hour, day_type]
        where = "WHERE h.hour=? AND h.day_type=?"
        if q:
            where += " AND (r.route_short_name LIKE ? OR r.route_long_name LIKE ? OR r.route_id LIKE ?)"
            token = f"%{q}%"
            params.extend([token, token, token])
        rows = conn.execute(
            f"SELECT h.route_id, AVG(h.passenger_journeys) AS demand, SUM(h.ticket_count) AS tickets, COUNT(DISTINCT h.service_date) AS days, r.route_short_name, r.route_long_name FROM ticket_route_hourly h JOIN routes r ON r.route_id=h.route_id {where} GROUP BY h.route_id ORDER BY demand DESC LIMIT ?",
            [*params, limit],
        ).fetchall()
        items = []
        for r in rows:
            estimate = crowding_for_route(conn, r["route_id"], hour, day_type)
            items.append({"route_id": r["route_id"], "route_short_name": r["route_short_name"], "route_long_name": r["route_long_name"], "average_passenger_journeys": round(float(r["demand"] or 0), 1), "ticket_count": int(r["tickets"] or 0), "observed_days": int(r["days"]), "crowding": estimate})
        return {"items": items, "hour": hour, "day_type": day_type, "period": "October 2026"}


def crowding_segments(route_id: str, hour: int | None = None, day_type: str | None = None) -> dict[str, Any]:
    """Return segment demand in the route's actual representative stop order.

    The previous implementation only enumerated pairs with a record in the exact
    requested hour. That hid historical pairs whenever the selected hour had no
    records, even though crowding_for_segment could legitimately use a nearest-hour
    fallback. Enumerating the ordered GTFS stop pairs first makes those fallbacks
    visible and keeps the display aligned with the route map/timeline.
    """
    now = local_now()
    hour = now.hour if hour is None else max(0, min(23, hour))
    day_type = day_type or ("weekend" if now.weekday() >= 5 else "weekday")
    with database() as conn:
        route = conn.execute("SELECT route_id FROM routes WHERE route_id=?", (route_id,)).fetchone()
        if not route:
            return {"route_id": route_id, "hour": hour, "day_type": day_type, "items": [], "period": "October 2026"}
        stops = conn.execute(
            """SELECT rso.stop_sequence, s.stop_id, s.stop_name
               FROM route_stop_order rso JOIN stops s ON s.stop_id=rso.stop_id
               WHERE rso.route_id=? ORDER BY rso.stop_sequence""",
            (route_id,),
        ).fetchall()
        items: list[dict[str, Any]] = []
        for left, right in zip(stops, stops[1:]):
            estimate = crowding_for_segment(
                conn, route_id, left["stop_id"], right["stop_id"], hour, day_type
            )
            items.append({
                "from_stop_id": left["stop_id"],
                "to_stop_id": right["stop_id"],
                "from_stop_name": left["stop_name"],
                "to_stop_name": right["stop_name"],
                "average_passenger_journeys": estimate.get("passenger_journeys_median"),
                "ticket_count": estimate.get("sample_size", 0),
                "observed_days": estimate.get("observed_days", 0),
                "crowding": estimate,
            })
        return {"route_id": route_id, "hour": hour, "day_type": day_type, "items": items, "period": "October 2026"}


def stop_crowding_details(stop_id: str) -> dict[str, Any] | None:
    """Return routes serving a stop with historical route and adjacent-segment demand."""
    now = local_now()
    day_type = "weekend" if now.weekday() >= 5 else "weekday"
    with database() as conn:
        stop = conn.execute(
            "SELECT stop_id, stop_code, stop_name, stop_lat, stop_lon FROM stops WHERE stop_id=?",
            (stop_id,),
        ).fetchone()
        if not stop:
            return None

        served = conn.execute(
            """SELECT r.route_id, r.route_short_name, r.route_long_name,
                      rso.stop_sequence
               FROM route_stop_order rso
               JOIN routes r ON r.route_id=rso.route_id
               WHERE rso.stop_id=?
               ORDER BY r.route_short_name, r.route_id
               LIMIT 100""",
            (stop_id,),
        ).fetchall()
        routes: list[dict[str, Any]] = []
        for row in served:
            route_id = str(row["route_id"])
            sequence = int(row["stop_sequence"])
            previous = conn.execute(
                """SELECT s.stop_id, s.stop_name FROM route_stop_order rso
                   JOIN stops s ON s.stop_id=rso.stop_id
                   WHERE rso.route_id=? AND rso.stop_sequence<?
                   ORDER BY rso.stop_sequence DESC LIMIT 1""",
                (route_id, sequence),
            ).fetchone()
            following = conn.execute(
                """SELECT s.stop_id, s.stop_name FROM route_stop_order rso
                   JOIN stops s ON s.stop_id=rso.stop_id
                   WHERE rso.route_id=? AND rso.stop_sequence>?
                   ORDER BY rso.stop_sequence LIMIT 1""",
                (route_id, sequence),
            ).fetchone()
            before = None
            after = None
            if previous:
                before = {
                    "from_stop_id": previous["stop_id"],
                    "from_stop_name": previous["stop_name"],
                    "to_stop_id": stop_id,
                    "to_stop_name": stop["stop_name"],
                    "crowding": crowding_for_segment(
                        conn, route_id, previous["stop_id"], stop_id, now.hour, day_type
                    ),
                }
            if following:
                after = {
                    "from_stop_id": stop_id,
                    "from_stop_name": stop["stop_name"],
                    "to_stop_id": following["stop_id"],
                    "to_stop_name": following["stop_name"],
                    "crowding": crowding_for_segment(
                        conn, route_id, stop_id, following["stop_id"], now.hour, day_type
                    ),
                }
            routes.append({
                "route_id": route_id,
                "route_short_name": row["route_short_name"],
                "route_long_name": row["route_long_name"],
                "stop_sequence": sequence,
                "crowding": crowding_for_route(conn, route_id, now.hour, day_type),
                "previous_segment": before,
                "next_segment": after,
            })

        return {
            "stop": dict(stop),
            "routes": routes,
            "routes_count": len(routes),
            "hour": now.hour,
            "day_type": day_type,
            "period": "October 2026 ticket records",
            "methodology": "Historical ticket-demand proxy for routes and adjacent stop segments. It is not live onboard occupancy.",
        }


def crowding_trends(route_id: str | None = None, day_type: str = "weekday") -> dict[str, Any]:
    with database() as conn:
        params: list[Any] = [day_type]
        where = "WHERE day_type=?"
        if route_id:
            where += " AND route_id=?"
            params.append(route_id)
        rows = conn.execute(
            f"SELECT hour, SUM(passenger_journeys) AS passenger_journeys, SUM(ticket_count) AS ticket_count, COUNT(DISTINCT route_id) AS route_count FROM ticket_route_hourly {where} GROUP BY hour ORDER BY hour",
            params,
        ).fetchall()
        return {"route_id": route_id, "day_type": day_type, "items": [dict(r) for r in rows], "period": "October 2026"}


def _leg_schedule(conn: sqlite3.Connection, from_stop: str, to_stop: str, service_ids: list[str], after: str, max_rows: int = 4) -> list[dict[str, Any]]:
    if not service_ids:
        return []
    placeholders = ",".join("?" for _ in service_ids)
    sql = f"""
      SELECT t.route_id,t.trip_id,t.shape_id,r.route_short_name,r.route_long_name,
             a.departure_time,b.arrival_time,a.stop_sequence AS from_sequence,b.stop_sequence AS to_sequence
      FROM stop_times a
      JOIN stop_times b ON b.trip_id=a.trip_id AND b.stop_sequence>a.stop_sequence
      JOIN trips t ON t.trip_id=a.trip_id
      JOIN routes r ON r.route_id=t.route_id
      WHERE a.stop_id=? AND b.stop_id=? AND a.departure_time>=? AND t.service_id IN ({placeholders})
      ORDER BY a.departure_time LIMIT ?
    """
    return [dict(r) for r in conn.execute(sql, [from_stop, to_stop, after, *service_ids, max_rows]).fetchall()]


def _geometry(conn: sqlite3.Connection, shape_id: str | None, max_points: int = 120) -> list[list[float]]:
    if not shape_id:
        return []
    rows = conn.execute("SELECT shape_pt_lat,shape_pt_lon FROM shapes WHERE shape_id=? ORDER BY shape_pt_sequence", (shape_id,)).fetchall()
    if not rows:
        return []
    stride = max(1, math.ceil(len(rows) / max_points))
    points = [[float(r[0]), float(r[1])] for i, r in enumerate(rows) if i % stride == 0]
    if rows and points[-1] != [float(rows[-1][0]), float(rows[-1][1])]:
        points.append([float(rows[-1][0]), float(rows[-1][1])])
    return points


def search_journeys(origin_stop_id: str, destination_stop_id: str, travel_date: date, departure_time: str, max_transfers: int = 1) -> dict[str, Any]:
    if origin_stop_id == destination_stop_id:
        return {"items": [], "message": "Choose two different stops."}
    with database() as conn:
        origin = conn.execute("SELECT * FROM stops WHERE stop_id=?", (origin_stop_id,)).fetchone()
        destination = conn.execute("SELECT * FROM stops WHERE stop_id=?", (destination_stop_id,)).fetchone()
        if not origin or not destination:
            return {"items": [], "message": "Origin or destination stop was not found."}
        services = service_ids_for(conn, travel_date)
        if not services:
            return {"items": [], "message": "No GTFS service calendar is active for the selected date."}
        direct = _leg_schedule(conn, origin_stop_id, destination_stop_id, services, departure_time, 12)
        journeys: list[dict[str, Any]] = []
        for leg in direct:
            start_min = time_to_minutes(leg["departure_time"])
            end_min = time_to_minutes(leg["arrival_time"])
            if start_min is None or end_min is None or end_min < start_min:
                continue
            duration = round(end_min - start_min)
            journeys.append({
                "id": f"direct-{leg['trip_id']}-{origin_stop_id}-{destination_stop_id}",
                "type": "direct",
                "legs": [{
                    "route_id": leg["route_id"], "route_short_name": leg["route_short_name"], "route_long_name": leg["route_long_name"],
                    "trip_id": leg["trip_id"], "shape_id": leg["shape_id"],
                    "from_sequence": leg["from_sequence"], "to_sequence": leg["to_sequence"],
                    "from_stop": dict(origin), "to_stop": dict(destination),
                    "departure_time": leg["departure_time"], "arrival_time": leg["arrival_time"],
                    "duration_minutes": duration, "geometry": _geometry(conn, leg["shape_id"]),
                }],
                "duration_minutes": duration, "transfers": 0,
                "departure_time": leg["departure_time"], "arrival_time": leg["arrival_time"],
                "recommendation_reason": "Direct scheduled service with no transfer.",
            })

        if max_transfers > 0 and len(journeys) < 8:
            origin_rows = conn.execute("SELECT route_id, stop_sequence FROM route_stop_order WHERE stop_id=?", (origin_stop_id,)).fetchall()
            destination_rows = conn.execute("SELECT route_id, stop_sequence FROM route_stop_order WHERE stop_id=?", (destination_stop_id,)).fetchall()
            origin_routes = {r["route_id"] for r in origin_rows}
            destination_routes = {r["route_id"] for r in destination_rows}
            origin_sequences: dict[str, list[str]] = {}
            destination_sequences: dict[str, list[str]] = {}
            for route_id in origin_routes:
                origin_sequences[route_id] = [r[0] for r in conn.execute("SELECT stop_id FROM route_stop_order WHERE route_id=? ORDER BY stop_sequence", (route_id,))]
            for route_id in destination_routes:
                destination_sequences[route_id] = [r[0] for r in conn.execute("SELECT stop_id FROM route_stop_order WHERE route_id=? ORDER BY stop_sequence", (route_id,))]
            transfer_candidates = []
            for route_a in origin_routes:
                seq_a = origin_sequences[route_a]
                if origin_stop_id not in seq_a:
                    continue
                pos_a = seq_a.index(origin_stop_id)
                reachable = set(seq_a[pos_a + 1:])
                for route_b in destination_routes:
                    if route_a == route_b:
                        continue
                    seq_b = destination_sequences[route_b]
                    if destination_stop_id not in seq_b:
                        continue
                    pos_b = seq_b.index(destination_stop_id)
                    before_dest = set(seq_b[:pos_b])
                    for transfer_id in reachable.intersection(before_dest):
                        transfer_candidates.append((route_a, route_b, transfer_id))
                        if len(transfer_candidates) >= 80:
                            break
                    if len(transfer_candidates) >= 80:
                        break
                if len(transfer_candidates) >= 80:
                    break
            date_services = services
            for route_a, route_b, transfer_id in transfer_candidates:
                if len(journeys) >= 14:
                    break
                firsts = [l for l in _leg_schedule(conn, origin_stop_id, transfer_id, date_services, departure_time, 2) if l["route_id"] == route_a]
                if not firsts:
                    continue
                first = firsts[0]
                first_arrival = time_to_minutes(first["arrival_time"])
                if first_arrival is None:
                    continue
                second_after_minutes = first_arrival + 8
                second_after = f"{int(second_after_minutes // 60):02d}:{int(second_after_minutes % 60):02d}:00"
                seconds = [l for l in _leg_schedule(conn, transfer_id, destination_stop_id, date_services, second_after, 2) if l["route_id"] == route_b]
                if not seconds:
                    continue
                second = seconds[0]
                start_min = time_to_minutes(first["departure_time"])
                end_min = time_to_minutes(second["arrival_time"])
                second_depart = time_to_minutes(second["departure_time"])
                if None in (start_min, end_min, second_depart) or end_min < start_min:
                    continue
                transfer = conn.execute("SELECT * FROM stops WHERE stop_id=?", (transfer_id,)).fetchone()
                first_duration = round((first_arrival or 0) - (start_min or 0))
                second_duration = round((end_min or 0) - (second_depart or 0))
                journey_duration = round((end_min or 0) - (start_min or 0))
                journeys.append({
                    "id": f"transfer-{first['trip_id']}-{second['trip_id']}",
                    "type": "one_transfer",
                    "legs": [
                        {"route_id": first["route_id"], "route_short_name": first["route_short_name"], "route_long_name": first["route_long_name"], "trip_id": first["trip_id"], "shape_id": first["shape_id"], "from_sequence": first["from_sequence"], "to_sequence": first["to_sequence"], "from_stop": dict(origin), "to_stop": dict(transfer) if transfer else None, "departure_time": first["departure_time"], "arrival_time": first["arrival_time"], "duration_minutes": first_duration, "geometry": _geometry(conn, first["shape_id"])},
                        {"route_id": second["route_id"], "route_short_name": second["route_short_name"], "route_long_name": second["route_long_name"], "trip_id": second["trip_id"], "shape_id": second["shape_id"], "from_sequence": second["from_sequence"], "to_sequence": second["to_sequence"], "from_stop": dict(transfer) if transfer else None, "to_stop": dict(destination), "departure_time": second["departure_time"], "arrival_time": second["arrival_time"], "duration_minutes": second_duration, "geometry": _geometry(conn, second["shape_id"])},
                    ],
                    "duration_minutes": journey_duration,
                    "transfers": 1,
                    "departure_time": first["departure_time"],
                    "arrival_time": second["arrival_time"],
                    "transfer_stop": dict(transfer) if transfer else None,
                    "transfer_buffer_minutes": max(0, round((second_depart or 0) - (first_arrival or 0))),
                    "recommendation_reason": "One scheduled transfer via a stop shared by both GTFS route patterns.",
                })

        # Enrich legs with historical route-level demand for each time bucket.
        day_type = "weekend" if travel_date.weekday() >= 5 else "weekday"
        for journey in journeys:
            journey_crowding = []
            for leg in journey["legs"]:
                hh = int((leg.get("departure_time") or "00").split(":")[0]) % 24
                leg["crowding"] = crowding_for_route(conn, leg["route_id"], hh, day_type)
                journey_crowding.append(leg["crowding"].get("level", "insufficient_data"))
            journey["crowding"] = "high" if "high" in journey_crowding else "moderate" if "moderate" in journey_crowding else "low" if journey_crowding and all(x == "low" for x in journey_crowding) else "insufficient_data"
        journeys.sort(key=lambda item: (item["duration_minutes"], item["transfers"]))
        return {
            "items": journeys[:14],
            "origin": dict(origin),
            "destination": dict(destination),
            "date": travel_date.isoformat(),
            "departure_after": departure_time,
            "service_ids": services,
            "methodology": "Scheduled GTFS trips. Historical ticket-demand indicators are separate from live occupancy.",
            "message": None if journeys else "No scheduled journey was found for this stop pair and departure time. Try a nearby stop or a later departure.",
        }
