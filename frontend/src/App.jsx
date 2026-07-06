// CrisisCommand — one persistent globe, three modes (UI_DESIGN.md §6).
// Day 3 covers Mode A (overview) and Mode B selection mechanics:
// click → rails slide out → camera flight → rails return + situation panel.
import { useCallback, useEffect, useRef, useState } from 'react';
import GlobeScene from './globe/GlobeScene.jsx';
import TopBar from './panels/TopBar.jsx';
import EventFeed from './panels/EventFeed.jsx';
import ContextPanel from './panels/ContextPanel.jsx';
import { fetchEvents, fetchHealth } from './lib/api.js';

const FLIGHT_MS = 1200;

export default function App() {
  const [events, setEvents] = useState([]);
  const [seedMode, setSeedMode] = useState(true);
  const [selected, setSelected] = useState(null);
  const [flying, setFlying] = useState(false);
  const flightTimer = useRef(null);

  useEffect(() => {
    fetchEvents().then(setEvents).catch((err) => {
      console.error('event fetch failed — is the backend up?', err);
    });
    fetchHealth().then((h) => setSeedMode(h.seed_mode)).catch(() => {});
    return () => clearTimeout(flightTimer.current);
  }, []);

  // Selection: rails slide out during the camera flight, return after (§4).
  const handleSelect = useCallback((event) => {
    setSelected(event);
    setFlying(true);
    clearTimeout(flightTimer.current);
    flightTimer.current = setTimeout(() => setFlying(false), FLIGHT_MS);
  }, []);

  return (
    <>
      <div className="starfield" />
      <GlobeScene events={events} selected={selected} onSelect={handleSelect} />
      <TopBar seedMode={seedMode} />
      <aside className={`rail rail-left ${flying ? 'hidden-left' : ''}`}>
        <EventFeed events={events} selected={selected} onSelect={handleSelect} />
      </aside>
      <aside className={`rail rail-right ${flying ? 'hidden-right' : ''}`}>
        <ContextPanel event={selected} />
      </aside>
    </>
  );
}
