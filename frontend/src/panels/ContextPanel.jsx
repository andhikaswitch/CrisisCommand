// Right rail context stack (UI_DESIGN.md §4, §6, §8).
// Empty state: radar sweep. Selected: situation summary + AI briefing
// (typewriter) + simulation flow (progress → chart → option cards).
import HoloPanel from './HoloPanel.jsx';
import BriefingPanel from './BriefingPanel.jsx';
import SimulationPanel from './SimulationPanel.jsx';
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

function SituationSummary({ event }) {
  const sev = severityColor(event);
  const pop = event.population_context;
  const isSeed = event.source === 'SEED';
  return (
    <HoloPanel title="Situation" icon="◈" key={event.id}>
      {isSeed && (
        <div className="hist-banner">
          ◆ HISTORICAL DRILL — documented {new Date(event.started_at).getUTCFullYear()} event,
          used for simulation rehearsal
        </div>
      )}
      <div className="feed-kind" style={{ '--sev-color': sev, marginBottom: 4 }}>
        {event.kind === 'tension' ? '◇ tension signal' : event.kind}
        {' · sev '}
        {event.severity.toFixed(2)}
      </div>
      <div style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.4, marginBottom: 6 }}>
        {event.title}
      </div>
      <div className="detail-row">
        <span className="detail-label">Location</span>
        <span className="detail-value">
          {event.country} · {event.lat.toFixed(2)}, {event.lon.toFixed(2)}
        </span>
      </div>
      {pop && (
        <div className="detail-row">
          <span className="detail-label">Exposure base</span>
          <span className="detail-value">
            ~{pop.exposed_estimate.toLocaleString()} · {pop.density_band} density
          </span>
        </div>
      )}
    </HoloPanel>
  );
}

export default function ContextPanel({
  event, simResult, setSimResult, selectedOption, onSelectOption, onHoverOption,
}) {
  if (!event) return <EmptyState />;

  // Simulable = supported hazard kernel AND vetted population context.
  // Live-feed events carry no exposure base (we never invent one — honesty
  // rule), so they get an explanation instead of a button that would 422.
  const kindSupported = ['flood', 'earthquake', 'cyclone', 'wildfire'].includes(event.kind);
  const hasExposure = event.population_context != null;

  return (
    <div className="context-stack">
      <SituationSummary event={event} />
      <BriefingPanel event={event} />
      {kindSupported && hasExposure ? (
        <SimulationPanel
          event={event}
          result={simResult}
          setResult={setSimResult}
          selectedOption={selectedOption}
          onSelectOption={onSelectOption}
          onHoverOption={onHoverOption}
        />
      ) : (
        <div className="sim-note" style={{ marginTop: 4 }}>
          {!kindSupported
            ? 'Simulation kernels for this hazard class arrive with the full ensemble'
            : 'Live event — no vetted population data yet, so no simulation. ' +
              'Impact simulation runs on curated drill events (feed filter: DRILLS).'}
        </div>
      )}
    </div>
  );
}
