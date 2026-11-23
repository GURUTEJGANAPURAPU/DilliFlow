import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import {
  Activity, AlertTriangle, ArrowDownRight, ArrowUpRight, BusFront,
  Clock3, Download, LogIn, LogOut, LockKeyhole, RefreshCw, Route as RouteIcon,
  Save, Search, ShieldCheck, Ticket, TrendingUp, Users, XCircle, Gauge,
} from 'lucide-react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import SectionHeader from '../components/SectionHeader';
import CrowdBadge from '../components/CrowdBadge';
import { api, type OperatorCapacity, type OperatorDashboard, type OperatorSegment } from '../lib/api';

const TOKEN_KEY = 'dilliflow.operator.session';

function hourLabel(hour: number) {
  return new Date(2000, 0, 1, hour).toLocaleTimeString('en-IN', { hour: 'numeric', hour12: true });
}

export default function OperatorPage() {
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_KEY) || '');
  const [operatorId, setOperatorId] = useState('');
  const [password, setPassword] = useState('');
  const [loginBusy, setLoginBusy] = useState(false);
  const [loginError, setLoginError] = useState('');
  const [operatorName, setOperatorName] = useState('');
  const [hour, setHour] = useState(new Date().getHours());
  const [dayType, setDayType] = useState<'weekday' | 'weekend'>('weekday');
  const [dashboard, setDashboard] = useState<OperatorDashboard | null>(null);
  const [capacities, setCapacities] = useState<OperatorCapacity[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [refreshKey, setRefreshKey] = useState(0);
  const [capacityRoute, setCapacityRoute] = useState('');
  const [seats, setSeats] = useState('');
  const [standing, setStanding] = useState('');
  const [capacityBusy, setCapacityBusy] = useState(false);
  const [capacityMessage, setCapacityMessage] = useState('');
  const [segmentSearch, setSegmentSearch] = useState('');
  const [priorityFilter, setPriorityFilter] = useState<'all' | 'high' | 'review' | 'monitor'>('all');

  const logout = useCallback(() => {
    sessionStorage.removeItem(TOKEN_KEY);
    setToken('');
    setDashboard(null);
    setCapacities([]);
    setOperatorName('');
  }, []);

  useEffect(() => {
    if (!token) return;
    let alive = true;
    setLoading(true);
    setError('');
    Promise.all([api.operatorDashboard(token, hour, dayType), api.operatorCapacities(token)])
      .then(([data, profiles]) => {
        if (!alive) return;
        setDashboard(data);
        setCapacities(profiles.items || []);
        setOperatorName((current) => current || 'Operator');
        setError('');
      })
      .catch((err: unknown) => {
        if (!alive) return;
        const message = err instanceof Error ? err.message : 'Operator data could not be loaded.';
        setError(message);
        if (/401|invalid or expired|login required/i.test(message)) logout();
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [token, hour, dayType, refreshKey, logout]);

  async function signIn(event: FormEvent) {
    event.preventDefault();
    setLoginBusy(true);
    setLoginError('');
    try {
      const result = await api.operatorLogin(operatorId.trim(), password);
      sessionStorage.setItem(TOKEN_KEY, result.access_token);
      setToken(result.access_token);
      setOperatorName(result.operator_id);
      setPassword('');
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : 'Operator sign-in failed.');
    } finally {
      setLoginBusy(false);
    }
  }

  async function saveCapacity(event: FormEvent) {
    event.preventDefault();
    if (!token || !capacityRoute || Number(seats) < 1 || Number(standing) < 0) return;
    setCapacityBusy(true);
    setCapacityMessage('');
    try {
      await api.saveOperatorCapacity(token, capacityRoute, Number(seats), Number(standing));
      setCapacityMessage('Verified route capacity saved. Passenger-facing crowd labels will now use this configured baseline.');
      setRefreshKey((value) => value + 1);
    } catch (err) {
      setCapacityMessage(err instanceof Error ? err.message : 'Capacity profile could not be saved.');
    } finally {
      setCapacityBusy(false);
    }
  }

  async function removeCapacity(routeId: string) {
    if (!token || !window.confirm(`Remove the capacity profile for route ${routeId}? Crowd badges will return to relative demand levels.`)) return;
    try {
      await api.deleteOperatorCapacity(token, routeId);
      setRefreshKey((value) => value + 1);
    } catch (err) {
      setCapacityMessage(err instanceof Error ? err.message : 'Capacity profile could not be removed.');
    }
  }

  // Keep all hooks above conditional render branches to preserve React hook order
  // for both logged-out and authenticated renders.
  if (!token) {
    return <div className="page-stack operator-login-page">
      <SectionHeader eyebrow="RESTRICTED OPERATIONS" title="Operator workspace." description="A separate workspace for transport operators and planning teams. Commuter journey planning remains public and does not require an account." action={<span className="source-chip"><LockKeyhole size={14} /> Operator access only</span>} />
      <div className="operator-login-layout">
        <section className="panel operator-login-card">
          <div className="operator-login-icon"><ShieldCheck size={24} /></div>
          <span className="panel-kicker">SECURE OPERATOR SIGN-IN</span>
          <h2>Welcome to operations.</h2>
          <p>Sign in with the operator ID and password configured by the DilliFlow administrator.</p>
          <form onSubmit={signIn} className="operator-login-form">
            <label>OPERATOR ID<input autoComplete="username" value={operatorId} onChange={(event) => setOperatorId(event.target.value)} placeholder="Enter operator ID" required /></label>
            <label>PASSWORD<input autoComplete="current-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Enter password" required /></label>
            {loginError && <div className="inline-alert"><AlertTriangle size={15} />{loginError}</div>}
            <button className="primary-button" disabled={loginBusy} type="submit"><LogIn size={15} />{loginBusy ? 'Signing in…' : 'Sign in to operations'}</button>
          </form>
          <div className="operator-login-note"><LockKeyhole size={14} /> Commuters can continue using Journey Planner, Live Bus Map and Crowding Insights without signing in.</div>
        </section>
        <aside className="panel operator-login-aside">
          <span className="panel-kicker">WHAT OPERATORS CAN DO</span>
          <h3>Turn ticket evidence into service decisions.</h3>
          <div><Activity size={17} /><span><strong>Identify overloaded stretches</strong><small>See high-demand route segments by hour and direction.</small></span></div>
          <div><BusFront size={17} /><span><strong>Review extra-service priorities</strong><small>Spot areas where current scheduled departures may not meet recorded demand.</small></span></div>
          <div><ShieldCheck size={17} /><span><strong>Configure verified capacity</strong><small>Enter actual seat and standing capacity so commuter labels can be calibrated.</small></span></div>
          <p>Operator recommendations are decision support, not automatic dispatch instructions.</p>
        </aside>
      </div>
    </div>;
  }

  const chartData = useMemo(() => (dashboard?.peak_hours || []).slice().sort((a, b) => a.hour - b.hour).map((item) => ({ ...item, label: hourLabel(item.hour) })), [dashboard]);
  const summary = dashboard?.summary;
  const investigationSegments = dashboard?.investigation_segments || dashboard?.priority_segments || [];
  const filteredInvestigations = useMemo(() => investigationSegments.filter((segment) => {
    const query = segmentSearch.trim().toLowerCase();
    const matchesQuery = !query || [segment.route_short_name, segment.route_long_name, segment.direction, segment.from_stop_name, segment.to_stop_name].join(' ').toLowerCase().includes(query);
    return matchesQuery && (priorityFilter === 'all' || segment.priority === priorityFilter);
  }), [investigationSegments, segmentSearch, priorityFilter]);

  function exportOperatorReport() {
    if (!dashboard) return;
    const rows: Array<Array<string | number>> = [
      ['Report', 'DilliFlow Operator Intelligence'],
      ['Period', `${dashboard.period.start || ''} to ${dashboard.period.end || ''}`],
      ['Selected hour', hourLabel(dashboard.selected_hour)],
      ['Service day', dashboard.day_type],
      [],
      ['Route rank', 'Route', 'GTFS route ID', 'Direction', 'Avg ticketed journeys/day-hour', 'Estimated ticketed passengers/bus', 'Scheduled departures/hour', 'Ticket records', 'Observed days', 'Verified capacity'],
      ...dashboard.route_demand.map((route) => [route.rank || '', route.route_short_name, route.route_id, route.direction, route.average_ticketed_passengers_per_hour, route.estimated_ticketed_passengers_per_bus ?? '', route.scheduled_departures_in_hour, route.ticket_count, route.observed_days, route.capacity_configured ? 'Yes' : 'No']),
      [],
      ['Priority', 'Route', 'GTFS route ID', 'Direction', 'From stop', 'To stop', 'Ticketed passengers/bus', 'Tickets', 'Observed days', 'Recommendation'],
      ...investigationSegments.map((segment) => [segment.priority, segment.route_short_name, segment.route_id, segment.direction, segment.from_stop_name, segment.to_stop_name, segment.estimated_ticketed_passengers_per_bus ?? '', segment.ticket_count, segment.observed_days, segment.recommendation]),
    ];
    const csv = rows.map((row) => row.map((value) => `"${String(value ?? '').replace(/"/g, '""')}"`).join(',')).join('\r\n');
    const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `dilliflow-operator-${dashboard.day_type}-${String(dashboard.selected_hour).padStart(2, '0')}.csv`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  return <div className="page-stack operator-dashboard-page">
    <SectionHeader eyebrow="TRANSPORT OPERATIONS" title="See where service needs attention." description="Route, direction, stop-segment and time-of-day demand signals from the October ticket dataset." action={<div className="operator-user-chip"><ShieldCheck size={14} /> {operatorName || 'Operator'} <button type="button" onClick={logout} aria-label="Sign out"><LogOut size={14} /> Sign out</button></div>} />

    <div className="operator-filter-bar panel">
      <div><span className="panel-kicker">ANALYSIS WINDOW</span><strong>October 2026 ticket reference data</strong></div>
      <label>TIME OF DAY<select value={hour} onChange={(event) => setHour(Number(event.target.value))}>{Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{hourLabel(h)}</option>)}</select></label>
      <label>SERVICE DAY<select value={dayType} onChange={(event) => setDayType(event.target.value as 'weekday' | 'weekend')}><option value="weekday">Weekday</option><option value="weekend">Weekend</option></select></label>
      <button className="secondary-button" type="button" disabled={loading} onClick={() => setRefreshKey((value) => value + 1)}><RefreshCw size={14} /> Refresh analysis</button>
    </div>

    {error && <div className="inline-alert"><AlertTriangle size={15} />{error}<button className="text-action" onClick={() => setRefreshKey((value) => value + 1)}>Retry</button></div>}
    {loading && !dashboard && <div className="loading-row">Loading operator analytics…</div>}
    {dashboard && summary && <>
      <div className="operator-kpi-grid">
        <Kpi icon={<Ticket size={17} />} label="TICKET RECORDS" value={summary.ticket_records.toLocaleString()} detail="October source records" />
        <Kpi icon={<RouteIcon size={17} />} label="ROUTE MATCH" value={`${summary.route_match_percentage.toFixed(1)}%`} detail={`${summary.routes_with_ticket_data.toLocaleString()} routes with ticket data`} />
        <Kpi icon={<MapPinIcon />} label="BOARDING STOP MATCH" value={`${(summary.boarding_stop_match_percentage ?? dashboard.data_quality?.boarding_stop_match_percentage ?? 0).toFixed(1)}%`} detail="Matched ticket origins" />
        <Kpi icon={<MapPinIcon />} label="ALIGHTING STOP MATCH" value={`${(summary.alighting_stop_match_percentage ?? dashboard.data_quality?.alighting_stop_match_percentage ?? 0).toFixed(1)}%`} detail="Matched ticket destinations" />
        <Kpi icon={<Users size={17} />} label="VEHICLE ID MISSING" value={`${summary.missing_vehicle_number_percentage.toFixed(1)}%`} detail="Limits vehicle-level validation" warning />
        <Kpi icon={<ShieldCheck size={17} />} label="VERIFIED CAPACITY PROFILES" value={summary.capacity_profiles_configured.toLocaleString()} detail="Operator-entered route profiles" />
      </div>

      <div className="operator-overview-grid">
        <section className="panel operator-chart-panel">
          <div className="panel-heading"><div><span className="panel-kicker">NETWORK DEMAND</span><h2>When demand concentrates</h2><p>Average ticketed passenger journeys across the network per observed day.</p></div><TrendingUp size={19} /></div>
          <div className="operator-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}><CartesianGrid strokeDasharray="3 5" vertical={false} stroke="#e7ebe6" /><XAxis dataKey="label" tick={{ fontSize: 10, fill: '#87948b' }} interval={2} axisLine={false} tickLine={false} /><YAxis tick={{ fontSize: 10, fill: '#87948b' }} axisLine={false} tickLine={false} /><Tooltip formatter={(value) => [Number(value).toLocaleString(), 'Avg ticketed journeys/day']} /><Bar dataKey="avg_ticketed_journeys" fill="#1b765f" radius={[5, 5, 0, 0]} maxBarSize={26} /></BarChart></ResponsiveContainer></div>
        </section>
        <section className="panel operator-priority-panel">
          <div className="panel-heading"><div><span className="panel-kicker">SERVICE PLANNING</span><h2>Priority stretches</h2><p>Highest demand signals for the selected time bucket.</p></div><Activity size={19} /></div>
          <div className="operator-priority-summary"><strong>{(dashboard.service_recommendations || []).length}</strong><span>action cards for this time bucket</span></div>
          <p>Service-review leads are ranked from ticketed journeys per scheduled departure. Capacity exceedance is only asserted against operator-verified profiles; all other flags request field validation rather than automatic dispatch.</p>
        </section>
      </div>

      <section className="panel operator-recommendations-panel">
        <div className="panel-heading"><div><span className="panel-kicker">DECISION SUPPORT · NOT AUTOMATIC DISPATCH</span><h2>Operator service recommendations</h2><p>Prioritized actions grounded in October ticket demand, scheduled departures and configured route capacity.</p></div><span className="panel-icon"><Gauge size={19} /></span></div>
        <div className="operator-recommendation-grid">
          {(dashboard.service_recommendations || []).map((item, index) => <article className={`operator-recommendation-card recommendation-${item.priority}`} key={`${item.type}-${item.route_id}-${index}`}>
            <div className="operator-recommendation-top"><span className={`operator-priority-label priority-${item.priority}`}>{item.priority === 'high' ? 'HIGH PRIORITY' : item.priority === 'review' ? 'REVIEW' : 'MONITOR'}</span><span>{item.route_short_name || 'Network'} · {item.direction}</span></div>
            <h3>{item.title}</h3>
            <strong className="operator-recommendation-segment">{item.segment}</strong>
            <p className="operator-recommendation-evidence">{item.evidence}</p>
            <p className="operator-recommendation-action"><ShieldCheck size={14} />{item.action}</p>
          </article>)}
          {!(dashboard.service_recommendations || []).length && <div className="operator-no-priority">Service recommendations will appear when matching route-hour and segment records are available for the selected filter.</div>}
        </div>
      </section>

      <section className="panel operator-table-panel">
        <div className="panel-heading"><div><span className="panel-kicker">ROUTE RANKINGS & DIRECTION ANALYSIS</span><h2>Highest demand routes</h2><p>Ranked by median ticketed passengers per scheduled departure, then total hourly demand. Direction is the dominant GTFS trip pattern; ticket records are route-level, not direction-tagged. Ticket proxy, not onboard headcount.</p></div><div className="operator-panel-actions"><span className="source-chip"><Clock3 size={13} /> {hourLabel(hour)} · {dayType}</span><button className="secondary-button" type="button" onClick={exportOperatorReport}><Download size={14} /> Export CSV</button></div></div>
        <div className="operator-table-wrap"><table className="operator-table"><thead><tr><th>RANK</th><th>ROUTE</th><th>REPRESENTATIVE GTFS DIRECTION</th><th>AVG JOURNEYS / DAY-HR</th><th>TICKETED / BUS</th><th>DEPARTURES / HR</th><th>CROWD SIGNAL</th><th>CAPACITY BASIS</th></tr></thead><tbody>
          {dashboard.route_demand.slice(0, 20).map((route) => <tr key={route.route_id}><td><span className="operator-rank">#{route.rank || '—'}</span></td><td><strong>{route.route_short_name}</strong><small>{route.route_long_name || route.route_id} · ID {route.route_id}</small></td><td>{route.direction}</td><td>{route.average_ticketed_passengers_per_hour.toLocaleString('en-IN', { maximumFractionDigits: 1 })}</td><td>{route.estimated_ticketed_passengers_per_bus == null ? 'Network reference' : `~${route.estimated_ticketed_passengers_per_bus.toFixed(1)}`}</td><td>{route.scheduled_departures_in_hour || '—'}</td><td><CrowdBadge estimate={route.crowding} /></td><td>{route.capacity_configured ? <span className="verified-capacity-tag">Verified · {route.crowding.seat_capacity}+{route.crowding.standing_capacity}</span> : <span className="muted-tag">Planning baseline</span>}</td></tr>)}
        </tbody></table></div>
      </section>

      <section className="panel operator-overload-panel" id="segment-investigations">
        <div className="panel-heading"><div><span className="panel-kicker">STOP-TO-STOP LOAD ESTIMATES</span><h2>Overloaded-segment investigations</h2><p>Search and review route stretches, ticket evidence, per-departure estimates and recommended next actions.</p></div><span className="panel-icon"><BusFront size={19} /></span></div>
        <div className="operator-investigation-tools">
          <label className="operator-search-field"><Search size={15} /><input value={segmentSearch} onChange={(event) => setSegmentSearch(event.target.value)} placeholder="Search route, direction or stop name" /></label>
          <label className="operator-priority-filter">PRIORITY<select value={priorityFilter} onChange={(event) => setPriorityFilter(event.target.value as typeof priorityFilter)}><option value="all">All investigations</option><option value="high">High priority</option><option value="review">Review</option><option value="monitor">Monitor</option></select></label>
          <span className="operator-investigation-count">{filteredInvestigations.length} of {investigationSegments.length} stretches</span>
        </div>
        {filteredInvestigations.length ? <div className="operator-segment-list">{filteredInvestigations.slice(0, 40).map((segment) => <OperatorSegmentRow key={`${segment.route_id}-${segment.from_stop_id}-${segment.to_stop_id}`} segment={segment} />)}</div> : <div className="operator-no-priority"><Search size={18} /><div><strong>No matching segments.</strong><p>Change the search phrase or priority filter.</p></div></div>}
        <p className="operator-disclaimer"><AlertTriangle size={14} /> High and review flags are investigation leads, not proof of overcrowding. Ticket records may omit passengers; validate with field counts and vehicle-specific capacity before dispatch changes.</p>
      </section>

      <section className="panel capacity-panel">
        <div className="panel-heading"><div><span className="panel-kicker">FLEET CAPACITY CONFIGURATION</span><h2>Set verified vehicle capacity by route</h2><p>Verified seat and standing values override the transparent DilliFlow planning baseline (35 seats + 25 standing). Only mark a profile as verified when confirmed for the route fleet; individual vehicle variants may differ.</p></div><span className="panel-icon"><ShieldCheck size={19} /></span></div>
        <form className="capacity-form" onSubmit={saveCapacity}>
          <label>GTFS ROUTE ID<input value={capacityRoute} onChange={(event) => setCapacityRoute(event.target.value)} list="operator-route-options" placeholder="e.g. 641" required /></label>
          <datalist id="operator-route-options">{dashboard.route_demand.map((route) => <option key={route.route_id} value={route.route_id}>{route.route_short_name}</option>)}</datalist>
          <label>SEATS<input type="number" min="1" max="500" value={seats} onChange={(event) => setSeats(event.target.value)} placeholder="Verified seats" required /></label>
          <label>STANDING CAPACITY<input type="number" min="0" max="1000" value={standing} onChange={(event) => setStanding(event.target.value)} placeholder="Verified standing capacity" required /></label>
          <button className="primary-button" disabled={capacityBusy || !capacityRoute}><Save size={14} />{capacityBusy ? 'Saving…' : 'Save verified capacity'}</button>
        </form>
        {capacityMessage && <div className="capacity-message"><InfoIcon />{capacityMessage}</div>}
        <div className="capacity-profile-list">{capacities.length ? capacities.map((profile) => <div className="capacity-profile-row" key={profile.route_id}><div><strong>{profile.route_short_name || profile.route_id}</strong><small>GTFS ID {profile.route_id} · {profile.seat_capacity} seats + {profile.standing_capacity} standing</small></div><span>{profile.seat_capacity + profile.standing_capacity} total</span><button type="button" className="text-action danger-action" onClick={() => void removeCapacity(profile.route_id)}><XCircle size={13} /> Remove</button></div>) : <div className="empty-state compact-empty">No verified capacity profiles configured yet. Relative crowding estimates remain available in the commuter dashboard.</div>}</div>
      </section>
      <section className="operator-data-quality-panel">
        <div><strong>Data quality & interpretation</strong><span>Route matching {summary.route_match_percentage.toFixed(1)}% · Boarding stops {(summary.boarding_stop_match_percentage ?? 0).toFixed(1)}% · Alighting stops {(summary.alighting_stop_match_percentage ?? 0).toFixed(1)}% · Vehicle IDs missing {summary.missing_vehicle_number_percentage.toFixed(1)}%</span></div>
        <small>Low stop-name coverage and missing vehicle identifiers can weaken segment or vehicle-level conclusions. Network and planning fallbacks are explicitly labelled.</small>
      </section>
      <section className="operator-method-note"><InfoIcon /><span>{dashboard.methodology}</span></section>
    </>}
  </div>;
}

function Kpi({ icon, label, value, detail, warning = false }: { icon: ReactNode; label: string; value: string; detail: string; warning?: boolean }) {
  return <article className="metric-card"><div className="metric-card-top"><span className="metric-label">{label}</span><span className={`metric-icon ${warning ? 'warn' : ''}`}>{icon}</span></div><strong>{value}</strong><span className="metric-foot">{detail}</span></article>;
}

function OperatorSegmentRow({ segment }: { segment: OperatorSegment }) {
  const priorityClass = `priority-${segment.priority}`;
  return <article className="operator-segment-row"><span className={`operator-priority-mark ${priorityClass}`}><ArrowUpRight size={16} /></span><div className="operator-segment-main"><div className="operator-segment-title"><strong>{segment.route_short_name}</strong><span>{segment.direction}</span><span className={`operator-priority-label ${priorityClass}`}>{segment.priority === 'high' ? 'Capacity pressure' : segment.priority === 'review' ? 'Review frequency' : 'Monitor'}</span></div><strong className="operator-segment-stops">{segment.from_stop_name} <ArrowDownRight size={13} /> {segment.to_stop_name}</strong><small>{segment.route_long_name || segment.route_id} · {segment.ticket_count.toLocaleString()} tickets · {segment.observed_days} observed days · {segment.scheduled_departures_in_hour} departures / hr</small><p>{segment.recommendation}</p></div><div className="operator-segment-load"><strong>{segment.estimated_ticketed_passengers_per_bus == null ? 'Network ref.' : segment.estimated_ticketed_passengers_per_bus.toFixed(1)}</strong><small>ticketed / bus</small><CrowdBadge estimate={segment.crowding} /></div></article>;
}

function MapPinIcon() { return <RouteIcon size={17} />; }
function InfoIcon() { return <span className="info-dot">i</span>; }
