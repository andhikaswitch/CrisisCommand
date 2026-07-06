// Right rail context panel (UI_DESIGN.md §4, §8).
// Empty state: radar sweep. Selected: situation panel + RUN SIMULATION.
// The briefing typewriter stream and simulation flow wire in on Day 4.
import HoloPanel from './HoloPanel.jsx';
import { severityColor } from '../lib/api.js';

function EmptyState() {
  return (
    <HoloPanel title="Context" icon="◎">
      <div className="context-empty">
        <div className="radar">
          <div className="radar-sweep" />
        </div>
        Select an event to begin analysis
      </div>
    </HoloPanel>
  );
}

export default function ContextPanel({ event }) {
  if (!event) return <EmptyState />;

  const sev = severityColor(event);
  const pop = event.population_context;

  return (
    <HoloPanel title="Situation" icon="◈" key={event.id}>
      <div className="feed-kind" style={{ '--sev-color': sev, marginBottom: 4 }}>
        {event.kind === 'tension' ? '◇ tension signal' : event.kind}
      </div>
      <div style={{ fontSize: 14.5, fontWeight: 600, lineHeight: 1.4, marginBottom: 10 }}>
        {event.title}
      </div>

      <div className="detail-row">
        <span className="detail-label">Severity</span>
        <span className="detail-value" style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 140 }}>
          <span className="sev-track" style={{ '--sev-color': sev }}>
            <span className="sev-fill" style={{ width: `${event.severity * 100}%`, display: 'block' }} />
          </span>
          {event.severity.toFixed(2)}
        </span>
      </div>
      <div className="detail-row">
        <span className="detail-label">Location</span>
        <span className="detail-value">
          {event.country} · {event.lat.toFixed(2)}, {event.lon.toFixed(2)}
        </span>
      </div>
      <div className="detail-row">
        <span className="detail-label">Started</span>
        <span className="detail-value">
          {new Date(event.started_at).toISOString().slice(0, 16).replace('T', ' ')}Z
        </span>
      </div>
      <div className="detail-row">
        <span className="detail-label">Source</span>
        <span className="detail-value">{event.source}</span>
      </div>
      {pop && (
        <>
          <div className="detail-row">
            <span className="detail-label">Nearest city</span>
            <span className="detail-value">
              {pop.nearest_city} ({pop.city_population.toLocaleString()})
            </span>
          </div>
          <div className="detail-row">
            <span className="detail-label">Exposure base</span>
            <span className="detail-value">
              ~{pop.exposed_estimate.toLocaleString()} · {pop.density_band} density
            </span>
          </div>
        </>
      )}

      <button className="run-sim-btn" disabled title="Simulation flow wires in on Day 4">
        ▶ Run Simulation
      </button>
      <div className="sim-note">Simulation — decision support only</div>
    </HoloPanel>
  );
}
