from __future__ import annotations

import json
import math
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..config import settings
from ..db import database
from .transit import crowding_for_route, crowding_for_segment, scheduled_departures_for_hour


def _direction_label(short_name: str | None, long_name: str | None, direction_id: str | None = None) -> str:
    value = f"{short_name or ''} {long_name or ''}".strip().upper()
    if "DOWN" in value:
        return "DOWN"
    if "UP" in value:
        return "UP"
    return f"GTFS direction {direction_id}" if direction_id not in (None, "") else "Direction not encoded"


def list_capacity_profiles() -> list[dict[str, Any]]:
    with database() as conn:
        rows = conn.execute(
            """SELECT c.route_id,c.seat_capacity,c.standing_capacity,c.updated_at,c.updated_by,
                      r.route_short_name,r.route_long_name
               FROM operator_route_capacity c LEFT JOIN routes r ON r.route_id=c.route_id
               ORDER BY r.route_short_name"""
        ).fetchall()
        return [dict(row) for row in rows]


def save_capacity_profile(route_id: str, seat_capacity: int, standing_capacity: int, updated_by: str) -> dict[str, Any] | None:
    now = datetime.now(ZoneInfo(settings.local_timezone)).isoformat(timespec="seconds")
    with database() as conn:
        exists = conn.execute("SELECT route_id,route_short_name,route_long_name FROM routes WHERE route_id=?", (route_id,)).fetchone()
        if not exists:
            return None
        conn.execute(
            """INSERT INTO operator_route_capacity(route_id,seat_capacity,standing_capacity,updated_at,updated_by)
               VALUES (?,?,?,?,?)
               ON CONFLICT(route_id) DO UPDATE SET seat_capacity=excluded.seat_capacity,
                 standing_capacity=excluded.standing_capacity,updated_at=excluded.updated_at,updated_by=excluded.updated_by""",
            (route_id, seat_capacity, standing_capacity, now, updated_by),
        )
        conn.commit()
        return {
            "route_id": route_id,
            "route_short_name": exists["route_short_name"],
            "route_long_name": exists["route_long_name"],
            "seat_capacity": seat_capacity,
            "standing_capacity": standing_capacity,
            "total_capacity": seat_capacity + standing_capacity,
            "updated_at": now,
            "updated_by": updated_by,
        }


def delete_capacity_profile(route_id: str) -> bool:
    with database() as conn:
        cur = conn.execute("DELETE FROM operator_route_capacity WHERE route_id=?", (route_id,))
        conn.commit()
        return cur.rowcount > 0


