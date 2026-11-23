# Live time and ETA correctness fix

The planner previously treated route-matched GTFS-Realtime vehicles as though they were confirmed instances of the selected static GTFS trip. The Delhi feed reports ADDED trip IDs that do not map to the static trip IDs, so that association must not be implied.

The fix makes the UI explicitly distinguish:

- the scheduled departure from GTFS (for example, 04:14 AM),
- the current GPS snapshot time (for example, 01:58 AM), and
- current vehicles reporting on the same route.

ETA safeguards:

- Route progress is normalized using the selected trip's boarding-to-alighting stop order, including shapes stored in the opposite direction.
- The GPS-to-shape corridor is reduced to 650 metres.
- A zero-minute ETA is emitted only when the GTFS-RT stop_id equals the selected boarding stop or the live coordinate is within 45 metres of that stop and close to the route shape.
- Non-zero ETAs require a reported or derived moving speed and a GPS bearing aligned with the selected trip direction.
- Scheduled-average speed is never substituted for live speed.
- Vehicles that have passed the boarding stop, have an unverified direction, or lack speed remain visible on the route but do not receive a fabricated arrival ETA.
- Only a vehicle whose live trip_id exactly matches the selected static trip is labelled as a trip match. Route ID match alone is explicitly described as route-level association.

Restart FastAPI after applying these files. No GTFS or ticket re-ingestion is required.
