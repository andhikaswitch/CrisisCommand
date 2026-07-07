// CrisisCommand — one persistent globe, three modes (UI_DESIGN.md §6).
// Mode A: overview. Mode B: crisis selected (briefing + RUN SIMULATION).
// Mode C: simulation running/results (chart, options, zones on globe).
import { useCallback, useEffect, useRef, useState } from 'react';
import GlobeScene from './globe/GlobeScene.jsx';
import TopBar from './panels/TopBar.jsx';
import EventFeed from './panels/EventFeed.jsx';
import ContextPanel from './panels/ContextPanel.jsx';
import GpuBar from './panels/GpuBar.jsx';
import { fetchEvents, fetchHealth } from './lib/api.js';
import { subscribe } from './lib/ws.js';
import { syntheticLoad, useQualityLadder } from './lib/quality.js';

const FLIGHT_MS = 1200;

export default function App() {
  const [events, setEvents] = useState([]);
  const [seedMode, setSeedMode] = useState(true);
  const [selected, setSelected] = useState(null);
  const [flying, setFlying] = useState(false);
  const [simResult, setSimResult] = useState(null);
  const [selectedOption, setSelectedOption] = useState(null);
  const [hoverOption, setHoverOption] = useState(null);
  const flightTimer = useRef(null);
  const qualityTier = useQualityLadder();

  useEffect(() => {
    const synthetic = syntheticLoad();
    fetchEvents()
      .then((live) => setEvents(synthetic.length ? [...synthetic, ...live] : live))
      .catch((err) => {
        console.error('event fetch failed — is the backend up?', err);
        if (synthetic.length) setEvents(synthetic);
      });
    fetchHealth().then((h) => setSeedMode(h.seed_mode)).catch(() => {});
    return () => clearTimeout(flightTimer.current);
  }, []);

  // Live ingestion: new markers drop in without a refetch (Mode A, §6).
  useEffect(() => subscribe((msg) => {
    if (msg.type !== 'event_new' || !msg.event) return;
    setEvents((prev) =>
      prev.some((e) => e.id === msg.event.id) ? prev : [msg.event, ...prev]
    );
  }), []);

  // Selection: rails slide out during the camera flight, return after (§4).
  const handleSelect = useCallback((event) => {
    setSelected(event);
    setSimResult(null);
    setSelectedOption(null);
    setHoverOption(null);
    setFlying(true);
    clearTimeout(flightTimer.current);
    flightTimer.current = setTimeout(() => setFlying(false), FLIGHT_MS);
  }, []);

  // hover previews an option's zones; explicit select pins them (§6.3)
  const activeOption = hoverOption ?? selectedOption;

  return (
    <>
      <div className="starfield" />
      <GlobeScene
        events={events}
        selected={selected}
        onSelect={handleSelect}
        activeOption={activeOption}
        qualityTier={qualityTier}
      />
      <TopBar seedMode={seedMode} />
      <aside className={`rail rail-left ${flying ? 'hidden-left' : ''}`}>
        <EventFeed events={events} selected={selected} onSelect={handleSelect} />
      </aside>
      <aside className={`rail rail-right ${flying ? 'hidden-right' : ''}`}>
        <ContextPanel
          event={selected}
          simResult={simResult}
          setSimResult={setSimResult}
          selectedOption={selectedOption}
          onSelectOption={setSelectedOption}
          onHoverOption={setHoverOption}
        />
      </aside>
      <GpuBar lastMetrics={simResult?.gpu_metrics} />
    </>
  );
}
