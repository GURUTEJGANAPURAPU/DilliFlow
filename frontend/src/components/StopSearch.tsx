import { useEffect, useRef, useState } from 'react';
import { MapPin, Search, X } from 'lucide-react';
import { api, type Stop } from '../lib/api';

interface Props {
  label: string;
  placeholder: string;
  value: Stop | null;
  onChange: (stop: Stop | null) => void;
}

export default function StopSearch({ label, placeholder, value, onChange }: Props) {
  const [query, setQuery] = useState(value?.stop_name || '');
  const [results, setResults] = useState<Stop[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [searchError, setSearchError] = useState('');
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    setQuery(value?.stop_name || '');
  }, [value?.stop_id]);

  useEffect(() => {
    if (value && query === value.stop_name) return;
    if (query.trim().length < 2) {
      setResults([]);
      setSearchError('');
      return;
    }
    if (timer.current !== undefined) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(async () => {
      setLoading(true);
      try {
        const response = await api.stops(query.trim());
        setResults(response.items || []);
        setSearchError('');
        setOpen(true);
      } catch (error) {
        setResults([]);
        setSearchError(error instanceof Error ? error.message : 'Could not search stops. Check that the local API is running.');
        setOpen(true);
      } finally {
        setLoading(false);
      }
    }, 260);
    return () => { if (timer.current !== undefined) window.clearTimeout(timer.current); };
  }, [query, value]);

  return (
    <div className="stop-search-field">
      <label>{label}</label>
      <div className="stop-input-wrap">
        <MapPin size={17} className="field-leading-icon" />
        <input
          value={query}
          placeholder={placeholder}
          onFocus={() => results.length && setOpen(true)}
          onChange={(event) => {
            setQuery(event.target.value);
            if (value) onChange(null);
          }}
          onKeyDown={(event) => { if (event.key === 'Escape') setOpen(false); }}
        />
        {loading && <span className="mini-spinner" />}
        {query && <button type="button" className="icon-button small clear-input" aria-label="Clear stop" onClick={() => { setQuery(''); onChange(null); setOpen(false); }}><X size={14} /></button>}
      </div>
      {open && results.length > 0 && (
        <div className="stop-results">
          {results.map((stop) => (
            <button key={stop.stop_id} type="button" className="stop-result" onClick={() => { onChange(stop); setQuery(stop.stop_name); setOpen(false); }}>
              <span className="stop-result-icon"><MapPin size={15} /></span>
              <span><strong>{stop.stop_name}</strong><small>{stop.stop_code || stop.stop_id}</small></span>
            </button>
          ))}
        </div>
      )}
      {open && !loading && searchError && (
        <div className="stop-results no-results"><Search size={15} /> {searchError}</div>
      )}
      {open && !loading && !searchError && query.length >= 2 && results.length === 0 && (
        <div className="stop-results no-results"><Search size={15} /> No matching stop found</div>
      )}
    </div>
  );
}
