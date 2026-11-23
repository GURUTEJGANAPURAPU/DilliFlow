from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from ..config import settings
from ..db import database
from .transit import crowding_for_route, crowding_for_segment, time_to_minutes


# Keep GPS-to-shape association conservative. A 1.8 km corridor can attach a
# parallel road, depot or opposite carriageway to the wrong route segment.
MAX_ROUTE_CROSS_TRACK_M = 650.0
AT_STOP_RADIUS_M = 45.0
PASSED_STOP_TOLERANCE_M = 75.0
MIN_ETA_DISTANCE_M = 50.0
MAX_ETA_MINUTES = 90
MAX_DIRECTION_DIFFERENCE_DEG = 75.0


def _haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6_371_000 * 2 * math.asin(min(1.0, math.sqrt(h)))


def _project_to_line(point: tuple[float, float], line: list[tuple[float, float]]) -> tuple[float, float]:
    """Return along-line metres and cross-track metres using a local equirectangular plane."""
    if not line:
        return 0.0, float("inf")
    if len(line) == 1:
        return 0.0, _haversine_m(point, line[0])

    lat0 = math.radians(point[0])
    sx = 111_320.0 * math.cos(lat0)
    sy = 110_540.0

    def xy(p: tuple[float, float]) -> tuple[float, float]:
        return p[1] * sx, p[0] * sy

    px, py = xy(point)
    cumulative = 0.0
    best_cross = float("inf")
    best_along = 0.0
    for idx in range(len(line) - 1):
        ax, ay = xy(line[idx])
        bx, by = xy(line[idx + 1])
        dx, dy = bx - ax, by - ay
        seg2 = dx * dx + dy * dy
        seg_len = math.sqrt(seg2)
        if seg2 <= 1e-8:
            t = 0.0
        else:
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
        qx, qy = ax + t * dx, ay + t * dy
        cross = math.hypot(px - qx, py - qy)
        if cross < best_cross:
            best_cross = cross
            best_along = cumulative + t * seg_len
        cumulative += seg_len
    return best_along, best_cross


def _line_length_m(line: list[tuple[float, float]]) -> float:
    return sum(_haversine_m(line[i], line[i + 1]) for i in range(len(line) - 1))


def _orient_progress(along: float, total: float, origin_along: float, destination_along: float) -> tuple[float, float, float, bool]:
    """Orient route progress from selected boarding stop to alighting stop.

    GTFS shapes are not guaranteed to be stored in the same direction as the
    selected trip's stop sequence. Normalize all positions before comparing.
    """
    forward = destination_along >= origin_along
    if forward:
        return along, origin_along, destination_along, True
    return total - along, total - origin_along, total - destination_along, False


