# REST API contract

Base URL for local use: `http://localhost:8000`.

All successful endpoints return JSON. The FastAPI OpenAPI page is `/docs`.

## System

- `GET /api/health`: database readiness, aggregate record counts, ingestion metadata and whether the server-side live-feed key is configured.
- `GET /api/meta`: static GTFS row counts and the full ticket-ingestion quality summary.

## Network

- `GET /api/routes?q=&limit=100&offset=0`: `{ items, total, limit, offset }`.
- `GET /api/routes/{route_id}`: `{ route, stops, geometry, crowding }`. Stop order is a representative scheduled pattern; geometry is one representative route shape.
- `GET /api/stops?q=&limit=100&offset=0`: `{ items, total, limit, offset }`.
- `GET /api/stops/search?q=...&limit=12`: stop autocomplete result.
- `GET /api/stops/{stop_id}/crowding`: routes serving a stop, route-level historical demand, and historical demand estimates for the previous/next stop segment in each representative route pattern.

## Live positions

- `GET /api/live-vehicles`: cached snapshot; query `?refresh=true` forces a new fetch.
- Status values: `connected`, `not_configured`, `error`, `degraded`.
- Each vehicle contains the reported ID, route ID/name if matched, coordinates, optional speed/bearing, source timestamp, computed age and freshness label.
- The transport API key is never returned to the client.

## Ticket-demand intelligence

- `GET /api/crowding/overview`: source period, full source-row count, matched ticket-row count, routes/dates covered, data-quality rates and higher-demand routes.
- `GET /api/crowding/routes?hour=8&day_type=weekday&q=&limit=50`: route-level demand estimates for a requested hour/day class.
- `GET /api/crowding/segments?route_id=...&hour=8&day_type=weekday`: consecutive stop-to-stop historical demand estimates in representative GTFS route order. Missing exact-hour buckets use the estimator's documented nearest-hour/all-hours fallback and retain lower confidence; pairs with no matched records are returned as `insufficient_data`.
- `GET /api/crowding/trends?day_type=weekday&route_id=...`: aggregate hourly passenger-journey proxy.
- `GET /api/data-quality`: source ingestion quality summary.

Crowding levels are relative ticket-demand indicators. They are not seat availability or measured occupancy.

## Journey search

`GET /api/journeys/search?origin_stop_id=...&destination_stop_id=...&travel_date=YYYY-MM-DD&departure_time=HH:MM&max_transfers=1`

Returns `items`, origin/destination, selected date, service IDs, methodology and a message when no scheduled itinerary is available. Journey legs are based on static GTFS scheduled trips and include the trip's stop sequence, stop-level historical segment crowding, and route-matched live vehicles when the selected date is today. Each live vehicle can include an estimated time to the boarding stop, route-corridor progress, inferred last/next stop, and projected stop-by-stop arrival times. Live ETAs are disabled for past/future dates because the GPS feed reports current positions only. When the feed uses ADDED trip descriptors, vehicles are associated by exact GTFS route ID plus route-shape proximity; this is not represented as an exact static-trip match. Downstream ETAs require a direction-aligned live bearing and reported or derived GPS speed. Scheduled-average speed is never substituted for GPS speed.


Journey search additionally enriches today's still-upcoming scheduled journeys with route-matched GPS bus candidates, a boarding-stop ETA, and per-stop arrival projections. The planner refreshes eligible results every 30 seconds. It does not forecast live GPS for future service dates or for timetable departures that have already passed.

## Selected-bus tracking in the journey planner

The Journey Planner presents route-matched live vehicles as individually selectable bus cards. Selecting a card or clicking its map marker focuses the map on that vehicle, highlights its marker, and updates the selected-bus tracker and stop timeline. The map can follow the selected vehicle as new 30-second GPS snapshots arrive; the passenger can pause map-follow mode.

The selected-bus tracker reports the available vehicle ID, GPS age/freshness, speed, current or last-passed stop, next stop, boarding-stop ETA, destination ETA, route-corridor progress and historical crowd estimate. The timeline displays GTFS stops in travel order, GPS-derived arrival projections where supportable, and ticket-demand crowd estimates for each segment.

Stop names inferred from shape projection are labelled as inferred route progress, not as a GTFS-RT-reported stop. If current speed/direction is unavailable, the vehicle remains visible on the map but its future stop ETAs remain unavailable. Historical crowding is not live occupancy.
