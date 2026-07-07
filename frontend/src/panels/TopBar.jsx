// Top bar: brand, UTC clock, LIVE/SEED badge, per-source freshness dots,
// and the honest vLLM-fallback banner (UI_DESIGN.md §4, §8).
import { useEffect, useState } from 'react';
import { fetchStatus } from '../lib/api.js';

function utcNow() {
  return new Date().toISOString().slice(11, 19);
}

const DOT_COLOR = {
  ok: 'var(--alert-teal)',
  stale: 'var(--alert-amber)',
  error: 'var(--alert-red)',
  idle: 'var(--text-dim)',
};

export default function TopBar({ seedMode }) {
  const [clock, setClock] = useState(utcNow());
  const [status, setStatus] = useState(null);

  useEffect(() => {
    const t = setInterval(() => setClock(utcNow()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const poll = () => fetchStatus().then(setStatus).catch(() => {});
    poll();
    const t = setInterval(poll, 15000); // freshness refresh
    return () => clearInterval(t);
  }, []);

  const mode = status?.mode ?? (seedMode ? 'SEED' : 'LIVE');
  const degraded = status?.sim_backend_degraded;

  return (
    <header className="top-bar">
      <div className="brand">
        <span className="brand-mark">◈</span>
        <span className="brand-name">CrisisCommand</span>
        <span className="brand-sub">AI Situation Room</span>
      </div>

      {status?.sources?.length > 0 && (
        <div className="freshness">
          {status.sources.map((s) => (
            <span key={s.source} className="fresh-item" title={
              `${s.source}: ${s.status}${s.last_error ? ` — ${s.last_error}` : ''}` +
              (s.last_success ? ` (last ${new Date(s.last_success).toISOString().slice(11, 19)}Z)` : '')
            }>
              <span className="fresh-dot" style={{ background: DOT_COLOR[s.status] }} />
              {s.source}
            </span>
          ))}
        </div>
      )}

      <div className="spacer" />

      {degraded && (
        <div className="fallback-banner" title="vLLM droplet unreachable; scenario calls routed to Fireworks / templates">
          ⚠ SIM BACKEND: FIREWORKS (FALLBACK)
        </div>
      )}

      <div className="utc-clock">
        <span className="utc-label">UTC</span>
        {clock}
      </div>
      <div className={`mode-badge ${mode === 'LIVE' ? 'live' : ''}`}>
        <span className="mode-dot" />
        {mode}
      </div>
    </header>
  );
}
