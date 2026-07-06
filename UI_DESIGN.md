# UI_DESIGN.md — CrisisCommand Holographic Interface Specification

The UI is the pitch. A judge should feel like they walked into a sci-fi situation room. This document is the single source of truth for frontend implementation — read fully before writing frontend code.

## 1. Concept

**One persistent 3D Earth, floating in dark space, surrounded by translucent holographic panels.** No page navigation, no scrolling layouts. Everything happens around the globe: panels materialize, the camera flies, data glows.

Reference feeling: Iron Man's JARVIS interface / a NASA mission control wall — but restrained. Holographic ≠ cluttered. Empty dark space is a feature.

## 2. Technology

| Layer | Choice | Notes |
|---|---|---|
| 3D globe | `react-globe.gl` (Three.js under the hood) | Fastest path to a beautiful globe: built-in points, arcs, rings, hex layers, atmosphere. Drop to raw Three.js only if a needed effect is impossible. |
| HUD panels | Plain React + CSS (NOT inside WebGL) | DOM panels over the canvas: crisp text, accessible, easy. Glass/holo look via CSS. |
| Charts | `recharts` inside panels | Escalation curves, option comparisons |
| Animation | CSS transitions + `requestAnimationFrame` for camera | No heavy animation lib needed |
| State | React state + WS events | No router — one screen, three modes |

## 3. Visual Language

### Palette (CSS variables)
```css
--bg-space:      #04070d;   /* near-black blue, page background */
--globe-ocean:   #0a1628;   /* dark navy sphere */
--globe-land:    #1b2f4a;   /* muted steel-blue landmass */
--holo-cyan:     #22d3ee;   /* primary hologram color: borders, glows, text accents */
--holo-cyan-dim: rgba(34,211,238,0.12);  /* panel fills, grid lines */
--alert-red:     #f43f5e;   /* severity ≥0.7 events */
--alert-amber:   #fbbf24;   /* severity 0.4–0.7 */
--alert-teal:    #2dd4bf;   /* severity <0.4 */
--tension-violet:#a78bfa;   /* geopolitical tension signals (distinct from disasters) */
--text-primary:  #e2f3ff;
--text-dim:      #7d99b5;
```

### Typography
- Headings / HUD labels: `"Rajdhani"` or `"Orbitron"` (Google Fonts) — squared, technical, uppercase, letter-spacing 0.08em
- Body/data: `"Inter"` — readability over style for actual content
- Numbers in data readouts: tabular-nums

### The Holographic Panel (core reusable component)
```
Backdrop: rgba(10, 22, 40, 0.55) + backdrop-filter: blur(12px)
Border:   1px solid rgba(34,211,238,0.35)
Corners:  cut corners (clip-path polygon), NOT rounded — technical look
Glow:     box-shadow 0 0 24px rgba(34,211,238,0.15)
Deco:     corner brackets (4 small L-shapes, --holo-cyan), 
          1px scanline overlay at 3% opacity,
          thin animated top border sweep on mount (0.6s)
Entry:    opacity 0→1 + translateY(8px)→0 + brief 1px horizontal 
          "glitch" flicker (120ms) — subtle, once, on mount only
```
All panels share this component (`<HoloPanel title icon>`). Never invent one-off panel styles.

## 4. Layout (Desktop, 1920×1080 target)

```
┌─────────────────────────────────────────────────────────────┐
│ TOP BAR: ◈ CRISISCOMMAND        UTC clock   ● LIVE/SEED     │
│          "AI SITUATION ROOM"    source freshness dots       │
├────────────┬───────────────────────────────┬────────────────┤
│ LEFT RAIL  │                               │ RIGHT RAIL     │
│ (320px)    │                               │ (360px)        │
│            │                               │                │
│ EVENT      │        3D GLOBE               │ CONTEXT PANEL  │
│ FEED       │     (fills center,            │ (empty state:  │
│ scrollable │      auto-rotates slowly      │  "select an    │
│ holo cards │      when idle)               │   event")      │
│            │                               │                │
│            │                               │ → briefing     │
│            │                               │ → simulation   │
│            │                               │ → options      │
├────────────┴───────────────────────────────┴────────────────┤
│ BOTTOM BAR: ⚡ MI300X readout: util % · VRAM · runs/sec      │
│             (animates during simulation — the AMD showcase) │
└─────────────────────────────────────────────────────────────┘
```

