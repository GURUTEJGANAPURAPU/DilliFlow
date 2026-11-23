# DilliFlow data and estimation methodology

## Sources

1. Static GTFS archive: routes, stops, trips, stop_times, calendar and shapes.
2. October 2026 e-ticket CSV: passenger_count, amount, vehicle_number, ticket_type_id, end_stop_name, route, start_stop_name, created_at and is_ac.
3. GTFS-Realtime VehiclePositions Protobuf feed: live vehicle GPS position and trip descriptor fields.

## Processing

- Route labels are normalized and matched to static GTFS route short/long names.
- Ticket stop labels are normalized. Exact stop-name matches are preferred; fuzzy matching is applied only above the configured conservative score threshold. Match quality is included in the stored summary.
- Ticket rows are streamed from the ZIP in batches, not loaded into memory as one giant dataframe.
- Route/hour/date and origin/destination/hour/date groups are aggregated.
- OD demand is expanded across consecutive segments of a representative scheduled stop sequence for the route.
- Hour-of-day patterns are split into weekday and weekend groups.

## Interpretation and caveats

- A ticket passenger count is a ticket-derived demand signal, not an onboard sensor reading.
- 48.52% of rows in the supplied full-file scan have no vehicle number. This limits linking tickets to a specific bus.
- The dataset's coverage of all passengers is not established. No unsupported multiplier is used to scale recorded tickets to total demand.
- A representative stop order cannot model every variant/direction/pattern of a route. Treat segment aggregates as exploratory estimates until pattern-level reconciliation is verified.
- Relative low/moderate/high classification is a historical comparison, not an absolute seat/standing-capacity category.
- Static GTFS schedules and live GPS are different sources. The live feed's ADDED trip IDs are not equated to scheduled static trip IDs when exact matching fails.
- GPS positions may be delayed. Freshness is derived from the individual vehicle timestamp.

## Freshness thresholds

- Fresh: age <= 90 seconds.
- Delayed: age > 90 seconds and <= 300 seconds.
- Stale: age > 300 seconds.
- Missing timestamp: unknown.
- More than 30 seconds in the future: flagged as future_timestamp.


## Passenger-facing capacity reference

Where an operator has not entered a verified route-fleet profile, DilliFlow displays an explicit planning baseline of 35 seats and 25 standing places so the journey planner remains populated. These are application planning assumptions, not verified specifications for every Delhi bus. Estimated available places are calculated from the historical ticket-demand proxy when one is available; otherwise the UI displays nominal upper bounds rather than claiming that seats are vacant. Seat/standing/crowded categorical claims are enabled only for operator-verified capacity profiles. None of these fields is a live vehicle occupancy measurement.
