import { useEffect, useState } from 'react';
import { NavLink, Route, Routes, useLocation } from 'react-router-dom';
import { Activity, ArrowUpRight, BarChart3, BusFront, ChevronDown, Compass, Info, MapPinned, Menu, RadioTower, Route as RouteIcon, ShieldCheck, Sparkles, X } from 'lucide-react';
import PlannerPage from './pages/PlannerPage';
import LiveMapPage from './pages/LiveMapPage';
import InsightsPage from './pages/InsightsPage';
import RoutesPage from './pages/RoutesPage';
import MethodologyPage from './pages/MethodologyPage';
import OperatorPage from './pages/OperatorPage';
import { api, type Health } from './lib/api';

const navigation = [
  { to: '/', label: 'Journey planner', icon: Compass, end: true },
  { to: '/live-map', label: 'Live bus map', icon: MapPinned },
  { to: '/insights', label: 'Crowding insights', icon: BarChart3 },
  { to: '/routes', label: 'Routes & stops', icon: RouteIcon },
];

function pageName(path: string) {
  if (path.startsWith('/live-map')) return 'Live bus map';
  if (path.startsWith('/insights')) return 'Crowding insights';
  if (path.startsWith('/routes')) return 'Routes & stops';
  if (path.startsWith('/methodology')) return 'Methodology';
  if (path.startsWith('/operator')) return 'Operator workspace';
  return 'Journey planner';
}

export default function App() {
  const location = useLocation();
  const [health, setHealth] = useState<Health | null>(null);
  const [mobileNav, setMobileNav] = useState(false);
  const [clock, setClock] = useState(new Date());

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const result = await api.health();
        if (alive) setHealth(result);
      } catch {
        if (alive) setHealth({ status: 'offline', database_ready: false, live_feed_configured: false });
      }
    };
    void load();
    const id = window.setInterval(load, 30_000);
    return () => { alive = false; window.clearInterval(id); };
  }, []);

  useEffect(() => {
    const id = window.setInterval(() => setClock(new Date()), 30_000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => setMobileNav(false), [location.pathname]);

  const dbReady = Boolean(health?.database_ready);
  const feedConfigured = Boolean(health?.live_feed_configured);
  const isConnected = health?.status === 'ok' && dbReady;

  return (
    <div className="app-shell">
      {mobileNav && <button className="mobile-scrim" onClick={() => setMobileNav(false)} aria-label="Close navigation" />}
      <aside className={`sidebar ${mobileNav ? 'open' : ''}`}>
        <div className="brand-lockup">
          <div className="brand-mark" aria-label="DilliFlow logo"><DilliFlowSymbol /></div>
          <div><strong>DilliFlow</strong><span>DELHI BUS INTELLIGENCE</span></div>
          <button className="icon-button sidebar-close" onClick={() => setMobileNav(false)} aria-label="Close menu"><X size={18} /></button>
        </div>
        <div className="sidebar-city"><span className="city-pin" /><span>DELHI, INDIA</span><ChevronDown size={13} /></div>
        <div className="nav-label">MOVE AROUND</div>
        <nav className="main-nav">
          {navigation.map((item) => <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}><item.icon size={18} strokeWidth={1.9} /><span>{item.label}</span>{item.to === '/live-map' && <span className="nav-live-dot" />}</NavLink>)}
        </nav>
        <div className="nav-label secondary-label">OPERATIONS</div>
        <nav className="main-nav"><NavLink to="/operator" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}><ShieldCheck size={18} /><span>Operator workspace</span><span className="nav-lock-label">ID</span></NavLink></nav>
        <div className="nav-label secondary-label">ABOUT THE DATA</div>
        <nav className="main-nav"><NavLink to="/methodology" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}><Info size={18} /><span>Methodology</span></NavLink></nav>
        <div className="sidebar-spacer" />
        <div className="sidebar-status-card">
          <div className="status-card-top"><span className={`status-dot ${isConnected ? 'fresh' : 'stale'}`} /><strong>{isConnected ? 'Transit data ready' : 'Local setup'}</strong></div>
          <p>{isConnected ? 'GTFS database is indexed and available.' : 'Connect the local API to unlock routes and journey planning.'}</p>
          <NavLink to="/methodology" className="status-card-link">How data works <ArrowUpRight size={13} /></NavLink>
        </div>
        <div className="sidebar-bottom"><span className="sidebar-version">DILLIFLOW / 1.0</span><span>Move smarter. Ride calmer.</span></div>
      </aside>

      <div className="main-column">
        <header className="topbar">
          <div className="topbar-left"><button className="icon-button mobile-menu-button" onClick={() => setMobileNav(true)} aria-label="Open navigation"><Menu size={19} /></button><span className="breadcrumb-root">DilliFlow</span><span className="breadcrumb-divider">/</span><strong>{pageName(location.pathname)}</strong></div>
          <div className="topbar-right">
            <div className={`service-pill ${isConnected ? 'online' : 'offline'}`}><span className="status-dot" />{isConnected ? 'Transit data ready' : 'Transit API offline'}</div>
            <div className="topbar-date">{clock.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' })}</div>
            <div className="avatar-mark">DF</div>
          </div>
        </header>
        <main className="main-content">
          <Routes>
            <Route path="/" element={<PlannerPage />} />
            <Route path="/live-map" element={<LiveMapPage />} />
            <Route path="/insights" element={<InsightsPage />} />
            <Route path="/routes" element={<RoutesPage />} />
            <Route path="/methodology" element={<MethodologyPage />} />
            <Route path="/operator" element={<OperatorPage />} />
            <Route path="*" element={<PlannerPage />} />
          </Routes>
        </main>
        <footer className="app-footer"><span>© 2026 DilliFlow</span><span>Built for clearer journeys across Delhi <Sparkles size={12} /></span><span>Data: GTFS · Ticket records · GTFS-Realtime</span></footer>
      </div>
    </div>
  );
}


function DilliFlowSymbol() {
  return (
    <svg viewBox="0 0 40 40" width="29" height="29" fill="none" aria-hidden="true">
      <path d="M8 12h7.5a5.5 5.5 0 1 1 0 11H12" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      <path d="M8 20h5.5a5.5 5.5 0 1 1 0 11H12" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      <path d="M8 28h4" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      <circle cx="8" cy="12" r="3" fill="#1b765f" />
      <circle cx="8" cy="20" r="2.2" fill="currentColor" />
      <circle cx="8" cy="28" r="2.2" fill="currentColor" />
      <circle cx="26.5" cy="17.5" r="2.5" fill="#1b765f" />
      <circle cx="26.5" cy="25.5" r="2.5" fill="#1b765f" />
    </svg>
  );
}
