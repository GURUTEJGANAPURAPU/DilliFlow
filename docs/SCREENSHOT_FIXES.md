# DilliFlow screenshot fixes and journey enhancements

## Routes & Stops HTTP 422

The earlier frontend sent an autocomplete-style request with `limit=80` to `/api/stops/search`, whose limit validation capped requests at 50. The current frontend list/search screen now calls `/api/stops?q=...&limit=80`, which supports up to 500 records. The compatibility `/api/stops/search` endpoint also accepts up to 250.

## Crowding Insights API error

The screenshot message “Cannot reach the DilliFlow API” means the browser could not connect to FastAPI at `http://localhost:8000`; it is not a ticket-data calculation error. Start the backend and frontend together from `D:\DilliFlow` with `\.\run_dilliflow.ps1`, or run `\.\run_backend.ps1` and `\.\run_frontend.ps1` in separate terminals. The insights page now loads the summary and chart independently, includes a retry action, and retains whichever section loaded successfully.

## Journey live arrivals and stop-by-stop details

When a passenger searches for an upcoming journey on the current local date, FastAPI associates buses to the scheduled route using the verified GTFS `route_id`, projects GPS positions onto the selected scheduled route shape, and calculates an estimated time to the boarding stop. If reported speed is unavailable, the API attempts to derive speed from consecutive GPS snapshots; a scheduled route-average fallback is labelled low-confidence. The planner re-requests today's upcoming journey options every 30 seconds, allowing successive snapshots to improve the speed estimate.

The map displays route geometry, route stops and route-matched live vehicle markers. The stop timeline shows the projected GPS arrival for each stop when available and the GTFS schedule otherwise. A crowding badge is shown for each stop segment and live bus card using historical route/segment ticket-demand data. It is not a bus sensor or a claim about actual current occupancy.

## Real-time date limitation

The Transport Stack vehicle feed reports current vehicle positions. It cannot reveal where a bus will be tomorrow. Live GPS arrivals are therefore shown only for today's local service date and only for journeys whose scheduled departure is still ahead. For future or past dates, DilliFlow shows the GTFS schedule and historical ticket-demand indicators without fabricating live ETAs.

## Trip matching limitation

The observed live feed marks vehicles with `ADDED` trip descriptors. These live trip IDs use a different naming convention from static GTFS trip IDs. DilliFlow does not force-match them. It uses the verified `route_id` and scheduled route shape for route-level map matching and ETA projection.
