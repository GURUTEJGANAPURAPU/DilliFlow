from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .db import database, ensure_runtime_schema
from .services.live_feed import live_feed_service
from .services.transit import (
    crowding_overview, crowding_routes, crowding_segments, crowding_trends,
    get_route, list_routes, list_stops, search_journeys, stop_crowding_details,
)
from .services.realtime_journey import enrich_journeys_with_live, live_snapshot_required
from .security import create_operator_token, verify_operator_credentials, verify_operator_token
from .services.operator import operator_dashboard, list_capacity_profiles, save_capacity_profile, delete_capacity_profile

@asynccontextmanager
async def app_lifespan(_: FastAPI):
    startup_runtime_schema()
    yield


app = FastAPI(
    title="DilliFlow API",
    description="Delhi bus journey planning, historical ticket-demand intelligence, and live vehicle positions.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=app_lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


def db_ready() -> bool:
    if not settings.database_path.exists() or settings.database_path.stat().st_size <= 0:
        return False
    try:
        with database() as conn:
            row = conn.execute("SELECT 1 FROM ingestion_meta WHERE key='db_built_at'").fetchone()
            return row is not None
    except Exception:
        return False


def require_db() -> None:
    if not db_ready():
        raise HTTPException(
            status_code=503,
            detail="Transit database is not prepared. Run: python -m app.ingest",
        )


class OperatorLoginBody(BaseModel):
    operator_id: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=512)


class RouteCapacityBody(BaseModel):
    seat_capacity: int = Field(ge=1, le=500)
    standing_capacity: int = Field(ge=0, le=1000)


bearer_scheme = HTTPBearer(auto_error=False)


def startup_runtime_schema() -> None:
    if settings.database_path.exists():
        try:
            ensure_runtime_schema()
        except Exception as exc:
            print(f"[STARTUP] Could not create operator settings table: {exc}")


