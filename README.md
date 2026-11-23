# DilliFlow

**Move smarter. Ride calmer.**

DilliFlow is a local-first Delhi bus journey intelligence application. It combines the complete supplied static GTFS network, October 2026 ticket-derived historical demand and an optional live GTFS-Realtime vehicle feed.

## What is included

- React 19 + TypeScript + Vite frontend.
- Python FastAPI backend with read-only REST endpoints.
- Full static GTFS archive and full October ticket CSV archive in `backend/data/raw/`.
- GTFS loader for routes, stops, trips, stop times, calendar and shapes.
- Ticket ingestion that streams the full CSV from its ZIP and builds route-hour, origin/destination and estimated stop-segment aggregates.
- Live GTFS-Realtime Protobuf decoder using the Transport Stack API (key is configured locally).
- Journey search for direct scheduled services and one-transfer options.
- Route-matched live bus arrivals at the selected boarding stop, with map markers and a stop-by-stop arrival timeline for today's trips.
- Historical route/segment crowd badges on itinerary buses and route stops, with low-confidence fallbacks when an exact hour bucket is absent.
- Premium responsive interface: Journey Planner, Live Bus Map, Crowding Insights, Routes & Stops and Methodology.
- Windows PowerShell setup and run scripts.

## Verified full-data ingestion

The full source archives were ingested and the API was exercised against the resulting database in the build environment. The verified counts were:

- Static GTFS: 2,574 routes, 6,862 stops, 80,357 trips, 2,737,136 stop-time rows and 965,607 shape points.
- Ticket file: 2,559,899 source records.
- Ticket route match: 2,514,677 records (98.23%) matched to a GTFS route.
- Ticket vehicle number missing: 1,242,167 records (48.52%).
- Boarding stop mapped: 81.00% of route-matched records; alighting stop mapped: 81.65%.
- Aggregates: 412,970 route/date/hour buckets, 1,511,663 origin/destination groups and 3,411,416 estimated stop-segment aggregates.

These are ingestion and matching statistics, not a claim that the ticket file represents all bus passengers. The generated SQLite database is not bundled; the included `prepare_data.ps1` script recreates it from the full raw archives.

## Important data interpretation

Crowding levels are **historical ticket-demand proxies**, not measured onboard occupancy. They are relative to a route's observed history and should not be read as a bus capacity/seat-availability guarantee. The complete ticket file contains 2,559,899 records; the full-file audit found 1,242,167 missing vehicle numbers (48.52%). Ticket routes and stop names are normalized/reconciled to GTFS; unmatched values are reported and excluded from segment aggregation.

Stop-segment estimates expand ticket origin/destination pairs across a representative GTFS stop sequence for each route. Routes that operate multiple patterns may require more advanced pattern/direction-specific reconciliation before these estimates can be interpreted as precise segment loads. The app labels this limitation explicitly.

GTFS-Realtime vehicle positions are a separate source. Live route IDs are associated with static routes. The observed feed uses ADDED trip descriptors whose trip IDs do not match the static scheduled trip IDs; DilliFlow does not force those trip matches. Journey live ETAs are generated only for the current local service date and only while the selected scheduled departure is still ahead of the current local time. The Journey Planner rechecks today’s active journey options every 30 seconds while an upcoming service is being viewed. Buses are projected onto the selected scheduled route shape, and ETA uses the feed's speed, a speed derived from successive GPS snapshots, or (with low confidence) a scheduled route-average speed fallback. This is an estimate, not an official arrival prediction. A GPS marker indicates the reported position and timestamp, not passenger occupancy.

Bus capacity and ticket-sampling expansion factors are not supplied, so DilliFlow does not invent either.

## Requirements

- Windows 10/11 or Linux/macOS.
- Python 3.11+ (3.12 recommended; the project uses standard Python libraries plus pinned-compatible packages).
- Node.js 20+ and npm.
- Internet connection for installing dependencies and OpenStreetMap tiles.
- For live vehicle positions: a valid Transport Stack API key.

## Quick start on Windows

