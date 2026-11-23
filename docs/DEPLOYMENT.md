# Deployment

## Local development (recommended first)

Use the Windows scripts from the repository root. Run data ingestion once, then run the API and Vite frontend. Keep the API key in `backend/.env` only.

## Frontend on Vercel

1. Push the `frontend/` folder to a Git repository or configure the frontend project root as `frontend`.
2. Build command: `npm run build`.
3. Output directory: `dist`.
4. Set `VITE_API_BASE_URL` to the public HTTPS URL of the FastAPI service.
5. `vercel.json` is included for SPA route fallback.

## Backend on Render

A starter Blueprint is included in `render.yaml`.

1. Push the project repository to GitHub (avoid committing any real `.env` file or generated database).
2. Create the web service from the Blueprint.
3. Provide `TRANSPORT_STACK_API_KEY` as a secret environment variable on Render.
4. Set `CORS_ORIGINS` to the exact Vercel frontend origin, including `https://` and excluding trailing path segments.
5. Attach the persistent disk configured in the Blueprint. The service builds the database on first start if the persistent file is absent.
6. Confirm `/api/health` returns `database_ready: true` and `/api/live-vehicles` reports a connected feed before describing the map as live.

The first deployment runs the GTFS/ticket ETL and may take several minutes. The persistent disk is required because the generated SQLite database must survive restarts. The starter service and persistent disk may incur hosting charges; check the current provider plan/pricing before creating resources.

## Production-hardening before public launch

The included app is a complete local-first hackathon application and API, not a fully managed transit SaaS. For sustained multi-user production use, move analytics tables to PostgreSQL/PostGIS, add ingestion scheduling and atomic database swaps, secure administrative endpoints, rate-limit external calls, add centralized logs/metrics, automated backups and monitor GTFS-Realtime feed freshness. OpenStreetMap public tiles have usage policies and should not be treated as an unlimited tile-hosting service.
