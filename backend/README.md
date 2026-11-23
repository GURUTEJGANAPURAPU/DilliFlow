# DilliFlow FastAPI backend

## Setup (Windows PowerShell)

From the project root, run `..\setup_windows.ps1` (recommended). For a backend-only setup:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and add `TRANSPORT_STACK_API_KEY` only when enabling the live feed. Keep the key server-side; never place it in a `VITE_` variable or frontend source.

## Prepare the local database

```powershell
python -m app.ingest
```

This reads the original GTFS and ticket ZIP archives, creates a SQLite database, indexes the GTFS network and generates route-hour, OD and estimated stop-segment aggregates. It is a first-run build; rerun after replacing the source datasets.

## Run API

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API docs: http://127.0.0.1:8000/docs

## Verify API

With the backend running:

```powershell
python scripts/smoke_test.py
```

## Data and interpretation

- Static GTFS supplies route, stop, trip, schedule and shape information.
- The October 2026 ticket file supplies historical ticket-demand signals.
- GTFS-Realtime supplies vehicle positions only when a valid server-side API key is configured.
- Ticket-derived crowding levels are relative demand proxies, not measurements of onboard passenger occupancy.
- Vehicle-level ticket attribution is incomplete: 48.52% of records have no vehicle number.
- Segment demand is distributed over a representative GTFS stop order per route. The data-quality endpoint exposes matching coverage and limitations.

## Deployment

Host the frontend separately (for example, Vercel) and FastAPI on a service with persistent storage. Set `CORS_ORIGINS`, `TRANSPORT_STACK_API_KEY` and the data paths in the backend environment. The SQLite database must be on persistent writable storage. For larger multi-user production traffic, migrate the analytics store to PostgreSQL/PostGIS and add scheduled ingestion, observability, backups, access controls and rate limiting.