Rails are overlays floating OVER the globe canvas (globe canvas is full-viewport). Rails collapse (slide out) when the camera flies in to a crisis, then return.

## 5. The Globe (scene spec)

- **Sphere:** dark navy ocean, muted steel-blue landmasses (use globe.gl `globeImageUrl` with a dark earth texture, or hex-polygon countries in `--globe-land` for a more holographic vector look — prototype both on day 1 of frontend work, pick one, commit).
- **Atmosphere:** cyan rim glow (`atmosphereColor: #22d3ee`, altitude 0.18) — this single setting delivers 50% of the hologram feel.
- **Graticule:** faint lat/lon grid lines at 6% opacity.
- **Idle motion:** auto-rotate 0.3°/s; pauses on user drag; resumes after 8s idle.
- **Event markers:**
  - Pulsing ring (globe.gl `ringsData`) — color by severity palette, ring radius ∝ severity, period 1.8s
  - Point light dot at center of ring
  - "tension" events: `--tension-violet`, diamond sprite instead of ring — visually distinct class, no alarm pulse
- **Selection:** click marker → camera flies (`pointOfView`, 1.2s ease) to lat/lon at altitude 0.6 → marker ring brightens, others dim to 40%
- **Option zones:** when a policy option is hovered/selected, render its `affected_zones` as translucent filled polygons/circles (cyan for evacuation zones, red for hazard extent) + animated dashed arc from nearest logistics hub (globe.gl `arcsData`, dash animation) representing supply routes.
- **Starfield:** sparse static stars in background (2% density) — depth without noise.

## 6. Interaction Flow (Three Modes)

### Mode A — Overview (default)
Globe rotating, all events pulsing, feed streaming in left rail. New event → marker drops in with a brief bright flash + feed card slides in.

### Mode B — Crisis Selected
1. Camera flight to event (rails slide out during flight, return after)
2. Right rail: `<HoloPanel "SITUATION BRIEF">` — AI briefing streams in word-by-word (typewriter, 40ms/word — reuse the actual token stream if easy, else simulate)
3. Below it: big cut-corner button `[ ▶ RUN SIMULATION ]`

### Mode C — Simulation
1. Button → panel `"SIMULATION — MI300X"` with:
   - progress: `MONTE CARLO ▸ 6,400 / 10,000 RUNS` (live WS numbers)
   - bottom-bar GPU readout animates: utilization bar fills, VRAM number counts up — **this moment is the AMD demo, make it prominent**
2. Results arrive:
   - Escalation chart (recharts area chart, cyan gradient, 6h/24h/72h tabs) with p10–p90 band shading — visible uncertainty
   - Three `<PolicyOptionCard>`s: name, exposed-population range BEFORE→AFTER, cost range, response time, tradeoff list. Severity-colored left edge.
3. Hover/select option → globe draws its zones + routes (spec §5). Selecting a different option cross-fades zones (300ms).
4. Small persistent label on all simulated data: `SIMULATION — DECISION SUPPORT ONLY`

## 7. Performance Ladder

Target 60fps with ≤200 markers. If frame time >20ms sustained, degrade IN THIS ORDER (implement as a quality manager, log which tier is active):
1. Disable scanline overlays on panels
2. Reduce ring pulse layers (rings → static dots for severity <0.4)
3. Disable atmosphere shader
4. Static globe texture instead of hex polygons

Never degrade: marker click accuracy, text legibility, GPU readout.

## 8. Empty/Edge States

- No event selected: right rail shows animated radar-sweep placeholder + "SELECT AN EVENT TO BEGIN ANALYSIS"
- Live source stale >30 min: its freshness dot turns amber with tooltip
- vLLM fallback active: top bar shows `⚠ SIM BACKEND: FIREWORKS (FALLBACK)` — honesty is part of the aesthetic
- Simulation error: panel shows retriable error in holo style, never a raw stack trace

## 9. Sound (Optional, Day-6-only Polish)

If and only if everything else is done: soft UI tick on panel mount, low hum swell during simulation (Web Audio, −24dB, mute toggle in top bar). Skip entirely under time pressure — silent is fine, broken audio is not.

## 10. What "Done" Looks Like

A 10-second screen recording of Mode A→B→C transition should look like a movie UI shot with REAL data flowing through it. If any panel looks like Bootstrap, it's not done.