def operator_dashboard(hour: int, day_type: str) -> dict[str, Any]:
    with database() as conn:
        meta = {row["key"]: row["value"] for row in conn.execute("SELECT key,value FROM ingestion_meta")}
        summary = json.loads(meta.get("ticket_summary", "{}"))

        peak_rows = conn.execute(
            """SELECT hour,
                      ROUND(SUM(passenger_journeys) * 1.0 / COUNT(DISTINCT service_date),1) AS avg_ticketed_journeys,
                      SUM(ticket_count) AS ticket_count,
                      COUNT(DISTINCT service_date) AS observed_days,
                      COUNT(DISTINCT route_id) AS routes
               FROM ticket_route_hourly WHERE day_type=? GROUP BY hour ORDER BY avg_ticketed_journeys DESC""",
            (day_type,),
        ).fetchall()
        peak_hours = [dict(r) for r in peak_rows]

        route_rows = conn.execute(
            """SELECT h.route_id,AVG(h.passenger_journeys) AS avg_demand,
                      SUM(h.ticket_count) AS ticket_count,COUNT(DISTINCT h.service_date) AS observed_days,
                      r.route_short_name,r.route_long_name,
                      (SELECT t.direction_id FROM trips t WHERE t.route_id=h.route_id GROUP BY t.direction_id ORDER BY COUNT(*) DESC LIMIT 1) AS direction_id
               FROM ticket_route_hourly h JOIN routes r ON r.route_id=h.route_id
               WHERE h.hour=? AND h.day_type=?
               GROUP BY h.route_id ORDER BY avg_demand DESC""",
            (hour, day_type),
        ).fetchall()
        route_demand = []
        for row in route_rows:
            route_id = str(row["route_id"])
            estimate = crowding_for_route(conn, route_id, hour, day_type)
            capacity = conn.execute("SELECT seat_capacity,standing_capacity FROM operator_route_capacity WHERE route_id=?", (route_id,)).fetchone()
            per_bus = estimate.get("estimated_ticketed_passengers_per_bus")
            median_demand = estimate.get("passenger_journeys_median")
            departures = int(estimate.get("scheduled_departures_in_hour") or 0)
            total_capacity = (int(capacity[0]) + int(capacity[1])) if capacity else None
            pressure = round(float(per_bus) / total_capacity, 2) if per_bus is not None and total_capacity else None
            extra_departures = max(0, math.ceil(float(median_demand) / total_capacity) - departures) if median_demand is not None and total_capacity and departures > 0 else None
            route_demand.append({
                "route_id": route_id,
                "route_short_name": row["route_short_name"] or route_id,
                "route_long_name": row["route_long_name"] or "",
                "direction": _direction_label(row["route_short_name"], row["route_long_name"], row["direction_id"]),
                "average_ticketed_passengers_per_hour": round(float(row["avg_demand"] or 0), 1),
                "estimated_ticketed_passengers_per_bus": per_bus,
                "scheduled_departures_in_hour": departures,
                "ticket_count": int(row["ticket_count"] or 0),
                "observed_days": int(row["observed_days"] or 0),
                "crowding": estimate,
                "capacity_configured": bool(capacity),
                "capacity_pressure_ratio": pressure,
                "potential_extra_departures_per_hour": extra_departures,
            })

        # Rank by ticketed demand per scheduled departure first, then by total
        # hourly ticketed demand. These are evidence rankings, not occupancy counts.
        route_demand.sort(
            key=lambda item: (
                item["estimated_ticketed_passengers_per_bus"] is not None,
                float(item["estimated_ticketed_passengers_per_bus"] or 0),
                float(item["average_ticketed_passengers_per_hour"] or 0),
            ),
            reverse=True,
        )
        for rank, item in enumerate(route_demand, start=1):
            item["rank"] = rank

        segment_rows = conn.execute(
            """SELECT h.route_id,h.from_stop_id,h.to_stop_id,
                      AVG(h.passenger_journeys) AS avg_ticketed_demand,
                      SUM(h.ticket_count) AS ticket_count,
                      COUNT(DISTINCT h.service_date) AS observed_days,
                      r.route_short_name,r.route_long_name,
                      fs.stop_name AS from_stop_name,ts.stop_name AS to_stop_name,
                      (SELECT t.direction_id FROM trips t WHERE t.route_id=h.route_id GROUP BY t.direction_id ORDER BY COUNT(*) DESC LIMIT 1) AS direction_id
               FROM ticket_segment_hourly h
               JOIN routes r ON r.route_id=h.route_id
               JOIN stops fs ON fs.stop_id=h.from_stop_id
               JOIN stops ts ON ts.stop_id=h.to_stop_id
               WHERE h.hour=? AND h.day_type=?
               GROUP BY h.route_id,h.from_stop_id,h.to_stop_id
               HAVING SUM(h.ticket_count)>0
               ORDER BY avg_ticketed_demand DESC LIMIT 120""",
            (hour, day_type),
        ).fetchall()
        segments = []
        per_bus_values: list[float] = []
        for row in segment_rows:
            route_id = str(row["route_id"])
            estimate = crowding_for_segment(conn, route_id, str(row["from_stop_id"]), str(row["to_stop_id"]), hour, day_type)
            # Reuse the same median-by-day estimate exposed to commuters; avoid
            # calculating a second average-based figure for the operator view.
            departures = int(estimate.get("scheduled_departures_in_hour") or 0)
            per_bus = estimate.get("estimated_ticketed_passengers_per_bus")
            median_demand = estimate.get("passenger_journeys_median")
            if per_bus is not None:
                per_bus_values.append(float(per_bus))
            cap = conn.execute("SELECT seat_capacity,standing_capacity FROM operator_route_capacity WHERE route_id=?", (route_id,)).fetchone()
            total_capacity = (int(cap[0]) + int(cap[1])) if cap else None
            pressure = round(float(per_bus) / total_capacity, 2) if per_bus is not None and total_capacity else None
            extra_departures = max(0, math.ceil(float(median_demand) / total_capacity) - departures) if median_demand is not None and total_capacity and departures > 0 else None
            segments.append({
                "route_id": route_id,
                "route_short_name": row["route_short_name"] or route_id,
                "route_long_name": row["route_long_name"] or "",
                "direction": _direction_label(row["route_short_name"], row["route_long_name"], row["direction_id"]),
                "from_stop_id": row["from_stop_id"],
                "from_stop_name": row["from_stop_name"],
                "to_stop_id": row["to_stop_id"],
                "to_stop_name": row["to_stop_name"],
                "average_ticketed_demand": round(float(median_demand if median_demand is not None else row["avg_ticketed_demand"] or 0), 1),
                "estimated_ticketed_passengers_per_bus": round(float(per_bus), 1) if per_bus is not None else None,
                "scheduled_departures_in_hour": departures,
                "ticket_count": int(row["ticket_count"] or 0),
                "observed_days": int(row["observed_days"] or 0),
                "crowding": estimate,
                "capacity_configured": bool(cap),
                "capacity_pressure_ratio": pressure,
                "potential_extra_departures_per_hour": extra_departures,
                "capacity_source": estimate.get("capacity_source", "dilliflow_planning_baseline"),
            })

        # When capacity has not been configured, use a transparent relative priority:
        # segments above the 80th percentile of observed ticketed passengers/departure
        # are flagged for frequency review, not prescribed an exact bus count.
        threshold = sorted(per_bus_values)[max(0, int((len(per_bus_values) - 1) * 0.8))] if per_bus_values else None
        recommendations = []
        for seg in segments:
            per_bus = seg["estimated_ticketed_passengers_per_bus"]
            cap = seg["crowding"].get("total_capacity") if seg["capacity_configured"] else None
            if cap and per_bus is not None and per_bus > cap:
                seg["priority"] = "high"
                extra = seg.get("potential_extra_departures_per_hour")
                extra_text = f" The simple capacity ratio indicates {extra} additional departure(s) per hour for review." if extra is not None else ""
                seg["recommendation"] = f"Review an additional departure on this stretch; the ticketed-load proxy exceeds configured capacity by {per_bus - cap:.1f} passengers per scheduled bus.{extra_text} Validate ticket coverage and field counts before dispatch changes."
            elif cap and per_bus is not None and per_bus >= 0.8 * cap:
                seg["priority"] = "review"
                seg["recommendation"] = "Near the configured capacity threshold. Review headway and vehicle allocation, then validate with field counts before changing dispatch."
            elif per_bus is not None and threshold is not None and per_bus >= threshold:
                seg["priority"] = "review"
                seg["recommendation"] = "High relative ticketed demand per scheduled departure. Review service frequency and validate with field counts; this is a relative demand signal, not proof of overcrowding."
            else:
                seg["priority"] = "monitor"
                seg["recommendation"] = "Continue monitoring this stretch against historical ticket demand."
            if seg["priority"] in {"high", "review"}:
                recommendations.append(seg)

        # Keep the investigation list complete; recommendations are a separate,
        # compact action queue so operators can inspect evidence before deciding.
        priority_order = {"high": 0, "review": 1, "monitor": 2}
        segments.sort(key=lambda item: (
            priority_order.get(item.get("priority", "monitor"), 2),
            -(float(item.get("estimated_ticketed_passengers_per_bus") or 0)),
            -int(item.get("ticket_count") or 0),
        ))
        investigations = segments[:60]

        service_recommendations: list[dict[str, Any]] = []
        for seg in recommendations[:10]:
            priority = seg["priority"]
            if priority == "high":
                action = "Escalate this stretch for a capacity and headway review. Validate with onboard counts before changing dispatch."
                title = "Configured capacity threshold exceeded"
                evidence = f"~{seg['estimated_ticketed_passengers_per_bus']:.1f} ticketed passengers per scheduled bus against the verified {seg['crowding']['total_capacity']} passenger route profile."
            else:
                action = "Review scheduled headway and conduct a targeted passenger count during this time bucket. Consider a trial additional departure only after field validation."
                title = "High relative demand per departure"
                value = seg.get("estimated_ticketed_passengers_per_bus")
                evidence = f"{value:.1f} ticketed passengers per scheduled bus; {seg['ticket_count']:,} ticket records across {seg['observed_days']} observed days." if value is not None else f"{seg['ticket_count']:,} ticket records across {seg['observed_days']} observed days."
            service_recommendations.append({
                "priority": priority,
                "title": title,
                "route_id": seg["route_id"],
                "route_short_name": seg["route_short_name"],
                "direction": seg["direction"],
                "segment": f"{seg['from_stop_name']} → {seg['to_stop_name']}",
                "evidence": evidence,
                "action": action,
                "type": "segment_service_review",
            })

        for route in route_demand:
            pressure = route.get("capacity_pressure_ratio")
            if pressure is not None and pressure >= 0.8:
                service_recommendations.append({
                    "priority": "high" if pressure >= 1 else "review",
                    "title": "Route approaching configured capacity",
                    "route_id": route["route_id"],
                    "route_short_name": route["route_short_name"],
                    "direction": route["direction"],
                    "segment": "Route-wide reference",
                    "evidence": f"Estimated ticketed load is {pressure:.0%} of the operator-configured total capacity per scheduled bus.",
                    "action": "Review headway, vehicle allocation and field counts for this hour before changing service.",
                    "type": "route_capacity_review",
                })
            if len(service_recommendations) >= 12:
                break

        if not service_recommendations:
            top_route = route_demand[0] if route_demand else None
            if top_route:
                service_recommendations.append({
                    "priority": "monitor",
                    "title": "Maintain monitoring on the highest-demand route",
                    "route_id": top_route["route_id"],
                    "route_short_name": top_route["route_short_name"],
                    "direction": top_route["direction"],
                    "segment": "Route-wide reference",
                    "evidence": f"{top_route['average_ticketed_passengers_per_hour']:.1f} average ticketed journeys per observed day-hour in this bucket.",
                    "action": "Keep the current timetable under review and compare this signal with fresh field counts and the next data refresh.",
                    "type": "monitoring",
                })
            else:
                service_recommendations.append({
                    "priority": "monitor",
                    "title": "No matched demand records in this time bucket",
                    "route_id": "",
                    "route_short_name": "Network",
                    "direction": "All directions",
                    "segment": "Network-wide",
                    "evidence": "The selected time/day filter did not return route-hour records.",
                    "action": "Switch the hour or service-day filter. Do not infer that buses are empty or that service is unnecessary.",
                    "type": "data_coverage_review",
                })

        high_pressure_routes = sum(1 for r in route_demand if r.get("capacity_pressure_ratio") is not None and r["capacity_pressure_ratio"] >= 0.9)
        capacity_profiles = conn.execute("SELECT COUNT(*) FROM operator_route_capacity").fetchone()[0]
        total_routes = conn.execute("SELECT COUNT(DISTINCT route_id) FROM ticket_route_hourly").fetchone()[0]
        quality = {
            "route_match_percentage": float(summary.get("route_match_percentage", 0) or 0),
            "boarding_stop_match_percentage": float(summary.get("boarding_stop_match_percentage", 0) or 0),
            "alighting_stop_match_percentage": float(summary.get("alighting_stop_match_percentage", 0) or 0),
            "missing_vehicle_number_percentage": float(summary.get("missing_vehicle_number_percentage", 0) or 0),
            "total_ticket_records": int(summary.get("total_records", 0) or 0),
            "matched_route_records": int(summary.get("route_matched_records", 0) or 0),
            "unmatched_route_records": int(summary.get("unmatched_route_records", 0) or 0),
        }
        return {
            "period": summary.get("date_range", {"start": "2026-10-01", "end": "2026-10-31"}),
            "selected_hour": hour,
            "day_type": day_type,
            "summary": {
                "ticket_records": int(summary.get("total_records", 0)),
                "route_matched_records": int(summary.get("route_matched_records", 0)),
                "route_match_percentage": summary.get("route_match_percentage", 0),
                "missing_vehicle_number_percentage": summary.get("missing_vehicle_number_percentage", 0),
                "boarding_stop_match_percentage": summary.get("boarding_stop_match_percentage", 0),
                "alighting_stop_match_percentage": summary.get("alighting_stop_match_percentage", 0),
                "routes_with_ticket_data": int(total_routes or 0),
                "capacity_profiles_configured": int(capacity_profiles or 0),
                "routes_near_capacity": high_pressure_routes,
            },
            "data_quality": quality,
            "peak_hours": peak_hours,
            "route_demand": route_demand,
            "priority_segments": recommendations[:30],
            "investigation_segments": investigations,
            "service_recommendations": service_recommendations[:12],
            "segments_reviewed": len(segments),
            "capacity_profiles": int(capacity_profiles or 0),
            "methodology": "Ticketed passenger journeys per scheduled bus are estimated from the median daily ticket passenger count for a route/segment/hour divided by GTFS scheduled departures at that route origin/segment start. This is a historical observed-ticket proxy, not verified total onboard occupancy. Capacity bands only activate after an operator enters verified seat and standing capacity for a route. Without verified capacity, rankings are relative and recommendations request review rather than prescribing an exact number of buses.",
        }
