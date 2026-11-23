import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import {
  Activity, ArrowDownUp, ArrowRight, ArrowUpRight, BusFront, CalendarDays,
  Clock3, Footprints, Info, LoaderCircle, MapPin, RadioTower, Search,
  ShieldCheck, Sparkles, Timer, TrafficCone, Wifi, WifiOff,
} from 'lucide-react';
import StopSearch from '../components/StopSearch';
import MapView from '../components/MapView';
import CrowdBadge from '../components/CrowdBadge';
import SectionHeader from '../components/SectionHeader';
import { api, type CrowdEstimate, type Journey, type JourneyLeg, type JourneyStop, type Stop, type Vehicle } from '../lib/api';

function localDate() {
  const d = new Date();
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

function formatArrival(value?: string | null) {
  if (!value) return 'ETA unavailable';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'ETA unavailable';
  return date.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
}

function localTime() {
  const d = new Date();
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return local.toISOString().slice(11, 16);
}

function gtfsMinutes(value?: string | null) {
  if (!value) return -1;
  const parts = value.split(':').map(Number);
  if (parts.length < 2 || parts.some((part) => Number.isNaN(part))) return -1;
  return parts[0] * 60 + parts[1];
}

function currentLocalMinutes() {
  const now = new Date();
  return now.getHours() * 60 + now.getMinutes();
}

function formatGtfsTime(value?: string | null) {
  if (!value) return '—';
  const parts = value.split(':').map(Number);
  if (parts.length < 2 || parts.some((part) => Number.isNaN(part))) return value;
  const [rawHours, minutes] = parts;
  const dayOffset = Math.floor(rawHours / 24);
  const hours = rawHours % 24;
  const formatted = new Date(2000, 0, 1, hours, minutes).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' });
  return dayOffset > 0 ? `${formatted} (+${dayOffset} day${dayOffset > 1 ? 's' : ''})` : formatted;
}

function etaLabel(minutes?: number | null, arrival?: string | null) {
  if (minutes == null) return 'Live ETA unavailable';
  if (minutes === 0) return `At boarding stop · ${formatArrival(arrival)}`;
  return `Arrives in ${minutes} min · ${formatArrival(arrival)}`;
}

function liveVehicleStatus(bus: Vehicle) {
  switch (bus.approach_status) {
    case 'at_boarding_stop': return 'GPS confirms bus at stop';
    case 'approaching': return 'Approaching in selected direction';
    case 'passed_boarding_stop': return 'Already passed boarding stop';
    case 'near_boarding_stop_unconfirmed': return 'Near stop · not confirmed at stop';
    case 'direction_unverified': return 'Direction not verified';
    case 'speed_unavailable': return 'Live speed unavailable';
    case 'on_route_eta_out_of_range': return 'On route · too far for ETA';
    default: return 'Live position on route';
  }
}

function liveVehicleEta(bus: Vehicle) {
  if (bus.approach_status === 'at_boarding_stop') return 'At stop';
  if (bus.approach_status === 'approaching' && bus.eta_to_board_minutes != null) return `${bus.eta_to_board_minutes} min`;
  if (bus.approach_status === 'passed_boarding_stop') return 'Passed';
  return 'ETA unavailable';
}

function gpsAgeLabel(bus: Vehicle) {
  if (bus.age_seconds == null) return 'GPS timestamp unavailable';
  if (bus.age_seconds < 60) return `GPS ${Math.round(bus.age_seconds)}s ago`;
  return `GPS ${Math.floor(bus.age_seconds / 60)}m ago`;
}

const crowdRank: Record<import('../lib/api').CrowdLevel, number> = { low: 0, seats_available: 0, standing_room: 1, moderate: 2, high: 3, crowded: 3, insufficient_data: 4 };

export default function PlannerPage() {
  const [origin, setOrigin] = useState<Stop | null>(null);
  const [destination, setDestination] = useState<Stop | null>(null);
  const [travelDate, setTravelDate] = useState(localDate());
  const [departureTime, setDepartureTime] = useState(localTime);
  const [journeys, setJourneys] = useState<Journey[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [selectedBusId, setSelectedBusId] = useState<string | null>(null);
  const [followSelectedBus, setFollowSelectedBus] = useState(true);
  const [sort, setSort] = useState<'fastest' | 'comfortable'>('comfortable');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [searched, setSearched] = useState(false);
  const [liveUpdatedAt, setLiveUpdatedAt] = useState<Date | null>(null);
  const [activeSearch, setActiveSearch] = useState<{ origin: string; destination: string; date: string; time: string } | null>(null);
  const pollBusy = useRef(false);

  const ordered = useMemo(() => [...journeys].sort((a, b) => {
    if (sort === 'fastest') return a.duration_minutes - b.duration_minutes;
    const aRank = crowdRank[a.crowding || 'insufficient_data'];
    const bRank = crowdRank[b.crowding || 'insufficient_data'];
    return aRank - bRank || a.duration_minutes - b.duration_minutes;
  }), [journeys, sort]);
  const chosen = ordered.find((item) => item.id === selected) || ordered[0];
  const primaryLeg = chosen?.legs[0];
  const primaryBuses = primaryLeg?.live_vehicles || [];
  const selectedBus = primaryBuses.find((bus) => bus.vehicle_id === selectedBusId) || primaryBuses[0];
  const selectedBusNextStopArrival = selectedBus?.stop_arrivals?.find((stop) => stop.stop_id === selectedBus.next_stop_id);
  const selectedBusDestinationArrival = selectedBus?.stop_arrivals?.find((stop) => stop.stop_id === primaryLeg?.to_stop?.stop_id);
  const mapVehicles = useMemo(() => primaryBuses, [primaryBuses]);

  // While today's journey results are open, re-request them every 30 seconds.
  // The backend refreshes GTFS-RT on its configured poll interval and derives speed from successive GPS snapshots.
  const upcomingScheduleKey = ordered
    .filter((journey) => gtfsMinutes(journey.departure_time) >= currentLocalMinutes() && ['connected', 'error', 'degraded'].includes(journey.legs[0]?.live_arrivals_status || ''))
    .map((journey) => journey.id)
    .join('|');

  useEffect(() => {
    if (!searched || !activeSearch || activeSearch.date !== localDate() || !upcomingScheduleKey) return;
    let active = true;
    const refreshLive = async () => {
      if (pollBusy.current || !upcomingScheduleKey) return;
      pollBusy.current = true;
      try {
        const result = await api.journeys(activeSearch.origin, activeSearch.destination, activeSearch.date, activeSearch.time);
        if (active) {
          setJourneys(result.items || []);
          setLiveUpdatedAt(new Date());
        }
      } catch {
        // Keep the last successful timetable and GPS snapshot visible during transient refresh failures.
      } finally {
        pollBusy.current = false;
      }
    };
    const timer = window.setInterval(() => { void refreshLive(); }, 30_000);
    return () => { active = false; window.clearInterval(timer); };
  }, [searched, activeSearch, upcomingScheduleKey]);

  async function searchJourneys(event: FormEvent) {
    event.preventDefault();
    if (!origin || !destination) {
      setError('Choose both an origin and a destination from the stop suggestions.');
      return;
    }
    if (origin.stop_id === destination.stop_id) {
      setError('Choose two different stops.');
      return;
    }
    setLoading(true);
    setError('');
    setSearched(false);
    setActiveSearch(null);
    setJourneys([]);
    setSelected(null);
    setLiveUpdatedAt(null);
    setSelectedBusId(null);
    setFollowSelectedBus(true);
    try {
      const result = await api.journeys(origin.stop_id, destination.stop_id, travelDate, departureTime);
      setJourneys(result.items || []);
      const hasLiveEligibleJourney = travelDate === localDate() && (result.items || []).some((journey) => gtfsMinutes(journey.departure_time) >= currentLocalMinutes());
      setLiveUpdatedAt(hasLiveEligibleJourney ? new Date() : null);
      setSelected(result.items?.[0]?.id || null);
      setActiveSearch({ origin: origin.stop_id, destination: destination.stop_id, date: travelDate, time: departureTime });
      setSearched(true);
      if (!result.items?.length) setError(result.message || 'No scheduled journey was found for this search.');
    } catch (err) {
      setJourneys([]);
      setSearched(true);
      setError(err instanceof Error ? err.message : 'Journey search failed.');
    } finally {
      setLoading(false);
    }
  }

  function swapStops() {
    setOrigin(destination);
    setDestination(origin);
  }

  return (
    <div className="page-stack">
      <SectionHeader eyebrow="JOURNEY PLANNER" title="A better way across Delhi." description="Find a bus journey that fits your time and your comfort." action={<span className="source-chip"><ShieldCheck size={14} /> Scheduled GTFS + live GPS + ticket insights</span>} />

      <div className="planner-layout">
        <section className="panel planner-panel">
          <div className="panel-heading">
            <div><span className="panel-kicker">PLAN A JOURNEY</span><h2>Where are you headed?</h2></div>
            <span className="panel-icon"><BusFront size={20} /></span>
          </div>
          <form onSubmit={searchJourneys} className="journey-form">
            <div className="stop-fields">
              <StopSearch label="FROM" placeholder="Choose your starting stop" value={origin} onChange={setOrigin} />
              <button type="button" className="swap-button" onClick={swapStops} aria-label="Swap stops"><ArrowDownUp size={16} /></button>
              <StopSearch label="TO" placeholder="Choose your destination" value={destination} onChange={setDestination} />
            </div>
            <div className="journey-time-row">
              <label className="compact-field"><span><CalendarDays size={14} /> DATE</span><input type="date" value={travelDate} onChange={(e) => setTravelDate(e.target.value)} /></label>
              <label className="compact-field"><span><Clock3 size={14} /> DEPARTURE</span><input type="time" value={departureTime} onChange={(e) => setDepartureTime(e.target.value)} /></label>
            </div>
            {error && <div className="inline-alert"><Info size={16} />{error}</div>}
            <button className="primary-button search-button" type="submit" disabled={loading}>
              {loading ? <LoaderCircle size={17} className="spin" /> : <Search size={17} />}
              {loading ? 'Finding journeys…' : 'Find journeys'}
              {!loading && <ArrowRight size={17} />}
            </button>
          </form>
          <div className="planner-footnote"><Info size={14} /> Scheduled times come from GTFS. Live arrival estimates use route-matched GPS positions; crowd labels are historical ticket-demand estimates, not onboard passenger counts.</div>
        </section>

        <section className="panel planner-map-panel">
          <div className="map-panel-head">
            <div><span className="panel-kicker">LIVE JOURNEY TRACKING</span><h2>{selectedBus ? `Tracking ${selectedBus.vehicle_id}` : mapVehicles.length ? `${mapVehicles.length} buses on this route` : 'Plan with the city in view'}</h2></div>
            <span className="live-map-label"><span className={`status-dot ${mapVehicles.length ? 'fresh' : 'muted'}`} /> {selectedBus ? 'Selected bus focused' : mapVehicles.length ? 'Live bus locations' : 'Route map'}</span>
          </div>
          <MapView line={primaryLeg?.geometry || []} fitPoints={primaryLeg?.geometry || []} stopMarkers={primaryLeg?.stops || []} vehicles={mapVehicles} selectedVehicleId={selectedBus?.vehicle_id || null} onVehicleSelect={(vehicle) => { setSelectedBusId(vehicle.vehicle_id); setFollowSelectedBus(true); }} followSelectedVehicle={followSelectedBus} className="planner-map" zoom={11} />
          <div className="map-caption"><span><span className="map-legend-line" /> Selected route + journey stops</span><span><RadioTower size={14} /> {mapVehicles.length ? 'Choose a bus card or map marker to focus its live location' : 'Live markers appear when buses are returned by the feed'}</span></div>
        </section>
      </div>

      <section className="results-section">
        <div className="results-heading">
          <div><span className="panel-kicker">YOUR OPTIONS</span><h2>{searched ? `${ordered.length} journeys found` : 'Journeys made clearer'}</h2></div>
          <div className="sort-control" role="group" aria-label="Sort journey options">
            <button className={sort === 'comfortable' ? 'active' : ''} onClick={() => setSort('comfortable')} type="button"><Sparkles size={14} /> More comfortable</button>
            <button className={sort === 'fastest' ? 'active' : ''} onClick={() => setSort('fastest')} type="button"><Timer size={14} /> Fastest</button>
          </div>
        </div>
        {!searched && (
          <div className="empty-state wide-empty">
            <div className="empty-illustration"><BusFront size={28} /><span className="empty-route-line" /></div>
            <div><strong>Your next journey starts here.</strong><p>Choose two stops above to compare scheduled buses, GPS-based arrival estimates and historical route-demand indicators.</p></div>
          </div>
        )}
        {searched && !loading && ordered.length === 0 && (
          <div className="empty-state"><TrafficCone size={24} /><div><strong>No journey options yet</strong><p>Try a different stop pair, departure time, or nearby stop.</p></div></div>
        )}
        {loading && <div className="loading-row"><LoaderCircle className="spin" /> Searching the GTFS schedule and matching live buses…</div>}
        {ordered.length > 0 && chosen && <div className="journey-results-grid">
          <div className="journey-list">
            {ordered.map((journey) => {
              return <button className={`journey-card ${chosen.id === journey.id ? 'selected' : ''}`} key={journey.id} onClick={() => { setSelected(journey.id); setSelectedBusId(null); setFollowSelectedBus(true); }} type="button">
                <div className="journey-card-top"><div className="route-chip-list">{journey.legs.map((leg, i) => <span className="route-chip" key={`${leg.route_id}-${i}`}>{leg.route_short_name || leg.route_id}</span>)}</div><CrowdBadge level={journey.crowding} fallbackLabel="Typical network reference" /></div>
                <div className="journey-ticketed-load-line">{journey.legs.map((leg, i) => <span key={`${leg.route_id}-${i}`}><strong>{leg.route_short_name || leg.route_id}:</strong> {leg.crowding?.estimated_ticketed_passengers_per_bus == null ? 'network planning reference' : `~${leg.crowding.estimated_ticketed_passengers_per_bus.toFixed(1)} ticketed / scheduled bus`}</span>)}</div>
                <div className="journey-capacity-line">{journey.legs.map((leg, i) => <CapacityInline key={`${leg.route_id}-capacity-${i}`} estimate={leg.crowding} routeName={leg.route_short_name || leg.route_id} />)}</div>
                <div className="journey-time-block"><div><strong>{formatGtfsTime(journey.departure_time)}</strong><small>{journey.legs[0]?.from_stop?.stop_name}</small></div><div className="journey-duration"><span>{journey.duration_minutes} min</span><span className="duration-track"><i /></span><small>{journey.transfers === 0 ? 'Direct' : `${journey.transfers} transfer`}</small></div><div className="align-right"><strong>{formatGtfsTime(journey.arrival_time)}</strong><small>{journey.legs[journey.legs.length - 1]?.to_stop?.stop_name}</small></div></div>
                <div className="journey-card-bottom"><span>{journey.recommendation_reason || 'Scheduled bus journey'}</span><span className="view-link">Details <ArrowUpRight size={13} /></span></div>
              </button>;
            })}
          </div>
          <div className="panel journey-detail-panel">
            <div className="detail-top"><div><span className="panel-kicker">JOURNEY DETAILS</span><h3>{chosen.duration_minutes} minutes</h3><p>{chosen.transfers === 0 ? 'Direct bus journey' : 'One transfer'} · Scheduled {formatGtfsTime(chosen.departure_time)} to {formatGtfsTime(chosen.arrival_time)}</p></div><span className="detail-icon"><BusFront size={19} /></span></div>

            {primaryLeg && <TicketedLoadPanel estimate={primaryLeg.crowding} />}

            <div className="live-arrivals-section">
              <div className="live-arrivals-heading"><div><span className="panel-kicker">AVAILABLE BUSES · GAMYAM-STYLE TRACKING</span><h4>{primaryBuses.length ? `${primaryLeg?.live_route_vehicle_count || primaryBuses.length} buses reporting on this route` : 'Buses approaching your stop'}</h4>{liveUpdatedAt && primaryLeg?.live_arrivals_status === 'connected' && <small className="live-updated-label">Last refreshed {liveUpdatedAt.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })} · refreshes every 30 seconds</small>}</div><span className={`feed-status ${primaryLeg?.live_arrivals_status === 'connected' ? 'is-connected' : 'is-muted'}`}>{primaryLeg?.live_arrivals_status === 'connected' ? <Wifi size={13} /> : <WifiOff size={13} />}{primaryLeg?.live_arrivals_status === 'connected' ? 'GPS feed connected' : primaryLeg?.live_arrivals_status === 'date_not_current' ? 'Live GPS is for today only' : primaryLeg?.live_arrivals_status === 'selected_time_passed' ? 'Selected time has passed' : 'Live feed unavailable'}</span></div>
              {primaryLeg?.live_schedule_context_note && primaryLeg?.live_arrivals_status === 'connected' && <div className="live-schedule-context"><strong>Scheduled service vs current GPS:</strong> {primaryLeg.live_schedule_context_note}</div>}
              {(primaryLeg?.live_arrivals_status === 'date_not_current' || primaryLeg?.live_arrivals_status === 'selected_time_passed') && <div className="live-empty-note">{primaryLeg.live_arrivals_message}</div>}
              {primaryLeg?.live_arrivals_status === 'not_configured' && <div className="live-empty-note">Add your Transport Stack API key to <code>backend/.env</code> to see live bus arrivals. Scheduled GTFS departures remain available.</div>}
              {(primaryLeg?.live_arrivals_status === 'error' || primaryLeg?.live_arrivals_status === 'degraded') && <div className="live-empty-note">{primaryLeg.live_feed_message || 'The live GPS service is temporarily unavailable. Scheduled GTFS times remain available.'}</div>}
              {primaryLeg?.live_arrivals_status === 'connected' && primaryBuses.length === 0 && <div className="live-empty-note">No fresh or delayed GPS vehicles are currently matched to this route and its shape corridor. This does not mean the scheduled service is cancelled; it means no current vehicle position can be confidently associated with this journey.</div>}
              {primaryBuses.length > 0 && <>
                {(primaryLeg?.live_route_vehicle_count || primaryBuses.length) > primaryBuses.length && <div className="live-candidate-count">Showing {primaryBuses.length} closest route-matched buses from {primaryLeg?.live_route_vehicle_count} GPS candidates.</div>}
                <div className="live-bus-list">
                {primaryBuses.map((bus) => <button type="button" key={bus.vehicle_id} onClick={() => { setSelectedBusId(bus.vehicle_id); setFollowSelectedBus(true); }} className={`live-bus-card ${selectedBus?.vehicle_id === bus.vehicle_id ? 'active' : ''}`}>
                  <span className="live-bus-icon"><BusFront size={17} /></span>
                  <span className="live-bus-main"><strong>{bus.vehicle_id}</strong><small>{bus.route_short_name || bus.route_id} · GPS {bus.age_seconds == null ? 'age unknown' : `${Math.round(bus.age_seconds)}s old`} · {bus.schedule_relationship || 'trip status unknown'}</small></span>
                  <span className="live-bus-eta"><strong>{liveVehicleEta(bus)}</strong><small>{bus.approach_message || liveVehicleStatus(bus)}</small></span>
                  <span className="live-bus-crowd"><CrowdBadge estimate={bus.crowding} fallbackLabel="Route demand reference" />{bus.crowding?.estimated_ticketed_passengers_per_bus != null && <small>~{bus.crowding.estimated_ticketed_passengers_per_bus.toFixed(1)} ticketed / scheduled bus</small>}<CapacityInline estimate={bus.crowding} compact /></span>
                  <span className="live-bus-track-label">{selectedBus?.vehicle_id === bus.vehicle_id ? 'Tracking' : 'Track bus'}</span>
                </button>)}
                </div>
              </>}
              {selectedBus && <div className="selected-bus-summary"><div><strong>{selectedBus.approach_status === 'at_boarding_stop' ? 'GPS confirms this bus is at the boarding stop' : selectedBus.approach_status === 'approaching' ? etaLabel(selectedBus.eta_to_board_minutes, selectedBus.estimated_arrival_at_boarding) : liveVehicleStatus(selectedBus)}</strong><span>{selectedBus.approach_message} {selectedBus.matches_selected_scheduled_trip ? 'This vehicle trip matches the selected timetable trip.' : 'This vehicle is matched by route and direction evidence, not confirmed as the selected scheduled trip.'}</span></div><div className="selected-bus-coordinates"><MapPin size={13} /> {selectedBus.latitude.toFixed(5)}, {selectedBus.longitude.toFixed(5)}</div></div>}
              {selectedBus && <div className="bus-tracking-card">
                <div className="bus-tracking-top"><div><span className="panel-kicker">TRACKING SELECTED BUS</span><strong>{selectedBus.vehicle_id}</strong></div><span className={`tracking-live-pill ${selectedBus.freshness === 'fresh' ? 'fresh' : selectedBus.freshness === 'delayed' ? 'delayed' : 'stale'}`}><span className="status-dot" />{selectedBus.freshness === 'fresh' ? 'Live · fresh GPS' : selectedBus.freshness === 'delayed' ? 'Delayed GPS' : 'Last known position'}</span></div>
                <div className="bus-tracking-grid">
                  <div><small>Current / nearest stop</small><strong>{selectedBus.current_stop_name || selectedBus.last_passed_stop_name || 'Between mapped stops'}</strong></div>
                  <div><small>Next stop on this journey</small><strong>{selectedBus.next_stop_name || 'Not determined'}</strong>{selectedBusNextStopArrival && <em>{formatArrival(selectedBusNextStopArrival.estimated_arrival_at)} · GPS estimate</em>}</div>
                  <div><small>Arrival at your boarding stop</small><strong>{selectedBus.approach_status === 'at_boarding_stop' ? 'At stop now' : selectedBus.eta_to_board_minutes != null ? `${selectedBus.eta_to_board_minutes} min · ${formatArrival(selectedBus.estimated_arrival_at_boarding)}` : 'ETA unavailable'}</strong></div>
                  <div><small>Destination arrival</small><strong>{selectedBusDestinationArrival ? formatArrival(selectedBusDestinationArrival.estimated_arrival_at) : 'GPS ETA unavailable'}</strong></div>
                  <div><small>GPS position age</small><strong>{gpsAgeLabel(selectedBus)}</strong></div>
                  <div><small>Live speed</small><strong>{selectedBus.speed_estimate_mps != null ? `${(selectedBus.speed_estimate_mps * 3.6).toFixed(1)} km/h` : 'Waiting for movement sample'}</strong></div>
                  <div><small>Trip association</small><strong>{selectedBus.matches_selected_scheduled_trip ? 'Exact GTFS trip match' : `Route match · ${selectedBus.schedule_relationship || 'trip unknown'}`}</strong></div>
                </div>
                <div className="bus-progress-wrap"><div className="bus-progress-label"><span>Journey corridor progress</span><strong>{selectedBus.progress_percent != null ? `${Math.round(selectedBus.progress_percent)}%` : '—'}</strong></div><div className="bus-progress-track"><span style={{ width: `${selectedBus.progress_percent ?? 0}%` }} /></div><small>Progress is estimated by projecting the GPS point onto the selected GTFS route shape.</small></div>
                <div className="bus-tracking-actions"><span><MapPin size={13} /> Map focused on this bus · {selectedBus.latitude.toFixed(5)}, {selectedBus.longitude.toFixed(5)}</span><button type="button" onClick={() => setFollowSelectedBus((value) => !value)}>{followSelectedBus ? 'Pause map follow' : 'Follow this bus'} <RadioTower size={13} /></button></div>
              </div>}
              <p className="crowd-source-note"><Info size={13} /> Crowd badges on each bus use historical route-level ticket demand for the selected departure hour. They are not vehicle sensors or live occupancy readings.</p>
            </div>

            <div className="route-stops-section">
              <div className="route-stops-heading"><div><span className="panel-kicker">STOP-BY-STOP</span><h4>Your route stops</h4></div><span className="stop-count-label">{primaryLeg?.stops?.length || 0} stops on this leg</span></div>
              {chosen.legs.map((leg, legIndex) => <LegStopTimeline key={`${leg.route_id}-${leg.trip_id}`} leg={leg} bus={legIndex === 0 ? selectedBus : leg.live_vehicles?.find((candidate) => candidate.eta_to_board_minutes != null)} legIndex={legIndex} />)}
            </div>
            {chosen.transfer_stop && <div className="transfer-note"><Footprints size={15} /> Transfer at {chosen.transfer_stop.stop_name}; scheduled gap {chosen.transfer_buffer_minutes ?? '—'} minutes.</div>}
            <div className="demand-disclaimer"><Info size={14} /> Live bus positions are matched by GTFS route ID. Stop-by-stop GPS ETAs are projections on the scheduled route shape because the feed's ADDED trip IDs do not match static trip IDs.</div>
          </div>
        </div>}
      </section>
    </div>
  );
}

