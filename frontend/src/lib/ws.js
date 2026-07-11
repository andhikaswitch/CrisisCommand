// WebSocket client for /ws: event_new, sim_progress, gpu_stats.
// Auto-reconnects with backoff; subscribers filter by message type.
const listeners = new Set();
let socket = null;
let retryMs = 1000;

function wsUrl() {
  const base = import.meta.env.VITE_API_BASE;
  if (base) return base.replace(/^http/, 'ws') + '/ws';
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/ws`;
}

function connect() {
  socket = new WebSocket(wsUrl());
  socket.onopen = () => { retryMs = 1000; };
  socket.onmessage = (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    listeners.forEach((fn) => fn(msg));
  };
  socket.onclose = () => {
    socket = null;
    setTimeout(connect, retryMs);
    retryMs = Math.min(retryMs * 2, 15000);
  };
  socket.onerror = () => socket?.close();
}

// Static showcase has no backend, so no WebSocket: subscribe is a no-op that
// never opens a socket (avoids an endless reconnect loop against nothing).
const DEMO = import.meta.env.VITE_DEMO_DATA === '1';

export function subscribe(fn) {
  if (DEMO) return () => {};
  if (!socket) connect();
  listeners.add(fn);
  return () => listeners.delete(fn);
}
