// Mode C: simulation progress + results (UI_DESIGN.md §6).
// Progress numbers come from live WS sim_progress messages; results show
// the escalation chart (p10-p90 band, horizon tabs) and three option cards.
import { useEffect, useMemo, useState } from 'react';
import {
  Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import HoloPanel from './HoloPanel.jsx';
import { fetchGpu, fmtRange, runSimulation, severityColor } from '../lib/api.js';
import { subscribe } from '../lib/ws.js';

const HORIZONS = ['6h', '24h', '72h'];

/** Whatever AMD (or dev) device the backend reports — never hardcode a model. */
function useDeviceName() {
  const [device, setDevice] = useState(null);
  useEffect(() => {
    fetchGpu()
      .then((g) => setDevice(g?.backend === 'gpu' ? g.device : null))
      .catch(() => {});
    return subscribe((msg) => {
      if (msg.type === 'gpu_stats') {
        setDevice(msg.backend === 'gpu' ? msg.device : null);
      }
    });
  }, []);
  return device;
}

function ProgressView({ progress }) {
  const pct = progress ? Math.round((progress.runs_done / progress.runs_total) * 100) : 0;
  const stageLabel =
    !progress || progress.stage === 'monte_carlo' ? 'MONTE CARLO'
    : progress.stage === 'scenario_agent' ? 'SCENARIO AGENT'
    : 'FINALIZING';
  return (
    <div className="sim-progress">
      <div className="sim-stage">
        {stageLabel} ▸ {progress
          ? `${progress.runs_done.toLocaleString()} / ${progress.runs_total.toLocaleString()} RUNS`
          : 'DISPATCHING'}
      </div>
      <div className="sim-track"><div className="sim-fill" style={{ width: `${pct}%` }} /></div>
    </div>
  );
}

function EscalationChart({ horizons, active, hours }) {
  const fc = horizons[active];
  const data = useMemo(() => {
    if (!fc) return [];
    const n = fc.severity_curve.length;
    return fc.severity_curve.map((mid, i) => ({
      t: +((i * hours) / n).toFixed(1),
      band: [fc.severity_band_low?.[i] ?? mid, fc.severity_band_high?.[i] ?? mid],
      mid,
    }));
  }, [fc, hours]);

  return (
    <div className="chart-wrap">
      <ResponsiveContainer width="100%" height={150}>
        <AreaChart data={data} margin={{ top: 6, right: 6, bottom: 0, left: -26 }}>
          <defs>
            <linearGradient id="bandFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.35} />
              <stop offset="100%" stopColor="#22d3ee" stopOpacity={0.06} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="t" tick={{ fill: '#7d99b5', fontSize: 9 }}
            tickLine={false} axisLine={{ stroke: 'rgba(34,211,238,0.2)' }}
            unit="h"
          />
          <YAxis
            domain={[0, 1]} tick={{ fill: '#7d99b5', fontSize: 9 }}
            tickLine={false} axisLine={false}
          />
          <Tooltip
            contentStyle={{
              background: 'rgba(10,22,40,0.92)', border: '1px solid rgba(34,211,238,0.35)',
              fontSize: 11, color: '#e2f3ff',
            }}
            formatter={(v, name) =>
              name === 'band'
                ? [`${v[0].toFixed(2)}–${v[1].toFixed(2)}`, 'p10–p90']
                : [Number(v).toFixed(2), 'mean']}
            labelFormatter={(l) => `t+${l}h`}
          />
          <Area type="monotone" dataKey="band" stroke="none" fill="url(#bandFill)" isAnimationActive />
          <Area
            type="monotone" dataKey="mid" stroke="#22d3ee" strokeWidth={1.5}
            fill="none" isAnimationActive
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function OptionCard({ option, baseline, selected, onSelect, onHover }) {
  return (
    <button
      className={`option-card ${selected ? 'selected' : ''}`}
      onClick={() => onSelect(option)}
      onMouseEnter={() => onHover(option)}
      onMouseLeave={() => onHover(null)}
    >
      <div className="option-name">{option.name}</div>
      <div className="option-metric">
        <span>EXPOSED</span>
        <span>{fmtRange(baseline)} → <b>{fmtRange(option.exposed_population_after)}</b></span>
      </div>
      <div className="option-metric">
        <span>COST</span><span>{fmtRange(option.est_cost_usd, '$')}</span>
      </div>
      <div className="option-metric">
        <span>RESPONSE</span><span>{option.response_time_hours}h</span>
      </div>
      <ul className="option-tradeoffs">
        {option.tradeoffs.slice(0, 3).map((t, i) => <li key={i}>{t}</li>)}
      </ul>
    </button>
  );
}

export default function SimulationPanel({ event, result, setResult, selectedOption, onSelectOption, onHoverOption }) {
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState(null);
  const [horizon, setHorizon] = useState('24h');
  const device = useDeviceName();

  useEffect(() => {
    // reset when switching events
    setRunning(false); setProgress(null); setError(null);
  }, [event.id]);

  useEffect(() => subscribe((msg) => {
    if (msg.type === 'sim_progress' && msg.event_id === event.id) setProgress(msg);
  }), [event.id]);

  const start = async () => {
    setRunning(true); setError(null); setProgress(null);
    onSelectOption(null);
    try {
      const r = await runSimulation(event.id, horizon);
      setResult(r);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setRunning(false);
    }
  };

  const hours = { '6h': 6, '24h': 24, '72h': 72 }[horizon];

  if (!result && !running) {
    return (
      <>
        <button className="run-sim-btn" onClick={start}>▶ Run Simulation</button>
        {error && <div className="sim-error">SIMULATION FAILED — {error} <button className="retry" onClick={start}>RETRY</button></div>}
        <div className="sim-note">Simulation — decision support only</div>
      </>
    );
  }

  if (running) {
    return (
      <HoloPanel title={`Simulation — ${device ?? 'CPU'}`} icon="⚡">
        <ProgressView progress={progress} />
        <div className="sim-note">Simulation — decision support only</div>
      </HoloPanel>
    );
  }

  const baseline = result.horizons[horizon]?.exposed_population
    ?? result.horizons['24h'].exposed_population;

  return (
    <HoloPanel title="Escalation Forecast" icon="◭">
      <div className="horizon-tabs">
        {HORIZONS.map((h) => (
          <button
            key={h}
            className={`horizon-tab ${h === horizon ? 'active' : ''}`}
            onClick={() => setHorizon(h)}
          >
            {h}
          </button>
        ))}
        <span className="conf-label">
          confidence: {result.horizons[horizon]?.confidence}
        </span>
      </div>
      <EscalationChart horizons={result.horizons} active={horizon} hours={hours} />
      <div className="chart-caption">
        exposed population {fmtRange(baseline)} (p10–p90)
      </div>

      <div className="options-head">Response options</div>
      {result.options.map((o) => (
        <OptionCard
          key={o.id}
          option={o}
          baseline={baseline}
          selected={selectedOption?.id === o.id}
          onSelect={(opt) => onSelectOption(selectedOption?.id === opt.id ? null : opt)}
          onHover={onHoverOption}
        />
      ))}
      <div className="sim-note">Simulation — decision support only</div>
    </HoloPanel>
  );
}
