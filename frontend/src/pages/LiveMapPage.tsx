import { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, Clock3, LocateFixed, MapPinned, RefreshCw, Search, Signal, Wifi, WifiOff } from 'lucide-react';
import MapView from '../components/MapView';
import SectionHeader from '../components/SectionHeader';
import { api, type LiveSnapshot, type Vehicle } from '../lib/api';

function ageLabel(seconds?: number | null) {
  if (seconds === null || seconds === undefined) return 'Timestamp unavailable';
  if (seconds < 60) return `${Math.round(seconds)} sec ago`;
  return `${Math.floor(seconds / 60)} min ago`;
}

export default function LiveMapPage() {
  const [snapshot, setSnapshot] = useState<LiveSnapshot | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [freshness, setFreshness] = useState('all');
  const [selected, setSelected] = useState<Vehicle | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const refresh = useCallback(async (force = false) => {
    if (force) setRefreshing(true);
    try {
      const result = await api.liveVehicles(force);
      setSnapshot(result);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load live vehicles.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), 30_000);
    return () => window.clearInterval(id);
  }, [refresh]);

  const filtered = useMemo(() => (snapshot?.vehicles || []).filter((vehicle) => {
    const matchesSearch = !search || `${vehicle.vehicle_id} ${vehicle.route_short_name} ${vehicle.route_id}`.toLowerCase().includes(search.toLowerCase());
    const matchesFreshness = freshness === 'all' || vehicle.freshness === freshness;
    return matchesSearch && matchesFreshness;
  }), [snapshot, search, freshness]);

  const counts = useMemo(() => {
    const all = snapshot?.vehicles || [];
    return {
      fresh: all.filter((v) => v.freshness === 'fresh').length,
      delayed: all.filter((v) => v.freshness === 'delayed').length,
      stale: all.filter((v) => v.freshness === 'stale' || v.freshness === 'unknown' || v.freshness === 'future_timestamp').length,
    };
  }, [snapshot]);

  return (
    <div className="page-stack">
      <SectionHeader eyebrow="LIVE OPERATIONS" title="Delhi, in motion." description="A live view of vehicle positions reported by the Transport Stack feed." action={<button className="secondary-button" onClick={() => void refresh(true)} disabled={refreshing}><RefreshCw size={15} className={refreshing ? 'spin' : ''} /> Refresh feed</button>} />
      <div className="live-stats-grid">
        <div className="metric-card"><span className="metric-label">POSITIONS RECEIVED</span><strong>{snapshot?.returned_count?.toLocaleString() ?? '—'}</strong><span className="metric-foot"><MapPinned size={14} /> Vehicle entities with coordinates</span></div>
        <div className="metric-card"><span className="metric-label">FRESH POSITIONS</span><strong>{counts.fresh.toLocaleString()}</strong><span className="metric-foot"><span className="status-dot fresh" /> ≤ 90 seconds old</span></div>
        <div className="metric-card"><span className="metric-label">DELAYED POSITIONS</span><strong>{counts.delayed.toLocaleString()}</strong><span className="metric-foot"><span className="status-dot delayed" /> 91 seconds – 5 minutes</span></div>
        <div className="metric-card"><span className="metric-label">STALE / UNKNOWN</span><strong>{counts.stale.toLocaleString()}</strong><span className="metric-foot"><span className="status-dot stale" /> Older than 5 minutes or unknown</span></div>
      </div>
      <div className="live-map-layout">
        <section className="panel map-workspace">
          <div className="map-toolbar">
            <div className="search-box compact-search"><Search size={16} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Find vehicle or route" /></div>
            <select value={freshness} onChange={(e) => setFreshness(e.target.value)} aria-label="Filter by GPS freshness"><option value="all">All positions</option><option value="fresh">Fresh</option><option value="delayed">Delayed</option><option value="stale">Stale</option></select>
            <span className={`feed-status ${snapshot?.status === 'connected' ? 'is-connected' : 'is-muted'}`}>{snapshot?.status === 'connected' ? <Wifi size={14} /> : <WifiOff size={14} />}{snapshot?.status === 'connected' ? 'Feed connected' : snapshot?.status === 'not_configured' ? 'API key required' : 'Feed unavailable'}</span>
          </div>
          <MapView vehicles={filtered} selectedVehicleId={selected?.vehicle_id} onVehicleSelect={setSelected} className="live-map-canvas" zoom={10} />
          <div className="map-legend-row"><span><i className="legend-dot fresh" /> Fresh</span><span><i className="legend-dot delayed" /> Delayed</span><span><i className="legend-dot stale" /> Stale / unknown</span><span className="legend-spacer" /><span>{filtered.length.toLocaleString()} shown</span></div>
          {loading && <div className="map-overlay"><div className="map-overlay-card"><Activity className="spin" /><strong>Connecting to vehicle feed</strong><span>Checking the FastAPI service…</span></div></div>}
          {(error || (snapshot && snapshot.status !== 'connected')) && !loading && <div className="feed-notice"><Signal size={16} /><span>{error || snapshot?.message || 'Live vehicle feed is not connected.'}</span></div>}
        </section>
        <aside className="panel vehicle-panel">
          <div className="panel-heading"><div><span className="panel-kicker">VEHICLE DETAILS</span><h2>{selected ? selected.vehicle_id : 'Select a bus'}</h2></div><span className="panel-icon"><BusIcon /></span></div>
          {selected ? <div className="vehicle-detail-content">
            <div className="vehicle-route-pill">{selected.route_short_name || selected.route_id} <span>{selected.route_long_name || 'Delhi bus route'}</span></div>
            <div className="vehicle-detail-row"><span>Vehicle ID</span><strong>{selected.vehicle_id}</strong></div>
            <div className="vehicle-detail-row"><span>Route ID</span><strong>{selected.route_id}</strong></div>
            <div className="vehicle-detail-row"><span>GPS age</span><strong>{ageLabel(selected.age_seconds)}</strong></div>
            <div className="vehicle-detail-row"><span>Freshness</span><strong className={`freshness-text ${selected.freshness}`}>{selected.freshness.replace('_', ' ')}</strong></div>
            <div className="vehicle-detail-row"><span>Speed</span><strong>{selected.speed_mps == null ? '—' : `${(selected.speed_mps * 3.6).toFixed(1)} km/h`}</strong></div>
            <div className="vehicle-detail-row"><span>Bearing</span><strong>{selected.bearing == null ? '—' : `${Math.round(selected.bearing)}°`}</strong></div>
            <div className="vehicle-coordinates"><LocateFixed size={15} /> {selected.latitude.toFixed(5)}, {selected.longitude.toFixed(5)}</div>
          </div> : <div className="vehicle-empty"><div className="vehicle-empty-icon"><MapPinned size={25} /></div><strong>Choose a marker on the map</strong><p>Vehicle identity, route, timestamp and GPS quality appear here.</p></div>}
          <div className="panel-divider" />
          <div className="feed-meta"><span><Clock3 size={14} /> Last fetched</span><strong>{snapshot?.fetched_at ? new Date(snapshot.fetched_at).toLocaleTimeString() : 'Not available'}</strong></div>
          <div className="feed-meta"><span><RefreshCw size={14} /> Poll interval</span><strong>30 seconds</strong></div>
        </aside>
      </div>
    </div>
  );
}

function BusIcon() {
  return <span className="bus-icon-visual">▰</span>;
}
