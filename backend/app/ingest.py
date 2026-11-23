from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
import sys
import unicodedata
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

try:
    from rapidfuzz import process, fuzz
except Exception:  # optional: exact normalized matching still works without rapidfuzz
    process = None
    fuzz = None

from .config import settings
from .db import connect, initialize_schema

BATCH = 300_000
MISSING = {"", "null", "none", "nan", "n/a", "na", "nil", "-"}


def norm(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", str(value))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def is_missing(value: str | None) -> bool:
    return value is None or str(value).strip().lower() in MISSING


def to_float(value: str | None) -> float:
    if is_missing(value):
        return 0.0
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0


def csv_rows_from_zip(zf: zipfile.ZipFile, basename: str):
    candidates = [
        name for name in zf.namelist()
        if name.split("/")[-1] == basename and not name.startswith("__MACOSX/")
    ]
    if not candidates:
        return None
    stream = zf.open(candidates[0])
    text = io.TextIOWrapper(stream, encoding="utf-8-sig", newline="")
    return csv.DictReader(text)


def batch_insert(conn: sqlite3.Connection, sql: str, rows: Iterable[tuple]) -> int:
    count = 0
    batch: list[tuple] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= BATCH:
            conn.executemany(sql, batch)
            count += len(batch)
            batch.clear()
    if batch:
        conn.executemany(sql, batch)
        count += len(batch)
    return count


def load_static_gtfs(conn: sqlite3.Connection, path: Path) -> dict:
    print(f"[GTFS] Loading {path}")
    stats: dict[str, int] = {}
    with zipfile.ZipFile(path) as zf:
        definitions = {
            "routes.txt": ("routes", "route_id,agency_id,route_long_name,route_short_name,route_desc,route_type", lambda r: (r.get("route_id", ""), r.get("agency_id", ""), r.get("route_long_name", ""), r.get("route_short_name", ""), r.get("route_desc", ""), r.get("route_type", ""))),
            "stops.txt": ("stops", "stop_id,stop_code,stop_name,stop_lat,stop_lon", lambda r: (r.get("stop_id", ""), r.get("stop_code", ""), r.get("stop_name", ""), to_float(r.get("stop_lat")), to_float(r.get("stop_lon")))),
            "trips.txt": ("trips", "trip_id,route_id,service_id,trip_headsign,trip_short_name,direction_id,block_id,shape_id,wheelchair_accessible,bikes_allowed", lambda r: (r.get("trip_id", ""), r.get("route_id", ""), r.get("service_id", ""), r.get("trip_headsign", ""), r.get("trip_short_name", ""), r.get("direction_id", ""), r.get("block_id", ""), r.get("shape_id", ""), r.get("wheelchair_accessible", ""), r.get("bikes_allowed", ""))),
            "stop_times.txt": ("stop_times", "trip_id,arrival_time,departure_time,stop_id,stop_sequence,fare_stage,stop_dist", lambda r: (r.get("trip_id", ""), r.get("arrival_time", ""), r.get("departure_time", ""), r.get("stop_id", ""), int(float(r.get("stop_sequence") or 0)), r.get("fare_stage", ""), to_float(r.get("stop_dist")))),
            "shapes.txt": ("shapes", "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence,shape_dist_traveled", lambda r: (r.get("shape_id", ""), to_float(r.get("shape_pt_lat")), to_float(r.get("shape_pt_lon")), int(float(r.get("shape_pt_sequence") or 0)), to_float(r.get("shape_dist_traveled")))),
            "calendar.txt": ("calendar", "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date", lambda r: (r.get("service_id", ""), *[int(r.get(k) or 0) for k in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]], r.get("start_date", ""), r.get("end_date", ""))),
        }
        for filename, (table, columns, mapper) in definitions.items():
            reader = csv_rows_from_zip(zf, filename)
            if reader is None:
                if filename == "calendar.txt":
                    continue
                raise RuntimeError(f"Required GTFS file {filename} not found")
            conn.execute(f"DELETE FROM {table}")
            placeholders = ",".join("?" for _ in columns.split(","))
            sql = f"INSERT OR REPLACE INTO {table} ({columns}) VALUES ({placeholders})"
            rows = (mapper(row) for row in reader)
            stats[table] = batch_insert(conn, sql, rows)
            conn.commit()
            print(f"[GTFS] {table}: {stats[table]:,}")

    # Select one deterministic representative scheduled trip per route.
    # This is a proxy for route order, not a claim that every route variant is identical.
    conn.execute("DELETE FROM route_stop_order")
    conn.execute("""
        INSERT OR REPLACE INTO route_stop_order(route_id, stop_sequence, stop_id)
        SELECT chosen.route_id, st.stop_sequence, st.stop_id
        FROM (SELECT route_id, MIN(trip_id) AS trip_id FROM trips GROUP BY route_id) chosen
        JOIN stop_times st ON st.trip_id=chosen.trip_id
    """)
    conn.commit()
    stats["route_stop_order"] = conn.execute("SELECT COUNT(*) FROM route_stop_order").fetchone()[0]
    return stats


