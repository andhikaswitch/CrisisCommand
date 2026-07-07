// The 3D globe scene — UI_DESIGN.md §5 spec.
//
// Globe look decision (Day 3 checklist): HEX POLYGONS over texture.
// Rationale: the vector look is more holographic AND needs no runtime
// texture download — the countries GeoJSON is bundled, so a dead conference
// Wi-Fi cannot strip the globe (offline rule). Texture variant rejected.
import { useEffect, useMemo, useRef, useState } from 'react';
import Globe from 'react-globe.gl';
import {
  CircleGeometry,
  Group,
  Mesh,
  MeshBasicMaterial,
  MeshPhongMaterial,
  RingGeometry,
} from 'three';
import { severityHex } from '../lib/api.js';

// dark navy ocean sphere (§3 palette)
const OCEAN_MATERIAL = new MeshPhongMaterial({ color: '#0a1628' });

const GLOBE_RADIUS_KM = 6371;
const ZONE_FADE_MS = 300;

const IDLE_RESUME_MS = 8000;
// OrbitControls autoRotateSpeed 2.0 ~= 12 deg/s; spec wants 0.3 deg/s.
const AUTO_ROTATE_SPEED = 2.0 * (0.3 / 12);

// Zone colors by role (§5): cyan evacuation, red hazard, amber staging.
// [color, fillOpacity, outlineOpacity]
const ZONE_STYLE = {
  evacuation: ['#22d3ee', 0.16, 0.75],
  hazard: ['#f43f5e', 0.14, 0.6],
  staging: ['#fbbf24', 0.13, 0.6],
};

// Zones as tangent-plane circle meshes (globe.gl's polygon triangulation
// mangles polygons this small, so we draw exact THREE circles instead).
// A 300ms opacity tween on mount gives the §6 cross-fade between options.
function buildZoneObject(zone) {
  const [color, fillOp, edgeOp] = ZONE_STYLE[zone.role] ?? ZONE_STYLE.hazard;
  // globe.gl sphere radius is 100 scene units
  const r = Math.max(0.4, (zone.radius_km / GLOBE_RADIUS_KM) * 100);
  const group = new Group();
  const fill = new Mesh(
    new CircleGeometry(r, 48),
    new MeshBasicMaterial({
      color, transparent: true, opacity: 0, depthWrite: false, side: 2,
    })
  );
  const edge = new Mesh(
    new RingGeometry(r * 0.965, r, 48),
    new MeshBasicMaterial({
      color, transparent: true, opacity: 0, depthWrite: false, side: 2,
    })
  );
  group.add(fill, edge);
  const start = performance.now();
  const tick = () => {
    const k = Math.min(1, (performance.now() - start) / ZONE_FADE_MS);
    fill.material.opacity = fillOp * k;
    edge.material.opacity = edgeOp * k;
    if (k < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
  return group;
}

export default function GlobeScene({ events, selected, onSelect, activeOption, qualityTier = 0 }) {
  const globeRef = useRef(null);
  const idleTimer = useRef(null);
  const [countries, setCountries] = useState([]);
  const [size, setSize] = useState({ w: window.innerWidth, h: window.innerHeight });
  // Country under the cursor + cursor position (own tooltip — the globe.gl
  // built-in label tooltip proved unreliable).
  const [hoverCountry, setHoverCountry] = useState(null);
  const cursor = useRef({ x: 0, y: 0 });

  useEffect(() => {
    const track = (ev) => {
      cursor.current = { x: ev.clientX, y: ev.clientY };
      // keep the tooltip glued to the cursor without re-rendering React
      const el = document.getElementById('country-tip');
      if (el) {
        el.style.left = `${ev.clientX + 14}px`;
        el.style.top = `${ev.clientY + 12}px`;
      }
    };
    window.addEventListener('mousemove', track);
    return () => window.removeEventListener('mousemove', track);
  }, []);

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

  // Quality ladder (§7): tier 2 drops rings for low-severity events (dots
  // remain), tier 3 kills the atmosphere, tier 4 flattens to a plain sphere.
  const ringEvents = useMemo(
    () => (qualityTier >= 2 ? disasters.filter((e) => e.severity >= 0.4) : disasters),
    [disasters, qualityTier]
  );
  const showAtmosphere = qualityTier < 3;
  const hexData = qualityTier < 4 ? countries : [];

  const dimmed = (e) => selected && selected.id !== e.id;

  // Option zones; supply arc from the staging zone (or a nearby offset
  // point standing in for the logistics hub) to the event.
  const zoneData = useMemo(() => {
    if (!activeOption) return [];
    return activeOption.affected_zones.map((z, i) => ({
      ...z, id: `${activeOption.id}-${i}`,
    }));
  }, [activeOption]);

  const supplyArcs = useMemo(() => {
    if (!activeOption || !selected) return [];
    const staging = activeOption.affected_zones.find((z) => z.role === 'staging');
    const from = staging
      ? { lat: staging.lat + 2.4, lon: staging.lon + 2.4 }
      : { lat: selected.lat + 3.2, lon: selected.lon + 3.2 };
    return [{
      startLat: from.lat, startLng: from.lon,
      endLat: selected.lat, endLng: selected.lon,
    }];
  }, [activeOption, selected]);

  return (
    <div className="globe-layer">
      <Globe
        ref={globeRef}
        width={size.w}
        height={size.h}
        backgroundColor="rgba(0,0,0,0)"
        showGlobe
        globeMaterial={OCEAN_MATERIAL}
        // ocean sphere + hex-polygon landmass (vector holographic look).
        // Light translucent blue so continents read clearly against the
        // dark ocean (user request — brighter than the original spec value).
        hexPolygonsData={hexData}
        hexPolygonResolution={3}
        hexPolygonMargin={0.62}
        hexPolygonAltitude={0.006}
        hexPolygonColor={() => 'rgba(125, 211, 252, 0.55)'}
        onHexPolygonHover={(poly) =>
          setHoverCountry(poly?.properties?.NAME ?? null)}
        showAtmosphere={showAtmosphere}
        atmosphereColor="#22d3ee"
        atmosphereAltitude={0.18}
        showGraticules
        // --- event markers: pulsing severity rings (disasters) ---
        ringsData={ringEvents}
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
        // --- policy option zones (Mode C): translucent circles, 300ms fade ---
        customLayerData={zoneData}
        customThreeObject={(z) => buildZoneObject(z)}
        customThreeObjectUpdate={(obj, z) => {
          const globe = globeRef.current;
          if (!globe) return;
          Object.assign(obj.position, globe.getCoords(z.lat, z.lon, 0.015));
          obj.lookAt(0, 0, 0); // tangent to the sphere surface
        }}
        // --- animated dashed supply arc from logistics staging to event ---
        arcsData={supplyArcs}
        arcColor={() => ['rgba(34,211,238,0.9)', 'rgba(34,211,238,0.25)']}
        arcAltitude={0.06}
        arcStroke={0.5}
        arcDashLength={0.35}
        arcDashGap={0.25}
        arcDashAnimateTime={1400}
        rendererConfig={{ antialias: true, alpha: true }}
      />
      {hoverCountry && (
        <div
          id="country-tip"
          className="country-label"
          style={{
            position: 'fixed',
            left: cursor.current.x + 14,
            top: cursor.current.y + 12,
            zIndex: 30,
            pointerEvents: 'none',
          }}
        >
          {hoverCountry}
        </div>
      )}
    </div>
  );
}
