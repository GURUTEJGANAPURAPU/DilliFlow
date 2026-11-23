
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
load_dotenv(BACKEND_DIR / ".env")


def _path_env(name: str, default: Path) -> Path:
    value = os.getenv(name, "").strip()
    return Path(value).expanduser().resolve() if value else default.resolve()


class Settings:
    app_name = "DilliFlow API"
    api_prefix = "/api"

    database_path = _path_env(
        "DILLIFLOW_DB_PATH",
        BACKEND_DIR / "data" / "processed" / "dilliflow.sqlite",
    )

    turso_database_url = os.getenv("TURSO_DATABASE_URL", "").strip()
    turso_auth_token = os.getenv("TURSO_AUTH_TOKEN", "").strip()

    transport_api_key = os.getenv("TRANSPORT_STACK_API_KEY", "").strip()
    gtfs_zip_path = _path_env(
        "GTFS_ZIP_PATH",
        BACKEND_DIR / "data" / "raw" / "delhi_buses_static_gtfs_v1.zip",
    )
    ticket_zip_path = _path_env(
        "TICKET_ZIP_PATH",
        BACKEND_DIR / "data" / "raw" / "October-Delhi.csv.zip",
    )

    poll_interval_seconds = max(15, int(os.getenv("POLL_INTERVAL_SECONDS", "30")))

    cors_origins = [
        x.strip()
        for x in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if x.strip()
    ]

    live_feed_url = os.getenv(
        "LIVE_FEED_URL",
        "https://dts-backend.transportstack.in/api/dataset/otd/get-file?agency=delhi-buses&category=realtime_gtfs&filename=VehiclePositions.pb",
    )

    live_feed_timeout_seconds = max(5, int(os.getenv("LIVE_FEED_TIMEOUT_SECONDS", "40")))
    stale_after_seconds = max(90, int(os.getenv("STALE_AFTER_SECONDS", "300")))
    local_timezone = os.getenv("APP_TIMEZONE", "Asia/Kolkata")

    operator_id = os.getenv("OPERATOR_ID", "").strip()
    operator_password = os.getenv("OPERATOR_PASSWORD", "")
    operator_token_secret = os.getenv("OPERATOR_TOKEN_SECRET", "")
    operator_token_ttl_seconds = max(
        900,
        int(os.getenv("OPERATOR_TOKEN_TTL_SECONDS", "28800")),
    )


settings = Settings()