def build_name_maps(conn: sqlite3.Connection):
    routes = conn.execute("SELECT route_id, route_short_name, route_long_name FROM routes").fetchall()
    route_map: dict[str, str] = {}
    for row in routes:
        for label in (row["route_short_name"], row["route_long_name"]):
            key = norm(label)
            if key and key not in route_map:
                route_map[key] = row["route_id"]

    stops = conn.execute("SELECT stop_id, stop_name FROM stops").fetchall()
    stop_map: dict[str, str] = {}
    names: list[str] = []
    name_to_id: dict[str, str] = {}
    for row in stops:
        key = norm(row["stop_name"])
        if key:
            stop_map.setdefault(key, row["stop_id"])
            if key not in name_to_id:
                names.append(row["stop_name"])
                name_to_id[key] = row["stop_id"]
    return route_map, stop_map, names, name_to_id


def fuzzy_stop_id(raw: str, stop_map: dict[str, str], names: list[str], name_to_id: dict[str, str]) -> str | None:
    key = norm(raw)
    if not key:
        return None
    if key in stop_map:
        return stop_map[key]
    if process is None or fuzz is None:
        return None
    match = process.extractOne(raw, names, scorer=fuzz.WRatio, score_cutoff=93)
    if not match:
        return None
    return name_to_id.get(norm(match[0]))


def create_indexes(conn: sqlite3.Connection, include_ticket: bool = True) -> None:
    """Build secondary indexes after bulk imports to keep initial ingestion fast."""
    statements = [
        "CREATE INDEX IF NOT EXISTS idx_routes_short_name ON routes(route_short_name)",
        "CREATE INDEX IF NOT EXISTS idx_stops_name ON stops(stop_name)",
        "CREATE INDEX IF NOT EXISTS idx_trips_route ON trips(route_id)",
        "CREATE INDEX IF NOT EXISTS idx_trips_shape ON trips(shape_id)",
        "CREATE INDEX IF NOT EXISTS idx_stop_times_stop ON stop_times(stop_id)",
        "CREATE INDEX IF NOT EXISTS idx_stop_times_trip_stop ON stop_times(trip_id, stop_id)",
        "CREATE INDEX IF NOT EXISTS idx_stop_times_departure ON stop_times(departure_time)",
        "CREATE INDEX IF NOT EXISTS idx_route_order_stop ON route_stop_order(stop_id, route_id)",
    ]
    if include_ticket:
        statements.extend([
            "CREATE INDEX IF NOT EXISTS idx_ticket_route_hourly ON ticket_route_hourly(route_id, day_type, hour)",
            "CREATE INDEX IF NOT EXISTS idx_ticket_od_route ON ticket_od_hourly(route_id, start_stop_id, end_stop_id)",
            "CREATE INDEX IF NOT EXISTS idx_ticket_segment_query ON ticket_segment_hourly(route_id, day_type, hour, from_stop_id, to_stop_id)",
        ])
    for sql in statements:
        conn.execute(sql)
    conn.commit()


