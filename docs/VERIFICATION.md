# Build verification record

The complete input archives were processed in the build environment and the generated SQLite database passed `PRAGMA quick_check` (`ok`). The following local API checks passed against that database:

- `/api/health`
- `/api/meta`
- `/api/routes`
- `/api/stops/search`
- `/api/routes/{route_id}`
- `/api/crowding/overview`
- `/api/crowding/routes`
- `/api/crowding/segments`
- `/api/crowding/trends`
- `/api/data-quality`
- `/api/journeys/search` (returned actual scheduled options for a sample pair of GTFS stops)
- `/api/live-vehicles` without a key (returns `not_configured`, without exposing a secret)

The backend's three unit tests pass, and Python application/scripts pass `compileall`.

The frontend TypeScript/TSX source files passed a syntax transpilation check. A full `npm run build` was **not** run in this build environment because the npm registry was unreachable and the frontend dependencies were not preinstalled. Run `npm install` and `npm run build` on the target Windows machine after extracting the package.

The real Transport Stack GTFS-Realtime endpoint was not called during package validation because no API key is embedded or configured in this environment. To verify that live feed on your machine, set the secret in `backend/.env` and restart FastAPI. The source includes `gtfs-realtime-bindings` in `requirements.txt` and decodes `VehiclePositions.pb` on the server.
