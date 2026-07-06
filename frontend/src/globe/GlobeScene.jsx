// The 3D globe scene — UI_DESIGN.md §5 spec.
//
// Globe look decision (Day 3 checklist): HEX POLYGONS over texture.
// Rationale: the vector look is more holographic AND needs no runtime
// texture download — the countries GeoJSON is bundled, so a dead conference
// Wi-Fi cannot strip the globe (offline rule). Texture variant rejected.
import { useEffect, useMemo, useRef, useState } from 'react';
import Globe from 'react-globe.gl';
import { MeshPhongMaterial } from 'three';
import { severityHex } from '../lib/api.js';

// dark navy ocean sphere (§3 palette)
const OCEAN_MATERIAL = new MeshPhongMaterial({ color: '#0a1628' });

const IDLE_RESUME_MS = 8000;
// OrbitControls autoRotateSpeed 2.0 ~= 12 deg/s; spec wants 0.3 deg/s.
const AUTO_ROTATE_SPEED = 2.0 * (0.3 / 12);

export default function GlobeScene({ events, selected, onSelect }) {
  const globeRef = useRef(null);
  const idleTimer = useRef(null);
  const [countries, setCountries] = useState([]);
  const [size, setSize] = useState({ w: window.innerWidth, h: window.innerHeight });

  useEffect(() => {
    fetch('/data/countries-110m.geojson')
      .then((r) => r.json())
      .then((geo) => setCountries(geo.features))
      .catch(() => setCountries([])); // globe still renders as dark sphere
  }, []);

  useEffect(() => {
    const onResize = () => setSize({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  // Idle auto-rotate 0.3 deg/s; pause on drag, resume after 8s (§5).
  useEffect(() => {
    const globe = globeRef.current;
    if (!globe) return;
    const controls = globe.controls();
    controls.autoRotate = true;
    controls.autoRotateSpeed = AUTO_ROTATE_SPEED;
    const pause = () => {
      controls.autoRotate = false;
      clearTimeout(idleTimer.current);
      idleTimer.current = setTimeout(() => { controls.autoRotate = true; }, IDLE_RESUME_MS);
    };
    controls.addEventListener('start', pause);
    return () => {
      controls.removeEventListener('start', pause);
      clearTimeout(idleTimer.current);
    };
  }, [countries]); // re-attach after globe materializes

  // Camera flight on selection: 1.2s ease to altitude 0.6 (§5).
  useEffect(() => {
    const globe = globeRef.current;
    if (!globe || !selected) return;
    globe.controls().autoRotate = false;
    globe.pointOfView({ lat: selected.lat, lng: selected.lon, altitude: 0.6 }, 1200);
  }, [selected]);

  const disasters = useMemo(
    () => events.filter((e) => e.kind !== 'tension'),
    [events]
  );
  const tensions = useMemo(
    () => events.filter((e) => e.kind === 'tension'),
    [events]
  );

  const dimmed = (e) => selected && selected.id !== e.id;

  return (
    <div className="globe-layer">
      <Globe
        ref={globeRef}
        width={size.w}
        height={size.h}
        backgroundColor="rgba(0,0,0,0)"
        showGlobe
        globeMaterial={OCEAN_MATERIAL}
        // ocean sphere + hex-polygon landmass (vector holographic look)
        hexPolygonsData={countries}
        hexPolygonResolution={3}
        hexPolygonMargin={0.68}
        hexPolygonAltitude={0.006}
        hexPolygonColor={() => '#1b2f4a'}
        showAtmosphere
        atmosphereColor="#22d3ee"
        atmosphereAltitude={0.18}
        showGraticules
        // --- event markers: pulsing severity rings (disasters) ---
        ringsData={disasters}
        ringLat={(e) => e.lat}
        ringLng={(e) => e.lon}
        ringMaxRadius={(e) => 1.5 + e.severity * 6}
        ringRepeatPeriod={1800}
        ringPropagationSpeed={(e) => 1 + e.severity * 2}
        ringColor={(e) => {
          const alpha = dimmed(e) ? 0.4 : 1;
          const base = severityHex(e);
          return (t) => base + Math.round((1 - t) * alpha * 200 + 20)
            .toString(16).padStart(2, '0');
        }}
        // --- center dots for all disasters (clickable) ---
        pointsData={disasters}
        pointLat={(e) => e.lat}
        pointLng={(e) => e.lon}
        pointColor={(e) => severityHex(e, dimmed(e) ? 0.4 : 1)}
        pointAltitude={0.012}
        pointRadius={0.28}
        onPointClick={(e) => onSelect(e)}
        // --- tension signals: violet diamond sprites, no alarm pulse (§5) ---
        htmlElementsData={tensions}
        htmlLat={(e) => e.lat}
        htmlLng={(e) => e.lon}
        htmlAltitude={0.015}
        htmlElement={(e) => {
          const el = document.createElement('button');
          el.title = e.title;
          const dim = dimmed(e);
          el.style.cssText = [
            'width:11px', 'height:11px',
            'background:#a78bfa' + (dim ? '66' : ''),
            'transform:rotate(45deg)',
            'border:1px solid #e2f3ff44',
            'box-shadow:0 0 8px #a78bfa' + (dim ? '44' : 'aa'),
            'cursor:pointer', 'padding:0',
          ].join(';');
          el.onclick = (ev) => { ev.stopPropagation(); onSelect(e); };
          return el;
        }}
        rendererConfig={{ antialias: true, alpha: true }}
      />
    </div>
  );
}
