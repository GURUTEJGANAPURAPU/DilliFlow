# Transport Stack Hackathon 2026 — Problem 2 alignment

## Public commuter workspace

- No sign-in is required for Journey Planner, Live Bus Map, Crowding Insights, Routes & Stops or Methodology.
- Journey Planner exposes scheduled options, crowding estimates and Fastest / More Comfortable sorting.
- Selected-bus tracking is an additional experience. It combines the static GTFS route/stop sequence with route-matched GTFS-Realtime GPS vehicles. A route-level match is not presented as an exact static scheduled-trip match when the feed's trip descriptor is `ADDED`.
- Crowding is displayed at route/segment level using historical ticket data. GPS is used for bus location and ETA, not to infer passenger load.

## Protected operator workspace

- `/operator` presents an operator sign-in screen.
- `POST /api/operator/login` checks the configured operator ID/password and returns a signed, expiring bearer token.
- Dashboard, capacity-profile read, write and delete endpoints require that bearer token.
- Credentials and signing secret are held in `backend/.env`; configure them with `configure_operator.ps1`.
- No commuter route is protected by this authentication.

## Ticket-demand method

1. Read the complete October ticket CSV from its ZIP archive.
2. Normalize and reconcile ticket route labels to GTFS route records.
3. Reconcile boarding and alighting stop labels to GTFS stops; unmatched values remain unmatched and are counted in data-quality reporting.
4. For each ticket origin/destination pair, use the representative GTFS route stop order and add the ticket's passenger journeys to each consecutive segment between its matched stops.
5. Aggregate by route, service date, hour, weekday/weekend, and (for segment tables) ordered stop pair.
6. For a route/segment/hour, use the median daily ticketed journey count. Divide by GTFS departures passing the route origin or segment origin in that hour to produce estimated ticketed passengers per scheduled bus.
7. If there is no same-hour/nearest-hour denominator, do not produce a per-bus number from an all-hours blend. Fall back only to a relative ticket-demand category with low confidence.
8. Compare the per-bus ticketed proxy against an operator-entered verified route capacity only when such a profile exists. At/below seat capacity gives “Seats likely available”; above seats but at/below configured total capacity gives “Standing room likely”; above total capacity gives “Crowded”.

## Operator decision support

- Peak-hours chart compares average ticketed journeys across observed service days.
- Route table reports route label/direction, ticketed passengers per scheduled bus, scheduled departures, historical crowd signal and configured capacity.
- Segment priority list identifies high relative ticket-demand stretches for frequency review.
- Where a capacity profile is configured, the dashboard can show an indicative extra-departure calculation based on median segment ticket demand, current scheduled departures and configured total capacity. This is a planning lead, not an automatic dispatch instruction.

## Limits that must remain visible

- Ticket records are an observed sample, not proof that every passenger is represented.
- 48.52% of records lack vehicle numbers; vehicle-specific ticket load cannot be inferred for those records.
- Stop-name reconciliation is incomplete; coverage and confidence are surfaced.
- A representative scheduled route-stop pattern may not capture every trip variation.
- Capacity data is not contained in the supplied files; operators must supply a verified baseline before using seat/standing/crowded classifications.
- Relative Low/Moderate/High labels are not counts of onboard passengers.
- GPS feed records use added-trip identifiers that may not map to static GTFS trip IDs; route-level match and trip-level match are separate concepts.