function LegStopTimeline({ leg, bus, legIndex }: { leg: JourneyLeg; bus?: Vehicle; legIndex: number }) {
  const stops = leg.stops || [];
  const liveStops = new Map((bus?.stop_arrivals || []).map((item) => [item.stop_id, item]));
  return <div className="leg-stop-group">
    <div className="leg-stop-route-label"><span className="route-chip">{leg.route_short_name || leg.route_id}</span><span>{leg.from_stop?.stop_name} → {leg.to_stop?.stop_name}</span>{legIndex > 0 && <small>Transfer leg</small>}</div>
    {stops.length === 0 ? <div className="live-empty-note">The selected GTFS trip does not provide a stop sequence for this segment.</div> : <div className="stop-arrival-timeline">
      {stops.map((stop: JourneyStop, index) => {
        const live = liveStops.get(stop.stop_id);
        const isFirst = index === 0;
        const isLast = index === stops.length - 1;
        const isCurrent = Boolean(bus?.current_stop_id && bus.current_stop_id === stop.stop_id);
        const isNext = Boolean(bus?.next_stop_id && bus.next_stop_id === stop.stop_id);
        const isPassed = Boolean(bus?.last_passed_stop_sequence != null && stop.stop_sequence <= bus.last_passed_stop_sequence && !isCurrent && !isNext);
        const time = live?.estimated_arrival_at ? formatArrival(live.estimated_arrival_at) : formatGtfsTime(stop.arrival_time || stop.departure_time);
        const timeBasis = live?.arrival_source === 'gps_confirmed_stop' ? 'GPS confirms stop' : live?.arrival_source === 'gps_shape_projection' ? `${live.eta_minutes} min · GPS projection` : 'GTFS schedule';
        return <div className={`arrival-stop-row ${isFirst ? 'first' : ''} ${isLast ? 'last' : ''} ${isCurrent ? 'bus-current-stop' : ''} ${isNext ? 'bus-next-stop' : ''} ${isPassed ? 'bus-passed-stop' : ''}`} key={`${leg.trip_id}-${stop.stop_id}-${stop.stop_sequence}`}>
          <div className="arrival-stop-rail"><span className="arrival-stop-dot" />{!isLast && <span className="arrival-stop-line" />}</div>
          <div className="arrival-stop-copy"><strong>{stop.stop_name}</strong><small>{isCurrent ? 'Bus is here' : isNext ? 'Next stop for selected bus' : isPassed ? 'Bus passed this stop' : isFirst ? 'Board here' : isLast ? 'Alight here' : `Stop ${index + 1}`}</small></div>
          <div className="arrival-stop-time"><strong>{time}</strong><small>{timeBasis}</small></div>
          {!isLast && <div className="arrival-stop-crowd"><CrowdBadge estimate={stop.crowding_to_next || undefined} />{stop.crowding_to_next?.estimated_ticketed_passengers_per_bus != null && <small>~{stop.crowding_to_next.estimated_ticketed_passengers_per_bus.toFixed(1)} ticketed / bus</small>}</div>}
        </div>;
      })}
    </div>}
  </div>;
}