def load_tickets(conn: sqlite3.Connection, path: Path) -> dict:
    """Stream the ticket CSV into a temporary stage; SQLite performs the group-bys."""
    print(f"[TICKETS] Preparing {path}", flush=True)
    route_map, stop_map, stop_names, stop_name_to_id = build_name_maps(conn)
    ticket_routes: set[str] = set()
    unique_stop_names: set[str] = set()
    total = 0
    with zipfile.ZipFile(path) as zf:
        csv_candidates = [n for n in zf.namelist() if n.lower().endswith(".csv") and not n.startswith("__MACOSX/") and not n.split("/")[-1].startswith("._")]
        if len(csv_candidates) != 1:
            raise RuntimeError(f"Expected one ticket CSV, found: {csv_candidates}")
        csv_name = csv_candidates[0]
        with zf.open(csv_name) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
            required = {"passenger_count", "amount", "vehicle_number", "route", "end_stop_name", "start_stop_name", "created_at", "is_ac"}
            missing_cols = required - set(reader.fieldnames or [])
            if missing_cols:
                raise RuntimeError(f"Ticket CSV missing fields: {sorted(missing_cols)}")
            for row in reader:
                total += 1
                ticket_routes.add((row.get("route") or "").strip())
                unique_stop_names.add((row.get("start_stop_name") or "").strip())
                unique_stop_names.add((row.get("end_stop_name") or "").strip())
                if total % 500_000 == 0:
                    print(f"[TICKETS] Alias scan: {total:,}", flush=True)

        print(f"[TICKETS] Found {len(ticket_routes):,} ticket route values and {len(unique_stop_names):,} stop-name values", flush=True)
        stop_alias: dict[str, str | None] = {}
        fuzzy_used = 0
        for raw_name in unique_stop_names:
            key = norm(raw_name)
            if not key:
                stop_alias[raw_name] = None
            elif key in stop_map:
                stop_alias[raw_name] = stop_map[key]
            else:
                stop_alias[raw_name] = fuzzy_stop_id(raw_name, stop_map, stop_names, stop_name_to_id)
                fuzzy_used += 1
        matched_stop_aliases = sum(1 for value in stop_alias.values() if value)
        print(f"[TICKETS] Matched {matched_stop_aliases:,}/{len(stop_alias):,} unique stop names; fuzzy checks: {fuzzy_used:,}", flush=True)

        conn.execute("DELETE FROM ticket_route_hourly")
        conn.execute("DELETE FROM ticket_od_hourly")
        conn.execute("DELETE FROM ticket_segment_hourly")
        conn.commit()
        conn.execute("PRAGMA temp_store=FILE")
        conn.execute("DROP TABLE IF EXISTS temp.ticket_raw_stage")
        conn.execute("""
            CREATE TEMP TABLE ticket_raw_stage (
                route_id TEXT NOT NULL, service_date TEXT NOT NULL, hour INTEGER NOT NULL,
                day_type TEXT NOT NULL, passenger_journeys REAL NOT NULL,
                vehicle_known_count INTEGER NOT NULL, ac_ticket_count INTEGER NOT NULL,
                fare_total REAL NOT NULL, start_stop_id TEXT, end_stop_id TEXT
            )
        """)
        batch: list[tuple] = []
        unmatched_routes = 0
        invalid_dates = 0
        missing_vehicle = 0
        mapped_board = 0
        mapped_alight = 0
        matched_route_records = 0
        processed = 0
        with zf.open(csv_name) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
            for row in reader:
                processed += 1
                route_id = route_map.get(norm(row.get("route")))
                vehicle_known = 0 if is_missing(row.get("vehicle_number")) else 1
                missing_vehicle += 0 if vehicle_known else 1
                if not route_id:
                    unmatched_routes += 1
                    continue
                matched_route_records += 1
                try:
                    created = datetime.fromisoformat((row.get("created_at") or "").strip().replace("Z", "+00:00"))
                except ValueError:
                    invalid_dates += 1
                    continue
                start_raw = (row.get("start_stop_name") or "").strip()
                end_raw = (row.get("end_stop_name") or "").strip()
                start_id = stop_alias.get(start_raw)
                end_id = stop_alias.get(end_raw)
                mapped_board += 1 if start_id else 0
                mapped_alight += 1 if end_id else 0
                day_type = "weekend" if created.weekday() >= 5 else "weekday"
                is_ac = 1 if str(row.get("is_ac", "")).strip().lower() in {"true", "1", "yes"} else 0
                batch.append((route_id, created.date().isoformat(), created.hour, day_type,
                              max(0.0, to_float(row.get("passenger_count"))), vehicle_known,
                              is_ac, to_float(row.get("amount")), start_id, end_id))
                if len(batch) >= BATCH:
                    conn.executemany("INSERT INTO ticket_raw_stage VALUES (?,?,?,?,?,?,?,?,?,?)", batch)
                    conn.commit()
                    batch.clear()
                if processed % 500_000 == 0:
                    print(f"[TICKETS] Staged {processed:,}/{total:,} rows", flush=True)
        if batch:
            conn.executemany("INSERT INTO ticket_raw_stage VALUES (?,?,?,?,?,?,?,?,?,?)", batch)
            conn.commit()

    print("[TICKETS] Indexing staging rows…", flush=True)
    conn.execute("CREATE INDEX temp.idx_stage_route_bucket ON ticket_raw_stage(route_id,service_date,hour,day_type)")
    conn.execute("CREATE INDEX temp.idx_stage_od_bucket ON ticket_raw_stage(route_id,service_date,hour,day_type,start_stop_id,end_stop_id)")
    conn.commit()

    print("[TICKETS] Aggregating route-hour demand…", flush=True)
    conn.execute("""
        INSERT INTO ticket_route_hourly
        SELECT route_id, service_date, hour, day_type,
               SUM(passenger_journeys), COUNT(*), SUM(vehicle_known_count),
               SUM(ac_ticket_count), SUM(fare_total)
        FROM ticket_raw_stage GROUP BY route_id, service_date, hour, day_type
    """)
    conn.commit()

    print("[TICKETS] Aggregating origin/destination pairs…", flush=True)
    conn.execute("""
        INSERT INTO ticket_od_hourly
        SELECT route_id, service_date, hour, day_type, start_stop_id, end_stop_id,
               SUM(passenger_journeys), COUNT(*), SUM(vehicle_known_count)
        FROM ticket_raw_stage
        WHERE start_stop_id IS NOT NULL AND end_stop_id IS NOT NULL AND start_stop_id<>end_stop_id
        GROUP BY route_id, service_date, hour, day_type, start_stop_id, end_stop_id
    """)
    conn.commit()
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ticket_od_route_start ON ticket_od_hourly(route_id,start_stop_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ticket_od_route_end ON ticket_od_hourly(route_id,end_stop_id)")
    conn.commit()

    print("[TICKETS] Building stop-to-stop demand estimates…", flush=True)
    conn.execute("""
        INSERT INTO ticket_segment_hourly
        SELECT od.route_id, od.service_date, od.hour, od.day_type,
               seg_a.stop_id, seg_b.stop_id,
               SUM(od.passenger_journeys), SUM(od.ticket_count), SUM(od.vehicle_known_count)
        FROM ticket_od_hourly od
        JOIN route_stop_order board
          ON board.route_id=od.route_id AND board.stop_id=od.start_stop_id
        JOIN route_stop_order alight
          ON alight.route_id=od.route_id AND alight.stop_id=od.end_stop_id
             AND alight.stop_sequence>board.stop_sequence
        JOIN route_stop_order seg_a
          ON seg_a.route_id=od.route_id
             AND seg_a.stop_sequence>=board.stop_sequence
             AND seg_a.stop_sequence<alight.stop_sequence
        JOIN route_stop_order seg_b
          ON seg_b.route_id=seg_a.route_id
             AND seg_b.stop_sequence=seg_a.stop_sequence+1
        GROUP BY od.route_id, od.service_date, od.hour, od.day_type,
                 seg_a.stop_id, seg_b.stop_id
    """)
    conn.commit()
    segment_count = conn.execute("SELECT COUNT(*) FROM ticket_segment_hourly").fetchone()[0]
    od_count = conn.execute("SELECT COUNT(*) FROM ticket_od_hourly").fetchone()[0]
    route_buckets = conn.execute("SELECT COUNT(*) FROM ticket_route_hourly").fetchone()[0]
    conn.execute("DROP TABLE IF EXISTS temp.ticket_raw_stage")
    conn.commit()

    summary = {
        "source_file": path.name,
        "total_records": total,
        "route_matched_records": matched_route_records,
        "route_match_percentage": round(matched_route_records / total * 100, 2) if total else 0,
        "unique_ticket_routes": len([r for r in ticket_routes if norm(r) in route_map]),
        "unmatched_route_records": unmatched_routes,
        "invalid_timestamp_records": invalid_dates,
        "missing_vehicle_number_records": missing_vehicle,
        "missing_vehicle_number_percentage": round(missing_vehicle / total * 100, 2) if total else 0,
        "boarding_stop_matched_records": mapped_board,
        "boarding_stop_match_percentage": round(mapped_board / max(1, matched_route_records) * 100, 2),
        "alighting_stop_matched_records": mapped_alight,
        "alighting_stop_match_percentage": round(mapped_alight / max(1, matched_route_records) * 100, 2),
        "unique_ticket_stop_names": len(unique_stop_names),
        "matched_ticket_stop_names": matched_stop_aliases,
        "fuzzy_stop_alias_checks": fuzzy_used,
        "route_hour_buckets": route_buckets,
        "od_groups": od_count,
        "segment_aggregates": segment_count,
        "date_range": {
            "start": conn.execute("SELECT MIN(service_date) FROM ticket_route_hourly").fetchone()[0],
            "end": conn.execute("SELECT MAX(service_date) FROM ticket_route_hourly").fetchone()[0],
        },
        "methodology_note": "Ticket-derived demand proxy, not verified onboard occupancy. Segment aggregation uses normalized/fuzzy stop aliases and a representative scheduled stop order per route. Vehicle number is missing on a substantial share of records.",
    }
    conn.execute("INSERT OR REPLACE INTO ingestion_meta(key,value) VALUES ('ticket_summary',?)", (json.dumps(summary, indent=2),))
    conn.execute("INSERT OR REPLACE INTO ingestion_meta(key,value) VALUES ('ticket_ingested_at',datetime('now'))")
    conn.commit()
    print("[TICKETS] Completed summary:", json.dumps(summary, indent=2), flush=True)
    return summary


def ingest(gtfs_path: Path | None = None, ticket_path: Path | None = None, db_path: Path | None = None):
    gtfs_path = gtfs_path or settings.gtfs_zip_path
    ticket_path = ticket_path or settings.ticket_zip_path
    db_path = db_path or settings.database_path
    if not gtfs_path.exists():
        raise FileNotFoundError(f"Static GTFS archive not found: {gtfs_path}")
    if not ticket_path.exists():
        raise FileNotFoundError(f"Ticket archive not found: {ticket_path}")
    if db_path.exists():
        db_path.unlink()
    conn = connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("PRAGMA temp_store=FILE")
        conn.execute("PRAGMA cache_size=-120000")
        conn.execute("PRAGMA locking_mode=EXCLUSIVE")
        initialize_schema(conn)
        gtfs_stats = load_static_gtfs(conn, gtfs_path)
        print("[INDEX] Building GTFS search indexes…", flush=True)
        create_indexes(conn, include_ticket=False)
        ticket_summary = load_tickets(conn, ticket_path)
        print("[INDEX] Building ticket query indexes…", flush=True)
        create_indexes(conn)
        for key, value in gtfs_stats.items():
            conn.execute("INSERT OR REPLACE INTO ingestion_meta(key,value) VALUES (?,?)", (f"gtfs_{key}", str(value)))
        conn.execute("INSERT OR REPLACE INTO ingestion_meta(key,value) VALUES ('gtfs_source',?)", (gtfs_path.name,))
        conn.execute("INSERT OR REPLACE INTO ingestion_meta(key,value) VALUES ('db_built_at',datetime('now'))")
        conn.commit()
        conn.execute("PRAGMA optimize")
        print(f"[DONE] Database created: {db_path}")
        return {"gtfs": gtfs_stats, "tickets": ticket_summary}
    finally:
        conn.close()


if __name__ == "__main__":
    ingest()
