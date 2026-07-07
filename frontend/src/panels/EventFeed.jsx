// Left rail: scrollable event feed of holo cards (UI_DESIGN.md §4).
// Live events and curated historical drills are visually distinct: SEED
// events carry a HISTORICAL badge + year, and the feed can be filtered.
import { useMemo, useState } from 'react';
import HoloPanel from './HoloPanel.jsx';
import { severityColor } from '../lib/api.js';

function timeLabel(iso) {
  const d = new Date(iso);
  return d.toISOString().slice(0, 16).replace('T', ' ') + 'Z';
}

const FILTERS = ['ALL', 'LIVE', 'DRILLS'];

export default function EventFeed({ events, selected, onSelect }) {
  const [filter, setFilter] = useState('ALL');

  const shown = useMemo(() => {
    if (filter === 'LIVE') return events.filter((e) => e.source !== 'SEED');
    if (filter === 'DRILLS') return events.filter((e) => e.source === 'SEED');
    return events;
  }, [events, filter]);

  const liveCount = events.filter((e) => e.source !== 'SEED').length;

  return (
    <HoloPanel title="Event Feed" icon="▤" className="event-feed" style={{ height: '100%' }}>
      <div className="feed-filters">
        {FILTERS.map((f) => (
          <button
            key={f}
            className={`feed-filter ${filter === f ? 'active' : ''}`}
            onClick={() => setFilter(f)}
          >
            {f}
            {f === 'LIVE' && liveCount > 0 ? ` (${liveCount})` : ''}
          </button>
        ))}
      </div>
      <div className="feed-scroll">
        {shown.map((e) => {
          const isSeed = e.source === 'SEED';
          return (
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
                {isSeed && (
                  <span className="hist-badge">
                    HISTORICAL {new Date(e.started_at).getUTCFullYear()}
                  </span>
                )}
              </div>
              <div className="feed-title">{e.title}</div>
              <div className="feed-meta">
                {e.country} · {timeLabel(e.started_at)} · {isSeed ? 'DRILL' : e.source}
              </div>
            </button>
          );
        })}
        {shown.length === 0 && (
          <div className="feed-empty">NO EVENTS IN THIS FILTER</div>
        )}
      </div>
    </HoloPanel>
  );
}
