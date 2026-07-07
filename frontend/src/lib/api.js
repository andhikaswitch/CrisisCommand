// REST client. In dev, vite proxies /api to the backend (vite.config.js);
// in docker, VITE_API_BASE points at the backend service.
const BASE = import.meta.env.VITE_API_BASE || '';

async function get(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

async function post(path) {
  const res = await fetch(`${BASE}${path}`, { method: 'POST' });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

export const fetchEvents = () => get('/api/events');
export const fetchHealth = () => get('/api/health');
export const fetchStatus = () => get('/api/status');
export const fetchGpu = () => get('/api/health/gpu');
export const fetchBriefing = (id) => post(`/api/events/${id}/brief`);
export const runSimulation = (id, horizon = '24h') =>
  post(`/api/events/${id}/simulate?horizon=${horizon}`);

export function fmtRange([lo, hi], unit = '') {
  const f = (n) =>
    n >= 1e6 ? `${(n / 1e6).toFixed(1)}M`
    : n >= 1e3 ? `${Math.round(n / 1e3)}K`
    : `${n}`;
  return `${unit}${f(lo)}–${unit}${f(hi)}`;
}

// Severity palette thresholds per UI_DESIGN.md §3.
export function severityColor(event) {
  if (event.kind === 'tension') return 'var(--tension-violet)';
  if (event.severity >= 0.7) return 'var(--alert-red)';
  if (event.severity >= 0.4) return 'var(--alert-amber)';
  return 'var(--alert-teal)';
}

// Raw hex values for WebGL layers (CSS vars don't reach three.js materials).
export function severityHex(event, alpha = 1) {
  const hex =
    event.kind === 'tension' ? '#a78bfa'
    : event.severity >= 0.7 ? '#f43f5e'
    : event.severity >= 0.4 ? '#fbbf24'
    : '#2dd4bf';
  if (alpha >= 1) return hex;
  const a = Math.round(alpha * 255).toString(16).padStart(2, '0');
  return hex + a;
}