function CapacityInline({ estimate, routeName, compact = false }: { estimate?: CrowdEstimate; routeName?: string; compact?: boolean }) {
  const seats = estimate?.seat_capacity ?? 35;
  const standing = estimate?.standing_capacity ?? 25;
  const availableSeats = estimate?.estimated_available_seats ?? seats;
  const availableStanding = estimate?.estimated_available_standing_spaces ?? standing;
  const isVerified = estimate?.capacity_source === 'operator_verified' || estimate?.capacity_configured === true;
  const basis = estimate?.availability_basis || 'capacity_only_fallback';
  return <span className={`capacity-inline ${compact ? 'compact' : ''}`} title={basis === 'capacity_only_fallback' ? 'Nominal capacity is shown; no load sample was available to estimate vacant places.' : 'Route-level historical ticket-demand estimate. This is not an individual bus occupancy sensor.'}>
    {routeName && <strong>{routeName}: </strong>}
    <span>{seats} seats</span><span className="capacity-inline-separator">·</span>
    <span>{basis === 'capacity_only_fallback' ? `up to ${availableSeats} available` : `~${availableSeats} est. seats free`}</span><span className="capacity-inline-separator">·</span>
    <span>{standing} standing</span><span className="capacity-inline-separator">·</span>
    <span>{basis === 'capacity_only_fallback' ? `up to ${availableStanding} spaces` : `~${availableStanding} est. spaces free`}</span>
    {!compact && <em>{isVerified ? 'Operator-verified route capacity' : 'DilliFlow planning baseline · not vehicle-specific'}</em>}
  </span>;
}