1. Extract the DilliFlow ZIP to a folder such as `D:\DilliFlow`.
2. Open PowerShell in that folder.
3. Run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup_windows.ps1
```

4. Build the local transit database from the full source archives (one-time first setup):

```powershell
.\prepare_data.ps1
```

5. Start the backend and frontend in separate PowerShell windows:

```powershell
.\run_backend.ps1
```

```powershell
.\run_frontend.ps1
```

Open **http://localhost:5173**. FastAPI docs are at **http://localhost:8000/docs**.

After both windows open, verify the backend from a third PowerShell window:

```powershell
cd D:\DilliFlow\backend
..\.venv\Scripts\python.exe scripts\smoke_test.py
```

The smoke check includes an 80-row stop-search request to guard against the earlier HTTP 422 limit mismatch.

Or launch both services with:

```powershell
.\run_dilliflow.ps1
```

Run that command from the project root (`D:\DilliFlow`). If your current directory is `D:\DilliFlow\backend`, the `backend\run_dilliflow.ps1` wrapper is also provided; run `..\run_dilliflow.ps1` from the project root for the clearest path. The combined launcher opens separate backend and frontend PowerShell windows.

### Configure live bus positions

The app works without the live key: the Live Bus Map will show a clear not-configured state. To enable actual positions:

1. Open `backend\.env`.
2. Set `TRANSPORT_STACK_API_KEY=YOUR_KEY`.
3. Restart the backend.

Do not put the key into a `VITE_` variable, frontend source, Git repository or browser. The frontend never receives the secret.

### Manual setup (if PowerShell scripts are blocked)

Backend:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
Set-Location backend
python -m app.ingest
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend (new terminal):

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

## Backend endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | API/database/live-feed readiness |
| `GET /api/meta` | GTFS counts and ticket-ingestion summary |
| `GET /api/routes?q=&limit=&offset=` | Search/list routes |
| `GET /api/routes/{route_id}` | Representative stop pattern, route shape and route crowding |
| `GET /api/stops?q=&limit=&offset=` | Search/list stops |
| `GET /api/stops/search?q=&limit=` | Stop autocomplete |
| `GET /api/live-vehicles?refresh=true` | Live GTFS-Realtime positions |
| `GET /api/crowding/overview` | Summary and higher ticket-demand routes |
| `GET /api/crowding/routes?hour=&day_type=&q=` | Route-level historical demand |
| `GET /api/crowding/segments?route_id=&hour=&day_type=` | Stop-to-stop demand proxies |
| `GET /api/crowding/trends?day_type=&route_id=` | Hourly historical demand trend |
| `GET /api/data-quality` | Ingestion match/missingness statistics |
| `GET /api/journeys/search?...` | Direct and one-transfer scheduled journey options |

## Data ingestion notes

`python -m app.ingest` reads both full ZIP archives directly. It bulk-loads GTFS first, builds indexes, streams all ticket rows in batches, reconciles route and stop names (fuzzy threshold is conservative), creates aggregates with SQLite, then stores an ingestion-quality summary. The database is generated locally at `backend/data/processed/dilliflow.sqlite` and is ignored by Git.

The first full ingestion can take several minutes depending on CPU, disk speed and SQLite configuration. Do not close the terminal while it is running. If it fails, retain the terminal output/log and rerun after correcting the error; the ingestion rebuilds the local database from the supplied archives.

## Deployment notes

The frontend and backend are separate services. Set `VITE_API_BASE_URL` at frontend build time to the deployed FastAPI URL. Set `CORS_ORIGINS` on the backend to the exact deployed frontend origin. The backend needs access to the raw data ZIPs and a persistent writable disk for the generated SQLite database. Never expose `TRANSPORT_STACK_API_KEY` to the frontend.

For a small hackathon deployment, use a persistent-volume backend host and a static frontend host. A production multi-user deployment should move the analytics database to managed PostgreSQL/PostGIS and add scheduled ingestion, observability, rate limiting, backups and access controls; those managed infrastructure services are not provisioned by this local-first code bundle.

## Attribution

Static timetable/route/stop and vehicle feed data are supplied via the Transport Stack datasets described in the project materials. Map tiles are served by OpenStreetMap contributors; use is subject to OpenStreetMap tile usage policies. The application is not affiliated with DTC or Transport Stack.


## Selected-bus live tracking

Journey Planner supports a passenger flow inspired by live public-transport apps: search between stops, select a scheduled route option, choose an individual route-matched live vehicle, view that vehicle highlighted on the map, follow its live position, inspect the route stops in travel order, and view historical crowd estimates for each segment. Click a bus card or bus marker to focus it. Use the tracking control to pause/resume map-follow mode.

The live feed may provide ADDED trip descriptors that cannot be joined to static GTFS trip IDs. DilliFlow therefore labels route-level vehicle matches separately from exact trip matches. Position tracking can work without a speed sample; ETAs to future stops are shown only when GPS direction and speed are sufficient.


## Challenge alignment and operator workspace

DilliFlow has two workspaces:

- **Commuter dashboard (public):** no sign-in or account is required for Journey Planner, Live Bus Map, Crowding Insights, Routes & Stops or Methodology.
- **Operator Workspace (protected):** operator ID/password authentication protects operational analytics, priority-segment recommendations and route-capacity configuration.

### How the ticket model estimates passengers per bus

Ticket `passenger_count` is aggregated by route, service date and hour. Boarding/alighting pairs are reconciled to GTFS stops and expanded across each consecutive segment in the representative route stop pattern. For a route/segment/hour, DilliFlow takes the median daily ticketed passenger journeys and divides it by the number of GTFS scheduled departures in that hour (at the route origin for route-level summaries, or at the segment's boarding stop for segment summaries). This yields an **estimated ticketed passengers per scheduled bus** proxy. It is not a verified onboard count because the ticket file may not cover every passenger and vehicle numbers are missing on 48.52% of records. No unsupported expansion factor is applied.

### Seats / standing room / crowded labels

The system does not invent bus capacities. An operator must configure verified route-level seat and standing capacities in Operator Workspace. Once configured, commuter crowd badges use the calculated per-bus ticketed-demand proxy against those limits: at/below seats = **Seats likely available**; above seats but at/below total capacity = **Standing room likely**; above total capacity = **Crowded**. These remain historical planning estimates and should be validated against field counts. If a route has no capacity profile, the commuter app displays relative Low / Moderate / High ticket-demand labels instead.

### Configure operator authentication

In `backend/.env`, set these values (do not commit the file):

```env
OPERATOR_ID=your-operator-id
OPERATOR_PASSWORD=use-a-strong-unique-password
OPERATOR_TOKEN_SECRET=use-a-long-random-secret
OPERATOR_TOKEN_TTL_SECONDS=28800
```

Generate a random token secret in PowerShell with:

```powershell
$bytes = New-Object byte[] 48
[System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
[Convert]::ToBase64String($bytes)
```

Paste the printed value into `OPERATOR_TOKEN_SECRET`. Restart FastAPI after editing `.env`. Until all three settings are present, operator sign-in is disabled; commuter pages remain public. Login sessions use signed bearer tokens with an eight-hour default expiry and are held in browser session storage.

### Operator APIs

- `POST /api/operator/login`
- `GET /api/operator/dashboard?hour=8&day_type=weekday` (Bearer token required)
- `GET /api/operator/capacities` (Bearer token required)
- `PUT /api/operator/capacities/{route_id}` (Bearer token required)
- `DELETE /api/operator/capacities/{route_id}` (Bearer token required)

The operator dashboard ranks route/direction and stop-to-stop segments using ticketed passengers per scheduled departure. If capacity is configured and the estimated load exceeds total capacity, it flags a capacity-pressure review and calculates an indicative minimum additional departures per hour. Without capacity profiles, it flags only relative high-demand stretches for review and does not prescribe exact fleet additions.

### Configure the protected Operator Workspace

The public commuter dashboard never requires an account. The Operator Workspace is separate and requires an administrator-configured operator ID and password. From the project root in PowerShell, run:

```powershell
.\configure_operator.ps1
```

The script asks for an operator ID and password, generates a cryptographically random token-signing secret, and updates only the four `OPERATOR_*` keys in `backend/.env`. It preserves the Transport Stack API key and all other environment settings. Use a unique password of at least 12 characters. Restart FastAPI after configuration. Do not share or commit `backend/.env`.

### Problem 2 implementation checklist

| Challenge requirement | DilliFlow implementation |
|---|---|
| Use 4–5 weeks of ticket data | Full October 2026 file (31 calendar days) is ingested locally. |
| Estimate by route and time of day | Route × service-date × hour aggregates, separated into weekday/weekend patterns. |
| Estimate by direction | The supplied GTFS contains separate directional route records for the great majority of services; direction is read from route labels such as UP/DOWN. Routes without an explicit direction label are marked as not encoded rather than guessed. |
| Estimate by stretch between stops | Matched ticket origin/destination pairs are expanded over consecutive stops in the representative GTFS route-stop order and aggregated per segment/hour. |
| Show crowding with each journey option | Journey cards and selected-bus stop timeline display route/segment historical crowding estimates. |
| Faster vs more comfortable choice | Planner supports Fastest and More Comfortable sorting. |
| Seats / standing room / crowded | Enabled only where an operator enters a verified route capacity profile. Without verified capacity the app uses relative Low/Moderate/High ticket-demand labels. |
| Operator/planner audience | Protected Operator Workspace shows peak hours, route/direction demand, priority stop-pair stretches, ticket coverage and capacity profiles. |

The per-bus figure is a proxy: median daily ticketed passenger journeys in the route/segment/hour divided by GTFS scheduled departures in that hour. An all-hours fallback never produces a per-bus number because its time denominator would be inconsistent. No undocumented ticket-capture expansion factor is applied. The app does not claim sensor-measured onboard occupancy.

The GTFS feed has no direction_id values in the inspected static data; direction is represented by separate route IDs and route names for the routes that encode UP/DOWN. For the small set without a clear direction marker, DilliFlow labels direction as unavailable.

Capacity profiles are route-level. Only configure one when the vehicles operating that route share the supplied verified capacity baseline. If fleet vehicle types differ materially, obtain per-vehicle-type capacity data before using capacity-calibrated labels.