def _bearing_difference(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _shape_bearing_at(line: list[tuple[float, float]], along: float, forward: bool) -> float | None:
    """Approximate route bearing at a projected shape distance, in trip direction."""
    if len(line) < 2:
        return None
    cumulative = 0.0
    for start, end in zip(line, line[1:]):
        lat1, lon1 = map(math.radians, start)
        lat2, lon2 = map(math.radians, end)
        dlon = lon2 - lon1
        y = math.sin(dlon) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
        bearing = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
        segment_length = _haversine_m(start, end)
        if along <= cumulative + segment_length or end == line[-1]:
            return bearing if forward else (bearing + 180.0) % 360.0
        cumulative += segment_length
    return None


def _eta_minutes(distance_m: float, speed_mps: float | None, at_stop: bool = False) -> int | None:
    """Return a conservative live ETA. Zero is reserved for a GPS-confirmed stop."""
    if at_stop:
        return 0
    if distance_m <= MIN_ETA_DISTANCE_M or speed_mps is None or not (1.0 <= speed_mps <= 22.0):
        return None
    minutes = max(1, math.ceil(distance_m / speed_mps / 60.0))
    return minutes if minutes <= MAX_ETA_MINUTES else None


def _format_gtfs_clock(value: str) -> str:
    try:
        parts = [int(part) for part in value.split(":")]
        hour, minute = parts[0], parts[1]
        day_offset = hour // 24
        label = datetime(2000, 1, 1, hour % 24, minute).strftime("%I:%M %p").lstrip("0")
        return f"{label} (+{day_offset} day)" if day_offset else label
    except (TypeError, ValueError, IndexError):
        return value


def _shape_for_trip(conn, trip_id: str) -> list[tuple[float, float]]:
    row = conn.execute("SELECT shape_id FROM trips WHERE trip_id=?", (trip_id,)).fetchone()
    if not row or not row[0]:
        return []
    rows = conn.execute(
        "SELECT shape_pt_lat, shape_pt_lon FROM shapes WHERE shape_id=? ORDER BY shape_pt_sequence",
        (row[0],),
    ).fetchall()
    return [(float(r[0]), float(r[1])) for r in rows]


def _trip_stops(conn, leg: dict[str, Any], hour: int, day_type: str) -> list[dict[str, Any]]:
    trip_id = leg.get("trip_id")
    start_seq = leg.get("from_sequence")
    end_seq = leg.get("to_sequence")
    if not trip_id or start_seq is None or end_seq is None:
        return []
    rows = conn.execute(
        """SELECT st.stop_sequence, st.arrival_time, st.departure_time,
                  s.stop_id, s.stop_code, s.stop_name, s.stop_lat, s.stop_lon
           FROM stop_times st JOIN stops s ON s.stop_id=st.stop_id
           WHERE st.trip_id=? AND st.stop_sequence BETWEEN ? AND ?
           ORDER BY st.stop_sequence""",
        (trip_id, int(start_seq), int(end_seq)),
    ).fetchall()
    stops = [dict(r) for r in rows]
    for i, stop in enumerate(stops):
        stop["crowding_to_next"] = None
        stop["crowding_source"] = "not_available"
        if i + 1 < len(stops):
            estimate = crowding_for_segment(
                conn, leg["route_id"], stop["stop_id"], stops[i + 1]["stop_id"], hour, day_type
            )
            if estimate.get("estimate_basis") == "route_level_fallback" or estimate.get("availability_basis") in {"route_level_fallback", "network_reference"}:
                stop["crowding_source"] = "route_level_fallback"
            elif estimate.get("level") == "insufficient_data":
                estimate = crowding_for_route(conn, leg["route_id"], hour, day_type)
                stop["crowding_source"] = "route_level_fallback"
            else:
                stop["crowding_source"] = "historical_segment"
            stop["crowding_to_next"] = estimate
    return stops


def _route_progress_context(
    stop_positions: list[tuple[dict[str, Any], float, float]],
    vehicle_progress: float,
    origin_progress: float,
    destination_progress: float,
    current_stop_id: str = "",
    boarding_stop_id: str = "",
) -> dict[str, Any]:
    """Describe a bus position against the selected journey's ordered stop pattern.

    Stop names are inferred from the GTFS shape projection unless the real-time
    feed provides a stop_id. This is route progress, not proof of a trip match.
    """
    ordered = sorted(stop_positions, key=lambda item: item[1])
    current = next((item[0] for item in ordered if current_stop_id and str(item[0].get("stop_id")) == current_stop_id), None)
    if current is None and boarding_stop_id and abs(vehicle_progress - origin_progress) <= AT_STOP_RADIUS_M:
        current = next((item[0] for item in ordered if str(item[0].get("stop_id")) == boarding_stop_id), None)

    tolerance = 35.0
    passed = [item for item in ordered if item[1] <= vehicle_progress + tolerance]
    upcoming = [item for item in ordered if item[1] > vehicle_progress + tolerance]
    if current is not None:
        current_progress = next((item[1] for item in ordered if str(item[0].get("stop_id")) == str(current.get("stop_id"))), vehicle_progress)
        upcoming = [item for item in ordered if item[1] > current_progress + tolerance]
    last = passed[-1][0] if passed else None
    next_item = upcoming[0] if upcoming else None
    segment_length = max(1.0, destination_progress - origin_progress)
    progress_pct = max(0.0, min(100.0, (vehicle_progress - origin_progress) / segment_length * 100.0))
    next_distance = max(0.0, next_item[1] - vehicle_progress) if next_item else None
    return {
        "progress_percent": round(progress_pct, 1),
        "current_stop_id": current.get("stop_id") if current else None,
        "current_stop_name": current.get("stop_name") if current else None,
        "last_passed_stop_id": last.get("stop_id") if last else None,
        "last_passed_stop_name": last.get("stop_name") if last else None,
        "last_passed_stop_sequence": last.get("stop_sequence") if last else None,
        "next_stop_id": next_item[0].get("stop_id") if next_item else None,
        "next_stop_name": next_item[0].get("stop_name") if next_item else None,
        "next_stop_sequence": next_item[0].get("stop_sequence") if next_item else None,
        "distance_to_next_stop_m": round(next_distance) if next_distance is not None else None,
        "progress_source": "gtfs_stop_id" if current_stop_id and current else "gps_shape_projection",
    }


def _live_speed(vehicle: dict[str, Any]) -> tuple[float | None, str]:
    value = vehicle.get("speed_estimate_mps")
    source = vehicle.get("speed_source") or "derived_from_recent_positions"
    if value is None:
        value = vehicle.get("speed_mps")
        source = "gtfs_realtime_reported" if value is not None else "unavailable"
    try:
        speed = float(value) if value is not None else None
    except (TypeError, ValueError):
        speed = None
    if speed is None or not (1.0 <= speed <= 22.0):
        return None, "unavailable"
    return speed, source


def _enrich_leg(conn, leg: dict[str, Any], snapshot: dict[str, Any], travel_date, allow_live: bool, live_status_override: str | None = None) -> None:
    departure = str(leg.get("departure_time", "00:00:00"))
    try:
        hour = int(departure.split(":")[0]) % 24
    except (ValueError, IndexError):
        hour = 8
    day_type = "weekend" if travel_date.weekday() >= 5 else "weekday"
    leg["stops"] = _trip_stops(conn, leg, hour, day_type)
    route_crowding = leg.get("crowding") or crowding_for_route(conn, leg["route_id"], hour, day_type)
    leg["crowding"] = route_crowding
    leg["live_feed_status"] = snapshot.get("status", "unknown")
    leg["live_feed_message"] = snapshot.get("message")
    leg["live_feed_fetched_at"] = snapshot.get("fetched_at")
    leg["live_vehicles"] = []
    leg["live_trip_match_count"] = 0
    leg["live_arrivals_status"] = snapshot.get("status", "unknown") if allow_live else (live_status_override or "date_not_current")
    if not allow_live:
        if live_status_override == "selected_time_passed":
            leg["live_arrivals_message"] = "The selected departure time has already passed today. Choose a later time to see current GPS-based bus arrival estimates. Scheduled GTFS times and historical crowding remain available."
        else:
            leg["live_arrivals_message"] = "Live GPS is a current-position feed and cannot forecast a future or past service date. Scheduled GTFS times and historical crowding are shown for the selected date."
        return

    now = datetime.now(ZoneInfo(settings.local_timezone))
    departure_minutes = time_to_minutes(departure)
    now_minutes = now.hour * 60 + now.minute
    minutes_until_departure = (departure_minutes - now_minutes) if departure_minutes is not None else None
    leg["live_schedule_context_note"] = (
        f"Current GPS positions are a snapshot from {now.strftime('%I:%M %p').lstrip('0')}. "
        f"This scheduled trip departs at {_format_gtfs_clock(departure)}. "
        "The live feed uses ADDED trip IDs that are not linked to this static GTFS trip. "
        "These vehicles show current activity on the same route; they are not confirmed as the specific scheduled departure."
    )
    leg["minutes_until_scheduled_departure"] = minutes_until_departure
    leg["live_route_pattern_note"] = (
        "Live vehicles are matched by GTFS route ID. The feed's ADDED trip IDs do not match static scheduled trip IDs; the live positions are route activity, not confirmation of the selected scheduled trip."
    )

    if snapshot.get("status") != "connected":
        return

    shape = _shape_for_trip(conn, str(leg.get("trip_id", "")))
    if len(shape) < 2:
        leg["live_arrivals_message"] = "The selected scheduled trip has no usable shape geometry, so route-specific live ETA matching is unavailable."
        return

    raw_stop_positions: list[tuple[dict[str, Any], float, float]] = []
    for stop in leg["stops"]:
        if stop.get("stop_lat") is None or stop.get("stop_lon") is None:
            continue
        along, cross = _project_to_line((float(stop["stop_lat"]), float(stop["stop_lon"])), shape)
        raw_stop_positions.append((stop, along, cross))
    if not raw_stop_positions:
        return

    origin_id = str((leg.get("from_stop") or {}).get("stop_id", ""))
    destination_id = str((leg.get("to_stop") or {}).get("stop_id", ""))
    origin_row = next((x for x in raw_stop_positions if str(x[0]["stop_id"]) == origin_id), None)
    destination_row = next((x for x in raw_stop_positions if str(x[0]["stop_id"]) == destination_id), None)
    if not origin_row or not destination_row:
        leg["live_arrivals_message"] = "The selected boarding or alighting stop could not be projected onto the scheduled route shape."
        return

    total_length = _line_length_m(shape)
    origin_raw = origin_row[1]
    destination_raw = destination_row[1]
    _, origin_progress, destination_progress, forward = _orient_progress(
        origin_raw, total_length, origin_raw, destination_raw
    )
    if destination_progress < origin_progress:
        leg["live_arrivals_message"] = "The selected stop order does not follow the route shape; no GPS arrival estimate was produced."
        return

    stop_positions: list[tuple[dict[str, Any], float, float]] = []
    for stop, raw_along, cross in raw_stop_positions:
        progress, _, _, _ = _orient_progress(raw_along, total_length, origin_raw, destination_raw)
        stop_positions.append((stop, progress, cross))

    origin_point = (float(origin_row[0]["stop_lat"]), float(origin_row[0]["stop_lon"]))
    now_for_eta = now
    selected_trip_id = str(leg.get("trip_id", ""))
    matched_count = 0
    vehicles = snapshot.get("vehicles", [])
    for vehicle in vehicles:
        if str(vehicle.get("route_id", "")) != str(leg["route_id"]):
            continue
        if vehicle.get("freshness") not in ("fresh", "delayed"):
            continue
        try:
            point = (float(vehicle["latitude"]), float(vehicle["longitude"]))
        except (KeyError, TypeError, ValueError):
            continue
        raw_along, cross, = _project_to_line(point, shape)
        if cross > MAX_ROUTE_CROSS_TRACK_M:
            continue
        vehicle_progress, _, _, _ = _orient_progress(raw_along, total_length, origin_raw, destination_raw)
        distance_to_board = origin_progress - vehicle_progress
        direct_distance_to_board = _haversine_m(point, origin_point)
        vehicle_stop_id = str(vehicle.get("stop_id") or "")
        at_boarding_stop = vehicle_stop_id == origin_id or (
            direct_distance_to_board <= AT_STOP_RADIUS_M and cross <= 120.0
        )
        passed_boarding = distance_to_board < -PASSED_STOP_TOLERANCE_M and not at_boarding_stop

        raw_bearing = vehicle.get("bearing_estimate")
        if raw_bearing is None:
            raw_bearing = vehicle.get("bearing")
        try:
            vehicle_bearing = float(raw_bearing) % 360.0 if raw_bearing is not None else None
        except (TypeError, ValueError):
            vehicle_bearing = None
        route_bearing = _shape_bearing_at(shape, raw_along, forward)
        bearing_delta = _bearing_difference(vehicle_bearing, route_bearing) if vehicle_bearing is not None and route_bearing is not None else None
        direction_aligned = bearing_delta is not None and bearing_delta <= MAX_DIRECTION_DIFFERENCE_DEG

        speed, speed_source = _live_speed(vehicle)
        eta_minutes: int | None = None
        eta_time: str | None = None
        confidence = "unavailable"
        if at_boarding_stop:
            eta_minutes = 0
            eta_time = now_for_eta.isoformat()
            confidence = "medium" if vehicle_stop_id == origin_id else "low"
            approach_status = "at_boarding_stop"
            approach_message = "GPS confirms this vehicle is at the boarding stop."
        elif passed_boarding:
            approach_status = "passed_boarding_stop"
            approach_message = "This vehicle has moved past the selected boarding stop."
        elif distance_to_board < MIN_ETA_DISTANCE_M:
            approach_status = "near_boarding_stop_unconfirmed"
            approach_message = "Vehicle is close to the stop, but GPS does not confirm that it is at the stop."
        elif not direction_aligned:
            approach_status = "direction_unverified"
            approach_message = "Vehicle is on this route, but its direction toward the selected stop is not confirmed."
        elif speed is None:
            approach_status = "speed_unavailable"
            approach_message = "Live position is available, but a reliable moving speed is not available for an ETA."
        else:
            eta_minutes = _eta_minutes(distance_to_board, speed)
            if eta_minutes is not None:
                eta_time = (now_for_eta + timedelta(minutes=eta_minutes)).isoformat()
                confidence = "medium" if vehicle.get("freshness") == "fresh" else "low"
                approach_status = "approaching"
                approach_message = "Approaching the boarding stop in the selected route direction."
            else:
                approach_status = "on_route_eta_out_of_range"
                approach_message = "Vehicle is on the route, but it is too far away for a useful boarding-stop ETA."

        exact_trip_match = str(vehicle.get("trip_id") or "") == selected_trip_id and bool(selected_trip_id)
        if exact_trip_match:
            matched_count += 1

        progress_context = _route_progress_context(
            stop_positions,
            vehicle_progress,
            origin_progress,
            destination_progress,
            current_stop_id=vehicle_stop_id,
            boarding_stop_id=origin_id if at_boarding_stop else "",
        )

        # The current stop can be shown even before a usable moving-speed sample
        # exists. Downstream ETAs still require direction and real GPS speed.
        stop_arrivals: list[dict[str, Any]] = []
        for stop, stop_progress, _ in stop_positions:
            if stop_progress < origin_progress - 25 or stop_progress > destination_progress + 25:
                continue
            is_this_stop = (
                (vehicle_stop_id and str(vehicle_stop_id) == str(stop["stop_id"]))
                or (at_boarding_stop and str(stop["stop_id"]) == origin_id)
            )
            if is_this_stop:
                minutes = 0
                arrival_source = "gps_confirmed_stop"
            elif direction_aligned and speed is not None:
                remaining = stop_progress - vehicle_progress
                if remaining < -25:
                    continue
                minutes = _eta_minutes(max(0.0, remaining), speed)
                arrival_source = "gps_shape_projection"
            else:
                continue
            if minutes is None:
                continue
            stop_arrivals.append({
                "stop_id": stop["stop_id"],
                "stop_name": stop["stop_name"],
                "stop_sequence": stop["stop_sequence"],
                "eta_minutes": minutes,
                "estimated_arrival_at": (now_for_eta + timedelta(minutes=minutes)).isoformat(),
                "arrival_source": arrival_source,
                "crowding_to_next": stop.get("crowding_to_next"),
                "crowding_source": stop.get("crowding_source"),
            })

        item = {
            "vehicle_id": vehicle.get("vehicle_id"),
            "route_id": vehicle.get("route_id"),
            "route_short_name": vehicle.get("route_short_name"),
            "trip_id": vehicle.get("trip_id"),
            "schedule_relationship": vehicle.get("schedule_relationship"),
            "matches_selected_scheduled_trip": exact_trip_match,
            "latitude": point[0],
            "longitude": point[1],
            "speed_mps": vehicle.get("speed_mps"),
            "speed_estimate_mps": speed,
            "speed_source": speed_source,
            "bearing": vehicle.get("bearing"),
            "bearing_estimate": vehicle_bearing,
            "bearing_difference_degrees": round(bearing_delta, 1) if bearing_delta is not None else None,
            "direction_aligned": direction_aligned,
            "timestamp": vehicle.get("timestamp"),
            "age_seconds": vehicle.get("age_seconds"),
            "freshness": vehicle.get("freshness"),
            "cross_track_distance_m": round(cross),
            "distance_to_board_m": round(distance_to_board),
            "straight_line_distance_to_board_m": round(direct_distance_to_board),
            "stop_id": vehicle.get("stop_id"),
            **progress_context,
            "has_passed_boarding_stop": passed_boarding,
            "at_boarding_stop": at_boarding_stop,
            "approach_status": approach_status,
            "approach_message": approach_message,
            "eta_to_board_minutes": eta_minutes,
            "estimated_arrival_at_boarding": eta_time,
            "eta_confidence": confidence,
            "crowding": route_crowding,
            "stop_arrivals": stop_arrivals,
        }
        leg["live_vehicles"].append(item)

    leg["live_trip_match_count"] = matched_count
    leg["live_route_vehicle_count"] = len(leg["live_vehicles"])
    leg["live_vehicle_match_basis"] = "GTFS route ID + route-shape proximity; direction is verified when a usable GPS bearing is available."
    if leg["live_vehicles"] and matched_count == 0:
        leg["live_schedule_context_note"] += (
            " None of the returned vehicle trip IDs exactly matches this scheduled trip. "
            "Current vehicle locations are useful route activity, but must not be described as the 04:14 scheduled bus."
        )

    priority = {
        "at_boarding_stop": 0,
        "approaching": 1,
        "near_boarding_stop_unconfirmed": 2,
        "direction_unverified": 3,
        "speed_unavailable": 4,
        "on_route_eta_out_of_range": 5,
        "passed_boarding_stop": 6,
    }
    leg["live_vehicles"].sort(key=lambda x: (
        priority.get(x.get("approach_status"), 9),
        x["eta_to_board_minutes"] if x["eta_to_board_minutes"] is not None else 999999,
        x["age_seconds"] if x["age_seconds"] is not None else 999999,
    ))
    leg["live_vehicles"] = leg["live_vehicles"][:12]
    leg["live_arrival_basis"] = (
        "GPS-derived ETA only when the vehicle is route-aligned, moving in the selected direction, "
        "and has a usable reported or derived speed. Scheduled average speed is never substituted "
        "for live speed. Zero minutes is reserved for a GPS-confirmed boarding stop."
    )


def live_snapshot_required(payload: dict[str, Any]) -> bool:
    """Fetch GPS only for today's journeys that still have a scheduled departure ahead."""
    travel_date_text = payload.get("date")
    try:
        from datetime import date as date_cls
        travel_date = date_cls.fromisoformat(travel_date_text) if travel_date_text else datetime.now(ZoneInfo(settings.local_timezone)).date()
    except ValueError:
        return False
    now_local = datetime.now(ZoneInfo(settings.local_timezone))
    if travel_date != now_local.date():
        return False
    now_minutes = now_local.hour * 60 + now_local.minute
    return any(
        (minutes if (minutes := time_to_minutes(str(journey.get("departure_time", "")))) is not None else -1) >= now_minutes
        for journey in payload.get("items", [])
    )


def enrich_journeys_with_live(payload: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """Attach stop patterns, historical crowding and validated route-matched GPS information."""
    travel_date_text = payload.get("date")
    from datetime import date as date_cls
    try:
        travel_date = date_cls.fromisoformat(travel_date_text) if travel_date_text else datetime.now(ZoneInfo(settings.local_timezone)).date()
    except ValueError:
        travel_date = datetime.now(ZoneInfo(settings.local_timezone)).date()
    now_local = datetime.now(ZoneInfo(settings.local_timezone))
    today = now_local.date()
    now_minutes = now_local.hour * 60 + now_local.minute
    with database() as conn:
        for journey in payload.get("items", []):
            journey_departure = time_to_minutes(str(journey.get("departure_time", "")))
            journey_is_upcoming = journey_departure is not None and journey_departure >= now_minutes
            if travel_date != today:
                allow_live = False
                status_override = "date_not_current"
            elif not journey_is_upcoming:
                allow_live = False
                status_override = "selected_time_passed"
            else:
                allow_live = True
                status_override = None
            for leg in journey.get("legs", []):
                _enrich_leg(conn, leg, snapshot, travel_date, allow_live, status_override)
    return payload