function TicketedLoadPanel({ estimate }: { estimate?: CrowdEstimate }) {
  const perBus = estimate?.estimated_ticketed_passengers_per_bus;
  const seats = estimate?.seat_capacity ?? 35;
  const standing = estimate?.standing_capacity ?? 25;
  const availableSeats = estimate?.estimated_available_seats ?? seats;
  const availableStanding = estimate?.estimated_available_standing_spaces ?? standing;
  const verified = estimate?.capacity_source === 'operator_verified' || estimate?.capacity_configured === true;
  const capacityOnly = (estimate?.availability_basis || 'capacity_only_fallback') === 'capacity_only_fallback';
  return <section className="ticketed-load-panel" aria-label="Estimated capacity and historical ticket-demand snapshot">
    <div className="ticketed-load-heading"><span className="panel-kicker">BUS CAPACITY & HISTORICAL LOAD</span><strong>{perBus == null ? 'Historical load proxy unavailable for this time bucket' : `~${perBus.toFixed(1)} ticketed passengers / scheduled bus`}</strong><small>{estimate?.scheduled_departures_in_hour ? `${estimate.scheduled_departures_in_hour} scheduled departure(s) in the reference hour` : 'Capacity reference is shown for this scheduled service'}</small></div>
    <div className="ticketed-capacity-grid">
      <div><span>Seating capacity</span><strong>{seats}</strong><small>seats / bus</small></div>
      <div><span>Available seats</span><strong>{capacityOnly ? `≤${availableSeats}` : `~${availableSeats}`}</strong><small>{capacityOnly ? 'nominal upper bound' : 'estimated free'}</small></div>
      <div><span>Standing capacity</span><strong>{standing}</strong><small>standing spaces / bus</small></div>
      <div><span>Standing space free</span><strong>{capacityOnly ? `≤${availableStanding}` : `~${availableStanding}`}</strong><small>{capacityOnly ? 'nominal upper bound' : 'estimated free'}</small></div>
    </div>
    <div className="ticketed-load-meta"><CrowdBadge estimate={estimate} fallbackLabel="Typical network reference" /><span>{estimate?.confidence || 'low'} confidence · {(estimate?.sample_size || 0).toLocaleString()} supporting ticket records</span><span className={`capacity-source-pill ${verified ? 'verified' : ''}`}>{verified ? 'Operator-verified capacity' : 'Planning baseline: 35 seats + 25 standing'}</span></div>
    <p>{estimate?.note || 'Capacity and availability are planning estimates based on historical route demand. They are not live passenger counts or vehicle-specific sensor readings.'} {capacityOnly ? 'The available-place values are nominal upper bounds because a load proxy was not available for this bucket.' : 'Available-place figures are estimated from route-level historical ticket demand and are not a live bus scan.'}</p>
  </section>;
}
