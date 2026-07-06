// Bottom bar: the AMD showcase readout (UI_DESIGN.md §4).
// Idle: device + VRAM from /api/health/gpu + WS gpu_stats.
// During simulation: utilization bar fills with live run counts.
import { useEffect, useState } from 'react';
import { fetchGpu } from '../lib/api.js';
import { subscribe } from '../lib/ws.js';

export default function GpuBar({ lastMetrics }) {
  const [gpu, setGpu] = useState(null);
  const [progress, setProgress] = useState(null);

  useEffect(() => {
    fetchGpu().then(setGpu).catch(() => {});
    return subscribe((msg) => {
      if (msg.type === 'gpu_stats') setGpu(msg);
      if (msg.type === 'sim_progress') {
        setProgress(msg.stage === 'complete' ? null : msg);
      }
    });
  }, []);

  const pct = progress
    ? Math.round((progress.runs_done / progress.runs_total) * 100)
    : 0;
  const device = gpu?.device ?? '—';
  const isGpu = gpu?.backend === 'gpu';

  return (
    <footer className="gpu-bar">
      <span className="gpu-chip">⚡ {isGpu ? device : `${device} (dev fallback)`}</span>
      <div className="gpu-util">
        <span className="gpu-label">{progress ? `SIM ${pct}%` : 'IDLE'}</span>
        <div className="gpu-track">
          <div className={`gpu-fill ${progress ? 'hot' : ''}`} style={{ width: `${pct}%` }} />
        </div>
      </div>
      <span className="gpu-stat">
        VRAM {gpu?.vram_used_gb != null ? `${gpu.vram_used_gb} / ${gpu.vram_total_gb} GB` : 'n/a'}
      </span>
      <span className="gpu-stat">
        {lastMetrics
          ? `${Math.round(lastMetrics.runs_per_sec).toLocaleString()} runs/s · ${lastMetrics.n_runs.toLocaleString()} runs in ${lastMetrics.wall_ms.toFixed(0)}ms`
          : 'awaiting simulation'}
      </span>
    </footer>
  );
}
