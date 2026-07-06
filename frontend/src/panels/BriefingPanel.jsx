// Situation brief panel — AI briefing streams in word-by-word (Mode B, §6).
// 40ms/word typewriter per spec (simulated from the fetched text).
import { useEffect, useRef, useState } from 'react';
import HoloPanel from './HoloPanel.jsx';
import { fetchBriefing } from '../lib/api.js';

const WORD_MS = 40;

function Typewriter({ text }) {
  const [count, setCount] = useState(0);
  const words = text.split(' ');
  useEffect(() => {
    setCount(0);
    const t = setInterval(() => {
      setCount((c) => {
        if (c >= words.length) { clearInterval(t); return c; }
        return c + 1;
      });
    }, WORD_MS);
    return () => clearInterval(t);
  }, [text]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <p className="brief-summary">
      {words.slice(0, count).join(' ')}
      {count < words.length && <span className="caret">▍</span>}
    </p>
  );
}

export default function BriefingPanel({ event }) {
  const [brief, setBrief] = useState(null);
  const [error, setError] = useState(false);
  const requested = useRef(null);

  useEffect(() => {
    setBrief(null);
    setError(false);
    requested.current = event.id;
    fetchBriefing(event.id)
      .then((b) => { if (requested.current === event.id) setBrief(b); })
      .catch(() => { if (requested.current === event.id) setError(true); });
  }, [event.id]);

  return (
    <HoloPanel title="Situation Brief" icon="▤" key={event.id}>
      {!brief && !error && (
        <div className="brief-loading">ANALYZING FEED DATA<span className="caret">▍</span></div>
      )}
      {error && (
        <div className="brief-loading">BRIEFING UNAVAILABLE — FEED DATA ONLY</div>
      )}
      {brief && (
        <>
          <div className="brief-headline">{brief.headline}</div>
          <Typewriter text={brief.summary} />
          <div className="brief-section">Confirmed</div>
          <ul className="brief-list">
            {brief.confirmed_facts.map((f, i) => <li key={i}>{f}</li>)}
          </ul>
          <div className="brief-section">Key unknowns</div>
          <ul className="brief-list dim">
            {brief.key_unknowns.map((f, i) => <li key={i}>{f}</li>)}
          </ul>
        </>
      )}
    </HoloPanel>
  );
}