def require_operator(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> str:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Operator login required.", headers={"WWW-Authenticate": "Bearer"})
    payload = verify_operator_token(credentials.credentials, settings.operator_token_secret)
    if not payload:
        raise HTTPException(status_code=401, detail="Operator session is invalid or expired. Please sign in again.", headers={"WWW-Authenticate": "Bearer"})
    return str(payload["sub"])


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {"name": settings.app_name, "version": app.version, "docs": "/docs", "health": "/api/health"}


@app.get("/api/health", tags=["system"])
def health() -> dict[str, Any]:
    counts: dict[str, int] = {}
    meta: dict[str, str] = {}
    if db_ready():
        try:
            with database() as conn:
                stored = {row["key"]: row["value"] for row in conn.execute("SELECT key,value FROM ingestion_meta")}
                key_map = {
                    "routes": "gtfs_routes",
                    "stops": "gtfs_stops",
                    "trips": "gtfs_trips",
                    "stop_times": "gtfs_stop_times",
                    "shapes": "gtfs_shapes",
                }
                for public_name, meta_key in key_map.items():
                    if meta_key in stored:
                        counts[public_name] = int(stored[meta_key])
                summary = json.loads(stored.get("ticket_summary", "{}"))
                counts["ticket_route_hourly"] = int(summary.get("route_hour_buckets", 0))
                counts["ticket_segment_hourly"] = int(summary.get("segment_aggregates", 0))
                for key in ("db_built_at", "gtfs_source", "ticket_ingested_at"):
                    if key in stored:
                        meta[key] = stored[key]
        except Exception as exc:
            return {"status": "degraded", "database_ready": False, "database_error": str(exc), "live_feed_configured": bool(settings.transport_api_key)}
    return {
        "status": "ok" if db_ready() else "setup_required",
        "database_ready": db_ready(),
        "database_path": str(settings.database_path),
        "record_counts": counts,
        "metadata": meta,
        "live_feed_configured": bool(settings.transport_api_key),
        "live_feed_status": "configured" if settings.transport_api_key else "not_configured",
        "poll_interval_seconds": settings.poll_interval_seconds,
        "operator_login_configured": bool(settings.operator_id and settings.operator_password and settings.operator_token_secret),
    }


@app.get("/api/meta", tags=["system"])
def metadata() -> dict[str, Any]:
    require_db()
    with database() as conn:
        stored = {row["key"]: row["value"] for row in conn.execute("SELECT key,value FROM ingestion_meta")}
        summary = json.loads(stored.get("ticket_summary", "{}"))
        counts = {
            "routes": int(stored.get("gtfs_routes", 0)),
            "stops": int(stored.get("gtfs_stops", 0)),
            "trips": int(stored.get("gtfs_trips", 0)),
            "stop_times": int(stored.get("gtfs_stop_times", 0)),
            "shapes": int(stored.get("gtfs_shapes", 0)),
        }
        return {"product": "DilliFlow", "counts": counts, "ticket_summary": summary}


@app.get("/api/routes", tags=["transit"])
def routes(q: str | None = None, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    require_db()
    return list_routes(q=q, limit=limit, offset=offset)


@app.get("/api/routes/{route_id}", tags=["transit"])
def route_detail(route_id: str):
    require_db()
    result = get_route(route_id)
    if not result:
        raise HTTPException(status_code=404, detail="Route not found")
    return result


@app.get("/api/stops", tags=["transit"])
def stops(q: str | None = None, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    require_db()
    return list_stops(q=q, limit=limit, offset=offset)


@app.get("/api/stops/search", tags=["transit"])
def stop_search(q: str = Query(..., min_length=1), limit: int = Query(12, ge=1, le=250)):
    require_db()
    return list_stops(q=q, limit=limit, offset=0)


@app.get("/api/stops/{stop_id}/crowding", tags=["crowding"])
def stop_crowding(stop_id: str):
    require_db()
    result = stop_crowding_details(stop_id)
    if not result:
        raise HTTPException(status_code=404, detail="Stop not found")
    return result


@app.get("/api/live-vehicles", tags=["live"])
def live_vehicles(refresh: bool = False):
    snapshot = live_feed_service.snapshot(force=refresh)
    return snapshot


@app.get("/api/crowding/overview", tags=["crowding"])
def crowding_summary():
    require_db()
    return crowding_overview()


@app.get("/api/crowding/routes", tags=["crowding"])
def route_crowding(
    hour: int | None = Query(None, ge=0, le=23),
    day_type: str | None = Query(None, pattern="^(weekday|weekend)$"),
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
):
    require_db()
    return crowding_routes(hour=hour, day_type=day_type, q=q, limit=limit)


@app.get("/api/crowding/segments", tags=["crowding"])
def segment_crowding(
    route_id: str = Query(..., min_length=1),
    hour: int | None = Query(None, ge=0, le=23),
    day_type: str | None = Query(None, pattern="^(weekday|weekend)$"),
):
    require_db()
    return crowding_segments(route_id=route_id, hour=hour, day_type=day_type)


@app.get("/api/crowding/trends", tags=["crowding"])
def crowding_trend(route_id: str | None = None, day_type: str = Query("weekday", pattern="^(weekday|weekend)$")):
    require_db()
    return crowding_trends(route_id=route_id, day_type=day_type)


@app.get("/api/data-quality", tags=["crowding"])
def data_quality():
    require_db()
    with database() as conn:
        row = conn.execute("SELECT value FROM ingestion_meta WHERE key='ticket_summary'").fetchone()
        return json.loads(row[0]) if row else {"status": "not_available", "message": "Ticket ingestion summary is not present."}


@app.get("/api/journeys/search", tags=["journeys"])
def journeys(
    origin_stop_id: str = Query(..., min_length=1),
    destination_stop_id: str = Query(..., min_length=1),
    travel_date: date = Query(...),
    departure_time: str = Query(..., pattern=r"^\d{2}:\d{2}(:\d{2})?$"),
    max_transfers: int = Query(1, ge=0, le=1),
):
    require_db()
    result = search_journeys(origin_stop_id, destination_stop_id, travel_date, departure_time, max_transfers)
    should_fetch_live = live_snapshot_required(result)
    snapshot = live_feed_service.snapshot() if should_fetch_live else {
        "status": "not_requested",
        "message": "Live feed is only requested for today's journeys with a scheduled departure still ahead.",
        "vehicles": [],
        "returned_count": 0,
    }
    return enrich_journeys_with_live(result, snapshot)


@app.post("/api/operator/login", tags=["operator"])
def operator_login(body: OperatorLoginBody):
    if not (settings.operator_id and settings.operator_password and settings.operator_token_secret):
        raise HTTPException(status_code=503, detail="Operator access is not configured. Set OPERATOR_ID, OPERATOR_PASSWORD and OPERATOR_TOKEN_SECRET in backend/.env.")
    if not verify_operator_credentials(body.operator_id, body.password, settings.operator_id, settings.operator_password):
        raise HTTPException(status_code=401, detail="Incorrect operator ID or password.")
    token = create_operator_token(settings.operator_id, settings.operator_token_secret, settings.operator_token_ttl_seconds)
    return {"access_token": token, "token_type": "bearer", "expires_in": settings.operator_token_ttl_seconds, "operator_id": settings.operator_id}


@app.get("/api/operator/dashboard", tags=["operator"])
def operator_dashboard_data(
    operator_id: str = Depends(require_operator),
    hour: int = Query(8, ge=0, le=23),
    day_type: str = Query("weekday", pattern="^(weekday|weekend)$"),
):
    require_db()
    result = operator_dashboard(hour=hour, day_type=day_type)
    result["operator_id"] = operator_id
    return result


@app.get("/api/operator/capacities", tags=["operator"])
def operator_capacities(operator_id: str = Depends(require_operator)):
    require_db()
    return {"items": list_capacity_profiles(), "configured_by": operator_id}


@app.put("/api/operator/capacities/{route_id}", tags=["operator"])
def update_route_capacity(route_id: str, body: RouteCapacityBody, operator_id: str = Depends(require_operator)):
    require_db()
    result = save_capacity_profile(route_id, body.seat_capacity, body.standing_capacity, operator_id)
    if not result:
        raise HTTPException(status_code=404, detail="Route not found. Capacity was not saved.")
    return result


@app.delete("/api/operator/capacities/{route_id}", tags=["operator"])
def remove_route_capacity(route_id: str, operator_id: str = Depends(require_operator)):
    require_db()
    if not delete_capacity_profile(route_id):
        raise HTTPException(status_code=404, detail="No capacity profile exists for this route.")
    return {"deleted": True, "route_id": route_id}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception):
    # Keep technical detail in local logs; avoid exposing stack traces to API consumers.
    print(f"[API ERROR] {request.method} {request.url.path}: {exc}")
    return JSONResponse(status_code=500, content={"detail": "An unexpected server error occurred.", "request_path": request.url.path})
