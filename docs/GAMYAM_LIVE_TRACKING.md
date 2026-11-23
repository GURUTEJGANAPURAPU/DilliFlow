# DilliFlow — selected-bus live tracking

## Passenger flow

1. Search for origin, destination, travel date and departure time in Journey Planner.
2. Choose a scheduled itinerary. The planner shows route-matched vehicles for the first leg when the selected date is today and the scheduled departure is still upcoming.
3. Select a vehicle card in **Available buses**, or click its marker on the route map.
4. The map focuses the selected vehicle and highlights its marker. Follow mode keeps the map centred on the vehicle as the next live snapshots arrive; use **Pause map follow** to explore the map without automatic recentering.
5. The tracking card shows vehicle ID, GPS age, speed when valid, current/last-passed stop, next stop, route-corridor progress, boarding ETA and destination ETA when supportable.
6. The stop timeline shows the selected itinerary's stops in order, GPS-projected arrival times where supportable, and historical ticket-demand crowd badges for each segment.

## Matching and limitations

- A vehicle must have the same GTFS `route_id` as the selected journey and be within the configured route-shape corridor.
- Direction is considered confirmed only when a usable GTFS-Realtime bearing aligns with the selected journey's shape direction. When bearing is not available, the bus remains visible but future-stop ETAs are withheld until movement/bearing can be established.
- The Delhi feed can report `ADDED` trip IDs that do not match static `trips.txt`. A route match is not reported as an exact scheduled-trip match.
- When GTFS-Realtime provides a `stop_id`, it is used as the current stop. Otherwise, last-passed and next-stop labels are inferred by projecting GPS onto the selected GTFS route shape. They are labelled as inferred progress, not a sensor-reported stop.
- A bus at the boarding stop can be displayed even if no movement speed is available. ETAs to later stops require a usable reported or derived GPS speed plus direction alignment. Scheduled average speed is never substituted.
- Live GPS is a present-time feed. The planner does not claim live locations for past or future service dates, or for scheduled departures that have already passed.
- Crowding labels are historical ticket-demand estimates by route/segment/time. They are not live occupancy, seat availability, or a measurement from the selected vehicle.

## Refresh behaviour

The Journey Planner re-requests eligible same-day journey results approximately every 30 seconds. The backend's GTFS-Realtime cache/poll interval remains configured by `POLL_INTERVAL_SECONDS` (minimum 15 seconds). The map marker coordinates refresh on each successful response. When map-follow is enabled, the map pans to the latest position of the selected vehicle; pause it to keep manual map navigation.

## Local verification

Backend tests:

```powershell
cd D:\DilliFlow\backend
& "D:\DilliFlow\.venv\Scripts\python.exe" -m pytest -q
```

Frontend development server:

```powershell
cd D:\DilliFlow\frontend
npm run dev
```

Frontend production build:

```powershell
cd D:\DilliFlow\frontend
npm run build
```
