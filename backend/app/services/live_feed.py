from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

import requests
try:
    from google.transit import gtfs_realtime_pb2
except ImportError:  # optional until a live API key is configured
    gtfs_realtime_pb2 = None

from ..config import settings
from ..db import database


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 6_371_000 * 2 * asin(min(1.0, sqrt(a)))


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from the previous GPS sample to the current sample."""
    from math import atan2, cos, degrees, radians, sin
    p1, p2 = radians(lat1), radians(lat2)
    dl = radians(lon2 - lon1)
    y = sin(dl) * cos(p2)
    x = cos(p1) * sin(p2) - sin(p1) * cos(p2) * cos(dl)
    return (degrees(atan2(y, x)) + 360.0) % 360.0


class LiveFeedService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot: dict[str, Any] = {
            "status": "not_configured",
            "message": "Add TRANSPORT_STACK_API_KEY to backend/.env to enable live locations.",
            "vehicles": [],
            "returned_count": 0,
            "fetched_at": None,
            "feed_timestamp": None,
        }
        self._last_fetch_monotonic = 0.0

    def snapshot(self, force: bool = False) -> dict[str, Any]:
        if not settings.transport_api_key:
            result = dict(self._snapshot)
            result["status"] = "not_configured"
            result["message"] = "Live feed is not configured. Add TRANSPORT_STACK_API_KEY to backend/.env."
            return result

        if gtfs_realtime_pb2 is None:
            result = dict(self._snapshot)
            result["status"] = "error"
            result["message"] = "Live decoding dependency is missing. Install backend requirements.txt."
            return result

        now = time.monotonic()
        if not force and now - self._last_fetch_monotonic < settings.poll_interval_seconds:
            return dict(self._snapshot)

        if not self._lock.acquire(blocking=False):
            return dict(self._snapshot)
        try:
            now = time.monotonic()
            if not force and now - self._last_fetch_monotonic < settings.poll_interval_seconds:
                return dict(self._snapshot)
            self._last_fetch_monotonic = now
            try:
                response = requests.get(
                    settings.live_feed_url,
                    headers={"x-api-key": settings.transport_api_key},
                    timeout=settings.live_feed_timeout_seconds,
                )
                if response.status_code == 401:
                    raise RuntimeError("Transport Stack returned 401. Check the API key configured in backend/.env.")
                response.raise_for_status()
                feed = gtfs_realtime_pb2.FeedMessage()
                feed.ParseFromString(response.content)
                route_lookup: dict[str, dict[str, str]] = {}
                try:
                    with database() as conn:
                        route_lookup = {
                            row["route_id"]: {
                                "route_short_name": row["route_short_name"] or row["route_id"],
                                "route_long_name": row["route_long_name"] or "",
                            }
                            for row in conn.execute("SELECT route_id, route_short_name, route_long_name FROM routes")
                        }
                except Exception:
                    route_lookup = {}

                now_utc = datetime.now(timezone.utc)
                previous_by_id = {str(v.get("vehicle_id")): v for v in self._snapshot.get("vehicles", []) if v.get("vehicle_id")}
                vehicles: list[dict[str, Any]] = []
                missing_positions = 0
                for entity in feed.entity:
                    if not entity.HasField("vehicle"):
                        continue
                    vehicle = entity.vehicle
                    if not vehicle.HasField("position"):
                        missing_positions += 1
                        continue
                    position = vehicle.position
                    lat = float(position.latitude)
                    lon = float(position.longitude)
                    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
                        continue
                    trip = vehicle.trip if vehicle.HasField("trip") else None
                    route_id = str(trip.route_id) if trip else ""
                    timestamp = int(vehicle.timestamp) if vehicle.HasField("timestamp") else None
                    age = max(0.0, (now_utc.timestamp() - timestamp)) if timestamp else None
                    if timestamp and timestamp - now_utc.timestamp() > 30:
                        freshness = "future_timestamp"
                    elif age is None:
                        freshness = "unknown"
                    elif age <= 90:
                        freshness = "fresh"
                    elif age <= settings.stale_after_seconds:
                        freshness = "delayed"
                    else:
                        freshness = "stale"
                    label = vehicle.vehicle.label if vehicle.HasField("vehicle") else ""
                    vehicle_id = vehicle.vehicle.id if vehicle.HasField("vehicle") else (label or entity.id)
                    route = route_lookup.get(route_id, {})
                    vehicle_key = vehicle_id or entity.id
                    reported_speed = float(position.speed) if position.HasField("speed") else None
                    speed_estimate = reported_speed if reported_speed is not None and 1.0 <= reported_speed <= 22.0 else None
                    speed_source = "gtfs_realtime_reported" if speed_estimate is not None else "unavailable"
                    reported_bearing = float(position.bearing) % 360.0 if position.HasField("bearing") else None
                    bearing_estimate = reported_bearing
                    bearing_source = "gtfs_realtime_reported" if reported_bearing is not None else "unavailable"
                    previous = previous_by_id.get(str(vehicle_key))
                    if previous and timestamp and previous.get("timestamp"):
                        delta_seconds = timestamp - int(previous["timestamp"])
                        if 5 <= delta_seconds <= 180:
                            previous_lat = float(previous["latitude"])
                            previous_lon = float(previous["longitude"])
                            derived_distance = _distance_m(lat, lon, previous_lat, previous_lon)
                            if bearing_estimate is None and derived_distance >= 8.0:
                                bearing_estimate = _bearing_deg(previous_lat, previous_lon, lat, lon)
                                bearing_source = "derived_from_recent_positions"
                            if speed_estimate is None:
                                derived = derived_distance / delta_seconds
                                if 1.0 <= derived <= 22.0:
                                    speed_estimate = derived
                                    speed_source = "derived_from_recent_positions"
                    vehicles.append({
                        "vehicle_id": vehicle_key,
                        "route_id": route_id,
                        "route_short_name": route.get("route_short_name", route_id),
                        "route_long_name": route.get("route_long_name", ""),
                        "trip_id": str(trip.trip_id) if trip and trip.trip_id else None,
                        "schedule_relationship": gtfs_realtime_pb2.TripDescriptor.ScheduleRelationship.Name(trip.schedule_relationship) if trip else None,
                        "latitude": lat,
                        "longitude": lon,
                        "speed_mps": reported_speed,
                        "speed_estimate_mps": round(speed_estimate, 2) if speed_estimate is not None else None,
                        "speed_source": speed_source,
                        "bearing": reported_bearing,
                        "bearing_estimate": round(bearing_estimate, 1) if bearing_estimate is not None else None,
                        "bearing_source": bearing_source,
                        "timestamp": timestamp,
                        "age_seconds": round(age, 1) if age is not None else None,
                        "freshness": freshness,
                        "stop_id": vehicle.stop_id if vehicle.HasField("stop_id") and vehicle.stop_id else None,
                        "current_stop_sequence": int(vehicle.current_stop_sequence) if vehicle.HasField("current_stop_sequence") else None,
                    })

                feed_timestamp = int(feed.header.timestamp) if feed.header.HasField("timestamp") else None
                self._snapshot = {
                    "status": "connected",
                    "message": "Live vehicle positions received from Transport Stack.",
                    "vehicles": vehicles,
                    "returned_count": len(vehicles),
                    "entity_count": len(feed.entity),
                    "missing_position_entities": missing_positions,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "feed_timestamp": feed_timestamp,
                    "feed_version": feed.header.gtfs_realtime_version,
                    "http_status": response.status_code,
                }
            except Exception as exc:
                previous = dict(self._snapshot)
                previous["status"] = "error" if not previous.get("vehicles") else "degraded"
                previous["message"] = str(exc)
                previous["last_error_at"] = datetime.now(timezone.utc).isoformat()
                self._snapshot = previous
        finally:
            self._lock.release()
        return dict(self._snapshot)


live_feed_service = LiveFeedService()
