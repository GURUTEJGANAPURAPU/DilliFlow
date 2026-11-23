import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { Activity, AlertTriangle, CalendarDays, BarChart3, Info, LoaderCircle, RefreshCw, TrendingUp } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import SectionHeader from '../components/SectionHeader';
import CrowdBadge from '../components/CrowdBadge';
import { api, type CrowdEstimate } from '../lib/api';

interface Overview {
  ticket_records?: number;
  matched_ticket_records?: number;
  routes_with_ticket_data?: number;
  observed_dates?: number;
  missing_vehicle_number_pct?: number;
  route_match_pct?: number;
  boarding_stop_match_pct?: number;
  alighting_stop_match_pct?: number;
  period?: { start?: string; end?: string };
  top_demand_routes?: Array<{ route_id: string; route_short_name: string; route_long_name: string; average_ticket_demand: number; ticket_count: number; crowding: CrowdEstimate }>;
  methodology?: string;
}

export default function InsightsPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [trend, setTrend] = useState<Array<{ hour: number; passenger_journeys: number; ticket_count: number }>>([]);
  const [dayType, setDayType] = useState('weekday');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    setLoading(true);
    let active = true;
    Promise.allSettled([api.crowdingOverview(), api.trends(dayType)])
      .then(([summaryResult, chartResult]) => {
        if (!active) return;
        const messages: string[] = [];
        if (summaryResult.status === 'fulfilled') {
          setOverview(summaryResult.value as Overview);
        } else {
          messages.push(summaryResult.reason instanceof Error ? summaryResult.reason.message : 'Crowding summary could not be loaded.');
        }
        if (chartResult.status === 'fulfilled') {
          setTrend(chartResult.value.items || []);
        } else {
          setTrend([]);
          messages.push('Hourly trend data could not be loaded.');
        }
        setError(messages.join(' '));
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [dayType, retry]);

  const chartData = trend.map((item) => ({ ...item, label: `${String(item.hour).padStart(2, '0')}:00` }));
  const topRoutes = overview?.top_demand_routes || [];

  return (
    <div className="page-stack">
      <SectionHeader eyebrow="CROWDING INTELLIGENCE" title="Read the rhythm of the city." description="Historical ticket demand, translated into useful route and time patterns." action={<span className="source-chip"><CalendarDays size={14} /> October 2026 reference period</span>} />
      {error && <div className="inline-alert insights-error"><AlertTriangle size={16} /><span>{error}</span><button type="button" className="text-action" onClick={() => setRetry((value) => value + 1)}><RefreshCw size={13} /> Retry</button></div>}
      {loading && <div className="loading-row"><LoaderCircle className="spin" /> Loading verified ticket aggregates…</div>}
      {!loading && overview && <>
        <div className="insights-intro"><div className="insights-icon"><BarChart3 size={22} /></div><div><strong>Ticket-based demand intelligence</strong><p>All metrics below are calculated from the October 2026 ticket file after route and stop reconciliation. They are not measurements of actual onboard occupancy.</p></div></div>
        <div className="insights-metrics-grid">
          <Metric label="TICKET RECORDS" value={overview.ticket_records?.toLocaleString() || '—'} detail={`${overview.matched_ticket_records?.toLocaleString() || '—'} matched to GTFS routes`} icon={<Activity size={17} />} />
          <Metric label="ROUTES WITH DATA" value={overview.routes_with_ticket_data?.toLocaleString() || '—'} detail={`${overview.observed_dates ?? '—'} observed dates`} icon={<TrendingUp size={17} />} />
          <Metric label="VEHICLE NUMBER MISSING" value={overview.missing_vehicle_number_pct == null ? '—' : `${overview.missing_vehicle_number_pct.toFixed(1)}%`} detail="Limits bus-level attribution" icon={<AlertTriangle size={17} />} warn />
          <Metric label="ROUTE MATCH RATE" value={overview.route_match_pct == null ? '—' : `${overview.route_match_pct.toFixed(1)}%`} detail="Ticket route to GTFS route" icon={<Activity size={17} />} />
        </div>
        <div className="insights-grid">
          <section className="panel chart-panel">
            <div className="panel-heading"><div><span className="panel-kicker">DEMAND BY HOUR</span><h2>When Delhi boards</h2><p>Sum of ticket passenger journeys across matched routes.</p></div><select value={dayType} onChange={(e) => setDayType(e.target.value)}><option value="weekday">Weekdays</option><option value="weekend">Weekends</option></select></div>
            <div className="chart-wrap">
              {chartData.length ? <ResponsiveContainer width="100%" height="100%"><BarChart data={chartData} margin={{ top: 12, right: 8, bottom: 0, left: -18 }}><CartesianGrid strokeDasharray="3 5" vertical={false} stroke="#e7e9e3" /><XAxis dataKey="label" tick={{ fill: '#7b827d', fontSize: 11 }} axisLine={false} tickLine={false} interval={2} /><YAxis tick={{ fill: '#7b827d', fontSize: 11 }} axisLine={false} tickLine={false} /><Tooltip cursor={{ fill: '#edf3ef' }} contentStyle={{ border: '1px solid #e5e9e4', borderRadius: 12, boxShadow: '0 10px 28px rgba(31,50,41,.08)' }} formatter={(value) => [Number(value).toLocaleString(), 'Passenger journeys']} /><Bar dataKey="passenger_journeys" fill="#177c67" radius={[5, 5, 0, 0]} maxBarSize={30} /></BarChart></ResponsiveContainer> : <div className="chart-empty">No trend data for this selection.</div>}
            </div>
            <div className="chart-source-note"><Info size={13} /> Aggregated historical ticket journeys · not a live count</div>
          </section>
          <section className="panel demand-panel">
            <div className="panel-heading"><div><span className="panel-kicker">ROUTE SIGNALS</span><h2>Higher ticket demand</h2></div><span className="panel-icon"><TrendingUp size={19} /></span></div>
            {topRoutes.length ? <div className="demand-route-list">{topRoutes.map((route, i) => <div className="demand-route-row" key={route.route_id}><span className="demand-rank">{String(i + 1).padStart(2, '0')}</span><div className="demand-route-name"><strong>{route.route_short_name}</strong><small>{route.route_long_name || route.route_id}</small></div><div className="demand-route-value"><strong>{route.average_ticket_demand.toLocaleString()}</strong><small>avg ticket demand</small></div><CrowdBadge estimate={route.crowding} /></div>)}</div> : <div className="chart-empty">No matched ticket route aggregates found.</div>}
          </section>
        </div>
        <section className="panel quality-panel">
          <div className="panel-heading"><div><span className="panel-kicker">DATA QUALITY</span><h2>Know what the numbers can say</h2><p>Coverage indicators for interpreting the October ticket data.</p></div><span className="panel-icon"><ShieldCheckIcon /></span></div>
          <div className="quality-grid">
            <Quality label="Route name match" value={overview.route_match_pct} />
            <Quality label="Boarding stop match" value={overview.boarding_stop_match_pct} />
            <Quality label="Alighting stop match" value={overview.alighting_stop_match_pct} />
            <Quality label="Vehicle number missing" value={overview.missing_vehicle_number_pct} reverse />
          </div>
          <p className="quality-footnote"><Info size={14} /> Segment-level demand is estimated by spreading ticket journeys across a representative GTFS stop order. Unmatched stop names are excluded from segment estimates.</p>
        </section>
      </>}
      {!loading && !overview && !error && <div className="empty-state">Crowding aggregates are not yet available. Run the backend data-ingestion step.</div>}
      {!loading && !overview && error && <div className="panel retry-panel"><strong>Crowding insights are temporarily unavailable.</strong><p>Check that the FastAPI service is running at http://localhost:8000, then retry.</p><button type="button" className="secondary-button" onClick={() => setRetry((value) => value + 1)}><RefreshCw size={14} /> Retry connection</button></div>}
    </div>
  );
}

function Metric({ label, value, detail, icon, warn = false }: { label: string; value: string; detail: string; icon: ReactNode; warn?: boolean }) {
  return <div className="metric-card"><div className="metric-card-top"><span className="metric-label">{label}</span><span className={`metric-icon ${warn ? 'warn' : ''}`}>{icon}</span></div><strong>{value}</strong><span className="metric-foot">{detail}</span></div>;
}

function Quality({ label, value, reverse = false }: { label: string; value?: number; reverse?: boolean }) {
  const pct = value == null ? 0 : value;
  return <div className="quality-item"><div><span>{label}</span><strong>{value == null ? '—' : `${pct.toFixed(1)}%`}</strong></div><div className="quality-track"><i style={{ width: `${Math.min(100, Math.max(0, reverse ? 100 - pct : pct))}%`, background: reverse ? '#c98b43' : undefined }} /></div></div>;
}

function ShieldCheckIcon() {
  return <span className="shield-check">✓</span>;
}
