// Progressive quality ladder (UI_DESIGN.md §7). Monitors frame time and
// steps DOWN one tier after sustained slow frames (>20ms), back UP when
// frames recover. Degrade order is fixed by the spec:
//   tier 1: disable panel scanline overlays
//   tier 2: rings -> static dots for low-severity events
//   tier 3: disable atmosphere shader
//   tier 4: flat globe (drop hex polygons)
// Never degraded: marker click accuracy, text legibility, GPU readout.
//
// Override for demos/testing: ?quality=N pins a tier (no auto-adjust).
import { useEffect, useState } from 'react';

export const MAX_TIER = 4;
export const TIER_LABEL = [
  'FULL', 'NO-SCANLINE', 'STATIC-RINGS', 'NO-ATMOSPHERE', 'FLAT-GLOBE',
];

export function useQualityLadder() {
  const forced = new URLSearchParams(window.location.search).get('quality');
  const [tier, setTier] = useState(forced != null ? Number(forced) : 0);

  useEffect(() => {
    if (forced != null) return; // pinned — skip the auto-adjuster
    let raf;
    let last = performance.now();
    let slow = 0;
    let fast = 0;
    let cur = 0;
    const loop = (now) => {
      const dt = now - last;
      last = now;
      if (dt > 20) { slow += 1; fast = 0; } else { fast += 1; slow = 0; }
      if (slow > 90 && cur < MAX_TIER) {
        cur += 1; slow = 0; setTier(cur);
        console.info('[quality] degraded to tier', cur, TIER_LABEL[cur]);
      } else if (fast > 300 && cur > 0) {
        cur -= 1; fast = 0; setTier(cur);
        console.info('[quality] recovered to tier', cur, TIER_LABEL[cur]);
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [forced]);

  useEffect(() => {
    document.body.classList.toggle('q-no-scanline', tier >= 1);
  }, [tier]);

  return tier;
}

// Synthetic markers to exercise the ladder under load: ?load=200
export function syntheticLoad() {
  const n = Number(new URLSearchParams(window.location.search).get('load') || 0);
  if (!n) return [];
  const kinds = ['earthquake', 'flood', 'cyclone', 'wildfire'];
  return Array.from({ length: n }, (_, i) => ({
    id: `synthetic-${i}`,
    kind: kinds[i % kinds.length],
    title: `Synthetic load event ${i}`,
    lat: (Math.sin(i * 2.399) * 75),
    lon: (((i * 137.5) % 360) - 180),
    country: 'Loadtest',
    severity: (i % 10) / 10,
    started_at: new Date().toISOString(),
    source: 'SYNTH',
    source_url: 'about:blank',
    raw: {},
    population_context: null,
  }));
}
