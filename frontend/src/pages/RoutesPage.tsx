import { useEffect, useMemo, useState } from 'react';
import { Activity, ArrowUpRight, BusFront, CalendarClock, LoaderCircle, MapPin, Search, Signpost, Waypoints } from 'lucide-react';
import MapView from '../components/MapView';
import SectionHeader from '../components/SectionHeader';
import CrowdBadge from '../components/CrowdBadge';
import { api, type CrowdSegment, type Route, type Stop, type StopCrowdingDetails } from '../lib/api';

const insufficientCrowd = {
  level: 'insufficient_data' as const,
  label: 'Not enough data',
  confidence: 'low' as const,
  sample_size: 0,
  note: 'No reconciled ticket records were found for this segment.',
};

function segmentKey(from: string, to: string) {
  return `${from}::${to}`;
}

export default function RoutesPage() {
  const [tab, setTab] = useState<'routes' | 'stops'>('routes');
  const [query, setQuery] = useState('');
  const [routes, setRoutes] = useState<Route[]>([]);
  const [stops, setStops] = useState<Stop[]>([]);
  const [selectedRoute, setSelectedRoute] = useState<Route | null>(null);
  const [selectedStop, setSelectedStop] = useState<Stop | null>(null);
  const [routeDetail, setRouteDetail] = useState<Awaited<ReturnType<typeof api.route>> | null>(null);
  const [segmentRows, setSegmentRows] = useState<CrowdSegment[]>([]);
  const [stopCrowding, setStopCrowding] = useState<StopCrowdingDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [crowdingLoading, setCrowdingLoading] = useState(false);
  const [error, setError] = useState('');
  const [detailError, setDetailError] = useState('');

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    const timer = window.setTimeout(() => {
      const load = tab === 'routes' ? api.routes(query, 80) : api.stops(query, 80);
      load.then((response) => {
        if (!active) return;
        if (tab === 'routes') setRoutes(response.items as Route[]);
        else setStops(response.items as Stop[]);
        setError('');
      }).catch((err) => {
        if (active) setError(err instanceof Error ? err.message : 'Could not load transit records.');
      }).finally(() => { if (active) setLoading(false); });
    }, 220);
    return () => { active = false; window.clearTimeout(timer); };
  }, [tab, query]);

  async function showRoute(route: Route) {
    setSelectedRoute(route);
    setSelectedStop(null);
    setRouteDetail(null);
    setStopCrowding(null);
    setSegmentRows([]);
    setDetailError('');
    setDetailLoading(true);
    setCrowdingLoading(true);
    const [detailResult, crowdResult] = await Promise.allSettled([
      api.route(route.route_id),
      api.segments(route.route_id),
    ]);
    if (detailResult.status === 'fulfilled') setRouteDetail(detailResult.value);
    else {
      setDetailError(detailResult.reason instanceof Error ? detailResult.reason.message : 'Route details could not be loaded.');
    }
    if (crowdResult.status === 'fulfilled') setSegmentRows(crowdResult.value.items || []);
    else setSegmentRows([]);
    setDetailLoading(false);
    setCrowdingLoading(false);
  }

  async function showStop(stop: Stop) {
    setSelectedStop(stop);
    setSelectedRoute(null);
    setRouteDetail(null);
    setSegmentRows([]);
    setStopCrowding(null);
    setDetailError('');
    setCrowdingLoading(true);
    try {
      setStopCrowding(await api.stopCrowding(stop.stop_id));
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : 'Stop crowding information is unavailable.');
    } finally {
      setCrowdingLoading(false);
    }
  }

  const segmentsByPair = useMemo(() => {
    const map = new Map<string, CrowdSegment>();
    segmentRows.forEach((segment) => map.set(segmentKey(segment.from_stop_id, segment.to_stop_id), segment));
    return map;
  }, [segmentRows]);

  return (
    <div className="page-stack">
      <SectionHeader eyebrow="TRANSIT DIRECTORY" title="The network, made navigable." description="Explore Delhi bus routes, scheduled stop patterns and individual stops." action={<span className="source-chip"><Waypoints size={14} /> Static GTFS network + historical crowding</span>} />
      <div className="directory-layout">
        <section className="panel directory-panel">
          <div className="directory-tabs">
            <button className={tab === 'routes' ? 'active' : ''} onClick={() => { setTab('routes'); setQuery(''); setSelectedStop(null); setSelectedRoute(null); }}><BusFront size={15} /> Routes</button>
            <button className={tab === 'stops' ? 'active' : ''} onClick={() => { setTab('stops'); setQuery(''); setSelectedStop(null); setSelectedRoute(null); }}><MapPin size={15} /> Stops</button>
          </div>
          <div className="search-box directory-search"><Search size={16} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={tab === 'routes' ? 'Search route number or name' : 'Search stop name or code'} /></div>
          {error && <div className="inline-alert">{error}</div>}
          {loading ? <div className="loading-row compact"><LoaderCircle className="spin" /> Loading {tab}…</div> : <div className="directory-list">
            {tab === 'routes' && routes.map((route) => <button key={route.route_id} className={`directory-item ${selectedRoute?.route_id === route.route_id ? 'active' : ''}`} onClick={() => void showRoute(route)}><span className="directory-route-number">{route.route_short_name || route.route_id}</span><span className="directory-item-copy"><strong>{route.route_long_name || route.route_short_name}</strong><small>{route.agency_id || 'Delhi transit'} · ID {route.route_id}</small></span><ArrowUpRight size={15} /></button>)}
            {tab === 'stops' && stops.map((stop) => <button key={stop.stop_id} className={`directory-item ${selectedStop?.stop_id === stop.stop_id ? 'active' : ''}`} onClick={() => void showStop(stop)}><span className="directory-stop-icon"><MapPin size={16} /></span><span className="directory-item-copy"><strong>{stop.stop_name}</strong><small>{stop.stop_code || stop.stop_id} · {stop.stop_lat?.toFixed(4) ?? '—'}, {stop.stop_lon?.toFixed(4) ?? '—'}</small></span><ArrowUpRight size={15} /></button>)}
            {((tab === 'routes' && !routes.length) || (tab === 'stops' && !stops.length)) && <div className="empty-state small-empty">No matching records.</div>}
          </div>}
          <div className="directory-footer">Showing {tab === 'routes' ? routes.length : stops.length} {tab}</div>
        </section>

        <section className="panel directory-detail">
          {selectedRoute ? <>
            <div className="directory-detail-head"><div><span className="panel-kicker">ROUTE DETAIL</span><h2>{selectedRoute.route_short_name || selectedRoute.route_id}</h2><p>{selectedRoute.route_long_name || selectedRoute.route_desc || `GTFS route ${selectedRoute.route_id}`}</p></div><span className="detail-icon"><BusFront size={20} /></span></div>
            {detailLoading ? <div className="loading-row"><LoaderCircle className="spin" /> Loading route and crowding details…</div> : routeDetail ? <>
              <div className="route-detail-map"><MapView line={routeDetail.geometry} fitPoints={routeDetail.geometry} stopMarkers={routeDetail.stops} /></div>
              <div className="route-detail-summary"><span><Signpost size={14} /> {routeDetail.stops.length} stops in representative GTFS pattern</span><CrowdBadge estimate={routeDetail.crowding} /></div>
              <section className="directory-crowd-card">
                <div className="directory-crowd-heading"><div><span className="panel-kicker">ROUTE CROWDING</span><h3>Historical demand for this route</h3></div><Activity size={18} /></div>
                <div className="directory-crowd-stats">
                  <div><span>Typical ticket demand</span><strong>{routeDetail.crowding?.passenger_journeys_median == null ? '—' : routeDetail.crowding.passenger_journeys_median.toLocaleString()}</strong></div>
                  <div><span>Ticket sample</span><strong>{routeDetail.crowding?.sample_size == null ? '—' : routeDetail.crowding.sample_size.toLocaleString()}</strong></div>
                  <div><span>Observed days</span><strong>{routeDetail.crowding?.observed_days ?? '—'}</strong></div>
                  <div><span>Confidence</span><strong className="capitalize">{routeDetail.crowding?.confidence || 'low'}</strong></div>
                </div>
                <p>October 2026 ticket-demand estimate for the current local time bucket. This is not a live passenger count.</p>
              </section>
              <section className="segment-crowding-section">
                <div className="segment-crowding-heading"><div><span className="panel-kicker">STOP-TO-STOP INTELLIGENCE</span><h3>Crowding along this route</h3><p>Each badge describes historical ticket demand between consecutive stops.</p></div><span className="source-chip"><CalendarClock size={13} /> October 2026</span></div>
                {crowdingLoading ? <div className="loading-row compact"><LoaderCircle className="spin" /> Loading segment estimates…</div> : routeDetail.stops.length > 1 ? <div className="segment-crowding-list">
                  {routeDetail.stops.slice(0, -1).map((stop, index) => {
                    const next = routeDetail.stops[index + 1];
                    const match = segmentsByPair.get(segmentKey(stop.stop_id, next.stop_id));
                    const estimate = match?.crowding || insufficientCrowd;
                    return <div className="segment-crowding-row" key={`${stop.stop_id}-${next.stop_id}`}>
                      <span className="sequence-index">{index + 1}</span>
                      <div className="segment-crowding-copy"><strong>{stop.stop_name} <span>to</span> {next.stop_name}</strong><small>{match ? `${match.average_passenger_journeys == null ? 'No demand estimate' : `${match.average_passenger_journeys.toLocaleString()} ticketed journeys`} · ${match.crowding.estimated_ticketed_passengers_per_bus == null ? 'per-bus estimate unavailable' : `${match.crowding.estimated_ticketed_passengers_per_bus.toLocaleString()} ticketed passengers / scheduled bus`} · ${match.ticket_count.toLocaleString()} tickets · ${match.observed_days} observed days` : 'No matched historical ticket data for this exact stop pair'}</small></div>
                      <div className="segment-crowding-status"><CrowdBadge estimate={estimate} /><small>{estimate.confidence || 'low'} confidence</small></div>
                    </div>;
                  })}
                </div> : <div className="chart-empty">No consecutive stop pairs are available for this route.</div>}
                {!crowdingLoading && !segmentRows.length && <p className="segment-no-data"><InfoIcon /> No exact stop-pair aggregates were returned. Segment badges are marked “Not enough data” rather than inferred from another segment.</p>}
              </section>
              <section className="route-stop-sequence-section">
                <div className="segment-crowding-heading"><div><span className="panel-kicker">GTFS STOP ORDER</span><h3>All stops on this route</h3></div><span className="route-stop-count">{routeDetail.stops.length} stops</span></div>
                <div className="stop-sequence-list">{routeDetail.stops.map((stop, index) => <div className="stop-sequence-row" key={`${stop.stop_id}-${stop.stop_sequence}`}><span className="sequence-index">{index + 1}</span><strong>{stop.stop_name}</strong><small>{stop.stop_code || stop.stop_id}</small></div>)}</div>
              </section>
            </> : <div className="empty-state">{detailError || 'Route details could not be loaded.'}</div>}
          </> : selectedStop ? <>
            <div className="directory-detail-head"><div><span className="panel-kicker">STOP DETAIL</span><h2>{selectedStop.stop_name}</h2><p>Stop code {selectedStop.stop_code || selectedStop.stop_id}</p></div><span className="detail-icon"><MapPin size={20} /></span></div>
            {selectedStop.stop_lat != null && selectedStop.stop_lon != null ? <div className="route-detail-map stop-detail-map"><MapView fitPoints={[[selectedStop.stop_lat, selectedStop.stop_lon]]} stopMarkers={[selectedStop]} zoom={16} /></div> : <div className="empty-state">Coordinates are not available for this stop.</div>}
            <div className="stop-coordinate-card"><span>Latitude</span><strong>{selectedStop.stop_lat ?? '—'}</strong><span>Longitude</span><strong>{selectedStop.stop_lon ?? '—'}</strong><span>GTFS stop ID</span><strong>{selectedStop.stop_id}</strong></div>
            <section className="stop-served-routes">
              <div className="segment-crowding-heading"><div><span className="panel-kicker">CROWDING AT THIS STOP</span><h3>Routes serving this stop</h3><p>Route-level and adjacent-segment ticket-demand estimates.</p></div><span className="route-stop-count">{stopCrowding?.routes_count ?? '—'} routes</span></div>
              {crowdingLoading ? <div className="loading-row compact"><LoaderCircle className="spin" /> Loading routes and crowding…</div> : stopCrowding?.routes.length ? <div className="stop-served-route-list">
                {stopCrowding.routes.map((route) => <article className="stop-served-route-card" key={route.route_id}>
                  <div className="stop-served-route-top"><div><strong>{route.route_short_name || route.route_id}</strong><small>{route.route_long_name || `GTFS route ${route.route_id}`} · stop sequence {route.stop_sequence}</small></div><CrowdBadge estimate={route.crowding} /></div>
                  <div className="stop-adjacent-crowds">
                    <div><small>Previous segment</small><span>{route.previous_segment ? `${route.previous_segment.from_stop_name} → ${route.previous_segment.to_stop_name}` : 'Start of representative pattern'}</span>{route.previous_segment && <CrowdBadge estimate={route.previous_segment.crowding} />}</div>
                    <div><small>Next segment</small><span>{route.next_segment ? `${route.next_segment.from_stop_name} → ${route.next_segment.to_stop_name}` : 'End of representative pattern'}</span>{route.next_segment && <CrowdBadge estimate={route.next_segment.crowding} />}</div>
                  </div>
                  <button className="text-action" onClick={() => void showRoute({ route_id: route.route_id, route_short_name: route.route_short_name, route_long_name: route.route_long_name })}>View route stops <ArrowUpRight size={13} /></button>
                </article>)}
              </div> : <div className="directory-no-routes">{detailError || 'No routes are associated with this stop in the representative GTFS stop patterns.'}</div>}
              <p className="segment-no-data"><InfoIcon /> Crowd levels are historical ticket-demand estimates, not current passenger counts.</p>
            </section>
          </> : <div className="directory-empty"><div className="directory-empty-art"><Waypoints size={30} /></div><strong>Explore the Delhi network</strong><p>Select a route to see its shape, stop-by-stop crowding and complete stop pattern, or choose a stop to see the routes and crowding around it.</p></div>}
        </section>
      </div>
    </div>
  );
}

function InfoIcon() {
  return <span className="info-dot" aria-hidden="true">i</span>;
}
