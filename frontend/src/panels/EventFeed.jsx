// Left rail: scrollable event feed of holo cards (UI_DESIGN.md §4).
import HoloPanel from './HoloPanel.jsx';
import { severityColor } from '../lib/api.js';

function timeLabel(iso) {
  const d = new Date(iso);
  return d.toISOString().slice(0, 16).replace('T', ' ') + 'Z';
}

export default function EventFeed({ events, selected, onSelect }) {
  return (
    <HoloPanel title="Event Feed" icon="▤" className="event-feed" style={{ height: '100%' }}>
      <div className="feed-scroll">
        {events.map((e) => (
          <button
            key={e.id}
            className={`feed-card ${selected?.id === e.id ? 'selected' : ''}`}
            style={{ '--sev-color': severityColor(e) }}
            onClick={() => onSelect(e)}
          >
            <div className="feed-kind">
              {e.kind === 'tension' ? '◇ tension signal' : e.kind}
              {' · sev '}
              {e.severity.toFixed(2)}
            </div>
            <div className="feed-title">{e.title}</div>
            <div className="feed-meta">
              {e.country} · {timeLabel(e.started_at)} · {e.source}
            </div>
          </button>
        ))}
      </div>
    </HoloPanel>
  );
}
