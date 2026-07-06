// Top bar: brand, UTC clock, LIVE/SEED mode badge (UI_DESIGN.md §4).
// Source freshness dots join on Day 5 with live ingestion.
import { useEffect, useState } from 'react';

function utcNow() {
  return new Date().toISOString().slice(11, 19);
}

export default function TopBar({ seedMode }) {
  const [clock, setClock] = useState(utcNow());

  useEffect(() => {
    const t = setInterval(() => setClock(utcNow()), 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <header className="top-bar">
      <div className="brand">
        <span className="brand-mark">◈</span>
        <span className="brand-name">CrisisCommand</span>
        <span className="brand-sub">AI Situation Room</span>
      </div>
      <div className="spacer" />
      <div className="utc-clock">
        <span className="utc-label">UTC</span>
        {clock}
      </div>
      <div className="mode-badge">
        <span className="mode-dot" />
        {seedMode ? 'SEED' : 'LIVE'}
      </div>
    </header>
  );
}
